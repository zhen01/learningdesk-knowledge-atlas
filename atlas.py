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
import study
import practice
import later
import threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, quote
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
INBOX = ROOT / "inbox"
VIDEO={".mp4",".m4v",".mov",".webm"}
AUDIO={".mp3",".m4a",".wav",".ogg",".flac",".aac"}
IMAGES={".png",".jpg",".jpeg",".webp",".gif"}
_cover_slots=threading.BoundedSemaphore(2)
MEDIA=VIDEO|AUDIO|IMAGES
EXT = {".pdf", ".docx", ".pptx", ".md", ".markdown", ".txt", ".csv", ".json", ".html", ".htm", ".srt", ".vtt"}|MEDIA
DEFAULT_COLLECTIONS=("Career","Product Data Science","Textbook Knowledge","Fun Knowledge")

def db():
    DATA.mkdir(exist_ok=True)
    conn = sqlite3.connect(DATA / "atlas.sqlite", timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    # Back up the pre-upgrade database before adding new tables. Existing rows
    # are never dropped, rewritten, or re-indexed by a schema upgrade.
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='documents'").fetchone() and not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='highlights'").fetchone():
        backup_db(conn, "before-reader-upgrade")
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='documents'").fetchone() and not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='collections'").fetchone():
        backup_db(conn, "before-library-upgrade")
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='documents'").fetchone() and not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='study_materials'").fetchone():
        backup_db(conn, "before-study-upgrade")
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='documents'").fetchone() and not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='chapter_done'").fetchone():
        backup_db(conn, "before-practice-upgrade")
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='documents'").fetchone() and not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='material_modules'").fetchone():
        backup_db(conn, "before-material-roadmap-upgrade")
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='documents'").fetchone() and not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='later_items'").fetchone():
        backup_db(conn, "before-later-upgrade")
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS documents(id TEXT PRIMARY KEY,name TEXT NOT NULL,original TEXT NOT NULL,created TEXT NOT NULL,status TEXT NOT NULL,error TEXT);
    CREATE TABLE IF NOT EXISTS sections(document TEXT, label TEXT, text TEXT, PRIMARY KEY(document,label));
    CREATE TABLE IF NOT EXISTS nodes(id TEXT PRIMARY KEY,name TEXT NOT NULL,kind TEXT NOT NULL,parent TEXT,explanation TEXT NOT NULL DEFAULT '',aliases TEXT NOT NULL DEFAULT '[]');
    CREATE TABLE IF NOT EXISTS placements(concept TEXT,parent TEXT,PRIMARY KEY(concept,parent));
    CREATE TABLE IF NOT EXISTS sources(concept TEXT,document TEXT,label TEXT,quote TEXT,explanation TEXT,PRIMARY KEY(concept,document,label,quote));
    CREATE TABLE IF NOT EXISTS connections(id TEXT PRIMARY KEY,a TEXT,b TEXT,kind TEXT,explanation TEXT,document TEXT,label TEXT,quote TEXT);
    CREATE TABLE IF NOT EXISTS processed(document TEXT,label TEXT,PRIMARY KEY(document,label));
    CREATE TABLE IF NOT EXISTS highlights(id TEXT PRIMARY KEY,document TEXT NOT NULL,label TEXT NOT NULL,start INTEGER NOT NULL,end INTEGER NOT NULL,quote TEXT NOT NULL,color TEXT NOT NULL,note TEXT NOT NULL DEFAULT '',created TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS reading_positions(document TEXT PRIMARY KEY,label TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS collections(id TEXT PRIMARY KEY,name TEXT NOT NULL COLLATE NOCASE UNIQUE);
    CREATE TABLE IF NOT EXISTS document_collections(document TEXT,collection TEXT,PRIMARY KEY(document,collection));
    CREATE TABLE IF NOT EXISTS transcripts(document TEXT,hash TEXT,filename TEXT,original TEXT,PRIMARY KEY(document,hash));
    CREATE TABLE IF NOT EXISTS media_positions(document TEXT PRIMARY KEY,seconds REAL NOT NULL);
    """)
    conn.executemany("INSERT OR IGNORE INTO collections VALUES(?,?)",[(key("collection",name),name) for name in DEFAULT_COLLECTIONS])
    conn.commit()
    study.schema(conn)
    practice.schema(conn)
    later.schema(conn)
    return conn

def backup_db(conn, reason="manual"):
    folder=DATA/"backups"
    folder.mkdir(parents=True,exist_ok=True)
    path=folder/f"{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')}-{reason}.sqlite"
    with sqlite3.connect(path) as target:
        conn.backup(target)
    return path

def reader_document(doc):
    with db() as c:
        d=c.execute("SELECT id,name,status FROM documents WHERE id=?",(doc,)).fetchone()
        if not d:
            raise ValueError("Document not found.")
        position=c.execute("SELECT label FROM reading_positions WHERE document=?",(doc,)).fetchone()
        media_position=c.execute("SELECT seconds FROM media_positions WHERE document=?",(doc,)).fetchone()
        return {"document":dict(d),"sections":rows(c,"SELECT label,text FROM sections WHERE document=? ORDER BY rowid",(doc,)),
                "highlights":rows(c,"SELECT * FROM highlights WHERE document=? ORDER BY label,start",(doc,)),
                "position":position[0] if position else None,
                "transcripts":rows(c,"SELECT filename,hash FROM transcripts WHERE document=?",(doc,)),
                "media_position":media_position[0] if media_position else 0,
                "study":dict(record) if (record:=c.execute("SELECT * FROM study_materials WHERE document=?",(doc,)).fetchone()) else {}}

def material_cover(doc):
    """Optional macOS Quick Look preview, cached separately from source data."""
    if not isinstance(doc,str) or not re.fullmatch(r"[0-9a-f]{64}",doc):
        return None
    with db() as c:
        record=c.execute("SELECT original FROM documents WHERE id=?",(doc,)).fetchone()
    if not record:return None
    original=(DATA/record["original"]).resolve()
    if (DATA/"originals").resolve() not in original.parents or not original.is_file():
        return None
    if original.suffix.lower() not in ({".pdf",".docx",".pptx"}|VIDEO|IMAGES):return None
    if original.suffix.lower() in IMAGES:return original
    if sys.platform!="darwin" or not Path("/usr/bin/qlmanage").is_file():return None
    folder=DATA/"covers";folder.mkdir(exist_ok=True)
    cover=folder/(doc+".png");failed=folder/(doc+".unavailable")
    if cover.is_file():return cover
    if failed.exists():return None
    if not _cover_slots.acquire(timeout=1):return None
    try:
        if cover.is_file():return cover
        if failed.exists():return None
        import tempfile,subprocess
        with tempfile.TemporaryDirectory() as tmp:
            result=subprocess.run(["/usr/bin/qlmanage","-t","-s","640","-o",tmp,str(original)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15)
            previews=list(Path(tmp).glob("*.png"))
            if result.returncode==0 and previews:
                staging=folder/(doc+"."+Path(tmp).name+".png")
                shutil.copyfile(previews[0],staging)
                staging.replace(cover)
                return cover
        failed.touch()
    except (OSError,subprocess.TimeoutExpired):
        return None
    finally:
        _cover_slots.release()
    return None

def collection_change(payload):
    with db() as c:
        if payload.get("action")=="create":
            name=payload.get("name","").strip()
            if not 1<=len(name)<=80:raise ValueError("Enter a collection name.")
            c.execute("INSERT OR IGNORE INTO collections VALUES(?,?)",(key("collection",name),name))
            return dict(c.execute("SELECT * FROM collections WHERE name=? COLLATE NOCASE",(name,)).fetchone())
        document,collection=payload["document"],payload["collection"]
        if not c.execute("SELECT 1 FROM documents WHERE id=?",(document,)).fetchone() or not c.execute("SELECT 1 FROM collections WHERE id=?",(collection,)).fetchone():
            raise ValueError("Unknown document or collection.")
        if payload.get("assigned"):
            c.execute("INSERT OR IGNORE INTO document_collections VALUES(?,?)",(document,collection))
        else:
            c.execute("DELETE FROM document_collections WHERE document=? AND collection=?",(document,collection))
        return {"ok":True}

def transcript_sections(text,ext):
    if ext in (".vtt",".srt"):
        items=[]
        for block in re.split(r"\n\s*\n",text.replace("\r\n","\n").strip()):
            lines=block.splitlines()
            timing=next((i for i,l in enumerate(lines) if "-->" in l),None)
            if timing is None:continue
            start=lines[timing].split("-->")[0].strip().replace(",",".")
            if not re.fullmatch(r"(?:\d{1,3}:)?\d{2}:\d{2}(?:\.\d+)?",start):continue
            content="\n".join(re.sub(r"<[^>]+>","",l) for l in lines[timing+1:]).strip()
            if content:items.append((f"@ {start}",content))
        # Group adjacent cues into useful context windows, retain the first
        # timestamp as the citation and playback position.
        sections=[];label=None;parts=[]
        for timestamp,content in items:
            if parts and sum(map(len,parts))+len(content)>3500:
                sections.append((label,"\n".join(parts)));parts=[]
            if not parts:label=timestamp
            parts.append(content)
        if parts:sections.append((label,"\n".join(parts)))
        return sections
    return [(f"Part {i//12000+1}",text[i:i+12000]) for i in range(0,len(text),12000) if text[i:i+12000].strip()]

def attach_transcript(payload):
    doc,name,text=payload["document"],payload["name"],payload["text"]
    ext=Path(name).suffix.lower()
    if ext not in (".srt",".vtt",".txt",".md") or not isinstance(text,str) or not text.strip() or len(text)>5_000_000:
        raise ValueError("Attach a nonempty SRT, VTT, TXT or Markdown transcript.")
    sections=transcript_sections(text,ext)
    if not sections:raise ValueError("No readable transcript cues found.")
    digest=hashlib.sha256(text.encode()).hexdigest()
    with db() as c:
        d=c.execute("SELECT name FROM documents WHERE id=?",(doc,)).fetchone()
        if not d or Path(d["name"]).suffix.lower() not in VIDEO|AUDIO:raise ValueError("Choose a video or audio file.")
        if c.execute("SELECT 1 FROM transcripts WHERE document=? AND hash=?",(doc,digest)).fetchone():return {"ok":True,"duplicate":True}
        folder=DATA/"transcripts"/doc
        folder.mkdir(parents=True,exist_ok=True)
        original=folder/(digest+ext)
        original.write_text(text,encoding="utf-8")
        c.execute("INSERT INTO transcripts VALUES(?,?,?,?)",(doc,digest,Path(name).name,str(original.relative_to(DATA))))
        c.executemany("INSERT INTO sections VALUES(?,?,?)",[(doc,f"Transcript {digest[:12]} · {i+1} · {label}",content) for i,(label,content) in enumerate(sections)])
        c.execute("UPDATE documents SET status='ready',error=NULL WHERE id=?",(doc,))
        return {"ok":True,"duplicate":False}

def save_highlight(payload):
    doc,label=payload["document"],payload["label"]
    start,end=payload["start"],payload["end"]
    color=payload.get("color","yellow")
    note=payload.get("note","")
    if color not in ("yellow","green","blue","pink") or not isinstance(note,str) or len(note)>20000:
        raise ValueError("Invalid highlight.")
    with db() as c:
        s=c.execute("SELECT text FROM sections WHERE document=? AND label=?",(doc,label)).fetchone()
        if not s or type(start) is not int or type(end) is not int or not 0<=start<end<=len(s["text"]):
            raise ValueError("Invalid selection.")
        selected=s["text"][start:end]
        if not selected.strip() or selected!=payload["quote"]:
            raise ValueError("Selection does not match source.")
        hid=key(doc,label,start,end)
        existing=c.execute("SELECT note FROM highlights WHERE id=?",(hid,)).fetchone()
        if existing and "note" not in payload:
            note=existing["note"]
        c.execute("INSERT INTO highlights VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET color=excluded.color,note=excluded.note",(hid,doc,label,start,end,selected,color,note,datetime.now(timezone.utc).isoformat()))
        return dict(c.execute("SELECT * FROM highlights WHERE id=?",(hid,)).fetchone())

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
    elif ext==".pptx":
        sections=study.slide_sections(path)
    elif ext in (".srt",".vtt"):
        sections=transcript_sections(path.read_text(encoding="utf-8-sig"),ext)
    elif ext==".csv":
        import csv
        with path.open(encoding="utf-8-sig",newline="") as f:
            reader=csv.reader(f)
            header=next(reader,[])
            sections=[]
            batch=[]
            for i,row in enumerate(reader,1):
                batch.append(" | ".join(f"{header[j] if j<len(header) else 'Column '+str(j+1)}: {value}" for j,value in enumerate(row)))
                if len(batch)==25:
                    sections.append((f"Rows {i-24}–{i}","\n".join(batch)));batch=[]
            if batch:sections.append((f"Rows {i-len(batch)+1}–{i}","\n".join(batch)))
    elif ext==".json":
        parsed=json.loads(path.read_text(encoding="utf-8-sig"))
        text=json.dumps(parsed,ensure_ascii=False,indent=2)
        sections=[(f"JSON part {i//12000+1}",text[i:i+12000]) for i in range(0,len(text),12000)]
    elif ext in (".html",".htm"):
        from html.parser import HTMLParser
        class Extractor(HTMLParser):
            def __init__(self):
                super().__init__();self.parts=[];self.skip=0
            def handle_starttag(self,tag,attrs):
                if tag in ("script","style"):self.skip+=1
            def handle_endtag(self,tag):
                if tag in ("script","style") and self.skip:self.skip-=1
            def handle_data(self,data):
                if not self.skip and data.strip():self.parts.append(data.strip())
        parser=Extractor();parser.feed(path.read_text(encoding="utf-8-sig"))
        text="\n".join(parser.parts)
        sections=[(f"HTML part {i//12000+1}",text[i:i+12000]) for i in range(0,len(text),12000)]
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
    with path.open("rb") as f:
        digest=hashlib.sha256()
        for chunk in iter(lambda:f.read(1024*1024),b""):digest.update(chunk)
    docid = digest.hexdigest()
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
            shutil.copy2(path,saved)
        c.execute("INSERT OR IGNORE INTO documents VALUES(?,?,?,?,?,NULL)",(docid,path.name,str(saved.relative_to(DATA)),datetime.now(timezone.utc).isoformat(),"uploaded"))
    if path.suffix.lower() in MEDIA:
        with db() as c:c.execute("UPDATE documents SET status='media',error=NULL WHERE id=?",(docid,))
        return docid
    try:
        sections = parse(saved)
    except Exception as exc:
        with db() as c:
            c.execute("UPDATE documents SET status='error',error=? WHERE id=?",(str(exc),docid))
        return docid
    with db() as c:
        c.executemany("INSERT OR IGNORE INTO sections VALUES(?,?,?)",[(docid,l,t) for l,t in sections])
        c.execute("UPDATE documents SET status='ready',error=NULL WHERE id=?",(docid,))
    return docid

def rows(c,sql,args=()):
    return [dict(row) for row in c.execute(sql,args)]

def snapshot():
    with db() as c:
        return {
            "documents":rows(c,"SELECT id,name,created,status,error,(SELECT count(*) FROM sections s WHERE s.document=d.id) AS sections,(SELECT count(*) FROM processed p WHERE p.document=d.id) AS indexed,(SELECT count(*) FROM chapter_done p WHERE p.document=d.id) AS chapters_done FROM documents d ORDER BY created DESC"),
            "nodes":rows(c,"SELECT * FROM nodes ORDER BY name"),
            "placements":rows(c,"SELECT * FROM placements"),
            "sources":rows(c,"SELECT s.*,d.name AS document_name FROM sources s JOIN documents d ON s.document=d.id"),
            "connections":rows(c,"SELECT * FROM connections"),
            "collections":rows(c,"SELECT * FROM collections ORDER BY name"),
            "document_collections":rows(c,"SELECT * FROM document_collections"),
            "study_materials":rows(c,"SELECT * FROM study_materials"),
            "decks":rows(c,"SELECT * FROM decks ORDER BY name"),
            "cards":rows(c,"SELECT * FROM cards ORDER BY rowid")
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
        # A daily snapshot protects already-paid-for AI work without creating a
        # full copy for every small batch.
        day=datetime.now(timezone.utc).strftime("%Y%m%d")
        if not any((DATA/"backups").glob(f"{day}-*-before-index.sqlite")):
            backup_db(c,"before-index")
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
        if "roadmap" in payload:
            practice.save_roadmap(c,doc,payload["roadmap"],labels)
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
    def send_file(self,path,typ,disposition):
        size=path.stat().st_size
        start,end=0,size-1
        requested=self.headers.get("Range")
        if requested:
            m=re.fullmatch(r"bytes=(\d*)-(\d*)",requested)
            if not m or not any(m.groups()) or not size:
                self.send_response(416);self.send_header("Content-Range",f"bytes */{size}");self.end_headers();return
            a,b=m.groups()
            if not a:start=max(0,size-int(b))
            else:start=int(a);end=min(end,int(b)) if b else end
            if not 0<=start<=end<size:
                self.send_response(416);self.send_header("Content-Range",f"bytes */{size}");self.end_headers();return
        self.send_response(206 if requested else 200)
        self.send_header("Content-Type",typ)
        self.send_header("Content-Length",str(max(0,end-start+1)))
        self.send_header("Accept-Ranges","bytes")
        if requested:self.send_header("Content-Range",f"bytes {start}-{end}/{size}")
        self.send_header("Content-Disposition",f"{disposition}; filename*=UTF-8''{quote(path.name)}")
        self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("Cache-Control","no-store")
        self.end_headers()
        with path.open("rb") as file:
            file.seek(start);remaining=end-start+1
            try:
                while remaining>0:
                    chunk=file.read(min(remaining,1024*1024))
                    if not chunk:break
                    self.wfile.write(chunk);remaining-=len(chunk)
            except (BrokenPipeError,ConnectionResetError):pass
    def do_GET(self):
        if not self.valid_host():
            return self.send({"error":"Local access only"},status=403)
        u=urlparse(self.path)
        if u.path=="/api/atlas":
            return self.send(snapshot())
        if u.path=="/api/later":
            with db() as c:return self.send(later.state(c))
        if u.path=="/api/practice":
            with db() as c:return self.send(practice.state(c))
        if u.path=="/api/chapters":
            doc=parse_qs(u.query).get("id",[""])[0]
            with db() as c:return self.send(practice.chapter_roadmap(c,doc))
        if u.path=="/api/reader":
            try:
                return self.send(reader_document(parse_qs(u.query).get("id",[""])[0]))
            except ValueError as exc:
                return self.send({"error":str(exc)},status=404)
        if u.path=="/api/cover":
            cover=material_cover(parse_qs(u.query).get("id",[""])[0])
            if cover is None:return self.send({"error":"Cover unavailable"},status=404)
            return self.send_file(cover,mimetypes.guess_type(cover.name)[0] or "image/png","inline")
        if u.path=="/api/original":
            with db() as c:
                d=c.execute("SELECT * FROM documents WHERE id=?",(parse_qs(u.query).get("id",[""])[0],)).fetchone()
            if not d: return self.send({"error":"Not found"},status=404)
            p=DATA/d["original"]
            typ=mimetypes.guess_type(p.name)[0] or "application/octet-stream"
            if p.suffix.lower() in {".md",".markdown",".txt",".html",".htm"}: typ="text/plain; charset=utf-8"
            disposition="inline" if p.suffix.lower() in ({".pdf"}|MEDIA) else "attachment"
            return self.send_file(p,typ,disposition)
        if u.path in ("/","/app.js","/style.css","/reader.js","/graph.js","/upgrade.css","/library.js","/study.js","/study.css","/practice.js","/practice.css","/gallery.js","/gallery.css","/later.js","/later.css"):
            name="index.html" if u.path=="/" else u.path[1:]
            return self.send((ROOT/"web"/name).read_bytes(),mimetypes.guess_type(name)[0]+"; charset=utf-8")
        self.send({"error":"Not found"},status=404)
    def do_POST(self):
        action=urlparse(self.path).path
        if not self.valid_host() or self.headers.get("Origin")!=f"http://127.0.0.1:{self.server.server_port}" or action not in ("/api/import","/api/highlight","/api/position","/api/collection","/api/transcript","/api/media-position","/api/study","/api/flashcards","/api/practice","/api/later"):
            return self.send({"error":"Request rejected"},status=403)
        try:
            length=int(self.headers.get("Content-Length","0"))
            if action!="/api/import":
                if not 0<length<=(25_000_000 if action=="/api/transcript" else 12000000 if action=="/api/flashcards" else 1000000):
                    raise ValueError("Invalid request size.")
                payload=json.loads(self.rfile.read(length))
                if action=="/api/later":
                    with db() as c:return self.send(later.action(c,payload))
                if action=="/api/practice":
                    with db() as c:return self.send(practice.action(c,payload))
                if action in ("/api/study","/api/flashcards"):
                    with db() as c:return self.send(study.material(c,payload) if action=="/api/study" else study.flashcards(c,payload))
                if action=="/api/collection":return self.send(collection_change(payload))
                if action=="/api/transcript":return self.send(attach_transcript(payload))
                if action=="/api/media-position":
                    seconds=payload["seconds"]
                    if type(seconds) not in (int,float) or not 0<=seconds<=100000000:raise ValueError("Invalid playback position.")
                    with db() as c:
                        if not c.execute("SELECT 1 FROM documents WHERE id=?",(payload["document"],)).fetchone():raise ValueError("Unknown document.")
                        c.execute("INSERT INTO media_positions VALUES(?,?) ON CONFLICT(document) DO UPDATE SET seconds=excluded.seconds",(payload["document"],seconds))
                    return self.send({"ok":True})
                if action=="/api/highlight":
                    if payload.get("action")=="delete":
                        with db() as c:
                            c.execute("DELETE FROM highlights WHERE id=?",(payload["id"],))
                        return self.send({"ok":True})
                    return self.send(save_highlight(payload))
                with db() as c:
                    if not c.execute("SELECT 1 FROM sections WHERE document=? AND label=?",(payload["document"],payload["label"])).fetchone():
                        raise ValueError("Unknown reading position.")
                    c.execute("INSERT INTO reading_positions VALUES(?,?) ON CONFLICT(document) DO UPDATE SET label=excluded.label",(payload["document"],payload["label"]))
                return self.send({"ok":True})
            name=parse_qs(urlparse(self.path).query).get("name",[""])[0]
            if not name or Path(name).name!=name or "\\" in name or Path(name).suffix.lower() not in EXT or not 0<length<=(1024*1024*1024 if Path(name).suffix.lower() in MEDIA else 100*1024*1024):
                raise ValueError("Choose a supported file (text up to 100 MB; media up to 1 GB).")
            INBOX.mkdir(exist_ok=True)
            import tempfile
            with tempfile.TemporaryDirectory(dir=INBOX) as tmp:
                p=Path(tmp)/name
                with p.open("wb") as out:
                    remaining=length
                    while remaining:
                        chunk=self.rfile.read(min(remaining,1024*1024))
                        if not chunk:raise ValueError("Incomplete upload.")
                        out.write(chunk);remaining-=len(chunk)
                docid=ingest(p)
            self.send({"id":docid})
        except Exception as exc:
            self.send({"error":str(exc)},status=400)

def main():
    parser=argparse.ArgumentParser()
    sub=parser.add_subparsers(dest="cmd",required=True)
    serve=sub.add_parser("serve");serve.add_argument("--port",type=int,default=8765);serve.add_argument("--no-browser",action="store_true")
    imp=sub.add_parser("import");imp.add_argument("paths",nargs="*")
    sub.add_parser("pending");sub.add_parser("catalog");sub.add_parser("backup")
    sub.add_parser("roadmap-pending")
    sub.add_parser("later")
    roadmap_context=sub.add_parser("roadmap-context");roadmap_context.add_argument("document")
    roadmap_apply=sub.add_parser("roadmap-apply");roadmap_apply.add_argument("file")
    export=sub.add_parser("export-library");export.add_argument("destination")
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
    elif args.cmd=="backup":
        with db() as c:
            print(backup_db(c))
    elif args.cmd=="export-library":
        import tempfile
        import zipfile
        destination=Path(args.destination).expanduser().resolve()
        if destination.exists() or DATA.resolve() in destination.parents:
            raise ValueError("Choose a new ZIP file outside the data folder.")
        with tempfile.TemporaryDirectory() as tmp:
            safe_db=Path(tmp)/"atlas.sqlite"
            with db() as c, sqlite3.connect(safe_db) as target:
                c.backup(target)
            with zipfile.ZipFile(destination,"x",compression=zipfile.ZIP_DEFLATED,allowZip64=True) as archive:
                archive.write(safe_db,"data/atlas.sqlite")
                for name in ("originals","transcripts"):
                    folder=DATA/name
                    if folder.exists():
                        for p in folder.rglob("*"):
                            if p.is_file() and not p.is_symlink():archive.write(p,"data/"+str(p.relative_to(DATA)))
                if INBOX.exists():
                    for p in INBOX.rglob("*"):
                        if p.is_file() and not p.is_symlink():archive.write(p,"inbox/"+str(p.relative_to(INBOX)))
        print(f"Portable library saved: {destination}")
    elif args.cmd=="read":
        with db() as c:
            print(json.dumps([dict(r) for l in args.labels for r in c.execute("SELECT label,text FROM sections WHERE document=? AND label=?",(args.document,l))],ensure_ascii=False,indent=2))
    elif args.cmd=="apply":
        apply(json.loads(Path(args.file).read_text(encoding="utf-8")));print("Atlas updated.")
    elif args.cmd=="roadmap-pending":
        with db() as c:print(json.dumps(practice.roadmap_pending(c),ensure_ascii=False,indent=2))
    elif args.cmd=="later":
        with db() as c:print(json.dumps(later.state(c),ensure_ascii=False,indent=2))
    elif args.cmd=="roadmap-context":
        with db() as c:print(json.dumps(practice.roadmap_context(c,args.document),ensure_ascii=False,indent=2))
    elif args.cmd=="roadmap-apply":
        payload=json.loads(Path(args.file).read_text(encoding="utf-8"))
        with db() as c:
            doc=payload["document"];labels=payload["sections"]
            pending={x["label"] for x in practice.roadmap_context(c,doc)["unassigned_sections"]}
            if not isinstance(labels,list) or not labels or len(labels)!=len(set(labels)) or not set(labels)<=pending:raise ValueError("Choose only unassigned, indexed source sections.")
            practice.save_roadmap(c,doc,payload["roadmap"],labels)
        print("Material roadmap saved without re-indexing knowledge.")

if __name__=="__main__":
    main()
