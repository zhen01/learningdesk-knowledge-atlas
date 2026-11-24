"""Local study exercises, roadmaps and chapter checklists."""
import ast
import collections
import datetime
import json
import sqlite3
import time

TRACKS={
 "Data Engineering":["SQL joins and grain","Window functions","Data quality and tests","Python collections","Incremental pipelines","Data modeling"],
 "Product Data Science":["SQL joins and grain","Product metrics","Probability and sampling","Experiment design","Causal inference","Python collections"],
 "Analytics Engineering":["SQL joins and grain","Window functions","Dimensional modeling","Data quality and tests","Incremental pipelines","Stakeholder metrics"],
 "SDE — Data":["Python collections","Arrays and hash maps","Stateful processing","SQL joins and grain","Database design","Testing and reliability"],
}
SQL_SETUP="""CREATE TABLE customers(id INTEGER,name TEXT);
INSERT INTO customers VALUES(1,'Ava'),(2,'Ben'),(3,'Cleo'),(4,'Dan');
CREATE TABLE orders(id INTEGER,customer_id INTEGER,amount INTEGER,day TEXT);
INSERT INTO orders VALUES(1,1,20,'2026-01-01'),(2,1,50,'2026-01-02'),(3,2,10,'2026-01-01'),(4,2,60,'2026-01-03'),(5,3,30,'2026-01-02');
"""
PROBLEMS=[
 {"id":"sql-total","language":"SQL","topic":"SQL joins and grain","title":"Revenue by customer","difficulty":"Easy","prompt":"Return every customer name and total order amount, including customers with no orders. Sort by customer id.","starter":"SELECT ","hint":"LEFT JOIN preserves customers without orders. Group by customer id and name; use COALESCE.","solution":"SELECT c.name, COALESCE(SUM(o.amount),0) AS revenue FROM customers c LEFT JOIN orders o ON c.id=o.customer_id GROUP BY c.id,c.name ORDER BY c.id","why":"A LEFT JOIN preserves the customer grain; SUM aggregates the order rows."},
 {"id":"sql-latest","language":"SQL","topic":"Window functions","title":"Latest order per customer","difficulty":"Medium","prompt":"Return customer_id, id, amount for each customer's most recent order. Sort by customer_id; break date ties by higher order id.","starter":"WITH ranked AS (\n  SELECT * FROM orders\n)\nSELECT * FROM ranked;","hint":"Use ROW_NUMBER() partitioned by customer_id and ordered by day DESC, id DESC.","solution":"WITH ranked AS (SELECT *, ROW_NUMBER() OVER(PARTITION BY customer_id ORDER BY day DESC,id DESC) rn FROM orders) SELECT customer_id,id,amount FROM ranked WHERE rn=1 ORDER BY customer_id","why":"Rank within each customer, then retain only the first row."},
 {"id":"sql-repeat","language":"SQL","topic":"Product metrics","title":"Repeat customers","difficulty":"Easy","prompt":"Return the customer_id and number of orders for customers with at least two orders, ordered by customer_id.","starter":"SELECT ","hint":"GROUP BY customer_id; use HAVING instead of WHERE for aggregated counts.","solution":"SELECT customer_id,COUNT(*) FROM orders GROUP BY customer_id HAVING COUNT(*)>=2 ORDER BY customer_id","why":"HAVING filters grouped results after aggregation."},
 {"id":"py-dedup","language":"Python","topic":"Python collections","title":"Stable deduplication","difficulty":"Easy","prompt":"Define solve(items) to remove duplicates while preserving first occurrence order.","starter":"def solve(items):\n    # Write your solution\n    return []","hint":"Use a set for membership and a list for output.","solution":"def solve(items):\n    seen = set()\n    result = []\n    for item in items:\n        if item not in seen:\n            seen.add(item)\n            result.append(item)\n    return result","why":"A set offers fast membership checks; the list preserves order.","cases":[[[1,2,1,3,2],[1,2,3]],[[],[]],[[3,3,1],[3,1]]]},
 {"id":"py-frequency","language":"Python","topic":"Arrays and hash maps","title":"Count occurrences","difficulty":"Easy","prompt":"Define solve(items) to return a dictionary of item frequencies.","starter":"def solve(items):\n    return {}","hint":"Increment a dictionary entry using get(item, 0).","solution":"def solve(items):\n    counts = {}\n    for item in items:\n        counts[item] = counts.get(item, 0) + 1\n    return counts","why":"A dictionary stores one count per unique item.","cases":[[["a","b","a"],{"a":2,"b":1}],[[],{}],[["x"],{"x":1}]]},
 {"id":"py-positive","language":"Python","topic":"Python collections","title":"Sum positive values","difficulty":"Easy","prompt":"Define solve(items) to sum only values greater than zero.","starter":"def solve(items):\n    return 0","hint":"Loop through items and add only positive numbers.","solution":"def solve(items):\n    total = 0\n    for x in items:\n        if x > 0:\n            total += x\n    return total","why":"Apply the predicate before accumulating.","cases":[[[-2,5,3,0],8],[[-1,-2],0],[[],0]]}
]

