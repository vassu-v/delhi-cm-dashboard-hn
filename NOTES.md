# NOTES — Delhi CM Grievance Dashboard

Technical notes, architecture decisions, known quirks, and things to know before touching the code.

---

## Project Origin

This started as **SarkarSathi / Co-Pilot** — an AI assistant for Indian MLAs that tracked meeting commitments, escalated overdue items, and answered questions via RAG. It was refactored into a **CM-office grievance dashboard** for Delhi. The core AI infrastructure (embeddings, RAG engine, agentic loop) was kept intact and repointed at grievance data.

---

## File Map

```
Project/
├── ai.py                  — LLM wrapper (Gemini). Change model here only.
├── issue_engine.py        — Complaint intake + vector clustering (kept from original, ward→district)
├── grievance_engine.py    — Grievance CRUD, status flow, stale detection (new)
├── pattern_engine.py      — Pure SQL analytics, surge detection, heatmap (new)
├── rag_engine.py          — Context assembly, chat, agentic advisor (rewritten for CM context)
├── main.py                — FastAPI app, all API routes (rewritten)
├── seed.py                — Seed script for demo data (rewritten)
├── index.html             — Single-page frontend (rewritten)
├── static/
│   ├── style.css          — Dark government aesthetic (rewritten)
│   └── script.js          — All frontend logic (rewritten)
├── grievance_dashboard.db — SQLite database (auto-created on first run)
└── requirements.txt       — Frozen from venv (includes exact versions)
```

**Deleted from original:**
- `commitment_engine.py` — MLA commitment tracker
- `digest_engine.py` — Weekly digest (was pure SQL, not needed; pattern_engine replaces it)
- `verify_dashboard.py` — Playwright verification script (removed with commitment engine dependency)

---

## Environment

- **Python:** 3.12.3
- **Venv:** `.venv/` at repo root (`hncmsarkarsathi/.venv/`)
- **PyTorch:** `2.12.0+cpu` — CPU-only build installed deliberately. The default `pip install torch` pulls ~4GB of CUDA packages. Always use `--index-url https://download.pytorch.org/whl/cpu`.
- **Gemini model:** `gemini-3.1-flash-lite-preview` (set in `ai.py` default arg). Change model name in one place.
- **DB file:** `grievance_dashboard.db` in the Project directory. Rename is set in `issue_engine.py` and `grievance_engine.py` as `DB_PATH`.
- **Port:** 8000

**Run server from `Project/` directory** (uvicorn needs to resolve module imports from there):
```bash
cd india-innovates-CivicNTech/Project
../../.venv/bin/uvicorn main:app --port 8000
```

---

## Database Schema

### `grievances` (owned by grievance_engine)
```sql
id                  INTEGER PRIMARY KEY AUTOINCREMENT
title               TEXT
description         TEXT
district            TEXT                     -- one of 14 Delhi districts
category            TEXT                     -- one of 8 categories
department_assigned TEXT                     -- one of 10 departments
status              TEXT DEFAULT 'Received'  -- Received/Assigned/In Progress/Resolved
priority            TEXT DEFAULT 'medium'    -- low/medium/high/critical
citizen_name        TEXT
citizen_contact     TEXT
citizen_email       TEXT
source              TEXT DEFAULT 'portal'    -- portal/walk-in/phone/social
date_received       DATE
date_assigned       DATE
date_resolved       DATE
stale_flag          BOOLEAN DEFAULT 0        -- 1 if no update in 7+ days
days_since_update   INTEGER DEFAULT 0
cluster_id          INTEGER                  -- FK to issue_engine clusters table
created_at          TIMESTAMP
last_updated        TIMESTAMP
```

### `clusters` (owned by issue_engine)
```sql
id          INTEGER PRIMARY KEY AUTOINCREMENT
summary     TEXT
district    TEXT    -- renamed from 'ward' in original
weight      INTEGER DEFAULT 1
status      TEXT DEFAULT 'open'
urgency     TEXT DEFAULT 'normal'
created_at  TIMESTAMP
resolved_at DATE
```

### `complaints` (owned by issue_engine)
```sql
id              INTEGER PRIMARY KEY AUTOINCREMENT
citizen_name    TEXT
citizen_contact TEXT
district        TEXT    -- renamed from 'ward'
channel         TEXT
raw_description TEXT
date_received   DATE
status          TEXT DEFAULT 'pending'
cluster_id      INTEGER
staff_notes     TEXT
resolved_at     DATE
created_at      TIMESTAMP
```

