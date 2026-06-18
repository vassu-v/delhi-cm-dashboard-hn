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

DEPARTMENTS = [
    "MCD", "PWD", "DJB", "DUSIB", "Delhi Police",
    "Transport Department", "Health Department", "Education Department",
    "Revenue Department", "BSES"
]

CATEGORIES = [
    "Water Supply", "Drainage & Sewage", "Roads & Infrastructure",
    "Electricity & Power", "Sanitation & Garbage", "Public Safety",
    "Healthcare", "Education",
    "Public Transport", "Housing & Shelter", "Land & Property",
]

CATEGORY_DEPT_MAP = {
    "Water Supply":           "DJB",
    "Drainage & Sewage":      "DJB",
    "Roads & Infrastructure": "PWD",
    "Electricity & Power":    "BSES",
    "Sanitation & Garbage":   "MCD",
    "Public Safety":          "Delhi Police",
    "Healthcare":             "Health Department",
    "Education":              "Education Department",
    "Public Transport":       "Transport Department",
    "Housing & Shelter":      "DUSIB",
    "Land & Property":        "Revenue Department",
}

STALE_DAYS = 7


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS grievances (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        title               TEXT NOT NULL,
        description         TEXT,
        district            TEXT,
        category            TEXT,
        department_assigned TEXT,
        status              TEXT DEFAULT 'Received',
        priority            TEXT DEFAULT 'medium',
        citizen_name        TEXT,
        citizen_contact     TEXT,
        citizen_email       TEXT,
        source              TEXT DEFAULT 'portal',
        date_received       DATE,
        date_assigned       DATE,
        date_resolved       DATE,
        stale_flag          BOOLEAN DEFAULT 0,
        days_since_update   INTEGER DEFAULT 0,
        cluster_id          INTEGER,
        created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_updated        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS cm_profile (
        id              INTEGER PRIMARY KEY CHECK (id = 1),
        dashboard_name  TEXT DEFAULT 'Delhi CM Grievance Command Center',
        jurisdiction    TEXT DEFAULT 'National Capital Territory of Delhi',
        districts_count INTEGER DEFAULT 14,
        population      TEXT DEFAULT '3.2 Crore',
        daily_volume    INTEGER DEFAULT 2000,
        contact_email   TEXT DEFAULT 'cmoffice@delhi.gov.in',
        contact_phone   TEXT DEFAULT '+91-11-23392012',
        office_address  TEXT DEFAULT 'Delhi Secretariat, IP Estate, New Delhi - 110002'
    )
    """)
    cursor.execute("INSERT OR IGNORE INTO cm_profile (id) VALUES (1)")

    conn.commit()
    conn.close()


def _refresh_stale_flags():
    conn = get_db()
    cursor = conn.cursor()
    now = datetime.datetime.now()
    cursor.execute("SELECT id, last_updated FROM grievances WHERE status != 'Resolved'")
    rows = cursor.fetchall()
    for row in rows:
        try:
            last = datetime.datetime.fromisoformat(str(row["last_updated"]))
            days = (now - last).days
            stale = 1 if days >= STALE_DAYS else 0
            cursor.execute(
                "UPDATE grievances SET stale_flag=?, days_since_update=? WHERE id=?",
                (stale, days, row["id"])
            )
        except Exception:
            pass
    conn.commit()
    conn.close()


def add_grievance(data: dict) -> dict:
    conn = get_db()
    cursor = conn.cursor()
    now   = datetime.datetime.now().isoformat()
    today = datetime.date.today().isoformat()

    category = data.get("category", "")
    dept     = data.get("department_assigned") or CATEGORY_DEPT_MAP.get(category, "MCD")

    cursor.execute("""
        INSERT INTO grievances (
            title, description, district, category, department_assigned,
            status, priority, citizen_name, citizen_contact, citizen_email,
            source, date_received, cluster_id, created_at, last_updated
        ) VALUES (?, ?, ?, ?, ?, 'Received', ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data.get("title") or (data.get("description") or "")[:80],
        data.get("description"),
        data.get("district"),
        category,
        dept,
        data.get("priority", "medium"),
        data.get("citizen_name"),
        data.get("citizen_contact"),
        data.get("citizen_email"),
        data.get("source", "portal"),
        data.get("date_received", today),
        data.get("cluster_id"),
        now, now,
    ))
    gid = cursor.lastrowid
    conn.commit()
    conn.close()
    return {"id": gid, "department_assigned": dept, "status": "Received",
            "cluster_id": data.get("cluster_id")}


