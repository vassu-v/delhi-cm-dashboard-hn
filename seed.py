"""
Cluster-First Seed — all grievances flow through issue_engine.process_complaint()
so clusters and grievances are fully linked from the start.
Usage: .venv/bin/python seed.py --reset
"""
import sys, random, datetime, os
sys.path.insert(0, os.path.dirname(__file__))

import grievance_engine, issue_engine, rag_engine

random.seed(42)

DISTRICTS        = grievance_engine.DISTRICTS
CATEGORIES       = grievance_engine.CATEGORIES
CATEGORY_DEPT_MAP = grievance_engine.CATEGORY_DEPT_MAP
SOURCES          = ["portal", "phone", "walk-in", "WhatsApp", "email"]

TEMPLATES = {
    "Water Supply": [
        "No water supply since 3 days in our colony. Taps completely dry.",
        "Water supply has been disrupted for several days in our area.",
        "Pipeline burst near main road, water flowing onto street.",
        "Water pressure very low, barely comes in the morning for 30 minutes.",
        "Contaminated water supply, brown colored water from taps.",
        "Water tank in our building not filled since 4 days. Complete shortage.",
        "Pipeline leakage near park causing waterlogging on footpath.",
        "No drinking water availability in our mohalla for two days.",
    ],
    "Drainage & Sewage": [
        "Sewage overflow on main road near market area. Unbearable stench.",
        "Nala blocked causing sewage water to spill onto road and homes.",
        "Drain overflowing after rainfall, water entering houses.",
        "Manhole cover missing on colony road. Sewage water spilling out.",
        "Sewage pipe broken near school, water logging outside school gates.",
        "Stormwater drain choked, flooding during rain in low-lying area.",
        "Foul smell from blocked drain near residential colony.",
        "Sewage water accumulated on footpath, health hazard for residents.",
    ],
    "Roads & Infrastructure": [
        "Large pothole on main road causing accidents. Two bikes damaged.",
        "Road has not been repaired since last two years. Very bad condition.",
        "Footpath encroached by shops, pedestrians forced onto road.",
        "Street lights not working on main road causing accidents at night.",
        "Road divider damaged and lying on road creating traffic hazard.",
        "Construction debris dumped on road blocking traffic movement.",
        "Broken road near school causing danger to children.",
        "Speed breakers damaged and uneven, causing vehicle damage.",
    ],
    "Electricity & Power": [
        "No electricity since 8 hours. Repeated power cuts in our area.",
        "Electric pole leaning dangerously. Risk of falling on road.",
        "Transformer overloaded, causing frequent power outages in colony.",
        "Low voltage supply causing appliances to malfunction.",
        "Overhead electrical wires hanging dangerously low near footpath.",
        "Power cut from yesterday evening. No response from helpline.",
        "Electric meter not working properly, getting inflated bills.",
        "Power supply disconnected without prior notice in entire block.",
    ],
    "Sanitation & Garbage": [
        "Garbage not collected for 10 days. Huge pile near colony gate.",
        "No garbage pickup since a week. Overflowing bins causing disease.",
        "Open dumping of waste near park. Children playing nearby.",
        "Stray dogs rummaging through uncollected garbage near market.",
        "Recycling waste bins overflowing on main street.",
        "Garbage truck has not visited our lane in two weeks.",
        "Construction waste dumped on footpath, no clearance.",
        "Municipal bins overflowing near bus stop, health hazard.",
    ],
    "Public Safety": [
        "Theft incident near market area. No police patrol in our locality.",
        "Street harassment reported near metro station in evening hours.",
        "Drug abuse openly happening in park. No police action.",
        "Chain snatching incident near ATM. Area not safe at night.",
        "Illegal parking blocking emergency vehicle access to colony.",
        "Broken street lights creating unsafe environment at night.",
        "Suspicious activity near abandoned building reported multiple times.",
        "Stray cattle causing accidents on main road.",
    ],
    "Healthcare": [
        "Dispensary closed during working hours. Patients turned away.",
        "Medicine shortage at government hospital for a week.",
        "Dengue cases rising in our area. Need fumigation and health check.",
        "Malaria breeding spots near drain not addressed despite complaint.",
        "Community health center understaffed, long waiting times.",
        "No ambulance available at PHC during emergency call.",
        "Government hospital running low on essential medicines.",
        "Vaccination camp cancelled last minute with no rescheduling.",
    ],
    "Education": [
        "Government school building in dangerous condition. Roof leaking badly.",
        "Teachers absent frequently. Children losing learning time.",
        "School has no drinking water facility. Children drinking unsafe water.",
        "Toilets in government school non-functional for months.",
        "Mid-day meal quality very poor. Complaints ignored by school.",
        "School library books not updated for years, no new materials.",
        "Evening batch classes stopped without notice. Students affected.",
        "No replacement teacher provided despite teacher being on long leave.",
    ],
    "Public Transport": [
        "DTC bus not running on this route since two days. Commuters stranded.",
        "Bus stop shelter in dilapidated condition. No shade for passengers.",
        "Overcrowded buses, safety risk for passengers.",
        "Metro feeder bus service cancelled without any notice.",
        "Auto-rickshaw refusing to go by meter near metro station.",
        "Bus route timing not followed, long gaps between buses.",
        "Unauthorized autos overcharging passengers near railway station.",
        "Bus stand footpath broken, difficult for elderly and disabled.",
    ],
    "Housing & Shelter": [
        "Unauthorized construction blocking access to flats in colony.",
        "Leakage from upstairs flat causing damage to our property.",
        "Common areas of DDA flats not maintained for months.",
        "Encroachment on common passage, blocking emergency exit.",
        "Public housing building structure unsafe, cracks visible in walls.",
        "Housing society maintenance funds misused, no repair work done.",
        "Illegal commercial use of residential property in our block.",
        "Poor drainage in housing society causing waterlogging in homes.",
    ],
    "Land & Property": [
        "Property documents not processed despite multiple visits to office.",
        "Land encroachment by builder near our plot. FIR registered, no action.",
        "Property tax challan showing wrong property size. Excess billed.",
        "Mutation of property in deceased parents name not done.",
        "Illegal construction on green belt land near our area.",
        "Land acquisition dispute not resolved. Affected families not compensated.",
        "Registry of property delayed beyond two months at sub-registrar office.",
        "Property boundary dispute with neighbour, need survey by Revenue dept.",
    ],
}

