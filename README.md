# Delhi CM Grievance Command Center

AI-powered grievance management dashboard for the Delhi Chief Minister's Office. Tracks citizen complaints across all 14 districts, clusters similar issues using vector embeddings, detects surge patterns, measures department performance, and provides a strategic AI advisor for CM-level governance decisions.

---

## What's Running

### Engines

| Engine | Purpose |
|--------|---------|
| `issue_engine.py` | Clusters citizen complaints by semantic similarity using `sentence-transformers` + `sqlite-vec`. Runs fully locally — no LLM needed for embeddings. |
| `grievance_engine.py` | CRUD for the grievances table. Handles status flow (Received → Assigned → In Progress → Resolved), department assignment, stale flag logic. |
| `pattern_engine.py` | Pure SQL analytics — city overview, district breakdown, department performance, surge detection (2× baseline = surge alert), heatmap data. No LLM. |
| `rag_engine.py` | 3-layer context assembly for chat and advisor. Indexes grievance patterns as vector nodes. Runs an agentic multi-round suggestion loop with tool-calling. |
| `ai.py` | Centralized LLM wrapper (Gemini). One-line swappable to any other provider. |

### Dashboard Pages

| Page | What it does |
|------|-------------|
| Overview | Hero stats, 14×8 heatmap (district × category), surge alerts, dept performance table, live grievance feed |
| Districts | Per-district detail: open count, top categories, recent grievances |
| Departments | Department cards with resolution rate, avg days, stale grievance list, performance rating |
| Grievances | Full filterable table (district / dept / status / priority / category). Click any row for detail + status update. |
| Submit | Citizen complaint form. Auto-clusters on submit, shows "X similar complaints in your area" match. |
| Chat | RAG-powered assistant grounded in live dashboard data |
| Strategic Advisor | Agentic multi-round AI that investigates data and generates CM-level recommendations with visible thinking trace |

---

## Delhi-Specific Configuration

**14 Districts:** Central, East, New Delhi, North, North East, North West, Shahdara, South, South East, South West, Dwarka, West, Rohini, Outer

**10 Departments:** MCD, PWD, DJB, DUSIB, Delhi Police, Transport Department, Health Department, Education Department, Revenue Department, BSES

**8 Categories:** Water Supply, Drainage & Sewage, Roads & Infrastructure, Electricity & Power, Sanitation & Garbage, Public Safety, Healthcare, Education

**Default routing (category → department):**
- Water Supply → DJB
- Drainage & Sewage → DJB
- Roads & Infrastructure → PWD
- Electricity & Power → BSES
- Sanitation & Garbage → MCD
- Public Safety → Delhi Police
- Healthcare → Health Department
- Education → Education Department

---

## API Endpoints

```
GET  /api/grievances                  — all grievances, filterable by district/department/status/priority/category
GET  /api/grievances/{id}             — single grievance detail
POST /api/grievances                  — submit new grievance (auto-clusters via issue engine)
POST /api/grievances/{id}/assign      — assign to department
POST /api/grievances/{id}/status      — update status

GET  /api/clusters                    — complaint clusters from issue engine

GET  /api/patterns/city               — city-wide overview stats
GET  /api/patterns/districts          — per-district breakdown
GET  /api/patterns/departments        — department performance report
GET  /api/patterns/surges             — active surge alerts
GET  /api/patterns/heatmap            — district × category matrix
GET  /api/patterns/trends             — grievances filed per day (last N days)

POST /api/chat                        — RAG chat
POST /api/suggestions                 — strategic advisor (agentic)

GET  /api/profile                     — CM office profile
```

---

## Data Layer

Single SQLite file: `grievance_dashboard.db`

| Table | Owner | Purpose |
|-------|-------|---------|
| `grievances` | grievance_engine | All grievances with full lifecycle fields |
| `clusters` | issue_engine | Complaint clusters (semantic groupings) |
| `complaints` | issue_engine | Individual raw complaints linked to clusters |
| `vec_clusters` | issue_engine | Vector embeddings for complaint similarity |
| `knowledge_nodes` | rag_engine | RAG metadata nodes |
| `vec_knowledge` | rag_engine | Vector embeddings for RAG search |
| `ai_memory` | rag_engine | Persistent patterns learned by AI during chat |
| `cm_profile` | grievance_engine | CM office profile (singleton row) |

---

## Setup

### 1. Create and activate venv

```bash
python3 -m venv .venv
```

### 2. Install CPU-only PyTorch first (important — prevents CUDA download)

```bash
.venv/bin/pip install torch --index-url https://download.pytorch.org/whl/cpu
```

### 3. Install remaining dependencies

```bash
.venv/bin/pip install fastapi uvicorn python-multipart google-genai python-dotenv sentence-transformers sqlite-vec numpy
```

### 4. Set API key

Create `.env` in the project root (`hncmsarkarsathi/`):
```
GEMINI_API_KEY=your_key_here
```

Gemini is used for chat and strategic advisor only. All embeddings and analytics run locally without it.

### 5. Seed the database

```bash
cd india-innovates-CivicNTech/Project
../../.venv/bin/python seed.py --reset
```

### 6. Start the server

```bash
cd india-innovates-CivicNTech/Project
../../.venv/bin/uvicorn main:app --port 8000
```

Visit [http://localhost:8000](http://localhost:8000)

---

## Intelligence Layer

### 3-Layer Context Assembly
Every chat/advisor query assembles context from three layers:
- **Layer 1 (always-on):** City overview stats, surge alerts, department snapshot
- **Layer 2 (vector search):** Historical grievance patterns, resolved cluster history from `knowledge_nodes`
- **Layer 3 (live):** Active complaint clusters, stale grievances

### Semantic Router (zero-token)
Classifies queries locally before touching the LLM:
- **instant** — greetings / small talk → respond directly
- **follow-up** — embedding similar to recent retrieved nodes → skip re-search
- **search** — full 3-layer RAG pipeline

### Agentic Suggestion Loop
Strategic Advisor runs up to 3 rounds with tool-calling:
1. Analyses live context, decides whether to call a tool
2. Tool options: `get_district_data`, `get_department_performance`, `get_surge_details`, `get_stale_grievances`, `get_resolution_trends`
3. Synthesises findings into 3-4 CM-level recommendations

Thinking trace is visible in the UI so every recommendation is auditable.

### AI Self-Memory
If the LLM surfaces a non-obvious pattern during chat, it can emit `[MEMORY: Topic] fact [/MEMORY]`. The backend strips the tag, persists the fact to `ai_memory`, and it becomes part of Layer 2 context in future queries.

---

*Built for India Innovates 2026 — CivicNTech*
