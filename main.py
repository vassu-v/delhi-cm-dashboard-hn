from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, List
from contextlib import asynccontextmanager
import os
import grievance_engine
import issue_engine
import pattern_engine
import rag_engine
import ai

@asynccontextmanager
async def lifespan(app: FastAPI):
    grievance_engine.init_db()
    issue_engine.init_db()
    rag_engine.init_db()
    yield

app = FastAPI(title="Delhi CM Grievance Dashboard API", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")


# ── Pydantic Models ──────────────────────────────────────────────────────────

class GrievanceCreate(BaseModel):
    title:               Optional[str] = None
    description:         str
    district:            Optional[str] = None
    category:            Optional[str] = None
    department_assigned: Optional[str] = None
    priority:            str = "medium"
    citizen_name:        Optional[str] = None
    citizen_contact:     Optional[str] = None
    citizen_email:       Optional[str] = None
    source:              str = "portal"
    date_received:       Optional[str] = None

class AssignRequest(BaseModel):
    department: str

class StatusRequest(BaseModel):
    status: str
    notes:  str = ""

class ChatRequest(BaseModel):
    query:            str
    working_memory:   list = []
    strategic_context: Optional[str] = None
    history:          List[dict] = []

class SuggestionsRequest(BaseModel):
    query:   Optional[str] = None
    history: Optional[List[dict]] = None


# ── Submit (citizen-facing) ───────────────────────────────────────────────────

@app.post("/api/grievances")
def submit_grievance(data: GrievanceCreate):
    try:
        payload = data.dict(exclude_none=True)
        cluster_res = issue_engine.process_complaint({
            "citizen_name":    payload.get("citizen_name"),
            "citizen_contact": payload.get("citizen_contact"),
            "district":        payload.get("district"),
            "category":        payload.get("category"),
            "channel":         payload.get("source", "portal"),
            "complaint_text":  payload.get("description", ""),
            "date_received":   payload.get("date_received"),
        })
        payload["cluster_id"] = cluster_res.get("cluster_id")
        result = grievance_engine.add_grievance(payload)
        result["cluster_match"]   = cluster_res.get("action") == "added_to_existing"
        result["cluster_summary"] = cluster_res.get("cluster_summary")
        result["cluster_weight"]  = cluster_res.get("weight")
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Individual grievance endpoints (for modal drill-down) ─────────────────────

@app.get("/api/grievances")
def list_grievances(
    district:   Optional[str] = None,
    department: Optional[str] = None,
    status:     Optional[str] = None,
    priority:   Optional[str] = None,
    category:   Optional[str] = None,
    date_from:  Optional[str] = None,
    date_to:    Optional[str] = None,
):
    filters = {k: v for k, v in {
        "district": district, "department": department, "status": status,
        "priority": priority, "category": category,
        "date_from": date_from, "date_to": date_to,
    }.items() if v is not None}
    return grievance_engine.get_grievances(filters)

@app.get("/api/grievances/{grievance_id}")
def get_grievance(grievance_id: int):
    g = grievance_engine.get_grievance_by_id(grievance_id)
    if not g:
        raise HTTPException(status_code=404, detail="Grievance not found")
    return g

@app.post("/api/grievances/{grievance_id}/assign")
def assign_grievance(grievance_id: int, req: AssignRequest):
    grievance_engine.assign_department(grievance_id, req.department)
    return {"status": "assigned", "department": req.department}

@app.post("/api/grievances/{grievance_id}/status")
def update_grievance_status(grievance_id: int, req: StatusRequest):
    grievance_engine.update_status(grievance_id, req.status, req.notes)
    return {"status": "updated", "new_status": req.status}


# ── Cluster endpoints (primary unit) ─────────────────────────────────────────

@app.get("/api/clusters")
def list_clusters(
    district:   Optional[str] = None,
    category:   Optional[str] = None,
    department: Optional[str] = None,
    status:     Optional[str] = None,
    priority:   Optional[str] = None,
):
    filters = {k: v for k, v in {
        "district": district, "category": category,
        "department": department, "status": status, "priority": priority,
    }.items() if v is not None}
    return issue_engine.get_all_clusters(filters)

@app.get("/api/recent-clusters")
def recent_clusters(limit: int = 10):
    return issue_engine.get_recent_clusters(limit)

@app.get("/api/stale-clusters")
def stale_clusters(limit: int = 5):
    return issue_engine.get_stale_clusters(limit)

@app.get("/api/clusters/{cluster_id}")
def get_cluster(cluster_id: int):
    c = issue_engine.get_cluster_by_id(cluster_id)
    if not c:
        raise HTTPException(status_code=404, detail="Cluster not found")
    return c

@app.post("/api/clusters/{cluster_id}/status")
def update_cluster_status(cluster_id: int, req: StatusRequest):
    affected = issue_engine.update_cluster_status(cluster_id, req.status)
    return {"status": "updated", "new_status": req.status, "affected_grievances": affected}

@app.post("/api/clusters/{cluster_id}/assign")
def assign_cluster(cluster_id: int, req: AssignRequest):
    affected = issue_engine.assign_cluster_department(cluster_id, req.department)
    return {"status": "assigned", "department": req.department, "affected_grievances": affected}


# ── Patterns ─────────────────────────────────────────────────────────────────

@app.get("/api/patterns/city")
def city_overview():
    return pattern_engine.get_city_overview()

@app.get("/api/patterns/districts")
def districts_breakdown():
    return pattern_engine.get_district_breakdown()

@app.get("/api/patterns/departments")
def departments_report():
    return pattern_engine.get_department_report()

@app.get("/api/patterns/surges")
def surge_alerts():
    return pattern_engine.detect_surges()

@app.get("/api/patterns/heatmap")
def heatmap():
    return pattern_engine.get_heatmap_data()

@app.get("/api/patterns/trends")
def trends(days: int = 30):
    return pattern_engine.get_time_trends(days)


# ── Chat & Advisor ────────────────────────────────────────────────────────────

@app.post("/api/chat")
def chat(req: ChatRequest):
    try:
        route = rag_engine.needs_context(req.query, req.working_memory)

        if route == "instant":
            res_text = ai.call_ai(
                f"You are the CM Grievance Dashboard AI. Answer warmly. Query: {req.query}"
            )
            return {"response": res_text, "sources": [], "routed": "instant"}

        city_overview = pattern_engine.get_city_overview()
        surges        = pattern_engine.detect_surges()
        dept_report   = pattern_engine.get_department_report()
        clusters      = issue_engine.get_recent_clusters(limit=10)

        res_data = rag_engine.chat(
            query=req.query,
            city_overview=city_overview,
            surges=surges,
            dept_report=dept_report,
            clusters=clusters,
            strategic_context=req.strategic_context,
            history=req.history,
        )
        res_data["routed"] = route

        import re
        mem_match = re.search(r"\[MEMORY:\s*(.*?)\](.*?)\[/MEMORY\]", res_data["response"], re.DOTALL)
        if mem_match:
            rag_engine.store_memory(mem_match.group(1).strip(), mem_match.group(2).strip())
            res_data["response"] = re.sub(r"\[MEMORY:.*?/MEMORY\]", "", res_data["response"], flags=re.DOTALL).strip()
            res_data["memory_stored"] = True

        return res_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/suggestions")
def get_suggestions(req: Optional[SuggestionsRequest] = None):
    try:
        query   = req.query   if req else None
        history = req.history if req else None

        city_overview = pattern_engine.get_city_overview()
        surges        = pattern_engine.detect_surges()
        dept_report   = pattern_engine.get_department_report()
        clusters      = issue_engine.get_recent_clusters(limit=10)

        return rag_engine.generate_suggestions(
            city_overview=city_overview,
            surges=surges,
            dept_report=dept_report,
            clusters=clusters,
            user_query=query,
            history=history,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Profile ───────────────────────────────────────────────────────────────────

@app.get("/api/profile")
def get_profile():
    return grievance_engine.get_profile()


# ── Frontend ──────────────────────────────────────────────────────────────────

@app.get("/")
def read_root():
    return FileResponse(os.path.join(os.path.dirname(__file__), "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