NAMES = [
    "Amit Sharma", "Priya Singh", "Rajesh Kumar", "Sunita Devi", "Mohammad Iqbal",
    "Kavita Verma", "Suresh Gupta", "Anita Joshi", "Deepak Nair", "Meena Agarwal",
    "Vikram Malhotra", "Pooja Yadav", "Rohit Chaudhary", "Sonia Arora", "Manish Patel",
    "Rekha Goswami", "Arjun Reddy", "Nisha Tiwari", "Sandeep Dubey", "Lata Bisht",
    "Arun Pandey", "Swati Kapoor", "Naveen Rawat", "Geeta Mishra", "Ravi Shankar",
    "Anjali Singh", "Kiran Kumari", "Devesh Srivastava", "Poonam Gupta", "Sunil Tripathi",
]


def _rdate(days_ago_max=60, days_ago_min=0):
    days = random.randint(days_ago_min, days_ago_max)
    return (datetime.date.today() - datetime.timedelta(days=days)).isoformat()


def _build_complaint_batch():
    complaints = []

    # ── Surge: East + Shahdara drainage (last 5 days) ─────────────────────────
    surge_east = [
        "Nala completely blocked at Laxmi Nagar, sewage overflowing into street.",
        "Drain overflow at Gandhi Nagar market. Sewage water on road.",
        "Choked drain causing flooding near Laxmi Nagar Metro station.",
        "Sewage water entered our homes at Krishna Nagar. URGENT situation.",
        "Drain blocked near school in Geeta Colony, children cannot walk.",
        "Overflowing nala at Preet Vihar causing health issues for residents.",
        "Sewage water in lane near Anand Vihar, foul smell unbearable.",
    ]
    surge_shahdara = [
        "Sewage overflow Shahdara main road near vegetable market.",
        "Drain choked in Shastri Park, water stagnating on road.",
        "Sewage water spilling in Seemapuri colony, flooded footpaths.",
        "Blocked drain near Shahdara bus terminal, passengers suffering.",
        "Overflowing sewage near Dilshad Garden causing health hazard.",
        "Nala blocked at Welcome area, flooding in residential lanes.",
        "Vivek Vihar drain overflow, residents unable to walk on footpath.",
    ]
    for text in surge_east:
        complaints.append({
            "complaint_text": text, "district": "East", "category": "Drainage & Sewage",
            "citizen_name": random.choice(NAMES),
            "citizen_contact": f"98{random.randint(10000000, 99999999)}",
            "channel": random.choice(["phone", "WhatsApp"]),
            "date_received": _rdate(days_ago_max=4, days_ago_min=0),
        })
    for text in surge_shahdara:
        complaints.append({
            "complaint_text": text, "district": "Shahdara", "category": "Drainage & Sewage",
            "citizen_name": random.choice(NAMES),
            "citizen_contact": f"98{random.randint(10000000, 99999999)}",
            "channel": random.choice(["phone", "WhatsApp"]),
            "date_received": _rdate(days_ago_max=4, days_ago_min=0),
        })

    # ── Baseline: all districts × all categories ──────────────────────────────
    for district in DISTRICTS:
        for category in CATEGORIES:
            templates = TEMPLATES[category]
            # Most combos get 1 complaint, some get 2-4 for realism
            count = 1
            if random.random() < 0.25:
                count = random.randint(2, 3)
            elif random.random() < 0.07:
                count = random.randint(4, 5)
            for _ in range(count):
                text = random.choice(templates)
                if random.random() < 0.15:
                    text = text + f" Location: {district} area."
                complaints.append({
                    "complaint_text": text,
                    "district": district,
                    "category": category,
                    "citizen_name": random.choice(NAMES),
                    "citizen_contact": f"9{random.randint(600000000, 999999999)}",
                    "channel": random.choice(SOURCES),
                    "date_received": _rdate(days_ago_max=55, days_ago_min=3),
                })

    random.shuffle(complaints)
    return complaints