def schema(c):
    c.executescript("""
    CREATE TABLE IF NOT EXISTS practice_attempts(id INTEGER PRIMARY KEY AUTOINCREMENT,problem TEXT,code TEXT,passed INTEGER,feedback TEXT,created TEXT);
    CREATE TABLE IF NOT EXISTS roadmap_done(track TEXT,topic TEXT,PRIMARY KEY(track,topic));
    CREATE TABLE IF NOT EXISTS study_plans(id INTEGER PRIMARY KEY CHECK(id=1),track TEXT,start TEXT,days INTEGER,minutes INTEGER);
    CREATE TABLE IF NOT EXISTS chapter_done(document TEXT,label TEXT,PRIMARY KEY(document,label));
    CREATE TABLE IF NOT EXISTS mistake_notes(problem TEXT PRIMARY KEY,note TEXT NOT NULL DEFAULT '',resolved INTEGER NOT NULL DEFAULT 0);
    """)

def chapter_roadmap(c,doc):
    sections=list(c.execute("SELECT label,text FROM sections WHERE document=? ORDER BY rowid",(doc,)))
    completed={r[0] for r in c.execute("SELECT label FROM chapter_done WHERE document=?",(doc,))}
    # Use actual indexed concepts as descriptive labels; keep source order and
    # immutable section identifiers so future indexing never resets progress.
    names=collections.defaultdict(list)
    for r in c.execute("SELECT s.label,n.name FROM sources s JOIN nodes n ON n.id=s.concept WHERE s.document=? ORDER BY n.name",(doc,)):
        if r[1] not in names[r[0]]:names[r[0]].append(r[1])
    result=[]
    for r in sections:
        label,text=r[0],r[1]
        first=next((x.strip().lstrip("#").strip() for x in text.splitlines() if x.strip()),"")
        title=" / ".join(names[label][:3]) if names[label] else first[:90]
        result.append({"label":label,"title":title or label,"done":label in completed,"concepts":names[label]})
    # Prefer actual chapter boundaries if the original extraction contains them.
    # Otherwise group source sections into manageable, clearly labeled ranges.
    import re
    groups=[];current=None
    for i,item in enumerate(result):
        text=sections[i][1]
        heading=next((line.strip().lstrip("#").strip() for line in text.splitlines()[:8] if re.match(r"^\s*(?:#+\s+|(?:chapter|unit|module|part)\s+[\dIVX]+\b)",line,re.I)),None)
        if heading or current is None or (not current["explicit"] and len(current["sections"])>=8):
            current={"title":heading or item["title"],"explicit":bool(heading),"sections":[]}
            groups.append(current)
        current["sections"].append(item)
    for group in groups:
        items=group["sections"];group["done"]=all(x["done"] for x in items);group["completed"]=sum(x["done"] for x in items)
        group["range"]=items[0]["label"]+(" – "+items[-1]["label"] if len(items)>1 else "")
    return {"groups":groups,"total":len(result),"completed":sum(x["done"] for x in result)}