### `knowledge_nodes` (owned by rag_engine)
```sql
id         INTEGER PRIMARY KEY AUTOINCREMENT
domain     TEXT    -- 'grievance_pattern' | 'dept_track_record' | 'governance_context' etc.
district   TEXT    -- renamed from 'ward' in original
topic      TEXT
title      TEXT
content    TEXT
source_ref TEXT
created_at TIMESTAMP
```

### `cm_profile` (owned by grievance_engine)
Singleton table (id=1). Dashboard name, jurisdiction, districts count, population, contact info.

### `ai_memory` (owned by rag_engine)
Patterns the LLM writes during chat via `[MEMORY: topic] content [/MEMORY]` tags.

---

## Staleness Logic

Grievances are flagged stale if `last_updated` is 7+ days ago and status is not `Resolved`. This is a soft boolean flag — no escalation ladder. Refreshed on every call to `get_grievances()` and `get_department_stats()` via `_refresh_stale_flags()` in grievance_engine.

The threshold constant is `STALE_DAYS = 7` at the top of `grievance_engine.py`.

---

## Surge Detection Logic (`pattern_engine.detect_surges`)

A surge is flagged when a (district, category) pair sees ≥2× its 3-week baseline volume in the last 7 days.

```
recent_count = complaints in last 7 days for (district, category)
baseline_weekly = total complaints in prior 3 weeks / 3

surge if: recent_count >= baseline_weekly * 2
```

Edge case: if baseline is 0 (new problem with no history), flag if recent_count ≥ 3. This prevents noise from single new complaints surfacing as surges.

The seeded data puts East and Shahdara drainage at ~15x and ~12x to simulate monsoon surge.

---

## Embedding / Vector Search

Uses `all-MiniLM-L6-v2` from sentence-transformers. 384-dimension float32 vectors stored as BLOBs.

Two layers:
1. **`vec_clusters`** — complaint cluster embeddings for similarity-based complaint grouping (issue_engine)
2. **`vec_knowledge`** — knowledge node embeddings for RAG retrieval (rag_engine)

Both layers use `sqlite-vec` for fast cosine distance queries, with a fallback to in-memory cosine similarity if `sqlite-vec` extension loading fails (common on some Linux configs).

Similarity threshold: `THRESHOLD = 0.35` (cosine similarity). Complaints within this threshold are merged into existing clusters rather than creating new ones.

Model is loaded lazily on first use and cached as `_model` module-level global. First load downloads ~90MB from HuggingFace (cached to `~/.cache/huggingface/`).

---

## Complaint → Grievance Flow

When a citizen submits via `POST /api/grievances`:
1. `issue_engine.process_complaint()` runs — generates embedding, searches for matching cluster, adds to existing or creates new
2. `cluster_id` from step 1 is attached to the grievance row
3. `grievance_engine.add_grievance()` inserts the row with `status=Received` and auto-routed department
4. Response includes `cluster_match: true/false` and cluster summary — shown in frontend as "X similar complaints found in your area"

---

## RAG Context Assembly

Every chat and advisor query assembles 3 layers:

**Layer 1 (always-on):**
- `pattern_engine.get_city_overview()` — total, open, critical, stale, resolution rate, avg days
- `pattern_engine.get_department_report()` — top 5 departments snapshot
- `pattern_engine.detect_surges()` — active surges

**Layer 2 (vector search):**
- `rag_engine.query_nodes(query_text, limit=5)` — top-5 knowledge nodes by cosine similarity
- `ai_memory` table — last 5 AI-learned patterns

**Layer 3 (live):**
- Active complaint clusters from `issue_engine` (top 10 by weight)
- Surge alerts repeated for emphasis

---

## Agentic Advisor Tool List

The `run_suggestion_agent()` function in `rag_engine.py` exposes these tools to the LLM:

| Tool | What it fetches |
|------|----------------|
| `get_district_data(district)` | Grievance breakdown by category and status for a district |
| `get_department_performance(department)` | Resolution stats by status and priority |
| `get_surge_details(category_or_district)` | Filtered surges matching the argument |
| `get_stale_grievances(department)` | Stale grievances for a department, sorted by days |
| `get_resolution_trends(limit)` | Recent resolved grievances with resolution days |

