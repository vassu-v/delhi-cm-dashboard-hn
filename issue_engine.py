try:
    from pysqlite3 import dbapi2 as sqlite3
except ImportError:
    import sqlite3
import sqlite_vec
import datetime
from sentence_transformers import SentenceTransformer
import struct
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "grievance_dashboard.db")
MODEL_NAME = "all-MiniLM-L6-v2"
THRESHOLD = 0.55   # cosine similarity — same issue type in district
STALE_DAYS = 7     # cluster is stale if no update in this many days


def derive_priority(weight):
    """Auto-derive cluster priority from citizen count."""
    if weight >= 5: return "critical"
    if weight >= 3: return "high"
    return "medium"


def normalize_district(district_str):
    if not district_str:
        return None
    return str(district_str).lower().replace(" ", "")


def cosine_similarity(v1, v2):
    import math
    sumxx, sumyy, sumxy = 0, 0, 0
    for x, y in zip(v1, v2):
        sumxx += x*x; sumyy += y*y; sumxy += x*y
    if sumxx == 0 or sumyy == 0:
        return 0
    return sumxy / (math.sqrt(sumxx) * math.sqrt(sumyy))


_model = None
def get_model():
    global _model
    if _model is None:
        print(f"Loading SentenceTransformer model {MODEL_NAME}...")
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def get_db():
    db = sqlite3.connect(DB_PATH)
    try:
        db.enable_load_extension(True)
        sqlite_vec.load(db)
    except (AttributeError, sqlite3.OperationalError):
        pass
    finally:
        try:
            db.enable_load_extension(False)
        except Exception:
            pass
    db.row_factory = sqlite3.Row
    return db


def serialize_f32(vector):
    return struct.pack(f"{len(vector)}f", *vector)