def state(c):
    plan=c.execute("SELECT * FROM study_plans WHERE id=1").fetchone()
    return {"tracks":TRACKS,"problems":[{k:v for k,v in p.items() if k not in ("cases",)} for p in PROBLEMS],
      "attempts":[dict(x) for x in c.execute("SELECT * FROM practice_attempts ORDER BY id DESC LIMIT 500")],
      "roadmap_done":[dict(x) for x in c.execute("SELECT * FROM roadmap_done")],
      "plan":dict(plan) if plan else None,
      "mistake_notes":[dict(x) for x in c.execute("SELECT * FROM mistake_notes")]}

def sql_run(code,extra=False):
    with sqlite3.connect(":memory:") as c:
        c.executescript(SQL_SETUP)
        if extra:
            c.executescript("INSERT INTO customers VALUES(5,'Eli'); INSERT INTO orders VALUES(6,1,70,'2026-01-02'),(7,5,45,'2026-01-04');")
        c.setlimit(sqlite3.SQLITE_LIMIT_LENGTH,1000000)
        safe_functions={"sum","count","avg","min","max","coalesce","ifnull","nullif","round","abs","lower","upper","length","substr","trim","date","strftime","julianday","row_number","rank","dense_rank","lag","lead","first_value","last_value","total","group_concat","typeof","cast"}
        def authorize(action,a,b,*_):
            if action in (sqlite3.SQLITE_SELECT,sqlite3.SQLITE_READ,sqlite3.SQLITE_RECURSIVE):return sqlite3.SQLITE_OK
            if action==sqlite3.SQLITE_FUNCTION and (b or "").lower() in safe_functions:return sqlite3.SQLITE_OK
            return sqlite3.SQLITE_DENY
        c.set_authorizer(authorize)
        end=time.monotonic()+0.8
        c.set_progress_handler(lambda:int(time.monotonic()>end),1000)
        cur=c.execute(code)
        result=cur.fetchmany(201)
        if len(result)>200:raise ValueError("Result exceeds 200 rows.")
        return {"columns":[d[0] for d in cur.description],"rows":[list(r) for r in result]}

