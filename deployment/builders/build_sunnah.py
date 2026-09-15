#!/usr/bin/env python3
"""Pack 2 — build the 9 `sunnah_<coll>.db` + `scholars.db` from the donor
SQLite mirrors (data-api inventory/hadiths/*.db, which are 1:1 of the
SunnahApp deliverable.proto). Donor-authoritative; FTS5 is an external-content
DERIVED index over the matn text (ar+en), never canonical.

- Copies every relational table verbatim (incl. hadith_grades as-is — the empty
  grades in Bukhari/Muslim/etc. are correct: those are all-authentic collections).
- Adds pragmatic query indexes (no source indexes existed).
- Builds hadith_text(hadith_id, lang, matn) from hadith_contents.blocks_json and
  an external-content fts5 index over it.
"""
import sqlite3, os, json, sys

SRC = "/home/kaizen/AndroidStudioProjects/khushu-data-api/archive/inventory/hadiths"
OUT = os.path.join(os.path.dirname(__file__), "..", "..", "data", "build")
COLLS = ["bukhari","muslim","abudawud","tirmidhi","nasai","ibnmajah","malik","riyadussalihin","forty"]

REL_TABLES = ["collections","collection_translations","books","book_translations",
    "chapters","chapter_translations","hadiths","hadith_contents","hadith_references",
    "hadith_related","hadith_grades","hadith_narrators","bundle_meta"]

def matn_text(blocks_json):
    try: blocks = json.loads(blocks_json)
    except Exception: return ""
    return " ".join(b.get("text","").strip() for b in blocks
                    if b.get("type")=="matn" and b.get("text","").strip())

def build_collection(coll):
    src_path = f"{SRC}/{coll}.db"
    dst_path = f"{OUT}/sunnah_{coll}.db"
    if os.path.exists(dst_path): os.remove(dst_path)
    dst = sqlite3.connect(dst_path)
    src = sqlite3.connect(f"file:{src_path}?mode=ro", uri=True)
    copied = {}
    for t in REL_TABLES:
        ddl = src.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (t,)).fetchone()
        if not ddl or not ddl[0]:
            continue
        dst.execute(ddl[0])
        rows = src.execute(f'SELECT * FROM "{t}"').fetchall()
        if rows:
            cols = "?, "*0  # placeholder
            col_names = [d[0] for d in src.execute(f'SELECT * FROM "{t}" LIMIT 0').description]
            ph = ",".join("?"*len(col_names))
            dst.executemany(f'INSERT INTO "{t}" VALUES ({ph})', rows)
        copied[t] = len(rows)
    # query indexes
    for sql in [
        "CREATE INDEX IF NOT EXISTS ix_hadiths_book ON hadiths(book_id)",
        "CREATE INDEX IF NOT EXISTS ix_hadiths_chapter ON hadiths(chapter_id)",
        "CREATE INDEX IF NOT EXISTS ix_hadiths_num ON hadiths(collection_id, CAST(number AS INTEGER))",
        "CREATE INDEX IF NOT EXISTS ix_contents_hid ON hadith_contents(hadith_id)",
        "CREATE INDEX IF NOT EXISTS ix_narr_hid ON hadith_narrators(hadith_id)",
        "CREATE INDEX IF NOT EXISTS ix_grade_hid ON hadith_grades(hadith_id)",
    ]:
        dst.execute(sql)
    # derived search text + FTS5 external-content
    dst.execute("CREATE TABLE hadith_text(hadith_id TEXT, lang TEXT, matn TEXT, PRIMARY KEY(hadith_id,lang))")
    dst.executemany("INSERT INTO hadith_text VALUES(?,?,?)",
        [(hid,lang,matn_text(bj)) for hid,lang,bj in src.execute("SELECT hadith_id,lang,blocks_json FROM hadith_contents")])
    dst.execute("CREATE VIRTUAL TABLE hadith_fts USING fts5(matn, content='hadith_text', "
                "content_rowid='rowid', tokenize='unicode61')")
    dst.execute("INSERT INTO hadith_fts(rowid, matn) SELECT rowid, matn FROM hadith_text WHERE matn<>''")
    dst.execute("PRAGMA user_version=1")
    dst.commit()
    res = verify_collection(coll, src, dst, copied)
    src.close(); dst.close()
    return res

def verify_collection(coll, src, dst, copied):
    ok = True
    # exact row parity for every table vs source
    for t,n in copied.items():
        g = dst.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0]
        if g != n: ok=False; print(f"  MISMATCH {coll}.{t}: {g} vs {n}")
    # grades parity (the flagged concern): db must equal source, incl. 0 where expected
    gs = src.execute("select count(*) from hadith_grades").fetchone()[0]
    gd = dst.execute("select count(*) from hadith_grades").fetchone()[0]
    # text fidelity: compare a matn text sample src vs dst-derived
    hid = dst.execute("select hadith_id from hadith_text where matn<>'' and lang='ar' limit 1").fetchone()
    same = True
    if hid:
        s = src.execute("select blocks_json from hadith_contents where hadith_id=? and lang='ar'",(hid[0],)).fetchone()[0]
        same = (matn_text(s) == dst.execute("select matn from hadith_text where hadith_id=? and lang='ar'",(hid[0],)).fetchone()[0])
    fts = dst.execute("select count(*) from hadith_fts").fetchone()[0]
    n_hadith = copied.get("hadiths",0)
    n_grade_h = dst.execute("select count(distinct hadith_id) from hadith_grades").fetchone()[0]
    print(f"  {coll:14s} tables={len(copied)} hadiths={n_hadith} grades={gd}(src {gs}) grad-hadiths={n_grade_h} fts_rows={fts} text={'OK' if same else 'DIFF'}")
    ok &= (gs==gd and same)
    return ok

def build_scholars():
    src = sqlite3.connect(f"file:{SRC}/scholars_info.db?mode=ro", uri=True)
    if os.path.exists(f"{OUT}/scholars.db"): os.remove(f"{OUT}/scholars.db")
    dst = sqlite3.connect(f"{OUT}/scholars.db")
    ddl = src.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='scholars'").fetchone()[0]
    dst.execute(ddl)
    rows = src.execute("SELECT * FROM scholars").fetchall()
    cols = [d[0] for d in src.execute("SELECT * FROM scholars LIMIT 0").description]
    dst.executemany(f"INSERT INTO scholars VALUES ({','.join('?'*len(cols))})", rows)
    dst.execute("CREATE INDEX IF NOT EXISTS ix_scholars_rank ON scholars(rank)")
    dst.commit()
    s=src.execute("select count(*) from scholars").fetchone()[0]
    d=dst.execute("select count(*) from scholars").fetchone()[0]
    print(f"  scholars      rows={d} (src {s}) text={'OK' if s==d else 'DIFF'}")
    src.close(); dst.close(); return s==d

def main():
    os.makedirs(OUT, exist_ok=True)
    allok = True
    for c in COLLS:
        allok &= build_collection(c)
    allok &= build_scholars()
    print("\nRESULT:", "ALL VERIFIED" if allok else "FAILURES ABOVE")
    sys.exit(0 if allok else 1)

if __name__ == "__main__":
    main()