def _seed_rag_nodes():
    nodes = [
        ("governance", None, "department_performance", "DJB Historical Water Complaint Pattern",
         "DJB receives 30-40% of all water supply complaints. Resolution rate improved to 72% since 2022 after pipeline upgrade in South and Dwarka. East district remains persistent problem area due to aging infrastructure.",
         "Delhi Jal Board Annual Report 2023"),
        ("infrastructure", "East", "drainage", "East District Drainage Infrastructure",
         "East District has 3 major nalas prone to choking during monsoon. Historical surge rate: 4x normal during July-September. DJB has flagged for desilting since 2021.",
         "East Delhi Municipal Corporation Survey 2022"),
        ("governance", None, "escalation_protocol", "CM Office Grievance Escalation Protocol",
         "Clusters unresolved beyond 7 days are marked stale and escalated. Critical priority cases (5+ citizen complaints) require department head review within 48 hours.",
         "CM Office SOP 2023"),
        ("healthcare", None, "disease_alert", "Mosquito-Borne Disease Pattern",
         "Dengue cases spike in Delhi between August-November. North East and East districts historically most affected due to stagnant water near Yamuna.",
         "Delhi Health Department Epidemiology Report 2023"),
        ("infrastructure", "Rohini", "roads", "Rohini Sub-City Road Maintenance",
         "Rohini has 300+ km of internal roads under DUSIB maintenance. Phase 2 and Phase 3 areas have aging roads with poor drainage. PWD upgrade pending since 2022.",
         "PWD Delhi Sub-City Report"),
        ("governance", None, "resolution_benchmark", "Delhi Grievance Resolution Benchmarks",
         "Target resolution times: Water Supply 3 days, Electricity 24 hrs, Road Repair 14 days, Sanitation 2 days. DJB and BSES consistently below target.",
         "Delhi CM Office Performance Dashboard"),
        ("transport", None, "dtc_performance", "DTC Bus Service Coverage",
         "DTC operates 3500+ buses on 600+ routes. North West and South West districts have lowest frequency service. Last-mile connectivity gaps affect 40% of metro users.",
         "DTC Annual Operations Report 2023"),
        ("housing", None, "jj_colonies", "JJ Colony Housing Issues",
         "Delhi has 675 unauthorized JJ colonies with over 1 crore residents. DUSIB resettlement plans for 376 colonies pending since 2010. Major issues: unauthorized construction, poor drainage.",
         "DUSIB Survey Report 2022"),
        ("land", None, "revenue_department", "Property Registration Backlogs",
         "Delhi Revenue Department processes 800+ property registrations daily. Average delay: 6-8 weeks beyond statutory 30-day deadline. Sub-registrar offices in South Delhi most congested.",
         "Revenue Department Annual Report 2023"),
        ("education", None, "school_infrastructure", "Delhi Government School Infrastructure",
         "7000+ government schools in Delhi. 35% need infrastructure upgrade. South East and North East districts have worst infrastructure scores.",
         "Delhi Education Department Report 2023"),
    ]
    print(f"  Seeding {len(nodes)} RAG knowledge nodes...")
    for n in nodes:
        try:
            rag_engine.store_node(*n)
        except Exception as e:
            print(f"  Warning: RAG node failed: {e}")