class LessonPython:
    """Bounded interpreter for beginner Python exercises, not a general shell."""
    def __init__(self,code):
        tree=ast.parse(code)
        if len(tree.body)!=1 or not isinstance(tree.body[0],ast.FunctionDef):raise ValueError("Define exactly one function: solve(items).")
        self.fn=tree.body[0]
        if self.fn.name!="solve" or len(self.fn.args.args)!=1 or self.fn.decorator_list:raise ValueError("Define solve(items).")
        self.steps=0
    def tick(self):
        self.steps+=1
        if self.steps>20000:raise ValueError("Exercise step limit reached.")
    def expr(self,n,e):
        self.tick()
        if isinstance(n,ast.Constant) and type(n.value) in (int,float,str,bool,type(None)):return n.value
        if isinstance(n,ast.Name) and n.id in e:return e[n.id]
        if isinstance(n,(ast.List,ast.Tuple,ast.Set)):
            values=[self.expr(x,e) for x in n.elts]
            return list(values) if isinstance(n,ast.List) else tuple(values) if isinstance(n,ast.Tuple) else set(values)
        if isinstance(n,ast.Dict):return {self.expr(k,e):self.expr(v,e) for k,v in zip(n.keys,n.values)}
        if isinstance(n,ast.Subscript):return self.expr(n.value,e)[self.expr(n.slice,e)]
        if isinstance(n,ast.UnaryOp):
            x=self.expr(n.operand,e)
            if isinstance(n.op,ast.Not):return not x
            if isinstance(n.op,ast.USub) and type(x) in (int,float):return -x
        if isinstance(n,ast.BoolOp):
            vals=[self.expr(v,e) for v in n.values];return all(vals) if isinstance(n.op,ast.And) else any(vals)
        if isinstance(n,ast.Compare):
            a=self.expr(n.left,e)
            for op,x in zip(n.ops,n.comparators):
                b=self.expr(x,e)
                checks={ast.Eq:lambda:a==b,ast.NotEq:lambda:a!=b,ast.Lt:lambda:a<b,ast.LtE:lambda:a<=b,ast.Gt:lambda:a>b,ast.GtE:lambda:a>=b,ast.In:lambda:a in b,ast.NotIn:lambda:a not in b}
                if type(op) not in checks:raise ValueError("Unsupported comparison.")
                if not checks[type(op)]():return False
                a=b
            return True
        if isinstance(n,ast.BinOp):return self.binop(n.op,self.expr(n.left,e),self.expr(n.right,e))
        if isinstance(n,ast.Call) and not n.keywords:
            args=[self.expr(x,e) for x in n.args]
            if isinstance(n.func,ast.Name):
                functions={"set":set,"list":list,"dict":dict,"len":len,"sum":sum,"min":min,"max":max,"sorted":sorted,"abs":abs,"int":int,"str":str,"bool":bool,"range":lambda *a: list(range(*a)) if len(range(*a))<=10000 else (_ for _ in ()).throw(ValueError("Range too large."))}
                if n.func.id in functions:return functions[n.func.id](*args)
            if isinstance(n.func,ast.Attribute):
                target=self.expr(n.func.value,e);method=n.func.attr
                allowed={list:{"append","pop","count","index"},set:{"add","discard"},dict:{"get","keys","values","items"},str:{"lower","upper","strip","split","count","startswith","endswith"}}
                if method in allowed.get(type(target),set()):return getattr(target,method)(*args)
        raise ValueError("Unsupported Python syntax in this practice sandbox.")
    def binop(self,op,a,b):
        if isinstance(op,ast.Add):
            if type(a) in (list,str,tuple) and len(a)+len(b)>10000:raise ValueError("Value too large.")
            return a+b
        if type(a) not in (int,float) or type(b) not in (int,float):raise ValueError("Numeric operation required.")
        if any(abs(x)>10**12 for x in (a,b)):raise ValueError("Number too large.")
        if isinstance(op,ast.Sub):return a-b
        if isinstance(op,ast.Mult):return a*b
        if isinstance(op,ast.Div):return a/b
        if isinstance(op,ast.FloorDiv):return a//b
        if isinstance(op,ast.Mod):return a%b
        raise ValueError("Unsupported operation.")
    def assign(self,target,value,e):
        if isinstance(target,ast.Name):e[target.id]=value
        elif isinstance(target,ast.Subscript):self.expr(target.value,e)[self.expr(target.slice,e)]=value
        else:raise ValueError("Unsupported assignment.")
    def block(self,stmts,e):
        for n in stmts:
            self.tick()
            if isinstance(n,ast.Return):return True,self.expr(n.value,e)
            if isinstance(n,ast.Assign):
                value=self.expr(n.value,e)
                for t in n.targets:self.assign(t,value,e)
            elif isinstance(n,ast.AugAssign):self.assign(n.target,self.binop(n.op,self.expr(n.target,e),self.expr(n.value,e)),e)
            elif isinstance(n,ast.Expr):self.expr(n.value,e)
            elif isinstance(n,ast.If):
                result=self.block(n.body if self.expr(n.test,e) else n.orelse,e)
                if result[0]:return result
            elif isinstance(n,ast.For):
                for value in list(self.expr(n.iter,e)):
                    self.tick();self.assign(n.target,value,e);result=self.block(n.body,e)
                    if result[0]:return result
            elif isinstance(n,ast.Pass):pass
            else:raise ValueError("Unsupported Python statement; use assignments, if, for and return.")
        return False,None
    def run(self,items):
        self.steps=0
        return self.block(self.fn.body,{self.fn.args.args[0].arg:items})[1]

