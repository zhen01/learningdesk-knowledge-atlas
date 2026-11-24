#!/usr/bin/env python3
"""Local knowledge atlas. No API credentials, remote calls or telemetry."""
import argparse
import hashlib
import json
import mimetypes
import re
import shutil
import sqlite3
import sys
import unicodedata
import webbrowser
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, quote
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
INBOX = ROOT / "inbox"
EXT = {".pdf", ".docx", ".md", ".markdown", ".txt"}

def db():
    DATA.mkdir(exist_ok=True)
    conn = sqlite3.connect(DATA / "atlas.sqlite", timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS documents(id TEXT PRIMARY KEY,name TEXT NOT NULL,original TEXT NOT NULL,created TEXT NOT NULL,status TEXT NOT NULL,error TEXT);
    CREATE TABLE IF NOT EXISTS sections(document TEXT, label TEXT, text TEXT, PRIMARY KEY(document,label));
    CREATE TABLE IF NOT EXISTS nodes(id TEXT PRIMARY KEY,name TEXT NOT NULL,kind TEXT NOT NULL,parent TEXT,explanation TEXT NOT NULL DEFAULT '',aliases TEXT NOT NULL DEFAULT '[]');
    CREATE TABLE IF NOT EXISTS placements(concept TEXT,parent TEXT,PRIMARY KEY(concept,parent));
    CREATE TABLE IF NOT EXISTS sources(concept TEXT,document TEXT,label TEXT,quote TEXT,explanation TEXT,PRIMARY KEY(concept,document,label,quote));
    CREATE TABLE IF NOT EXISTS connections(id TEXT PRIMARY KEY,a TEXT,b TEXT,kind TEXT,explanation TEXT,document TEXT,label TEXT,quote TEXT);
    CREATE TABLE IF NOT EXISTS processed(document TEXT,label TEXT,PRIMARY KEY(document,label));
    """)
    return conn

def norm(s):
    return re.sub(r"[^\w]+", " ", unicodedata.normalize("NFKC", s).casefold()).strip()

def key(*values):
    return hashlib.sha256(json.dumps(values, ensure_ascii=False).encode()).hexdigest()[:24]

def compact(s):
    return " ".join(s.split())

def parse(path):
    ext = path.suffix.lower()
    if ext == ".pdf":
        from pypdf import PdfReader
        sections = [(f"Page {i+1}", p.extract_text() or "") for i,p in enumerate(PdfReader(path).pages)]
    elif ext == ".docx":
        from docx import Document
        doc = Document(path)
        sections = [(f"Paragraph {i+1}", p.text) for i,p in enumerate(doc.paragraphs)]
        for i,table in enumerate(doc.tables):
            sections.append((f"Table {i+1}", "\n".join(" | ".join(c.text for c in row.cells) for row in table.rows)))
    else:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
        sections = []
        start, buf = 1, []
        for i,line in enumerate(lines, 1):
            if buf and (re.match(r"^#{1,6}\s", line) or sum(map(len,buf)) > 5000):
                sections.append((f"Lines {start}–{i-1}", "\n".join(buf)))
                start,buf = i,[]
            buf.append(line)
        if buf:
            sections.append((f"Lines {start}–{len(lines)}", "\n".join(buf)))
    if not any(t.strip() for _,t in sections):
        raise ValueError("No extractable text. Scanned PDFs require OCR first.")
    result = []
    for label,text in sections:
        if text.strip():
            for i in range(0,len(text),16000):
                result.append((label if len(text)<=16000 else f"{label}, part {i//16000+1}",text[i:i+16000]))
    return result

def ingest(path):
    path = Path(path)
    if path.suffix.lower() not in EXT:
        raise ValueError("Unsupported file format.")
    content = path.read_bytes()
    docid = hashlib.sha256(content).hexdigest()
    original = DATA / "originals" / docid
    original.mkdir(parents=True,exist_ok=True)
    saved = original / path.name
    with db() as c:
        existing = c.execute("SELECT * FROM documents WHERE id=?",(docid,)).fetchone()
        if existing and existing["status"]!="error":
            return docid
        if existing:
            saved = DATA / existing["original"]
        if not saved.exists():
            saved.write_bytes(content)
        c.execute("INSERT OR IGNORE INTO documents VALUES(?,?,?,?,?,NULL)",(docid,path.name,str(saved.relative_to(DATA)),datetime.now(timezone.utc).isoformat(),"uploaded"))
    try:
        sections = parse(saved)
    except Exception as exc:
        with db() as c:
            c.execute("UPDATE documents SET status='error',error=? WHERE id=?",(str(exc),docid))
        return docid
    with db() as c:
        c.executemany("INSERT OR REPLACE INTO sections VALUES(?,?,?)",[(docid,l,t) for l,t in sections])
        c.execute("UPDATE documents SET status='ready',error=NULL WHERE id=?",(docid,))
    return docid

def rows(c,sql,args=()):
    return [dict(row) for row in c.execute(sql,args)]

def snapshot():
    with db() as c:
        return {
            "documents":rows(c,"SELECT id,name,created,status,error,(SELECT count(*) FROM sections s WHERE s.document=d.id) AS sections,(SELECT count(*) FROM processed p WHERE p.document=d.id) AS indexed FROM documents d ORDER BY created DESC"),
            "nodes":rows(c,"SELECT * FROM nodes ORDER BY name"),
            "placements":rows(c,"SELECT * FROM placements"),
            "sources":rows(c,"SELECT s.*,d.name AS document_name FROM sources s JOIN documents d ON s.document=d.id"),
            "connections":rows(c,"SELECT * FROM connections")
        }

def pending():
    with db() as c:
        return rows(c,"SELECT d.id,d.name,s.label,LENGTH(s.text) AS characters FROM documents d JOIN sections s ON s.document=d.id LEFT JOIN processed p ON p.document=s.document AND p.label=s.label WHERE p.label IS NULL ORDER BY d.created,s.rowid")

def apply(payload):
    doc = payload["document"]
    labels = payload["sections"]
    if not isinstance(labels,list) or not labels or len(labels)!=len(set(labels)):
        raise ValueError("Specify unique section labels.")
    with db() as c:
        c.execute("BEGIN IMMEDIATE")
        texts = {r["label"]:r["text"] for r in c.execute("SELECT label,text FROM sections WHERE document=?",(doc,))}
        if any(l not in texts for l in labels):
            raise ValueError("Unknown source section.")
        if any(c.execute("SELECT 1 FROM processed WHERE document=? AND label=?",(doc,l)).fetchone() for l in labels):
            raise ValueError("One or more sections are already indexed.")
        catalog = rows(c,"SELECT * FROM nodes WHERE kind='concept'")
        byid = {x["id"]:x for x in catalog}
        byname = {}
        for x in catalog:
            for name in [x["name"],*json.loads(x["aliases"])]:
                byname.setdefault(norm(name),set()).add(x["id"])
        mapped = {}
        def evidence(item):
            label,q = item["label"],item["quote"]
            if label not in labels or len(compact(q))<12 or compact(q) not in compact(texts[label]):
                raise ValueError(f"Evidence does not match source: {label}")
            return label,q
        for item in payload["concepts"]:
            label,q = evidence(item)
            name = item["name"].strip()
            aliases = item.get("aliases",[])
            explanation = item["explanation"].strip()
            if not name or not explanation or not all(isinstance(a,str) for a in aliases):
                raise ValueError("Missing concept information.")
            if item["key"] in mapped or item["key"] in byid:
                raise ValueError("Duplicate or reserved concept key.")
            existing = item.get("existing_id")
            if existing and existing not in byid:
                raise ValueError("Unknown existing concept ID.")
            matches = byname.get(norm(name),set())
            if not existing and len(matches)>1:
                raise ValueError("Ambiguous concept; provide existing_id.")
            cid = existing or (next(iter(matches)) if matches else key("concept",norm(name)))
            old = c.execute("SELECT * FROM nodes WHERE id=?",(cid,)).fetchone()
            merged = sorted(set(aliases + (json.loads(old["aliases"])+[name] if old else [])) - {old["name"] if old else name})
            c.execute("INSERT INTO nodes VALUES(?,?, 'concept',NULL,?,?) ON CONFLICT(id) DO UPDATE SET aliases=excluded.aliases",(cid,name,explanation,json.dumps(merged,ensure_ascii=False)))
            mapped[item["key"]] = cid
            for a in [name,*merged]:
                byname.setdefault(norm(a),set()).add(cid)
            parent=None
            for kind in ("domain","module","submodule"):
                title=item[kind].strip()
                if not title:
                    raise ValueError("Missing hierarchy level.")
                nid=key(kind,parent,norm(title))
                c.execute("INSERT OR IGNORE INTO nodes VALUES(?,?,?,?,?,?)",(nid,title,kind,parent,"","[]"))
                parent=nid
            c.execute("INSERT OR IGNORE INTO placements VALUES(?,?)",(cid,parent))
            c.execute("INSERT OR IGNORE INTO sources VALUES(?,?,?,?,?)",(cid,doc,label,q,explanation))
        for edge in payload.get("connections",[]):
            label,q=evidence(edge)
            a,b=(mapped.get(edge[x],edge[x]) for x in ("from","to"))
            valid=set(byid)|set(mapped.values())
            kind=edge["kind"]
            if a not in valid or b not in valid or a==b or not ({a,b}&set(mapped.values())) or kind not in {"prerequisite","application","shared principle","contrast","extension"} or not edge["explanation"].strip():
                raise ValueError("Invalid connection.")
            c.execute("INSERT OR IGNORE INTO connections VALUES(?,?,?,?,?,?,?,?)",(key(a,b,kind,doc,label),a,b,kind,edge["explanation"],doc,label,q))
        c.executemany("INSERT INTO processed VALUES(?,?)",[(doc,l) for l in labels])
        remaining=c.execute("SELECT count(*) FROM sections s LEFT JOIN processed p ON p.document=s.document AND p.label=s.label WHERE s.document=? AND p.label IS NULL",(doc,)).fetchone()[0]
        c.execute("UPDATE documents SET status=? WHERE id=?",("ready" if remaining else "complete",doc))

class Handler(BaseHTTPRequestHandler):
    def send(self,data,typ="application/json",status=200,extra=None):
        if not isinstance(data,bytes):
            data=json.dumps(data,ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type",typ)
        self.send_header("Content-Length",str(len(data)))
        self.send_header("Cache-Control","no-store")
        self.send_header("X-Content-Type-Options","nosniff")
        for k,v in (extra or {}).items(): self.send_header(k,v)
        self.end_headers()
        self.wfile.write(data)
    def valid_host(self):
        return self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}"
    def do_GET(self):
        if not self.valid_host():
            return self.send({"error":"Local access only"},status=403)
        u=urlparse(self.path)
        if u.path=="/api/atlas":
            return self.send(snapshot())
        if u.path=="/api/original":
            with db() as c:
                d=c.execute("SELECT * FROM documents WHERE id=?",(parse_qs(u.query).get("id",[""])[0],)).fetchone()
            if not d: return self.send({"error":"Not found"},status=404)
            p=DATA/d["original"]
            typ=mimetypes.guess_type(p.name)[0] or "application/octet-stream"
            if p.suffix.lower() in {".md",".markdown",".txt"}: typ="text/plain; charset=utf-8"
            disposition="inline" if p.suffix.lower()==".pdf" else "attachment"
            return self.send(p.read_bytes(),typ,extra={"Content-Disposition":f"{disposition}; filename*=UTF-8''{quote(p.name)}"})
        if u.path in ("/","/app.js","/style.css"):
            name="index.html" if u.path=="/" else u.path[1:]
            return self.send((ROOT/"web"/name).read_bytes(),mimetypes.guess_type(name)[0]+"; charset=utf-8")
        self.send({"error":"Not found"},status=404)
    def do_POST(self):
        if not self.valid_host() or self.headers.get("Origin")!=f"http://127.0.0.1:{self.server.server_port}" or urlparse(self.path).path!="/api/import":
            return self.send({"error":"Request rejected"},status=403)
        try:
            length=int(self.headers.get("Content-Length","0"))
            name=parse_qs(urlparse(self.path).query).get("name",[""])[0]
            if not name or Path(name).name!=name or "\\" in name or Path(name).suffix.lower() not in EXT or not 0<length<=100*1024*1024:
                raise ValueError("Choose a supported file up to 100 MB.")
            INBOX.mkdir(exist_ok=True)
            import tempfile
            with tempfile.TemporaryDirectory(dir=INBOX) as tmp:
                p=Path(tmp)/name
                p.write_bytes(self.rfile.read(length))
                docid=ingest(p)
            self.send({"id":docid})
        except Exception as exc:
            self.send({"error":str(exc)},status=400)

def main():
    parser=argparse.ArgumentParser()
    sub=parser.add_subparsers(dest="cmd",required=True)
    serve=sub.add_parser("serve");serve.add_argument("--port",type=int,default=8765);serve.add_argument("--no-browser",action="store_true")
    imp=sub.add_parser("import");imp.add_argument("paths",nargs="*")
    sub.add_parser("pending");sub.add_parser("catalog")
    read=sub.add_parser("read");read.add_argument("document");read.add_argument("labels",nargs="+")
    write=sub.add_parser("apply");write.add_argument("file")
    args=parser.parse_args()
    if args.cmd=="serve":
        db().close()
        server=ThreadingHTTPServer(("127.0.0.1",args.port),Handler)
        url=f"http://127.0.0.1:{args.port}"
        print(f"LearningDesk is open at {url}",flush=True)
        if not args.no_browser: webbrowser.open(url)
        server.serve_forever()
    elif args.cmd=="import":
        INBOX.mkdir(exist_ok=True)
        for p in [Path(x) for x in args.paths] or sorted(INBOX.iterdir()):
            if p.is_file() and p.suffix.lower() in EXT: print(f"{ingest(p)}  {p.name}")
    elif args.cmd=="pending":
        print(json.dumps(pending(),ensure_ascii=False,indent=2))
    elif args.cmd=="catalog":
        print(json.dumps(snapshot(),ensure_ascii=False,indent=2))
    elif args.cmd=="read":
        with db() as c:
            print(json.dumps([dict(r) for l in args.labels for r in c.execute("SELECT label,text FROM sections WHERE document=? AND label=?",(args.document,l))],ensure_ascii=False,indent=2))
    elif args.cmd=="apply":
        apply(json.loads(Path(args.file).read_text(encoding="utf-8")));print("Atlas updated.")

if __name__=="__main__":
    main()
