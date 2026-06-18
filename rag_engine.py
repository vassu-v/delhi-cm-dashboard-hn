import os
import json
try:
    from pysqlite3 import dbapi2 as sqlite3
except ImportError:
    import sqlite3
import struct
import datetime
from dotenv import load_dotenv
import google.genai as genai
from sentence_transformers import SentenceTransformer
import numpy as np
import ai

load_dotenv()
api_key = os.environ.get("GEMINI_API_KEY")

DB_PATH = os.path.join(os.path.dirname(__file__), "grievance_dashboard.db")
MODEL_NAME = "all-MiniLM-L6-v2"
THRESHOLD = 0.35

_model = None
def get_model():
    global _model
    if _model is None:
        print(f"Loading SentenceTransformer model {MODEL_NAME}...")
        _model = SentenceTransformer(MODEL_NAME)
    return _model

def get_client():
    if api_key:
        return genai.Client(api_key=api_key)
    return None

_intent_vectors = None

def get_intent_vectors():
    global _intent_vectors
    if _intent_vectors is not None:
        return _intent_vectors
    model = get_model()
    greetings = ["hi", "hello", "hey", "greetings", "namaste", "good morning", "good evening", "who are you", "what can you do"]
    thanks = ["thanks", "thank you", "much appreciated", "great", "awesome", "nice", "perfect"]
    _intent_vectors = {
        "small_talk": model.encode(greetings).mean(axis=0),
        "thanks": model.encode(thanks).mean(axis=0)
    }
    return _intent_vectors