def run_problem(c,p):
    problem=next((x for x in PROBLEMS if x["id"]==p.get("problem")),None)
    code=p.get("code","")
    if not problem or not isinstance(code,str) or not 0<len(code)<=10000:raise ValueError("Choose a problem and enter code.")
    output={};passed=False
    try:
        if problem["language"]=="SQL":
            output=sql_run(code);expected=sql_run(problem["solution"])
            second=sql_run(code,True);expected_second=sql_run(problem["solution"],True)
            passed=output["rows"]==expected["rows"] and second["rows"]==expected_second["rows"]
            feedback="Both data fixtures match." if passed else "Output differs from expected rows. Check filtering, grain, ordering and aggregation."
            output["expected_columns"]=expected["columns"];output["expected_rows"]=expected["rows"]
            output["additional_fixture_passed"]=second["rows"]==expected_second["rows"]
        else:
            interpreter=LessonPython(code);tests=[]
            for items,expected in problem["cases"]:
                actual=interpreter.run(json.loads(json.dumps(items)))
                tests.append({"input":items,"actual":actual,"expected":expected,"passed":actual==expected})
            output={"tests":tests};passed=all(t["passed"] for t in tests)
            feedback="All tests passed." if passed else "Some cases failed. Compare actual and expected values."
        json.dumps(output)
    except Exception as error:
        output={};feedback=str(error)[:500];passed=False
    c.execute("INSERT INTO practice_attempts(problem,code,passed,feedback,created) VALUES(?,?,?,?,?)",(problem["id"],code,int(passed),feedback,datetime.datetime.now(datetime.timezone.utc).isoformat()))
    if not passed:
        c.execute("INSERT INTO mistake_notes(problem,resolved) VALUES(?,0) ON CONFLICT(problem) DO UPDATE SET resolved=0",(problem["id"],))
    return {"passed":passed,"feedback":feedback,"output":output}

def action(c,p):
    kind=p.get("action")
    if kind=="run":return run_problem(c,p)
    if kind=="chapter":
        doc=p["document"];labels=p.get("labels",[])
        if not isinstance(labels,list) or len(labels)>10000 or type(p.get("done")) is not bool:raise ValueError("Invalid chapter selection.")
        for label in labels:
            if not c.execute("SELECT 1 FROM sections WHERE document=? AND label=?",(doc,label)).fetchone():raise ValueError("Unknown source section.")
            c.execute("INSERT OR IGNORE INTO chapter_done VALUES(?,?)" if p["done"] else "DELETE FROM chapter_done WHERE document=? AND label=?",(doc,label))
        return {"ok":True}
    if kind=="topic":
        track,topic=p["track"],p["topic"]
        if topic not in TRACKS.get(track,[]) or type(p.get("done")) is not bool:raise ValueError("Unknown roadmap topic.")
        c.execute("INSERT OR IGNORE INTO roadmap_done VALUES(?,?)" if p["done"] else "DELETE FROM roadmap_done WHERE track=? AND topic=?",(track,topic))
        return {"ok":True}
    if kind=="plan":
        track=p["track"];days=p["days"];minutes=p["minutes"];start=p["start"]
        if track not in TRACKS or type(days) is not int or not 1<=days<=90 or type(minutes) is not int or not 10<=minutes<=240:raise ValueError("Invalid plan.")
        datetime.date.fromisoformat(start)
        c.execute("INSERT OR REPLACE INTO study_plans VALUES(1,?,?,?,?)",(track,start,days,minutes));return {"ok":True}
    if kind=="mistake":
        problem=p["problem"];note=p.get("note","")
        if not any(x["id"]==problem for x in PROBLEMS) or not isinstance(note,str) or len(note)>20000 or type(p.get("resolved")) is not bool:raise ValueError("Invalid mistake note.")
        c.execute("INSERT INTO mistake_notes VALUES(?,?,?) ON CONFLICT(problem) DO UPDATE SET note=excluded.note,resolved=excluded.resolved",(problem,note,int(p["resolved"])));return {"ok":True}
    raise ValueError("Unknown practice action.")