Max 3 rounds (round 1 → optional tool → round 2 → optional tool → final synthesis). All tool results and thinking are returned in `thinking_trace` for UI display.

---

## Frontend Architecture

Single-page app. No framework. Pure JS with fetch API.

**Navigation:** `goPage(name)` swaps `.page.active` class and calls the loader function for that page. State is per-page — no shared store.

**Heatmap:** Pure CSS grid. Color is computed in JS (`heatColor(intensity, val)`) as an RGB interpolation from dim surface → amber → red based on value/max ratio. No canvas, no chart library.

**Chat:** Maintains `chatHistory` array (last 10 messages sent with each request) and `chatWorkingMemory` (embedding vectors from last retrieval, used by semantic router for follow-up detection).

**Advisor:** Maintains `advisorHistory` (full thinking trace) across "Run Analysis" calls — enables follow-up mode where the agent builds on previous reasoning without repeating itself.

**Grievance modal:** Fetches single grievance on click, renders detail view inline, allows status update.

---

## Seed Data Summary

Run: `python seed.py --reset`

| Metric | Value |
|--------|-------|
| Total grievances | 166 |
| Statuses | 69 Received, 37 Assigned, 38 In Progress, 22 Resolved |
| Districts covered | All 14 |
| Highest volume | South (18), South West (16), East (14+surge), Shahdara (13+surge) |
| Active surges | East Drainage 15×, Shahdara Drainage 12× |
| Complaint clusters | 17 (via issue_engine embeddings) |
| RAG knowledge nodes | 8 (historical patterns, dept track records, Delhi infra context) |

Dept resolution time variation (by design):
- **DJB:** 8–18 days (slowest)
- **PWD:** 6–14 days (moderate)
- **MCD:** 4–11 days (fastest)

---

## Known Quirks / Things to Watch

1. **First server start is slow** — sentence-transformers model loads on first complaint submission or RAG query (~2–3s). Cached after that.

2. **`_refresh_stale_flags()` on every read** — runs a SQL UPDATE on every call to `get_grievances()`. Fine for demo scale, would need a scheduled job (cron/celery) in production.

3. **`detect_surges()` is date-sensitive** — surge windows are relative to today. If the DB is seeded and then left sitting for weeks, surge data will shift. Re-run `seed.py --reset` to refresh.

4. **7 of 10 departments show in reports** — DUSIB, Transport Department, and Revenue Department have no seeded grievances (no category maps to them by default). They will appear once real grievances are assigned to them.

5. **Gemini model name** — `ai.py` uses `gemini-3.1-flash-lite-preview`. If this model is deprecated or renamed, change the default arg in `call_ai()`. Errors surface as `Chat failed: ...` in the UI.

6. **No auth** — This is a demo/prototype. No login, no role separation. In production, the CM office view vs. public submit form should be separate surfaces with auth.

7. **sqlite-vec extension** — Loading uses `enable_load_extension(True)`. Some Linux distributions compile SQLite without extension support. The code has a fallback to in-memory cosine similarity, but it's slower. If `sqlite-vec` errors appear, they're silently caught and the fallback kicks in.

8. **`ward` → `district` migration** — The original `issue_engine.py` had `ward` columns. These are now `district`. If you ever restore from an old `copilot.db`, schema will not match. Always use `grievance_dashboard.db` fresh.

---

## How to Extend

**Add a new department:** Add it to `DEPARTMENTS` list in `grievance_engine.py`. It will appear in filters automatically.

**Add a new category:** Add to `CATEGORIES` in `grievance_engine.py` and `pattern_engine.py`, and add the mapping in `CATEGORY_DEPT_MAP`. The heatmap will include it automatically (columns are driven by `CATEGORIES` constant, not DB query).

**Add a new district:** Add to `DISTRICTS` in both `grievance_engine.py` and `pattern_engine.py`. Heatmap rows are driven by the `DISTRICTS` constant.

**Change staleness threshold:** Edit `STALE_DAYS = 7` in `grievance_engine.py`.

**Change surge sensitivity:** Edit the `baseline_weekly * 2` multiplier in `pattern_engine.detect_surges()`.

**Swap LLM provider:** Edit `ai.py` only. The rest of the codebase calls `ai.call_ai(prompt)` and doesn't know or care about the provider.

---

*Last updated: 2026-06-17*
