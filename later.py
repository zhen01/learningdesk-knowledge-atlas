"""A small, durable reading list and research queue. Links stay local."""
import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse

# Public, curated starter shelf. Full books are not copied into the application.
STARTERS=[
 ("ddia","Designing Data-Intensive Applications","Data & Systems","Martin Kleppmann · Chris Riccomini (2nd ed.)","Understand the enduring tradeoffs behind reliable, scalable and maintainable data systems.","https://www.oreilly.com/library/view/designing-data-intensive/9781098119058/","Publisher preview / paid full book","https://dataintensive.net/","Author's website"),
 ("aie","AI Engineering","Applied AI","Chip Huyen","Learn how foundation model capabilities become usable and measurable applications.","https://github.com/chiphuyen/aie-book","Free author resources / summaries","https://www.oreilly.com/library/view/ai-engineering/9781098166298/","Full book (paid access)"),
 ("missing","The Missing Semester of Your CS Education","Engineering Fundamentals","MIT · 2026 lectures","Build practical command-line, Git, debugging, packaging and engineering skills.","https://missing.csail.mit.edu/2026/","Free lecture notes and videos","",""),
 ("pragmatic","The Pragmatic Programmer","Engineering Mindset","David Thomas · Andrew Hunt","Learn the habits behind maintainable software and thoughtful engineering decisions.","https://media.pragprog.com/titles/tpp20/dry.pdf","Free publisher extract / paid full book","https://books.pragprog.com/titles/tpp20/the-pragmatic-programmer-20th-anniversary-edition/","Publisher / full book"),
 ("powers","7 Powers","Business Strategy","Hamilton Helmer","Understand how lasting competitive advantages arise and why some businesses sustain returns.","https://7powers.com/","Author site / paid full book","https://7powers.com/download-chapter/","Free sample (form)"),
 ("ostep","Operating Systems: Three Easy Pieces","Computer Science","Remzi H. Arpaci-Dusseau · Andrea C. Arpaci-Dusseau","Understand processes, virtual memory, concurrency and persistent storage.","https://pages.cs.wisc.edu/~remzi/OSTEP/","Free complete chapters (PDF)","",""),
]

def schema(c):
    c.executescript("""
    CREATE TABLE IF NOT EXISTS later_items(id TEXT PRIMARY KEY,kind TEXT NOT NULL,title TEXT NOT NULL,category TEXT NOT NULL DEFAULT '',author TEXT NOT NULL DEFAULT '',note TEXT NOT NULL DEFAULT '',url TEXT NOT NULL DEFAULT '',access TEXT NOT NULL DEFAULT '',alt_url TEXT NOT NULL DEFAULT '',alt_label TEXT NOT NULL DEFAULT '',status TEXT NOT NULL,document TEXT,created TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS later_meta(key TEXT PRIMARY KEY);
    """)
    if not c.execute("SELECT 1 FROM later_meta WHERE key='starter-reading-list-v1'").fetchone():
        now=datetime.now(timezone.utc).isoformat()
        c.executemany("INSERT OR IGNORE INTO later_items VALUES(?,'reading',?,?,?,?,?,?,?,?,'saved',NULL,?)",[
            (id,title,category,author,note,url,access,alt_url,alt_label,now) for id,title,category,author,note,url,access,alt_url,alt_label in STARTERS
        ])
        c.execute("INSERT OR IGNORE INTO later_meta VALUES('starter-reading-list-v1')")
        c.commit()

def state(c):
    return [dict(r) for r in c.execute("SELECT * FROM later_items ORDER BY created DESC,id")]

def safe_url(value):
    if not value:return ""
    if not isinstance(value,str) or len(value)>2000 or any(ord(x)<32 for x in value):raise ValueError("Invalid link.")
    parsed=urlparse(value)
    if parsed.scheme not in ("http","https") or not parsed.hostname or parsed.username or parsed.password:raise ValueError("Use an http or https website link.")
    return value

def action(c,p):
    identifier=p.get("id") or uuid.uuid4().hex
    old=c.execute("SELECT * FROM later_items WHERE id=?",(identifier,)).fetchone()
    values=dict(old) if old else {"id":identifier,"kind":p.get("kind"),"title":"","category":"","author":"","note":"","url":"","access":"","alt_url":"","alt_label":"","status":"saved" if p.get("kind")=="reading" else "queued","document":None,"created":datetime.now(timezone.utc).isoformat()}
    for key,limit in (("title",300),("category",100),("author",200),("note",15000),("access",200),("alt_label",100)):
        if key in p:
            val=p[key]
            if not isinstance(val,str) or len(val)>limit:raise ValueError("Invalid "+key+".")
            values[key]=val.strip()
    for key in ("url","alt_url"):
        if key in p:values[key]=safe_url(p[key])
    if values["kind"] not in ("reading","research") or not values["title"]:raise ValueError("Enter a title and choose a list.")
    if not old and p.get("id"):raise ValueError("Unknown list item.")
    statuses=("saved","reading","finished","archived") if values["kind"]=="reading" else ("queued","researching","added","archived")
    if "status" in p:
        if p["status"] not in statuses:raise ValueError("Invalid status.")
        values["status"]=p["status"]
    if "document" in p:
        doc=p["document"] or None
        if doc and not c.execute("SELECT 1 FROM documents WHERE id=?",(doc,)).fetchone():raise ValueError("Unknown library material.")
        values["document"]=doc
    columns=("id","kind","title","category","author","note","url","access","alt_url","alt_label","status","document","created")
    c.execute("INSERT INTO later_items VALUES("+",".join("?" for _ in columns)+") ON CONFLICT(id) DO UPDATE SET "+",".join(k+"=excluded."+k for k in columns[2:-1]),tuple(values[k] for k in columns))
    return values