def init_db():
    db = get_db()
    db.execute("""
    CREATE TABLE IF NOT EXISTS clusters (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        summary             TEXT,
        district            TEXT,
        category            TEXT,
        department_assigned TEXT,
        weight              INTEGER DEFAULT 1,
        status              TEXT DEFAULT 'Received',
        priority            TEXT DEFAULT 'medium',
        date_received       DATE,
        date_assigned       DATE,
        date_resolved       DATE,
        stale_flag          BOOLEAN DEFAULT 0,
        days_since_update   INTEGER DEFAULT 0,
        last_updated        TIMESTAMP,
        created_at          TIMESTAMP
    )
    """)
    db.execute("""
    CREATE TABLE IF NOT EXISTS complaints (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        citizen_name    TEXT,
        citizen_contact TEXT,
        district        TEXT,
        channel         TEXT,
        raw_description TEXT,
        date_received   DATE,
        status          TEXT DEFAULT 'pending',
        cluster_id      INTEGER,
        staff_notes     TEXT,
        resolved_at     DATE,
        created_at      TIMESTAMP,
        FOREIGN KEY(cluster_id) REFERENCES clusters(id)
    )
    """)
    try:
        db.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS vec_clusters USING vec0(
            cluster_id INTEGER PRIMARY KEY,
            embedding float[384]
        )
        """)
    except sqlite3.OperationalError:
        db.execute("""
        CREATE TABLE IF NOT EXISTS vec_clusters (
            cluster_id INTEGER PRIMARY KEY,
            embedding BLOB
        )
        """)
    db.commit()
    db.close()


def process_complaint(complaint_data):
    """
    Embeds complaint text, finds or creates a cluster, and logs the complaint.
    complaint_data keys: complaint_text (required), district, category,
    citizen_name, citizen_contact, channel, date_received, staff_notes
    Returns: {action, cluster_id, cluster_summary, weight, priority, complaint_id}
    """
    from grievance_engine import CATEGORY_DEPT_MAP

    model = get_model()
    db = get_db()
    cursor = db.cursor()

    text = complaint_data.get("complaint_text", "")
    if not text:
        db.close()
        raise ValueError("complaint_text is required")

    category   = complaint_data.get("category") or ""
    department = complaint_data.get("department") or CATEGORY_DEPT_MAP.get(category, "MCD")
    district   = complaint_data.get("district")
    date_recv  = complaint_data.get("date_received") or datetime.date.today().isoformat()

    try:
        embedding      = model.encode(text)
        embedding_bytes = serialize_f32(embedding.tolist())
    except Exception as e:
        print(f"Embedding error: {e}")
        embedding_bytes = None

    now = datetime.datetime.now().isoformat()

    cursor.execute("""
        INSERT INTO complaints
            (citizen_name, citizen_contact, district, channel, raw_description,
             date_received, staff_notes, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        complaint_data.get("citizen_name"),
        complaint_data.get("citizen_contact"),
        district,
        complaint_data.get("channel"),
        text,
        date_recv,
        complaint_data.get("staff_notes"),
        now,
    ))
    complaint_id = cursor.lastrowid

    match        = None
    max_distance = 1.0 - THRESHOLD
    norm_dist    = normalize_district(district)

    if embedding_bytes:
        try:
            cursor.execute("""
                SELECT v.cluster_id, vec_distance_cosine(v.embedding, ?) as distance
                FROM vec_clusters v
                INNER JOIN clusters c ON v.cluster_id = c.id
                WHERE REPLACE(LOWER(c.district), ' ', '') IS ?
                  AND c.status != 'Resolved'
                ORDER BY distance ASC LIMIT 1
            """, (embedding_bytes, norm_dist))
            match = cursor.fetchone()
        except Exception:
            # In-memory fallback
            try:
                cursor.execute("""
                    SELECT c.id, v.embedding, c.district
                    FROM clusters c JOIN vec_clusters v ON c.id = v.cluster_id
                    WHERE c.status != 'Resolved'
                """)
                rows = cursor.fetchall()
            except Exception:
                rows = []

            best_sim, best_id = -1, None
            ev = embedding.tolist()
            for r in rows:
                if normalize_district(r["district"]) != norm_dist:
                    continue
                eb = r["embedding"]
                if eb:
                    try:
                        v = struct.unpack(f"{len(ev)}f", eb)
                        s = cosine_similarity(ev, v)
                        if s > best_sim:
                            best_sim, best_id = s, r["id"]
                    except Exception:
                        pass
            if best_id and best_sim >= THRESHOLD:
                match = {"cluster_id": best_id, "distance": 1.0 - best_sim}

    action           = ""
    target_cluster_id = None
    target_summary   = ""
    new_weight       = 1

    if match and match["distance"] <= max_distance:
        target_cluster_id = match["cluster_id"]
        cursor.execute("SELECT summary, weight FROM clusters WHERE id=?", (target_cluster_id,))
        row = cursor.fetchone()
        target_summary = row["summary"]
        if match["distance"] > 0.15 and len(target_summary) < 150:
            addition = text[:50].strip()
            if addition.lower() not in target_summary.lower():
                target_summary += " | " + addition
        new_weight   = row["weight"] + 1
        new_priority = derive_priority(new_weight)
        cursor.execute("""
            UPDATE clusters SET weight=?, priority=?, summary=?, last_updated=? WHERE id=?
        """, (new_weight, new_priority, target_summary, now, target_cluster_id))
        action = "added_to_existing"
    else:
        target_summary = text[:100] + "..." if len(text) > 100 else text
        cursor.execute("""
            INSERT INTO clusters
                (summary, district, category, department_assigned, weight, status, priority,
                 date_received, last_updated, created_at)
            VALUES (?, ?, ?, ?, 1, 'Received', 'medium', ?, ?, ?)
        """, (target_summary, district, category, department, date_recv, now, now))
        target_cluster_id = cursor.lastrowid
        if embedding_bytes:
            try:
                cursor.execute(
                    "INSERT INTO vec_clusters (cluster_id, embedding) VALUES (?, ?)",
                    (target_cluster_id, embedding_bytes)
                )
            except sqlite3.OperationalError:
                pass
        new_weight = 1
        action     = "new_cluster_created"

    cursor.execute("UPDATE complaints SET cluster_id=? WHERE id=?", (target_cluster_id, complaint_id))
    db.commit()
    db.close()

    return {
        "action":          action,
        "cluster_id":      target_cluster_id,
        "cluster_summary": target_summary,
        "weight":          new_weight,
        "priority":        derive_priority(new_weight),
        "complaint_id":    complaint_id,
    }


def refresh_cluster_stale_flags():
    """Update stale_flag and days_since_update for all non-resolved clusters."""
    db = get_db()
    now = datetime.datetime.now()
    cursor = db.cursor()
    cursor.execute("SELECT id, last_updated FROM clusters WHERE status != 'Resolved'")
    rows = cursor.fetchall()
    for row in rows:
        try:
            last = datetime.datetime.fromisoformat(str(row["last_updated"]))
            days = (now - last).days
            stale = 1 if days >= STALE_DAYS else 0
            cursor.execute(
                "UPDATE clusters SET stale_flag=?, days_since_update=? WHERE id=?",
                (stale, days, row["id"])
            )
        except Exception:
            pass
    db.commit()
    db.close()