def run(reset=False):
    print("=== CLUSTER-FIRST SEED ===")
    if reset:
        print("Resetting databases...")
        issue_engine.truncate_db()
        grievance_engine.truncate_db()
        rag_engine.truncate_db()
        grievance_engine.init_db()
        print("  Done.\n")

    complaints = _build_complaint_batch()
    total = len(complaints)
    print(f"Processing {total} complaints through issue engine...")

    cluster_ids_seen = set()
    for i, cdata in enumerate(complaints):
        if (i + 1) % 25 == 0 or i == 0:
            print(f"  [{i+1}/{total}] Embedding & clustering...")
        try:
            result = issue_engine.process_complaint(cdata)
            cid = result["cluster_id"]
            g_data = {
                "title":             cdata["complaint_text"][:80],
                "description":       cdata["complaint_text"],
                "district":          cdata["district"],
                "category":          cdata["category"],
                "department_assigned": CATEGORY_DEPT_MAP.get(cdata["category"], "MCD"),
                "citizen_name":      cdata.get("citizen_name"),
                "citizen_contact":   cdata.get("citizen_contact"),
                "source":            cdata.get("channel", "portal"),
                "date_received":     cdata.get("date_received"),
                "cluster_id":        cid,
                "priority":          result.get("priority", "medium"),
            }
            grievance_engine.add_grievance(g_data)
            cluster_ids_seen.add(cid)
        except Exception as e:
            print(f"  Error at complaint {i}: {e}")

    print(f"\nProcessed {total} complaints. Clusters formed: {len(cluster_ids_seen)}\n")

    # ── Post-process: set cluster statuses, cascade to grievances ─────────────
    print("Setting cluster statuses (target: ~62% resolved)...")
    db = issue_engine.get_db()
    cursor = db.cursor()
    cursor.execute("SELECT id FROM clusters ORDER BY id")
    all_ids = [r[0] for r in cursor.fetchall()]
    db.close()

    n = len(all_ids)
    n_resolved    = int(n * 0.62)
    n_in_progress = int(n * 0.14)
    n_assigned    = int(n * 0.12)

    shuffled = list(all_ids)
    random.shuffle(shuffled)

    for i, cid in enumerate(shuffled):
        if i < n_resolved:
            issue_engine.update_cluster_status(cid, "Resolved")
        elif i < n_resolved + n_in_progress:
            issue_engine.update_cluster_status(cid, "In Progress")
        elif i < n_resolved + n_in_progress + n_assigned:
            issue_engine.update_cluster_status(cid, "Assigned")
        # else: stays Received

    # ── Verify ────────────────────────────────────────────────────────────────
    db = issue_engine.get_db()
    c = db.cursor()
    c.execute("SELECT COUNT(*) FROM clusters")
    tc = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM clusters WHERE status='Resolved'")
    rc = c.fetchone()[0]
    db.close()

    conn = grievance_engine.get_db()
    gc = conn.cursor()
    gc.execute("SELECT COUNT(*) FROM grievances")
    tg = gc.fetchone()[0]
    gc.execute("SELECT COUNT(*) FROM grievances WHERE status='Resolved'")
    rg = gc.fetchone()[0]
    conn.close()

    print(f"Clusters: {tc} total, {rc} resolved ({round(rc/max(1,tc)*100,1)}%)")
    print(f"Grievances: {tg} total, {rg} resolved ({round(rg/max(1,tg)*100,1)}%)")

    # ── RAG knowledge nodes ───────────────────────────────────────────────────
    _seed_rag_nodes()
    print("\n=== SEED COMPLETE ===")


if __name__ == "__main__":
    reset = "--reset" in sys.argv
    run(reset=reset)
