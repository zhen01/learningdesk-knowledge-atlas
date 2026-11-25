"""Learning goals and evidence live alongside the original atlas."""
LEVELS = [
    ("Recognize", "Define the central idea and give a concrete example."),
    ("Explain", "Explain the mechanism, its assumptions, and one limitation."),
    ("Apply", "Solve a documented case and show how you checked the result."),
    ("Evaluate", "Compare two approaches on the same case and defend the trade-off."),
    ("Create", "Develop an original approach, test it, and explain where it fails."),
]

def schema(c):
    c.executescript("""
    CREATE TABLE IF NOT EXISTS shape_lessons(domain TEXT,level INTEGER,task TEXT,document TEXT,label TEXT,PRIMARY KEY(domain,level));
    CREATE TABLE IF NOT EXISTS shape_goals(domain TEXT PRIMARY KEY,target INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS shape_evidence(domain TEXT,level INTEGER,response TEXT,
      passed INTEGER,created TEXT DEFAULT CURRENT_TIMESTAMP);
    """)

def state(c):
    goals = dict(c.execute("SELECT domain,target FROM shape_goals"))
    for row in c.execute("SELECT name FROM nodes WHERE kind='domain'"):
        goals.setdefault(row[0], 3)
    result = []
    for domain,target in goals.items():
        history = [dict(r) for r in c.execute("SELECT level,response,passed,created FROM shape_evidence WHERE domain=? ORDER BY rowid DESC",(domain,))]
        current = max((r["level"] for r in history if r["passed"]), default=0)
        lessons = {r["level"]:dict(r) for r in c.execute("SELECT level,task,document,label FROM shape_lessons WHERE domain=?", (domain,))}
        result.append(dict(domain=domain,target=target,current=current,history=history,lessons=lessons))
    return dict(domains=result,levels=LEVELS)

def change(c,p):
    domain = str(p.get("domain","")).strip()
    if not 0 < len(domain) <= 180:
        raise ValueError("Enter a domain name (up to 180 characters).")
    c.execute("BEGIN IMMEDIATE")
    if p.get("action") == "goal":
        target = p.get("target")
        if type(target) is not int or not 1 <= target <= 5:
            raise ValueError("Choose L1 through L5.")
        c.execute("INSERT INTO shape_goals VALUES(?,?) ON CONFLICT(domain) DO UPDATE SET target=excluded.target",(domain,target))
    elif p.get("action") == "assess":
        goal = next((g for g in state(c)["domains"] if g["domain"]==domain),None)
        response = str(p.get("response","")).strip()
        if not goal or p.get("level")!=goal["current"]+1 or p["level"]>goal["target"] or not response or type(p.get("passed")) is not bool:
            raise ValueError("Refresh the current level and record your evidence.")
        c.execute("INSERT INTO shape_evidence(domain,level,response,passed) VALUES(?,?,?,?)",(domain,p["level"],response,p["passed"]))
    else:
        raise ValueError("Unknown action.")
    return state(c)

def apply_lessons(c,p):
    domain = p["domain"]
    if domain not in {g["domain"] for g in state(c)["domains"]}:
        raise ValueError("Choose an existing domain.")
    lessons = p["lessons"]
    if len(lessons)!=5 or {r["level"] for r in lessons}!=set(range(1,6)):
        raise ValueError("Provide one task for each level.")
    for row in lessons:
        source = c.execute("SELECT text FROM sections WHERE document=? AND label=?", (row["document"],row["label"])).fetchone()
        if not source or len(row["quote"])<12 or row["quote"] not in source[0] or not row["task"].strip():
            raise ValueError("Each task needs a verified source passage.")
    c.executemany("INSERT OR REPLACE INTO shape_lessons VALUES(?,?,?,?,?)",
        [(domain,r["level"],r["task"],r["document"],r["label"]) for r in lessons])