def assign_department(grievance_id: int, department: str) -> bool:
    conn = get_db()
    now   = datetime.datetime.now().isoformat()
    today = datetime.date.today().isoformat()
    conn.execute("""
        UPDATE grievances
        SET department_assigned=?, status='Assigned', date_assigned=?, last_updated=?
        WHERE id=?
    """, (department, today, now, grievance_id))
    conn.commit()
    conn.close()
    return True


def update_status(grievance_id: int, status: str, notes: str = "") -> bool:
    conn = get_db()
    now   = datetime.datetime.now().isoformat()
    today = datetime.date.today().isoformat()
    resolved_date = today if status == "Resolved" else None
    conn.execute("""
        UPDATE grievances
        SET status=?, date_resolved=COALESCE(?, date_resolved),
            last_updated=?, stale_flag=0, days_since_update=0
        WHERE id=?
    """, (status, resolved_date, now, grievance_id))
    conn.commit()
    conn.close()
    return True


def get_grievances(filters: dict = None) -> list:
    _refresh_stale_flags()
    conn = get_db()
    cursor = conn.cursor()
    query  = "SELECT * FROM grievances WHERE 1=1"
    params = []
    if filters:
        for key, col in [("district", "district"), ("department", "department_assigned"),
                         ("status", "status"), ("priority", "priority"), ("category", "category")]:
            if filters.get(key):
                query += f" AND {col}=?"
                params.append(filters[key])
        if filters.get("date_from"):
            query += " AND date_received >= ?"
            params.append(filters["date_from"])
        if filters.get("date_to"):
            query += " AND date_received <= ?"
            params.append(filters["date_to"])
    query += " ORDER BY created_at DESC"
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_grievance_by_id(grievance_id: int) -> dict:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM grievances WHERE id=?", (grievance_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_department_stats() -> list:
    _refresh_stale_flags()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            department_assigned as department,
            COUNT(*) as total,
            SUM(CASE WHEN status != 'Resolved' THEN 1 ELSE 0 END) as open_count,
            SUM(CASE WHEN status = 'Resolved'  THEN 1 ELSE 0 END) as resolved_count,
            SUM(CASE WHEN stale_flag = 1        THEN 1 ELSE 0 END) as stale_count,
            AVG(CASE WHEN status = 'Resolved' AND date_received IS NOT NULL AND date_resolved IS NOT NULL
                THEN julianday(date_resolved) - julianday(date_received) ELSE NULL END) as avg_resolution_days
        FROM grievances
        WHERE department_assigned IS NOT NULL
        GROUP BY department_assigned
        ORDER BY open_count DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        total = d["total"] or 1
        d["resolution_rate"]      = round((d["resolved_count"] / total) * 100, 1)
        d["avg_resolution_days"]  = round(d["avg_resolution_days"] or 0, 1)
        result.append(d)
    return result


def get_district_stats() -> list:
    _refresh_stale_flags()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            district,
            COUNT(*) as total,
            SUM(CASE WHEN status != 'Resolved' THEN 1 ELSE 0 END) as open_count,
            SUM(CASE WHEN status = 'Resolved'  THEN 1 ELSE 0 END) as resolved_count,
            SUM(CASE WHEN priority = 'critical' THEN 1 ELSE 0 END) as critical_count,
            SUM(CASE WHEN stale_flag = 1        THEN 1 ELSE 0 END) as stale_count
        FROM grievances WHERE district IS NOT NULL
        GROUP BY district ORDER BY total DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_pattern_summary() -> dict:
    _refresh_stale_flags()
    conn = get_db()
    cursor = conn.cursor()
    today = datetime.date.today().isoformat()

    def _q(sql, *args):
        return cursor.execute(sql, args).fetchone()[0]

    total         = _q("SELECT COUNT(*) FROM grievances")
    open_count    = _q("SELECT COUNT(*) FROM grievances WHERE status != 'Resolved'")
    critical      = _q("SELECT COUNT(*) FROM grievances WHERE priority='critical' AND status!='Resolved'")
    resolved_today = _q("SELECT COUNT(*) FROM grievances WHERE date_resolved=?", today)
    stale         = _q("SELECT COUNT(*) FROM grievances WHERE stale_flag=1")

    conn.close()
    return {"total": total, "open": open_count, "critical": critical,
            "resolved_today": resolved_today, "stale": stale}


def get_profile() -> dict:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM cm_profile WHERE id=1")
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else {}


def truncate_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM grievances")
    try:
        cursor.execute("DELETE FROM sqlite_sequence WHERE name='grievances'")
    except Exception:
        pass
    conn.commit()
    conn.close()