def get_all_clusters(filters=None):
    """Return clusters with filters. Default view hides Resolved unless status filter set."""
    refresh_cluster_stale_flags()
    db = get_db()
    cursor = db.cursor()

    query  = "SELECT * FROM clusters WHERE 1=1"
    params = []

    if filters:
        for col, key in [("district", "district"), ("category", "category"),
                         ("department_assigned", "department"), ("priority", "priority")]:
            if filters.get(key):
                query += f" AND {col}=?"
                params.append(filters[key])

        if filters.get("status"):
            query += " AND status=?"
            params.append(filters["status"])
        else:
            query += " AND status != 'Resolved'"
    else:
        query += " AND status != 'Resolved'"

    query += """ ORDER BY
        CASE priority WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
        weight DESC, last_updated DESC"""
    cursor.execute(query, params)
    rows = cursor.fetchall()
    db.close()
    return [dict(r) for r in rows]


def get_cluster_by_id(cluster_id):
    """Return cluster detail + all linked grievances (from grievances table)."""
    refresh_cluster_stale_flags()
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM clusters WHERE id=?", (cluster_id,))
    row = cursor.fetchone()
    if not row:
        db.close()
        return None
    cluster = dict(row)

    cursor.execute("""
        SELECT id, title, description, citizen_name, citizen_contact, citizen_email,
               source, status, priority, date_received, date_resolved, created_at
        FROM grievances WHERE cluster_id=? ORDER BY created_at ASC
    """, (cluster_id,))
    cluster["grievances"] = [dict(r) for r in cursor.fetchall()]
    db.close()
    return cluster


def update_cluster_status(cluster_id, status):
    """Update cluster status and cascade to all linked grievances. Returns # affected."""
    db = get_db()
    cursor = db.cursor()
    now   = datetime.datetime.now().isoformat()
    today = datetime.date.today().isoformat()

    if status == "Resolved":
        cursor.execute("""
            UPDATE clusters
            SET status=?, date_resolved=COALESCE(date_resolved, ?),
                last_updated=?, stale_flag=0, days_since_update=0
            WHERE id=?
        """, (status, today, now, cluster_id))
        cursor.execute("""
            UPDATE grievances
            SET status=?, date_resolved=COALESCE(date_resolved, ?), last_updated=?,
                stale_flag=0, days_since_update=0
            WHERE cluster_id=?
        """, (status, today, now, cluster_id))
    elif status == "Assigned":
        cursor.execute("""
            UPDATE clusters
            SET status=?, date_assigned=COALESCE(date_assigned, ?),
                last_updated=?, stale_flag=0, days_since_update=0
            WHERE id=?
        """, (status, today, now, cluster_id))
        cursor.execute("""
            UPDATE grievances
            SET status=?, date_assigned=COALESCE(date_assigned, ?), last_updated=?,
                stale_flag=0, days_since_update=0
            WHERE cluster_id=?
        """, (status, today, now, cluster_id))
    else:
        cursor.execute("""
            UPDATE clusters
            SET status=?, last_updated=?, stale_flag=0, days_since_update=0 WHERE id=?
        """, (status, now, cluster_id))
        cursor.execute("""
            UPDATE grievances
            SET status=?, last_updated=?, stale_flag=0, days_since_update=0 WHERE cluster_id=?
        """, (status, now, cluster_id))

    affected = cursor.rowcount
    db.commit()
    db.close()
    return affected


def assign_cluster_department(cluster_id, department):
    """Assign department to cluster and cascade to linked grievances."""
    db = get_db()
    cursor = db.cursor()
    now   = datetime.datetime.now().isoformat()
    today = datetime.date.today().isoformat()

    cursor.execute("""
        UPDATE clusters
        SET department_assigned=?, status='Assigned',
            date_assigned=COALESCE(date_assigned, ?),
            last_updated=?, stale_flag=0, days_since_update=0
        WHERE id=?
    """, (department, today, now, cluster_id))
    cursor.execute("""
        UPDATE grievances
        SET department_assigned=?, status='Assigned',
            date_assigned=COALESCE(date_assigned, ?), last_updated=?
        WHERE cluster_id=?
    """, (department, today, now, cluster_id))

    affected = cursor.rowcount
    db.commit()
    db.close()
    return affected


def get_recent_clusters(limit=10):
    """Return most recently updated active clusters for the overview feed."""
    refresh_cluster_stale_flags()
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT * FROM clusters WHERE status != 'Resolved'
        ORDER BY last_updated DESC LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    db.close()
    return [dict(r) for r in rows]


def truncate_db():
    """Drop all issue-engine tables and recreate (called by seed --reset)."""
    db = get_db()
    db.execute("DROP TABLE IF EXISTS complaints")
    db.execute("DROP TABLE IF EXISTS clusters")
    try:
        db.execute("DROP TABLE IF EXISTS vec_clusters")
    except Exception:
        pass
    db.commit()
    db.close()
    init_db()


def get_recent_complaints(limit=5):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM complaints ORDER BY created_at DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    db.close()
    return [dict(r) for r in rows]


if __name__ == "__main__":
    init_db()
    print("Database initialized.")
