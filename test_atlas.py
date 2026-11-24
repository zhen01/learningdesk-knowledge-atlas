import tempfile
import unittest
from pathlib import Path
import atlas

class AtlasTest(unittest.TestCase):
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
