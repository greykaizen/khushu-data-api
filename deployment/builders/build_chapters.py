#!/usr/bin/env python3
"""data/build/chapters.db — Quran per-surah chapter info (themes/purpose intro)
from archive/inventory/chapters/info/<lang>/<file>.json. 228 rows (en).
Verbatim HTML text preserved; resources[] kept as JSON. Merged into khushu-quran."""
import sqlite3,os,glob,json
SRC="/home/kaizen/AndroidStudioProjects/khushu-data-api/archive/inventory/chapters/info"
OUT=os.path.abspath(os.path.join(os.path.dirname(__file__),"..","..","data","build"))
def main():
    os.makedirs(OUT,exist_ok=True); db=OUT+"/chapters.db"
    if os.path.exists(db): os.remove(db)
    c=sqlite3.connect(db)
    c.executescript("""CREATE TABLE chapter_info(file_key TEXT PRIMARY KEY, chapter_id INTEGER,
      lang_code TEXT, source TEXT, short_text TEXT, text TEXT, resources_json TEXT);
      CREATE INDEX ix_chapter ON chapter_info(chapter_id,lang_code);""")
    rows=[]
    for f in glob.glob(f"{SRC}/*/*.json"):
        d=json.load(open(f)); fk=os.path.relpath(f,SRC).replace(os.sep,"/")
        rows.append((fk,d.get("chapter_id"),d.get("language_code"),d.get("source",""),
                     d.get("short_text",""),d.get("text",""),json.dumps(d.get("resources",[]),ensure_ascii=False)))
    c.executemany("INSERT INTO chapter_info VALUES(?,?,?,?,?,?,?)",rows)
    c.commit()
    got=c.execute("select count(*) from chapter_info").fetchone()[0]
    assert got==228, f"chapters {got}"
    c.close(); print("chapters.db:",got,"rows")
main()
