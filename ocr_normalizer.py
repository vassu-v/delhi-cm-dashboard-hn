"""
ocr_normalizer.py — Image-to-complaint extractor for the Delhi CM Grievance Dashboard.
Takes a base64-encoded image, sends to Gemini Vision, returns structured complaint fields.
Swappable: replace _call_vision() to use a different vision model or OCR provider.
"""

import os
import base64
import json
from dotenv import load_dotenv

load_dotenv()

# ── Provider setup (swap here if needed) ─────────────────────────────────────
import google.genai as genai
from google.genai import types as genai_types

_client = None
def _get_client():
    global _client
    if _client is None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise Exception("GEMINI_API_KEY not set.")
        _client = genai.Client(api_key=api_key)
    return _client

VISION_MODEL = "gemini-2.5-flash-lite"   # change this line to swap vision model

DELHI_DISTRICTS = [
    "Central", "East", "New Delhi", "North", "North East", "North West",
    "Shahdara", "South", "South East", "South West", "Dwarka", "West",
    "Rohini", "Outer"
]

CATEGORIES = [
    "Water Supply", "Drainage & Sewage", "Roads & Infrastructure",
    "Electricity & Power", "Sanitation & Garbage", "Public Safety",
    "Healthcare", "Education", "Public Transport", "Housing & Shelter",
    "Land & Property",
]

# ── Core extraction ───────────────────────────────────────────────────────────

def _call_vision(image_bytes: bytes, mime_type: str) -> str:
    """
    Sends image to Gemini Vision. Returns raw text response.
    Swap this function to use a different provider.
    """
    client = _get_client()
    prompt = f"""You are a complaint intake assistant for the Delhi Chief Minister's office.

Analyze this image. It may be a photo of a handwritten letter, a printed complaint form,
a WhatsApp screenshot, a social media post, or any other complaint document.
The text may be in English, Hindi, or a mix of both.

Extract the following fields if present. Return ONLY a valid JSON object, no markdown, no explanation.

Fields to extract:
- description: The main complaint text. Full description of the problem. If Hindi, translate to English. Required.
- citizen_name: Full name of the complainant if visible. Null if not found.
- citizen_contact: Phone number or email if visible. Null if not found.
- district: Which Delhi district this complaint is about. Must be one of: {", ".join(DELHI_DISTRICTS)}.
  If a locality or area is mentioned (e.g. "Laxmi Nagar", "Rohini Sector 3"), map it to the correct district.
  Null if location cannot be determined.
- category: The type of complaint. Must be one of: {", ".join(CATEGORIES)}.
  Choose the best match based on the complaint content.
- source: How this complaint arrived. Detect from context:
  "walk-in" if it looks like a handwritten letter or physical form,
  "WhatsApp" if it looks like a WhatsApp screenshot,
  "social" if it looks like a social media post,
  "portal" if it looks like a digital form,
  "phone" if it looks like a phone transcript.
  Default to "walk-in" if unclear.
- confidence: Object with a confidence level ("high", "medium", "low") for each field extracted.
  high = clearly stated, medium = inferred from context, low = uncertain guess.

If the image contains no readable complaint content (blank, unrelated, too blurry to read),
return exactly this JSON: {{"error": "nothing_recognizable"}}

Example output:
{{
  "description": "The drain near our colony has been blocked for 10 days causing flooding.",
  "citizen_name": "Ramesh Kumar",
  "citizen_contact": "9812345678",
  "district": "East",
  "category": "Drainage & Sewage",
  "source": "walk-in",
  "confidence": {{
    "description": "high",
    "citizen_name": "high",
    "citizen_contact": "medium",
    "district": "medium",
    "category": "high",
    "source": "low"
  }}
}}
"""
    response = client.models.generate_content(
        model=VISION_MODEL,
        contents=[
            genai_types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            prompt
        ]
    )
    return response.text.strip()


def extract_from_image(image_base64: str, mime_type: str = "image/jpeg") -> dict:
    """
    Main entry point. Takes base64-encoded image string.
    Returns extracted complaint fields or {"error": "nothing_recognizable"} or {"error": "extraction_failed"}.

    Return shape on success:
    {
        "description": str,
        "citizen_name": str | None,
        "citizen_contact": str | None,
        "district": str | None,
        "category": str | None,
        "source": str,
        "confidence": { field: "high"|"medium"|"low" }
    }
    """
    try:
        image_bytes = base64.b64decode(image_base64)
    except Exception:
        return {"error": "extraction_failed", "detail": "Invalid base64 image data."}

    try:
        raw = _call_vision(image_bytes, mime_type)
    except Exception as e:
        return {"error": "extraction_failed", "detail": str(e)}

    # Strip markdown fences if model returns them despite instructions
    if "```json" in raw:
        raw = raw.split("```json")[1].split("```")[0].strip()
    elif "```" in raw:
        raw = raw.split("```")[1].split("```")[0].strip()

    try:
        result = json.loads(raw)
    except Exception:
        return {"error": "extraction_failed", "detail": "Model returned unparseable response."}

    # Validate error case
    if result.get("error") == "nothing_recognizable":
        return {"error": "nothing_recognizable"}

    # Validate required field
    if not result.get("description"):
        return {"error": "nothing_recognizable"}

    # Sanitize: ensure district and category are valid if present
    if result.get("district") and result["district"] not in DELHI_DISTRICTS:
        result["district"] = None
        if result.get("confidence"):
            result["confidence"]["district"] = "low"

    if result.get("category") and result["category"] not in CATEGORIES:
        result["category"] = None
        if result.get("confidence"):
            result["confidence"]["category"] = "low"

    return result
