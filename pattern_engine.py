"""
Pure analytics layer — no LLM. SQL + simple ML-style inferences.
Feeds both the dashboard and the RAG engine.
"""
try:
    from pysqlite3 import dbapi2 as sqlite3
except ImportError:
    import sqlite3
import datetime
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "grievance_dashboard.db")

DISTRICTS = [
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


def _get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_city_overview() -> dict:
    conn = _get_db()
    c = conn.cursor()
    today = datetime.date.today().isoformat()

    c.execute("SELECT COUNT(*) as n FROM grievances")
    total = c.fetchone()["n"]

    # open/critical/stale from clusters so hero card matches the Issues page
    c.execute("SELECT COUNT(*) as n FROM clusters WHERE status != 'Resolved'")
    open_count = c.fetchone()["n"]

    c.execute("SELECT COUNT(*) as n FROM grievances WHERE status = 'Resolved' AND date_resolved = ?", (today,))
    resolved_today = c.fetchone()["n"]

    c.execute("SELECT COUNT(*) as n FROM clusters WHERE priority = 'critical' AND status != 'Resolved'")
    critical = c.fetchone()["n"]

    c.execute("SELECT COUNT(*) as n FROM clusters WHERE stale_flag = 1")
    stale = c.fetchone()["n"]

    # Overall resolution rate (grievances = citizen reports resolved)
    c.execute("SELECT COUNT(*) as n FROM grievances WHERE status = 'Resolved'")
    resolved_total = c.fetchone()["n"]
    resolution_rate = round((resolved_total / total * 100), 1) if total > 0 else 0

    # Avg resolution days from clusters
    c.execute("""
        SELECT AVG(julianday(date_resolved) - julianday(date_received)) as avg_days
        FROM clusters WHERE status = 'Resolved' AND date_received IS NOT NULL AND date_resolved IS NOT NULL
    """)
    row = c.fetchone()
    avg_days = round(row["avg_days"] or 0, 1)

    # Surges
    surges = detect_surges()
    conn.close()

    return {
        "total": total,
        "open": open_count,
        "resolved_today": resolved_today,
        "critical": critical,
        "stale": stale,
        "resolution_rate": resolution_rate,
        "avg_resolution_days": avg_days,
        "surge_count": len(surges),
        "surges": surges[:5],
    }


def get_district_breakdown() -> list:
    conn = _get_db()
    c = conn.cursor()
    c.execute("""
        SELECT
            district,
            COUNT(*) as total,
            SUM(CASE WHEN status != 'Resolved' THEN 1 ELSE 0 END) as open_count,
            SUM(CASE WHEN status = 'Resolved' THEN 1 ELSE 0 END) as resolved_count,
            SUM(CASE WHEN priority = 'critical' THEN 1 ELSE 0 END) as critical_count,
            SUM(CASE WHEN stale_flag = 1 THEN 1 ELSE 0 END) as stale_count,
            AVG(CASE WHEN status = 'Resolved' AND date_received IS NOT NULL AND date_resolved IS NOT NULL
                THEN julianday(date_resolved) - julianday(date_received) ELSE NULL END) as avg_resolution_days
        FROM grievances
        WHERE district IS NOT NULL
        GROUP BY district
        ORDER BY total DESC
    """)
    rows = c.fetchall()

    # Top category per district
    result = []
    for r in rows:
        d = dict(r)
        d["avg_resolution_days"] = round(d["avg_resolution_days"] or 0, 1)
        total = d["total"] or 1
        d["resolution_rate"] = round((d["resolved_count"] / total) * 100, 1)

        c.execute("""
            SELECT category, COUNT(*) as cnt FROM grievances
            WHERE district = ? AND category IS NOT NULL
            GROUP BY category ORDER BY cnt DESC LIMIT 3
        """, (d["district"],))
        d["top_categories"] = [dict(x) for x in c.fetchall()]

        c.execute("""
            SELECT * FROM grievances WHERE district = ?
            ORDER BY created_at DESC LIMIT 5
        """, (d["district"],))
        d["recent_grievances"] = [dict(x) for x in c.fetchall()]

        result.append(d)

    conn.close()
    return result


def get_department_report() -> list:
    conn = _get_db()
    c = conn.cursor()
    c.execute("""
        SELECT
            department_assigned as department,
            COUNT(*) as total,
            SUM(CASE WHEN status != 'Resolved' THEN 1 ELSE 0 END) as open_count,
            SUM(CASE WHEN status = 'Resolved' THEN 1 ELSE 0 END) as resolved_count,
            SUM(CASE WHEN stale_flag = 1 THEN 1 ELSE 0 END) as stale_count,
            AVG(CASE WHEN status = 'Resolved' AND date_received IS NOT NULL AND date_resolved IS NOT NULL
                THEN julianday(date_resolved) - julianday(date_received) ELSE NULL END) as avg_resolution_days
        FROM grievances
        WHERE department_assigned IS NOT NULL
        GROUP BY department_assigned
        ORDER BY open_count DESC
    """)
    rows = c.fetchall()
    result = []
    for r in rows:
        d = dict(r)
        total = d["total"] or 1
        d["resolution_rate"] = round((d["resolved_count"] / total) * 100, 1)
        d["avg_resolution_days"] = round(d["avg_resolution_days"] or 0, 1)

        # Performance rating: simple scoring
        score = d["resolution_rate"] * 0.5 - d["avg_resolution_days"] * 2 - d["stale_count"] * 1.5
        if score > 30:
            d["performance_rating"] = "Good"
        elif score > 10:
            d["performance_rating"] = "Average"
        else:
            d["performance_rating"] = "Poor"

        # Stale grievances list
        c.execute("""
            SELECT id, title, district, days_since_update, priority FROM grievances
            WHERE department_assigned = ? AND stale_flag = 1
            ORDER BY days_since_update DESC LIMIT 5
        """, (d["department"],))
        d["stale_grievances"] = [dict(x) for x in c.fetchall()]

        result.append(d)

    conn.close()
    return result


def get_category_trends() -> dict:
    conn = _get_db()
    c = conn.cursor()

    # City-wide top 5
    c.execute("""
        SELECT category, COUNT(*) as cnt FROM grievances
        WHERE category IS NOT NULL
        GROUP BY category ORDER BY cnt DESC LIMIT 5
    """)
    city_top = [dict(r) for r in c.fetchall()]

    # Per district top category
    c.execute("""
        SELECT district, category, COUNT(*) as cnt
        FROM grievances WHERE district IS NOT NULL AND category IS NOT NULL
        GROUP BY district, category
    """)
    rows = c.fetchall()

    district_top = {}
    for r in rows:
        d = r["district"]
        if d not in district_top:
            district_top[d] = []
        district_top[d].append({"category": r["category"], "count": r["cnt"]})

    # Sort each district's list
    for d in district_top:
        district_top[d].sort(key=lambda x: x["count"], reverse=True)
        district_top[d] = district_top[d][:3]

    conn.close()
    return {"city_top": city_top, "district_top": district_top}


def detect_surges() -> list:
    """
    Surge = a category in a district has 2x its normal weekly average in the last 7 days.
    """
    conn = _get_db()
    c = conn.cursor()

    today = datetime.date.today()
    week_ago = (today - datetime.timedelta(days=7)).isoformat()
    four_weeks_ago = (today - datetime.timedelta(days=28)).isoformat()

    # Count last 7 days per district+category
    c.execute("""
        SELECT district, category, COUNT(*) as recent_count
        FROM grievances
        WHERE date_received >= ? AND district IS NOT NULL AND category IS NOT NULL
        GROUP BY district, category
    """, (week_ago,))
    recent = {(r["district"], r["category"]): r["recent_count"] for r in c.fetchall()}

    # Count prior 3 weeks per district+category (baseline = avg weekly)
    c.execute("""
        SELECT district, category, COUNT(*) as base_count
        FROM grievances
        WHERE date_received >= ? AND date_received < ? AND district IS NOT NULL AND category IS NOT NULL
        GROUP BY district, category
    """, (four_weeks_ago, week_ago))
    baseline_raw = {(r["district"], r["category"]): r["base_count"] for r in c.fetchall()}

    surges = []
    for (district, category), recent_count in recent.items():
        base_total = baseline_raw.get((district, category), 0)
        baseline_weekly = base_total / 3  # avg per week over 3 weeks
        if baseline_weekly == 0:
            # New problem with no history — flag if >= 3 in last week
            if recent_count >= 3:
                surges.append({
                    "district": district,
                    "category": category,
                    "recent_count": recent_count,
                    "baseline_weekly": 0,
                    "surge_ratio": None,
                    "label": "New spike"
                })
        elif recent_count >= baseline_weekly * 2:
            surges.append({
                "district": district,
                "category": category,
                "recent_count": recent_count,
                "baseline_weekly": round(baseline_weekly, 1),
                "surge_ratio": round(recent_count / baseline_weekly, 1),
                "label": f"{round(recent_count / baseline_weekly, 1)}x normal"
            })

    surges.sort(key=lambda x: x["recent_count"], reverse=True)
    conn.close()
    return surges


def get_heatmap_data() -> dict:
    """
    Returns district × category matrix with grievance counts.
    """
    conn = _get_db()
    c = conn.cursor()
    c.execute("""
        SELECT district, category, COUNT(*) as cnt
        FROM grievances
        WHERE district IS NOT NULL AND category IS NOT NULL
        GROUP BY district, category
    """)
    rows = c.fetchall()
    conn.close()

    matrix = {}
    max_val = 0
    for r in rows:
        d = r["district"]
        cat = r["category"]
        cnt = r["cnt"]
        if d not in matrix:
            matrix[d] = {}
        matrix[d][cat] = cnt
        if cnt > max_val:
            max_val = cnt

    return {
        "districts": DISTRICTS,
        "categories": CATEGORIES,
        "matrix": matrix,
        "max_value": max_val
    }


def get_time_trends(days: int = 30) -> list:
    """Grievances filed per day for the last N days."""
    conn = _get_db()
    c = conn.cursor()
    since = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
    c.execute("""
        SELECT date_received as day, COUNT(*) as count
        FROM grievances WHERE date_received >= ?
        GROUP BY date_received ORDER BY date_received ASC
    """, (since,))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]
