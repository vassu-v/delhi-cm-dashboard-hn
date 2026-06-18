<div align="center">

# SarkarSathi
### Delhi CM Grievance Command Centre

*AI-powered civic governance — every complaint tracked, nothing forgotten*

<br>

[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![SQLite](https://img.shields.io/badge/SQLite-003B57?style=flat-square&logo=sqlite&logoColor=white)](https://sqlite.org/)
[![Gemini](https://img.shields.io/badge/Gemini_AI-4285F4?style=flat-square&logo=google&logoColor=white)](https://ai.google.dev/)
[![Python](https://img.shields.io/badge/Python_3.10+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org/)
[![India Innovates 2026](https://img.shields.io/badge/India_Innovates_2026-FF6B00?style=flat-square)](https://indiainnovates.in/)

</div>

---

Delhi's CM office receives thousands of citizen complaints daily — handwritten letters, WhatsApp screenshots, walk-ins, phone calls, online forms. They pile up in silos across 10 departments and 14 districts. No one knows in real time what's critical, what's stalling, or what's about to blow up.

**SarkarSathi is a single screen that changes that.** Live intelligence, automatic grouping, surge alerts, and an AI advisor that can explain what it sees and recommend what to do next.

---

## The Dashboard

```
+------------------------------------------------------------------+
|  SarkarSathi  Delhi CM Command Centre       Thu, 18 Jun 2026    |
|  ----------------------------------------------------------------|
|  Command Centre   Districts   Departments   Issues   AI Advisor  |
+------------------------------------------------------------------+

  DELHI CM COMMAND CENTRE
  +----------+  +----------+  +----------+  +----------+
  |   262    |  |    89    |  |    0     |  |   61%    |
  | Citizens |  |  Active  |  | Critical |  |Resolution|
  |  Heard   |  | Clusters |  |          |  |   Rate   |
  +----------+  +----------+  +----------+  +----------+

  [SURGE]  East / Drainage & Sewage  --  21x normal volume
  [STALE]  East  --  Foul smell from blocked drain  (3 citizens, 20 days)

  Complaint Heatmap  --  14 districts x 11 categories, click to filter
```

---

## The Problem, Solved

| Before | After |
|---|---|
| Complaints in physical files and scattered inboxes | One unified dashboard across all 14 districts |
| Officers manually spot duplicate complaints | AI auto-groups similar complaints into clusters |
| No one knows which area needs urgent attention | Surge alerts fire automatically at 2x normal volume |
| Physical letters sit undigitised for days | Staff photographs a letter, AI reads it in seconds |
| Stale issues quietly expire | 7-day staleness flag on every cluster, always visible |
| "What should the CM focus on?" requires a meeting | AI Strategic Advisor answers with evidence in 30 seconds |

---

## Features

### Command Centre

One screen covers all of Delhi. A heatmap plots 14 districts against 11 complaint categories — colour intensity maps to volume. Click any cell to jump to filtered issues. Stat cards animate in with live numbers on every load. Surge and stale alerts appear at the top bar the moment they become active.

---

### Surge Detection

Complaint spikes are detected automatically against a rolling 3-week baseline. When East Delhi's drainage complaints reach 21x their normal weekly volume, a red alert fires. No manual thresholds to configure, no reports to generate.

---

### Semantic Clustering

When a complaint arrives, the system embeds it and checks whether a similar issue already exists in the same district. Matching complaints merge into one cluster. A department sees:

> **8 citizens — Drainage blocked near Laxmi Nagar colony**

...instead of 8 separate tickets. Priority auto-escalates as more citizens report the same problem — 3+ citizens becomes high, 5+ becomes critical.

---

### Scan Any Complaint Document

Staff can photograph a handwritten Hindi letter, a printed form, or a WhatsApp screenshot. AI reads the image, translates if needed, and pre-fills the entire complaint form — name, district, category, description, source. Staff reviews, edits, and submits. Physical paperwork becomes a digital record in under 30 seconds.

---

### AI Side Panel

A persistent drawer accessible from any page via the AI Advisor button in the top bar. Two modes:

**Chat** — plain-English questions answered from live dashboard data.
- "Which district has the most open complaints right now?"
- "How is DJB performing this month?"
- "Which issues have been stale the longest?"

**Strategic Advisor** — an agentic AI that investigates the data before responding. It pulls district stats, checks department performance, looks at surge patterns, then returns 3-4 prioritised recommendations with its full reasoning visible on screen.

---

### Stale Issue Tracking

Any cluster that goes 7 days without a status update is flagged automatically — highlighted in the issues table, shown in the dashboard attention bar, and surfaced proactively by the Advisor.

---

## Who Uses What

| Role | Page | What they get |
|---|---|---|
| CM / Senior Officers | Command Centre, Advisor | Live overview, surge alerts, strategic recommendations |
| District Administrators | Districts | Open count, top categories, resolution rate per district |
| Department Heads | Departments | Performance vs peers, stale issues, avg resolution time |
| Intake Staff | Log Complaint | Scan physical documents, file complaints in seconds |
| Operations Team | Issues | Filter by any dimension, update status, assign department |

---

## For Judges & Evaluators

### What is actually novel

**Cluster-first architecture.** Complaints are secondary objects. The primary unit is a cluster — a group of citizens reporting the same problem in the same area. Departments manage one issue with a citizen count, not N identical tickets. Every metric on the dashboard (open count, critical count, stale count) is measured in clusters, not raw reports.

**Explainable AI.** The Strategic Advisor shows every tool call and reasoning step before its conclusion. A senior officer can see exactly why a recommendation was made. Nothing is a black box.

**OCR intake from physical documents.** Handwritten Hindi letters, printed forms, WhatsApp screenshots all flow into the same pipeline. No digitisation bottleneck, no department excluded because they still work on paper.

**Zero cloud dependency for analytics.** Surge detection, heatmaps, department rankings, stale flags — all pure SQL, no LLM. Works fully offline. Citizen data never leaves the machine except for Gemini API calls, which can be disabled.

**AI that learns from its own conversations.** If the LLM surfaces a non-obvious pattern during a chat session, it can persist it to memory. Future queries inherit that knowledge automatically.

---

### Why it would actually get deployed

- Single SQLite file — trivial to back up, audit, or migrate
- No cloud database, no Kubernetes, no microservices — runs on one government server
- Swap any AI provider in one line (`VISION_MODEL` in `ocr_normalizer.py`, `model_name` in `ai.py`)
- Full analytics function without AI key — departments don't lose visibility if the API is down

---

## Technical Architecture

<details>
<summary>Stack</summary>

<br>

| Layer | Technology | Reason |
|---|---|---|
| Backend | FastAPI + Uvicorn | Async, typed, minimal config |
| Database | SQLite + sqlite-vec | Single file, vector search, zero infrastructure |
| Embeddings | all-MiniLM-L6-v2 (384-dim) | Runs locally, CPU-only, no API cost |
| Text AI | gemini-3.1-flash-lite-preview | Low latency, free tier, agentic tool-calling |
| Vision AI | gemini-2.5-flash-lite | Multimodal, free tier, Hindi + English OCR |
| Frontend | Vanilla JS + CSS | No build step, no framework, zero cold start |

</details>

<details>
<summary>Semantic clustering</summary>

<br>

Incoming complaints are embedded using `all-MiniLM-L6-v2` and compared against active clusters in the same district using `sqlite-vec`'s `vec_distance_cosine`. Cosine similarity threshold: 0.55. Matches merge into the existing cluster and increment its citizen weight. Misses create a new cluster. Priority derives from weight — medium by default, high at 3+, critical at 5+.

</details>

<details>
<summary>Surge detection</summary>

<br>

`pattern_engine.py` computes a per-district, per-category rolling 3-week complaint baseline. Current week volume is compared against it. Ratio at or above 2x fires a surge. The ratio is surfaced as a human-readable label (`21.0x normal`) and injected into AI context so the Advisor can reference it directly.

</details>

<details>
<summary>3-layer RAG and semantic router</summary>

<br>

Every AI query builds context from three layers in parallel:

- Layer 1 (always-on) — live city stats, active surges, department snapshot
- Layer 2 (vector search) — historical patterns and resolved cases from `knowledge_nodes`
- Layer 3 (live) — current active clusters, stale issues

Before the pipeline runs, a local semantic router classifies the query by cosine similarity — greetings skip the pipeline entirely, follow-up questions skip the vector search, new questions run the full assembly. Zero tokens spent on routing.

</details>

<details>
<summary>Agentic advisor loop</summary>

<br>

The Strategic Advisor runs up to 3 rounds:

```
Round 1  --  Analyse context, decide whether to call a tool
             Tools: get_district_data, get_department_performance,
                    get_surge_details, get_stale_grievances, get_resolution_trends

Round 2  --  Analyse tool result, decide whether to call another

Round 3  --  Synthesise findings, output 3-4 prioritised recommendations
```

Every round's tool call and data result renders in the UI as a collapsible trace entry. The reasoning is never hidden.

</details>

<details>
<summary>OCR pipeline</summary>

<br>

`ocr_normalizer.py` is architecturally isolated — same pattern as `ai.py`, fully swappable in one line.

```
Upload image
  --> FastAPI reads bytes, base64-encodes
  --> Gemini Vision (gemini-2.5-flash-lite) + structured extraction prompt
  --> JSON: { description, citizen_name, contact, district, category, source, confidence{} }
  --> Server validates district and category against known lists
  --> Frontend pre-fills form, shows per-field confidence level
```

If parsing fails for any reason, a graceful error returns and the form remains fully usable manually.

</details>

<details>
<summary>API surface</summary>

<br>

```
POST  /api/grievances              -- submit complaint (auto-clusters on intake)
GET   /api/clusters                -- filterable issue clusters
GET   /api/patterns/city           -- live city overview stats
GET   /api/patterns/surges         -- active surge alerts
GET   /api/patterns/heatmap        -- district x category matrix
GET   /api/patterns/departments    -- department performance report
GET   /api/recent-clusters         -- last N active clusters
GET   /api/stale-clusters          -- overdue clusters (7-day threshold)
POST  /api/chat                    -- grounded RAG chat
POST  /api/suggestions             -- agentic strategic advisor
POST  /api/extract-complaint       -- OCR: image to complaint fields
```

</details>

---

## Setup

```bash
# 1. Create virtual environment
python3 -m venv .venv

# 2. Install PyTorch CPU build (skips the large CUDA download)
.venv/bin/pip install torch --index-url https://download.pytorch.org/whl/cpu

# 3. Install dependencies
.venv/bin/pip install fastapi uvicorn python-multipart google-genai \
    python-dotenv sentence-transformers sqlite-vec numpy

# 4. Set API key
echo "GEMINI_API_KEY=your_key_here" > .env

# 5. Seed with realistic Delhi data
.venv/bin/python seed.py --reset

# 6. Start
.venv/bin/uvicorn main:app --port 8000
```

Visit **http://localhost:8000**

> No Gemini key? All analytics, clustering, filtering, and heatmaps still work. Only Chat, Advisor, and document scanning require the key.
