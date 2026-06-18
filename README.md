# SarkarSathi — Delhi CM Grievance Command Centre

> **Real-time AI governance dashboard for the Delhi Chief Minister's office.**
> Every citizen complaint, intelligently routed — tracked from receipt to resolution.

---

## The Problem It Solves

Delhi's CM office receives thousands of citizen complaints daily — handwritten letters, WhatsApp screenshots, walk-ins, online forms, phone calls. Today, these pile up in silos across 10 departments and 14 districts. No one knows in real time: *Which areas are overwhelmed? Which departments are stalling? What's going critical?*

**SarkarSathi changes that.** It gives the CM's office a single screen that shows everything — live, intelligently, and with AI that can explain what it sees and recommend what to do next.

---

## What It Does — In Plain Language

### 📍 One Screen for All 14 Districts
The Command Centre loads automatically with live numbers: how many active complaints, how many are critical, what the resolution rate is today. A colour-coded heatmap shows every district × issue category at a glance — darker cells = more complaints, click to filter.

### 🚨 Surge Alerts Before Things Blow Up
If complaints about, say, "Drainage & Sewage" in East Delhi spike to **21× the normal weekly volume**, a red alert fires automatically at the top of the screen. Surge detection runs on a rolling 3-week baseline — no manual thresholds to set.

### 🧠 Similar Complaints Auto-Grouped
When a citizen submits a complaint, the system reads the description and silently checks: *"Has anyone nearby reported something similar?"* If yes, it groups them into the same cluster. A cluster about "blocked drain near Laxmi Nagar colony" might represent 8 different citizens — the department sees one issue, not eight tickets.

### 📸 Scan a Physical Complaint
Staff can photograph a handwritten letter, a printed form, or a WhatsApp screenshot and upload it. AI reads it — **even if it's written in Hindi** — translates it, and pre-fills the complaint form automatically. Staff reviews, edits if needed, then submits.

### ⏰ Nothing Gets Forgotten
Any issue that hasn't moved in 7 days is automatically flagged as **stale**. The dashboard highlights these in amber, shows them in a dedicated bar at the top, and the Strategic Advisor proactively surfaces them in its recommendations.

### 💬 Ask the Dashboard Anything
An AI chat panel (persistent, always accessible via the ✦ AI Advisor button) answers plain-English questions about live data:
- *"Which district has the most open complaints right now?"*
- *"How is DJB performing this month?"*
- *"Which issues have been stale the longest?"*

### 🎯 Strategic Advisor — For CM-Level Decisions
The Advisor tab runs an AI that *investigates* the data before responding. It pulls district data, checks department performance, looks at surge patterns — then generates 3–4 prioritised, actionable recommendations. Every step of its reasoning is visible on screen, so every recommendation is auditable.

### 📋 Log Complaints — With Camera Support
The "Log Complaint" floating button (bottom-left on every page) opens a form where staff can file a complaint manually or scan a document. On mobile, it opens the camera directly. On desktop, it accepts file uploads.

---

## Who Uses What

| Role | What they see |
|---|---|
| **CM / Senior Officers** | Command Centre overview, Surge alerts, Strategic Advisor recommendations |
| **District Administrators** | Districts page — their district's open count, top categories, resolution rate |
| **Department Heads** | Departments page — their performance card, stale issues, resolution rate vs peers |
| **Intake Staff** | Log Complaint page with OCR scan — file new complaints in seconds from any document |
| **Operations Team** | Issues page — full filterable cluster table, click to update status, assign department |

---

## Key Features at a Glance

| Feature | What makes it useful |
|---|---|
| 🗺️ District × Category Heatmap | See pressure points instantly — no reports, no meetings |
| ⚡ Surge Detection | Auto-alerts when complaint volume is 2× or more above the 3-week baseline |
| 🔗 Semantic Clustering | Groups similar complaints — one ticket per issue, not one per citizen |
| 📸 OCR Document Intake | Photograph any physical complaint — Hindi or English — and AI fills the form |
| 🤖 Agentic Strategic Advisor | AI that investigates data with tool-calls before recommending, with visible reasoning |
| 🕐 Stale Issue Tracking | 7-day staleness flag — nothing silently expires |
| 💬 Grounded RAG Chat | Chat answers come from live dashboard data, not hallucinated |
| 📱 Mobile-ready | Camera capture on mobile, FAB navigation, responsive layout |

---

## Setup

