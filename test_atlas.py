import tempfile
import unittest
from pathlib import Path
import atlas

class AtlasTest(unittest.TestCase):
    def test_practice_and_chapter_checklist(self):
        import practice
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);atlas.DATA=root/"data";p=root/"book.md"
            p.write_text("# Chapter 1\nSQL joins match rows.\n# Chapter 2\nWindow functions rank rows.")
            doc=atlas.ingest(p)
            before=atlas.snapshot()
            labels=[x["label"] for x in atlas.pending()]
            atlas.apply({"document":doc,"sections":labels,"concepts":[],"connections":[]})
            with atlas.db() as c:
                roadmap=practice.chapter_roadmap(c,doc)
                self.assertEqual(roadmap["groups"],[])
                self.assertEqual(roadmap["pending"],2)
                label=labels[0]
                practice.action(c,{"action":"chapter","document":doc,"labels":[label],"done":True})
                self.assertEqual(practice.chapter_roadmap(c,doc)["completed"],1)
                self.assertEqual(len(practice.roadmap_context(c,doc)["unassigned_sections"]),2)
                practice.save_roadmap(c,doc,[{"module":"joins","title":"Relational joins","goal":"Understand row matching.","labels":[labels[0]]},{"module":"windows","title":"Window functions","goal":"Understand row ranking.","labels":[labels[1]]}],labels)
                roadmap=practice.chapter_roadmap(c,doc)
                self.assertEqual([g["title"] for g in roadmap["groups"]],["Relational joins","Window functions"])
                self.assertTrue(roadmap["groups"][0]["done"])
                self.assertFalse(roadmap["groups"][1]["done"])
                self.assertEqual(practice.roadmap_pending(c),[])
                for p in practice.PROBLEMS:
                    result=practice.run_problem(c,{"problem":p["id"],"code":p["solution"]})
                    self.assertTrue(result["passed"],result)
                result=practice.run_problem(c,{"problem":"py-dedup","code":"def solve(items):\n    return []"})
                self.assertFalse(result["passed"])
                self.assertEqual(practice.state(c)["mistake_notes"][0]["problem"],"py-dedup")
                practice.action(c,{"action":"plan","track":"Data Engineering","start":"2026-11-24","days":14,"minutes":45})
                practice.action(c,{"action":"topic","track":"Data Engineering","topic":"SQL joins and grain","done":True})
                self.assertEqual(practice.state(c)["plan"]["days"],14)
            after=atlas.snapshot()
            for key in ("nodes","sources","connections","placements"):
                self.assertEqual(before[key],after[key])
            self.assertEqual(after["documents"][0]["chapters_done"],1)
    def test_index_can_save_roadmap_atomically(self):
        import practice
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);atlas.DATA=root/"data";p=root/"material.txt";p.write_text("Understanding how grouped queries summarize data.")
            doc=atlas.ingest(p);labels=[x["label"] for x in atlas.pending()]
            invalid={"document":doc,"sections":labels,"concepts":[],"connections":[],"roadmap":[{"module":"agg","title":"Aggregation","labels":["not a real label"]}]}
            with self.assertRaises(ValueError):atlas.apply(invalid)
            self.assertEqual([x["label"] for x in atlas.pending()],labels)
            atlas.apply({**invalid,"roadmap":[{"module":"agg","title":"Aggregation","goal":"Summarize rows by group.","labels":labels}]})
            with atlas.db() as c:
                self.assertEqual(practice.chapter_roadmap(c,doc)["groups"][0]["title"],"Aggregation")
                self.assertEqual(practice.roadmap_pending(c),[])
    def test_study_metadata_and_deck_reimport(self):
        import study
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);atlas.DATA=root/"data";p=root/"source.txt";p.write_text("A learning resource.");doc=atlas.ingest(p)
            with atlas.db() as c:
                original=c.execute("SELECT name FROM documents WHERE id=?",(doc,)).fetchone()[0]
                study.material(c,{"document":doc,"title":"My title","note":"My note","progress":.4,"completed":True})
                study.material(c,{"document":doc,"progress":.7})
                self.assertEqual(c.execute("SELECT name FROM documents WHERE id=?",(doc,)).fetchone()[0],original)
                payload={"action":"import","name":"Statistics","format":"csv","text":"Front,Back\nWhat is a mean?,An average"}
                self.assertEqual(study.flashcards(c,payload)["added"],1)
                card=c.execute("SELECT id FROM cards").fetchone()[0]
                study.flashcards(c,{"action":"review","id":card,"known":True})
                self.assertEqual(study.flashcards(c,payload)["added"],0)
                self.assertEqual(c.execute("SELECT known FROM cards").fetchone()[0],1)
            record=atlas.reader_document(doc)["study"]
            self.assertEqual((record["title"],record["note"],record["progress"],record["completed"]),("My title","My note",.7,1))
    def test_pptx_text(self):
        import zipfile
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);atlas.DATA=root/"data";p=root/"deck.pptx"
            with zipfile.ZipFile(p,"w") as z:
                z.writestr("ppt/slides/slide1.xml",'<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:p><a:r><a:t>Learning concept</a:t></a:r></a:p></p:sld>')
            doc=atlas.ingest(p)
            self.assertEqual(atlas.reader_document(doc)["sections"],[{"label":"Slide 1","text":"Learning concept"}])
    def test_collections_media_and_incremental_transcripts(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);atlas.DATA=root/"data"
            p=root/"lesson.mp4";p.write_bytes(b"synthetic fixture bytes")
            docid=atlas.ingest(p)
            self.assertEqual(atlas.pending(),[])
            state=atlas.snapshot()
            self.assertEqual(state["documents"][0]["status"],"media")
            self.assertEqual(len(state["collections"]),4)
            c=atlas.collection_change({"action":"create","name":"Interesting ideas"})
            for cid in [c["id"],state["collections"][0]["id"]]:
                atlas.collection_change({"document":docid,"collection":cid,"assigned":True})
            self.assertEqual(len(atlas.snapshot()["document_collections"]),2)
            payload={"document":docid,"name":"lesson.srt","text":"1\n00:01:02,000 --> 00:01:06,000\nA sample transcript about statistics.\n"}
            atlas.attach_transcript(payload)
            self.assertTrue(atlas.attach_transcript(payload)["duplicate"])
            self.assertEqual(len(atlas.pending()),1)
            label=atlas.pending()[0]["label"]
            self.assertIn("@ 00:01:02.000",label)
            atlas.apply({"document":docid,"sections":[label],"concepts":[],"connections":[]})
            self.assertEqual(atlas.pending(),[])
            self.assertEqual(atlas.ingest(p),docid)
            self.assertEqual(atlas.snapshot()["documents"][0]["status"],"complete")
            self.assertEqual((atlas.DATA/"originals"/docid/p.name).read_bytes(),p.read_bytes())
            self.assertEqual(len(atlas.reader_document(docid)["transcripts"]),1)
    def test_structured_parsing(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);atlas.DATA=root/"data"
            for name,content,expected in [("data.csv","metric,value\nretention,0.75","metric: retention"),("data.json",'{"metric":"retention"}','"metric": "retention"'),("page.html","<h1>Learning</h1><script>do_not_execute()</script>","Learning")]:
                path=root/name;path.write_text(content)
                docid=atlas.ingest(path)
                section=atlas.reader_document(docid)["sections"][0]["text"]
                self.assertIn(expected,section)
                self.assertNotIn("do_not_execute",section)
    def test_source_only_update_preserves_data(self):
        import sqlite3
        import update_existing
        with tempfile.TemporaryDirectory() as temp:
            destination=Path(temp)/"existing"
            destination.mkdir()
            (destination/"atlas.py").write_text("# old application")
            (destination/"data"/"originals").mkdir(parents=True)
            (destination/"inbox").mkdir()
            (destination/"inbox"/"personal.txt").write_text("personal material")
            (destination/"data"/"originals"/"source.txt").write_text("saved original")
            database=destination/"data"/"atlas.sqlite"
            with sqlite3.connect(database) as c:
                c.execute("CREATE TABLE concepts(name TEXT)")
                c.execute("INSERT INTO concepts VALUES('Existing concept')")
            original=database.read_bytes()
            backup=update_existing.update(destination)
            self.assertEqual(database.read_bytes(),original)
            self.assertEqual((destination/"inbox"/"personal.txt").read_text(),"personal material")
            self.assertEqual((destination/"data"/"originals"/"source.txt").read_text(),"saved original")
            self.assertTrue((destination/"web"/"reader.js").exists())
            with sqlite3.connect(backup) as c:
                self.assertEqual(c.execute("SELECT name FROM concepts").fetchone()[0],"Existing concept")
    def test_reader_annotations_survive_upgrade_and_indexing(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);atlas.DATA=root/"data"
            p=root/"notes.txt";p.write_text("A 🐱 is an example. Knowledge persists across sessions.",encoding="utf-8")
            docid=atlas.ingest(p)
            label=atlas.pending()[0]["label"]
            # Simulate the pre-reader schema without modifying real user data.
            with atlas.db() as c:
                c.execute("DROP TABLE highlights")
                c.execute("DROP TABLE reading_positions")
            before=atlas.snapshot()
            self.assertEqual(before["documents"][0]["id"],docid)
            backup=next((atlas.DATA/"backups").glob("*before-reader-upgrade.sqlite"))
            with sqlite3.connect(backup) as c:
                self.assertEqual(c.execute("SELECT id FROM documents").fetchone()[0],docid)
            payload={"document":docid,"label":label,"start":2,"end":3,"quote":"🐱","color":"yellow","note":"A personal note."}
            m=atlas.save_highlight(payload)
            self.assertEqual(atlas.reader_document(docid)["highlights"][0]["note"],"A personal note.")
            updated=dict(payload);updated.pop("note");updated["color"]="green"
            self.assertEqual(atlas.save_highlight(updated)["note"],"A personal note.")
            with self.assertRaises(ValueError):atlas.save_highlight({**payload,"quote":"wrong"})
            with atlas.db() as c:c.execute("INSERT INTO reading_positions VALUES(?,?)",(docid,label))
            atlas.apply({"document":docid,"sections":[label],"concepts":[],"connections":[]})
            self.assertEqual(atlas.reader_document(docid)["position"],label)
            self.assertEqual(atlas.reader_document(docid)["highlights"][0]["id"],m["id"])
            self.assertEqual(atlas.ingest(p),docid)
            self.assertEqual(atlas.pending(),[])
    def test_import_merge_evidence_and_persistence(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            atlas.DATA=root/"data"
            a=root/"first.md"
            a.write_text("# Statistics\nRandom assignment reduces confounding in experiments.",encoding="utf-8")
            b=root/"second.txt"
            b.write_text("Random assignment balances confounders across experimental groups. Causal estimates benefit from randomization.",encoding="utf-8")
            ids=[atlas.ingest(p) for p in (a,b)]
            self.assertEqual(atlas.ingest(a),ids[0])
            labels=[x["label"] for x in atlas.pending()]
            def payload(i,name,quote,existing=None):
                return {"document":ids[i],"sections":[labels[i]],"concepts":[{"key":"c1","existing_id":existing,"name":name,"aliases":["Randomization"],"domain":"Statistics","module":"Causal inference","submodule":"Experimental design","explanation":"Assignment by chance helps balance confounders.","label":labels[i],"quote":quote}],"connections":[]}
            bad=payload(0,"Random assignment","This text does not exist.")
            with self.assertRaises(ValueError): atlas.apply(bad)
            self.assertEqual(len(atlas.snapshot()["nodes"]),0)
            atlas.apply(payload(0,"Random assignment","Random assignment reduces confounding in experiments."))
            cid=next(n["id"] for n in atlas.snapshot()["nodes"] if n["kind"]=="concept")
            next_batch=payload(1,"Randomization","Random assignment balances confounders across experimental groups.",cid)
            next_batch["concepts"].append({"key":"c2","name":"Causal estimates","domain":"Statistics","module":"Causal inference","submodule":"Estimation","aliases":[],"explanation":"Quantifies a causal effect.","label":labels[1],"quote":"Causal estimates benefit from randomization."})
            next_batch["connections"].append({"from":"c1","to":"c2","kind":"application","explanation":"Randomized assignment helps identify causal effects.","label":labels[1],"quote":"Causal estimates benefit from randomization."})
            atlas.apply(next_batch)
            result=atlas.snapshot()
            self.assertEqual(len([n for n in result["nodes"] if n["kind"]=="concept"]),2)
            self.assertEqual(len([s for s in result["sources"] if s["concept"]==cid]),2)
            self.assertEqual(len(result["connections"]),1)
            self.assertEqual(atlas.pending(),[])
            self.assertEqual(len(list((atlas.DATA/"originals").glob("*/*"))),2)
            self.assertEqual(atlas.snapshot(),result)
            with self.assertRaises(ValueError): atlas.apply(next_batch)
    def test_parsers(self):
        from docx import Document
        from reportlab.pdfgen.canvas import Canvas
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);atlas.DATA=root/"data"
            docx=root/"notes.docx";d=Document();d.add_paragraph("Data quality means fit for purpose.");d.save(docx)
            pdf=root/"notes.pdf";c=Canvas(str(pdf));c.drawString(70,700,"Data quality means fit for purpose.");c.save()
            for p in (docx,pdf):
                docid=atlas.ingest(p)
                with atlas.db() as conn:
                    text=conn.execute("SELECT text FROM sections WHERE document=?",(docid,)).fetchone()[0]
                self.assertIn("Data quality means fit for purpose.",text)

if __name__=="__main__": unittest.main()
