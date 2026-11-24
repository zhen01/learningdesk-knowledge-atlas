"""Additive study metadata and flashcard storage; never changes atlas rows."""
import csv
import io
import json
import hashlib
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

def schema(c):
    c.executescript("""
    CREATE TABLE IF NOT EXISTS study_materials(document TEXT PRIMARY KEY,title TEXT NOT NULL DEFAULT '',completed INTEGER NOT NULL DEFAULT 0,note TEXT NOT NULL DEFAULT '',progress REAL NOT NULL DEFAULT 0,location TEXT NOT NULL DEFAULT '');
    CREATE TABLE IF NOT EXISTS decks(id TEXT PRIMARY KEY,name TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS cards(id TEXT PRIMARY KEY,deck TEXT NOT NULL,front TEXT NOT NULL,back TEXT NOT NULL,known INTEGER NOT NULL DEFAULT 0);
    """)

def material(c,p):
    doc=p["document"]
    if not c.execute("SELECT 1 FROM documents WHERE id=?",(doc,)).fetchone():raise ValueError("Unknown material.")
    c.execute("INSERT OR IGNORE INTO study_materials(document) VALUES(?)",(doc,))
    for field in ("title","note","completed","progress","location"):
        if field not in p:continue
        v=p[field]
        if field in ("title","note","location"):
            if not isinstance(v,str) or len(v)>(50000 if field=="note" else 300):raise ValueError("Invalid text.")
        elif field=="completed":
            if type(v) is not bool:raise ValueError("Invalid completion.")
            v=int(v)
        elif type(v) not in (int,float) or not 0<=v<=1:raise ValueError("Invalid progress.")
        c.execute("UPDATE study_materials SET "+field+"=? WHERE document=?",(v,doc))
    return dict(c.execute("SELECT * FROM study_materials WHERE document=?",(doc,)).fetchone())

def deck_id(s):return hashlib.sha256(s.encode()).hexdigest()[:24]

def flashcards(c,p):
    action=p.get("action")
    if action=="review":
        if type(p.get("known")) is not bool:raise ValueError("Invalid review.")
        if not c.execute("UPDATE cards SET known=? WHERE id=?",(int(p["known"]),p["id"])).rowcount:raise ValueError("Unknown card.")
        return {"ok":True}
    name=p.get("name","").strip()
    if not 1<=len(name)<=100:raise ValueError("Enter a deck name.")
    text=p.get("text","")
    if not isinstance(text,str) or not text.strip() or len(text)>2_000_000:raise ValueError("Choose a CSV, TSV or JSON deck.")
    if p.get("format")=="json":
        raw=json.loads(text)
        if not isinstance(raw,list):raise ValueError("JSON must be an array of front/back objects.")
        pairs=[(x["front"],x["back"]) for x in raw]
    else:
        rows=list(csv.reader(io.StringIO(text),delimiter="\t" if p.get("format")=="tsv" else ","))
        if rows and len(rows[0])>=2 and rows[0][0].strip().lower() in ("front","question","term") and rows[0][1].strip().lower() in ("back","answer","definition"):rows=rows[1:]
        if any(len(r)!=2 for r in rows if r):raise ValueError("Use two columns: Front, Back.")
        pairs=[tuple(r) for r in rows if r]
    if not pairs or len(pairs)>10000:raise ValueError("Deck must contain 1–10,000 cards.")
    if any(not isinstance(a,str) or not isinstance(b,str) or not a.strip() or not b.strip() or len(a)>20000 or len(b)>20000 for a,b in pairs):raise ValueError("Each card needs a question and answer.")
    did=deck_id(name.casefold())
    c.execute("INSERT OR IGNORE INTO decks VALUES(?,?)",(did,name))
    before=c.execute("SELECT count(*) FROM cards WHERE deck=?",(did,)).fetchone()[0]
    c.executemany("INSERT OR IGNORE INTO cards(id,deck,front,back) VALUES(?,?,?,?)",[(deck_id(json.dumps([did,a,b],ensure_ascii=False)),did,a,b) for a,b in pairs])
    count=c.execute("SELECT count(*) FROM cards WHERE deck=?",(did,)).fetchone()[0]
    return {"id":did,"added":count-before,"total":count}

def slide_sections(path):
    import re
    ns={"a":"http://schemas.openxmlformats.org/drawingml/2006/main"}
    with zipfile.ZipFile(path) as z:
        names=[n for n in z.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml",n)]
        names.sort(key=lambda n:int(re.search(r"slide(\d+)",n).group(1)))
        sections=[]
        for filename in names:
            if z.getinfo(filename).file_size>8_000_000:raise ValueError("Slide XML too large.")
            root=ET.fromstring(z.read(filename))
            text="\n".join("".join(t.text or "" for t in p.findall(".//a:t",ns)) for p in root.findall(".//a:p",ns))
            if text.strip():sections.append(("Slide "+re.search(r"slide(\d+)",filename).group(1),text))
        return sections