def needs_context(query, recent_node_embeddings=None):
    model = get_model()
    iv = get_intent_vectors()
    q_vec = model.encode([query.lower()])[0]

    def cosine_sim(a, b):
        if b is None or len(b) == 0: return 0
        a = np.array(a)
        b = np.array(b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0: return 0
        return (a @ b) / (norm_a * norm_b)

    if cosine_sim(q_vec, iv["small_talk"]) > 0.65 or cosine_sim(q_vec, iv["thanks"]) > 0.65:
        return "instant"
    if recent_node_embeddings:
        for node_vec in recent_node_embeddings:
            if node_vec is not None and cosine_sim(q_vec, node_vec) > 0.75:
                return "follow-up"
    return "search"

def store_memory(topic, content):
    db = get_db()
    db.execute("INSERT INTO ai_memory (topic, content) VALUES (?, ?)", (topic, content))
    db.commit()
    db.close()

def get_db():
    db = sqlite3.connect(DB_PATH)
    try:
        import sqlite_vec
        db.enable_load_extension(True)
        sqlite_vec.load(db)
    except (AttributeError, sqlite3.OperationalError, ImportError):
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
    CREATE TABLE IF NOT EXISTS knowledge_nodes (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        domain      TEXT,
        district    TEXT,
        topic       TEXT,
        title       TEXT,
        content     TEXT,
        source_ref  TEXT,
        created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    try:
        db.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS vec_knowledge USING vec0(
            node_id   INTEGER PRIMARY KEY,
            embedding float[384]
        )
        """)
    except sqlite3.OperationalError:
        db.execute("""
        CREATE TABLE IF NOT EXISTS vec_knowledge (
            node_id   INTEGER PRIMARY KEY,
            embedding BLOB
        )
        """)
    db.execute("""
    CREATE TABLE IF NOT EXISTS ai_memory (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        topic       TEXT,
        content     TEXT,
        created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    db.commit()
    db.close()

def store_node(domain, district, topic, title, content, source_ref):
    model = get_model()
    embedding = model.encode(content)
    embedding_bytes = serialize_f32(embedding.tolist())
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO knowledge_nodes (domain, district, topic, title, content, source_ref)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (domain, district, topic, title, content, source_ref))
    node_id = cursor.lastrowid
    try:
        cursor.execute("INSERT INTO vec_knowledge (node_id, embedding) VALUES (?, ?)", (node_id, embedding_bytes))
    except sqlite3.OperationalError:
        pass
    db.commit()
    db.close()
    return node_id

def cosine_similarity(v1, v2):
    import math
    sumxx, sumyy, sumxy = 0, 0, 0
    for x, y in zip(v1, v2):
        sumxx += x*x; sumyy += y*y; sumxy += x*y
    if sumxx == 0 or sumyy == 0: return 0
    return sumxy / (math.sqrt(sumxx) * math.sqrt(sumyy))

def query_nodes(query_text, limit=5, district_filter=None):
    model = get_model()
    query_embedding = model.encode(query_text)
    query_bytes = serialize_f32(query_embedding.tolist())
    db = get_db()
    cursor = db.cursor()
    nodes = []
    try:
        sql = """
            SELECT n.id, n.domain, n.district, n.topic, n.title, n.content, n.source_ref, n.created_at,
                   v.embedding, vec_distance_cosine(v.embedding, ?) as distance
            FROM vec_knowledge v
            JOIN knowledge_nodes n ON v.node_id = n.id
        """
        params = [query_bytes]
        if district_filter:
            sql += " WHERE n.district = ? OR n.district IS NULL"
            params.append(district_filter)
        sql += " ORDER BY distance ASC LIMIT ?"
        params.append(limit)
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        for r in rows:
            node = dict(r)
            node['similarity'] = 1.0 - r['distance']
            if r['embedding']:
                emb_data = r['embedding']
                node['embedding'] = list(struct.unpack(f"{len(emb_data)//4}f", emb_data))
            else:
                node['embedding'] = None
            nodes.append(node)
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        cursor.execute("SELECT * FROM knowledge_nodes")
        all_meta = cursor.fetchall()
        all_vecs = {}
        try:
            cursor.execute("SELECT node_id, embedding FROM vec_knowledge")
            all_vecs = {r['node_id']: r['embedding'] for r in cursor.fetchall()}
        except:
            pass
        q_vec = query_embedding.tolist()
        results = []
        for meta in all_meta:
            nid = meta['id']
            node = dict(meta)
            node['similarity'] = 0
            node['embedding'] = None
            if nid in all_vecs and all_vecs[nid]:
                if district_filter and meta['district'] and meta['district'] != district_filter:
                    continue
                v_bytes = all_vecs[nid]
                try:
                    v_vec = struct.unpack(f"{len(q_vec)}f", v_bytes)
                    sim = cosine_similarity(q_vec, v_vec)
                    if sim >= THRESHOLD:
                        node['similarity'] = sim
                        node['embedding'] = list(v_vec)
                        results.append(node)
                except:
                    continue
        results.sort(key=lambda x: x['similarity'], reverse=True)
        nodes = results[:limit]
    db.close()
    return nodes


def assemble_context(query, city_overview=None, surges=None, dept_report=None, clusters=None):
    """
    3-layer context assembly for the CM grievance dashboard.
    Layer 1: Always-on city stats + surges + dept snapshot
    Layer 2: Vector-searched historical grievance patterns
    Layer 3: Live clusters, surge alerts, stale grievances
    """
    nodes = query_nodes(query, limit=5)

    l1 = "=== LAYER 1: DELHI CITY STATE ===\n"
    if city_overview:
        l1 += f"Total Grievances: {city_overview.get('total', 0)} | Open: {city_overview.get('open', 0)} | Critical: {city_overview.get('critical', 0)}\n"
        l1 += f"Resolved Today: {city_overview.get('resolved_today', 0)} | Stale: {city_overview.get('stale', 0)} | Avg Resolution: {city_overview.get('avg_resolution_days', 0)} days\n"
        l1 += f"Resolution Rate: {city_overview.get('resolution_rate', 0)}%\n"
    if dept_report:
        l1 += "\nDepartment Snapshot:\n"
        for dept in (dept_report or [])[:5]:
            l1 += f"  {dept.get('department')}: {dept.get('open_count')} open, {dept.get('avg_resolution_days')}d avg, {dept.get('performance_rating')}\n"

    l2 = "\n=== LAYER 2: HISTORICAL GRIEVANCE PATTERNS ===\n"
    for node in nodes:
        l2 += f"[{node['domain']}] {node['title']}: {node['content']}\n"
    db = get_db()
    memories = db.execute("SELECT * FROM ai_memory ORDER BY created_at DESC LIMIT 5").fetchall()
    db.close()
    for m in memories:
        l2 += f"[ai_memory] {m['topic']}: {m['content']}\n"

    l3 = "\n=== LAYER 3: LIVE PATTERNS ===\n"
    if surges:
        l3 += "Active Surges:\n"
        for s in (surges or [])[:5]:
            l3 += f"  {s.get('district')} — {s.get('category')}: {s.get('recent_count')} this week ({s.get('label')})\n"
    if clusters:
        l3 += "Active Complaint Clusters:\n"
        for c in (clusters or [])[:3]:
            l3 += f"  [{c.get('district')}] {c.get('summary')} (weight: {c.get('weight')})\n"

    return l1 + l2 + l3, nodes


def chat(query, city_overview=None, surges=None, dept_report=None, clusters=None, strategic_context=None, history=None):
    context, nodes = assemble_context(query, city_overview, surges, dept_report, clusters)
    history_str = ""
    if history:
        history_str = "\n=== CONVERSATION HISTORY ===\n"
        for msg in history:
            role = "User" if msg.get("role") == "user" else "Assistant"
            history_str += f"{role}: {msg.get('content')}\n"

    prompt = f"""You are the AI Advisor for the Delhi Chief Minister's Grievance Command Center.
You have access to live grievance data across all 14 districts of Delhi.

INSTRUCTIONS:
1. Answer using ONLY the provided context and conversation history.
2. Be specific — reference actual districts, departments, counts, and dates.
3. If context is insufficient, say so clearly.
4. Cite source type inline: (grievance_pattern), (surge_alert), (dept_data).

STRATEGIC CONTEXT:
{strategic_context if strategic_context else "None provided."}

{history_str}

SELF-INDEXING:
If you learn something non-obvious about Delhi governance patterns, store it:
[MEMORY: Topic Name] The fact. [/MEMORY]

CONTEXT:
{context}

QUESTION:
{query}
"""
    try:
        response_text = ai.call_ai(prompt)
        sources = [{"id": n["id"], "domain": n["domain"], "title": n["title"]} for n in nodes]
        return {
            "response": response_text,
            "sources": sources,
            "working_memory": [n["embedding"] for n in nodes if n.get("embedding") is not None]
        }
    except Exception as e:
        return {"response": f"Chat failed: {e}", "sources": [], "working_memory": []}


def _execute_tool(tool_name, argument):
    """Execute tools for the suggestion agent."""
    import grievance_engine
    import pattern_engine

    try:
        if tool_name == "get_district_data":
            db = grievance_engine.get_db()
            rows = db.execute("""
                SELECT category, COUNT(*) as cnt, status FROM grievances
                WHERE district = ? GROUP BY category, status ORDER BY cnt DESC
            """, (argument,)).fetchall()
            db.close()
            if not rows:
                return f"No data found for district: {argument}"
            return "\n".join([str(dict(r)) for r in rows])

        elif tool_name == "get_department_performance":
            db = grievance_engine.get_db()
            rows = db.execute("""
                SELECT status, priority, COUNT(*) as cnt,
                       AVG(CASE WHEN status='Resolved' THEN julianday(date_resolved)-julianday(date_received) ELSE NULL END) as avg_days
                FROM grievances WHERE department_assigned = ?
                GROUP BY status, priority
            """, (argument,)).fetchall()
            db.close()
            if not rows:
                return f"No data found for department: {argument}"
            return "\n".join([str(dict(r)) for r in rows])

        elif tool_name == "get_surge_details":
            surges = pattern_engine.detect_surges()
            relevant = [s for s in surges if argument.lower() in s["category"].lower() or argument.lower() in s["district"].lower()]
            if not relevant:
                return f"No active surges matching: {argument}"
            return "\n".join([str(s) for s in relevant])

        elif tool_name == "get_stale_grievances":
            db = grievance_engine.get_db()
            rows = db.execute("""
                SELECT id, title, district, days_since_update, priority, status
                FROM grievances WHERE stale_flag=1 AND department_assigned=?
                ORDER BY days_since_update DESC LIMIT 10
            """, (argument,)).fetchall()
            db.close()
            if not rows:
                return f"No stale grievances for department: {argument}"
            return "\n".join([str(dict(r)) for r in rows])

        elif tool_name == "get_resolution_trends":
            limit = int(argument) if str(argument).isdigit() else 10
            db = grievance_engine.get_db()
            rows = db.execute("""
                SELECT district, department_assigned, category, date_received, date_resolved,
                       julianday(date_resolved)-julianday(date_received) as days_taken
                FROM grievances WHERE status='Resolved' AND date_resolved IS NOT NULL
                ORDER BY date_resolved DESC LIMIT ?
            """, (limit,)).fetchall()
            db.close()
            if not rows:
                return "No resolved grievances found."
            return "\n".join([str(dict(r)) for r in rows])

        else:
            return f"Error: Unknown tool {tool_name}"
    except Exception as e:
        return f"Tool error: {e}"


def _build_suggestions_context(city_overview, surges, dept_report, clusters):
    city_overview = city_overview or {}
    surges = surges or []
    dept_report = dept_report or []
    clusters = clusters or []

    ctx = "=== DELHI CM OFFICE — LIVE SITUATION ===\n"
    ctx += f"Total Grievances: {city_overview.get('total', 0)}\n"
    ctx += f"Open: {city_overview.get('open', 0)} | Critical: {city_overview.get('critical', 0)} | Stale: {city_overview.get('stale', 0)}\n"
    ctx += f"Resolved Today: {city_overview.get('resolved_today', 0)} | Resolution Rate: {city_overview.get('resolution_rate', 0)}%\n"
    ctx += f"Avg Resolution Days: {city_overview.get('avg_resolution_days', 0)}\n\n"

    ctx += "=== ACTIVE SURGE ALERTS ===\n"
    for s in surges[:5]:
        ctx += f"- {s['district']} / {s['category']}: {s['recent_count']} this week ({s.get('label', '')})\n"
    ctx += "\n"

    ctx += "=== DEPARTMENT PERFORMANCE ===\n"
    for dept in dept_report:
        ctx += f"- {dept.get('department')}: {dept.get('open_count')} open | {dept.get('avg_resolution_days')}d avg | {dept.get('stale_count')} stale | {dept.get('performance_rating')}\n"
    ctx += "\n"

    ctx += "=== TOP COMPLAINT CLUSTERS ===\n"
    for c in clusters[:5]:
        ctx += f"- [{c.get('district')}] {c.get('summary')} | {c.get('weight')} citizens | Priority: {c.get('priority')} | Status: {c.get('status')}\n"
    ctx += "\n"

    db = get_db()
    memories = db.execute("SELECT topic, content FROM ai_memory ORDER BY created_at DESC LIMIT 5").fetchall()
    db.close()
    if memories:
        ctx += "=== AI MEMORY ===\n"
        for m in memories:
            ctx += f"- [{m['topic']}]: {m['content']}\n"

    return ctx


def run_suggestion_agent(city_overview=None, surges=None, dept_report=None, clusters=None, user_query=None, history=None):
    client = get_client()
    if not client:
        return {
            "suggestions": [],
            "thinking_trace": [{"round": 1, "type": "error", "content": "API Key missing", "timestamp": datetime.datetime.now().isoformat()}],
            "rounds_used": 0,
            "tools_called": []
        }

    always_on_context = _build_suggestions_context(city_overview, surges, dept_report, clusters)

    inquiry_block = ""
    if user_query:
        inquiry_block = f"\nSPECIFIC INQUIRY FROM CM OFFICE: \"{user_query}\"\nFocus your analysis on this topic while considering the overall data."

    thinking_trace = history if history else []
    tools_called = [t['tool'] for t in thinking_trace if t.get('tool')]
    all_tool_results = [t['content'] for t in thinking_trace if t['type'] == 'tool_result']
    all_thinking_prev = "\n".join([t['content'] for t in thinking_trace if t['type'] == 'analysis'])

    session_context = ""
    if history:
        session_context = f"\nPREVIOUS SESSION THINKING:\n{all_thinking_prev}\n\nPREVIOUS TOOL RESULTS:\n" + "\n".join(all_tool_results)

    round_1_prompt = f"""You are the STRATEGIC ADVISOR AI for the Delhi Chief Minister's Grievance Command Center.

STRICT TOOL POLICY — only these tools exist:
1. get_district_data(district) — grievance history and status breakdown for a district
2. get_department_performance(department) — resolution stats for a department
3. get_surge_details(category_or_district) — surge analysis details
4. get_stale_grievances(department) — overdue/stale items per department
5. get_resolution_trends(limit) — recent resolution patterns

CURRENT DATA:
{always_on_context}
{inquiry_block}
{session_context}

TASK:
1. Analyse the data. Identify pressing issues and SYSTEMIC PATTERNS across Delhi's 14 districts.
2. If a SPECIFIC INQUIRY is provided, focus entirely on it.
3. In AUTONOMOUS MODE (no inquiry): find hidden district trends, departmental bottlenecks, or surging categories the CM office should act on. Do NOT just list top pending items.
4. If this is a follow-up, build upon previous thinking without repetition.

Respond with EXACTLY:
TOOL_CALL: tool_name | argument
THINKING: [reasoning]

OR

READY
THINKING: [strategic highlights]
"""

    current_round = 1
    try:
        r1_response = ai.call_ai(round_1_prompt)
        thinking_trace.append({"round": 1, "type": "analysis", "content": r1_response, "timestamp": datetime.datetime.now().isoformat()})

        if "TOOL_CALL:" in r1_response:
            parts = r1_response.split("TOOL_CALL:")[1].split("\n")[0].split("|")
            tool_name = parts[0].strip()
            argument = parts[1].strip() if len(parts) > 1 else ""

            thinking_trace.append({"round": 1, "type": "tool_call", "content": f"Fetching {tool_name} for {argument}...", "tool": tool_name, "args": argument, "timestamp": datetime.datetime.now().isoformat()})

            tool_result = _execute_tool(tool_name, argument)
            all_tool_results.append(f"TOOL RESULT ({tool_name} | {argument}):\n{tool_result}")
            tools_called.append(tool_name)
            thinking_trace.append({"round": 2, "type": "tool_result", "content": tool_result, "timestamp": datetime.datetime.now().isoformat()})

            round_2_prompt = f"""PREVIOUS ANALYSIS:
{r1_response}

TOOL RESULT ({tool_name} | {argument}):
{tool_result}

CURRENT DATA:
{always_on_context}

Call one more tool if needed, or proceed.
Respond with TOOL_CALL or READY as before.
"""
            r2_response = ai.call_ai(round_2_prompt)
            thinking_trace.append({"round": 2, "type": "analysis", "content": r2_response, "timestamp": datetime.datetime.now().isoformat()})
            current_round = 2

            if "TOOL_CALL:" in r2_response:
                parts = r2_response.split("TOOL_CALL:")[1].split("\n")[0].split("|")
                tool_name = parts[0].strip()
                argument = parts[1].strip() if len(parts) > 1 else ""

                thinking_trace.append({"round": 2, "type": "tool_call", "content": f"Fetching {tool_name} for {argument}...", "tool": tool_name, "args": argument, "timestamp": datetime.datetime.now().isoformat()})

                tool_result = _execute_tool(tool_name, argument)
                all_tool_results.append(f"TOOL RESULT ({tool_name} | {argument}):\n{tool_result}")
                tools_called.append(tool_name)
                thinking_trace.append({"round": 3, "type": "tool_result", "content": tool_result, "timestamp": datetime.datetime.now().isoformat()})
                current_round = 3

        tool_results_str = "\n".join(all_tool_results)
        all_thinking = f"{all_thinking_prev}\n\nROUND 1 THINKING:\n{r1_response}"
        if 'r2_response' in locals():
            all_thinking += f"\n\nROUND 2 THINKING:\n{r2_response}"

        inquiry_mode = "TRUE" if user_query else "FALSE"
        final_prompt = f"""ANALYSIS COMPLETE. Generate strategic suggestions for the CM office.

{always_on_context}

TOOL RESULTS:
{tool_results_str}

ANALYSIS SUMMARY:
{all_thinking}

TASK: Generate 3-4 specific, actionable suggestions for the Delhi CM office.
INQUIRY MODE: {inquiry_mode}
SPECIFIC INQUIRY: {user_query}

RULES:
1. If INQUIRY MODE is TRUE, every suggestion MUST directly address the inquiry.
2. If AUTONOMOUS, focus on pattern highlighting and strategic oversight — what needs immediate CM-level attention.
3. If follow-up, do NOT repeat previous suggestions. Add NEW refined insights.
4. Reference real data. No fluff.

Return a JSON array only. No markdown.
Each object: {{ "priority": "...", "title": "...", "body": "..." }}
"""
        final_response = ai.call_ai(final_prompt)

        if "```json" in final_response:
            final_response = final_response.split("```json")[1].split("```")[0].strip()

        try:
            suggestions = json.loads(final_response)
        except:
            suggestions = [{"priority": "normal", "title": "Strategic Recommendation", "body": final_response}]

        return {
            "suggestions": suggestions,
            "thinking_trace": thinking_trace,
            "rounds_used": current_round,
            "tools_called": tools_called,
            "context_summary": f"{current_round} rounds · {len(tools_called)} tool call{'s' if len(tools_called) != 1 else ''}" + (f" · {tools_called[-1]} fetched" if tools_called else "")
        }

    except Exception as e:
        return {
            "suggestions": [],
            "thinking_trace": thinking_trace + [{"round": current_round, "type": "error", "content": str(e), "timestamp": datetime.datetime.now().isoformat()}],
            "rounds_used": current_round,
            "tools_called": tools_called
        }


def generate_suggestions(city_overview=None, surges=None, dept_report=None, clusters=None, user_query=None, history=None):
    return run_suggestion_agent(city_overview, surges, dept_report, clusters, user_query, history)


def truncate_db():
    db = get_db()
    db.execute("DELETE FROM knowledge_nodes")
    try:
        db.execute("DELETE FROM vec_knowledge")
    except sqlite3.OperationalError:
        pass
    db.execute("DELETE FROM sqlite_sequence WHERE name='knowledge_nodes'")
    db.commit()
    db.close()