### Prerequisites
- Python 3.10+
- A [Gemini API key](https://aistudio.google.com/) (free tier works — used for chat, advisor, and OCR only)

### Install

```bash
# 1. Create virtual environment
python3 -m venv .venv

# 2. Install CPU-only PyTorch (avoids large CUDA download)
.venv/bin/pip install torch --index-url https://download.pytorch.org/whl/cpu

# 3. Install everything else
.venv/bin/pip install fastapi uvicorn python-multipart google-genai \
    python-dotenv sentence-transformers sqlite-vec numpy
```

### Configure

Create a `.env` file in the project root:
```
GEMINI_API_KEY=your_key_here
```

### Seed and Run

```bash
# Seed with realistic Delhi grievance data
.venv/bin/python seed.py --reset

# Start the server
.venv/bin/uvicorn main:app --port 8000
```

Open **http://localhost:8000** — the dashboard loads with pre-seeded data including surge conditions, stale clusters, and department performance spread across all 14 districts.

---

## For Judges & Evaluators

### The Core Bet
Most civic tech stops at "a better form." SarkarSathi is about what happens *after* the form — intelligent routing, pattern detection, and AI that flags what a human reviewing thousands of complaints would miss.

### What's Novel
- **Cluster-first architecture** — complaints are secondary; clusters (groups of similar issues) are the primary unit. A department sees "8 citizens, East Delhi, drainage blocked near Laxmi Nagar" — not 8 separate tickets.
- **OCR intake from physical documents** — handwritten letters in Hindi, WhatsApp screenshots, printed forms all flow into the same system. No digitisation bottleneck.
- **Explainable AI** — the Strategic Advisor's tool calls and reasoning steps are fully visible on screen. A CM or officer can see *why* a recommendation was made, not just what it is.
- **Zero external database** — runs entirely on SQLite with vector extensions. Deployable on a single government server with no cloud DB dependency or data leaving the machine (except Gemini API calls).
- **AI self-memory** — if the LLM surfaces a non-obvious pattern during chat, it can persist it to memory and use it in future queries.

### Real Deployability
- Offline-capable analytics (all pattern detection is pure SQL, no LLM)
- Degrades gracefully without Gemini key — all analytics, clustering, and filtering still work
- Single-file database — trivial to back up, audit, or migrate
- Swap any AI provider in one line (`VISION_MODEL` in `ocr_normalizer.py`, `model_name` in `ai.py`)

---

## Technical Architecture

### Stack
| Layer | Technology |
|---|---|
| **Backend** | FastAPI + Uvicorn (async) |
| **Database** | SQLite + `sqlite-vec` (vector extension) |
| **Embeddings** | `all-MiniLM-L6-v2` via sentence-transformers — 384-dim, CPU-only, runs locally |
| **Text AI** | Gemini `gemini-3.1-flash-lite-preview` via `google-genai` |
| **Vision AI** | Gemini `gemini-2.5-flash-lite` — multimodal, free tier |
| **Frontend** | Vanilla JS + CSS (no framework, no build step) |

### Intelligent Complaint Clustering
New complaints are embedded with `all-MiniLM-L6-v2` and compared against existing clusters using **cosine similarity** (`sqlite-vec`'s `vec_distance_cosine`). Threshold: **0.55**. Matches within the same district are merged into the existing cluster; misses create a new one. Priority auto-escalates at 3+ citizens (high) and 5+ citizens (critical).

### Surge Detection
Pattern engine computes a rolling 3-week baseline per district × category. A surge fires when the current week's volume exceeds **2× the baseline**. The East Delhi / Drainage seeded surge is at **21× normal** — visible immediately on load.

### 3-Layer RAG Context
Every AI query assembles context from three layers simultaneously:
- **Layer 1 (always-on):** City stats, active surge alerts, department snapshot
- **Layer 2 (vector search):** Historical patterns and resolved cases from `knowledge_nodes`
- **Layer 3 (live):** Current active clusters, stale issues

A local **semantic router** classifies queries (greeting / follow-up / full-search) *before* touching the LLM, so simple questions skip the full pipeline entirely.

### Agentic Advisor Loop
The Strategic Advisor runs up to **3 agentic rounds**. Each round: analyse context → optionally call a tool (`get_district_data`, `get_department_performance`, `get_surge_details`, `get_stale_grievances`, `get_resolution_trends`) → synthesise. Thinking trace is streamed to the UI. Final output: 3–4 prioritised recommendations, each labelled critical / high / medium.

### OCR Pipeline
`ocr_normalizer.py` is a standalone, swappable module. It base64-encodes the uploaded image, passes it to Gemini Vision with a structured extraction prompt (English + Hindi), and receives a JSON object with extracted fields and per-field confidence levels (`high / medium / low`). Invalid district or category values are sanitised server-side before returning to the frontend.

### API Surface
```
POST /api/grievances              — submit complaint (auto-clusters)
GET  /api/clusters                — filterable issue clusters
GET  /api/patterns/city           — live city overview stats
GET  /api/patterns/surges         — active surge alerts
GET  /api/patterns/heatmap        — district × category matrix
GET  /api/patterns/departments    — department performance
GET  /api/stale-clusters          — overdue clusters (7-day threshold)
POST /api/chat                    — grounded RAG chat
POST /api/suggestions             — agentic strategic advisor
POST /api/extract-complaint       — OCR image → complaint fields
```

---

*Built for **India Innovates 2026 — CivicNTech track.***
*Cluster-first. Explainable. Deployable.*
