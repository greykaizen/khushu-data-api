#!/usr/bin/env python3
"""Build quran.db from the AUTHORITATIVE donor DBs (quranapp/page_info/topics).

- Copies every relational table + real indexes verbatim (schema of record).
- Drops the two legacy FTS4 virtual tables and their shadow tables.
- Rebuilds search as **external-content FTS5** (index only, no duplicated text):
    arabic_fts      over search_arabic(ayah_id, normalized_text)  ← arabic_search_content
    surah_alias_fts over surah_search_aliases (surah-name search)
- Renames page_info's generic info/pages -> mushaf_info/mushaf_pages to avoid
  collision and read clearer.

Uses stdlib sqlite3 (has FTS5; pyturso does NOT). Output is plain SQLite that
Turso Cloud/embedded consume unchanged.
"""
import sqlite3, sys, os

REF = "/home/kaizen/AndroidStudioProjects/Osprey/reference/QuranApp/app/src/main/assets/db"
OUT = os.path.join(os.path.dirname(__file__), "..", "..", "data", "build")
DB = os.path.join(OUT, "quran.db")

# donor tables that are FTS implementation detail -> never copied as-is
FTS_DROP_PREFIXES = ("arabic_search", "surah_search_aliases_fts")
RENAMES = {"info": "mushaf_info", "pages": "mushaf_pages"}  # from page_info.db

def is_fts_shadow(name):
    return any(name == p or name.startswith(p + "_") for p in FTS_DROP_PREFIXES)

def copy_table(dst, src_db_alias, src_name, ddl, new_name):
    """Create + bulk-insert one table from an attached donor DB."""
    if new_name != src_name:
        ddl = ddl.replace(f'"{src_name}"', f'"{new_name}"', 1)
        ddl = ddl.replace(f" {src_name} ", f" {new_name} ", 1)
        ddl = ddl.replace(f"{src_name}(", f"{new_name}(", 1)
    dst.execute(ddl)
    dst.execute(f"INSERT INTO main.\"{new_name}\" SELECT * FROM {src_db_alias}.\"{src_name}\"")
    return new_name

def copy_indexes(dst, src_conn, src_tables_map):
    """Copy real (non-auto, non-fts) indexes, remapping renamed tables."""
    for name, sql, tbl in src_conn.execute(
        "SELECT name, sql, tbl_name FROM sqlite_master WHERE type='index' "
        "AND sql IS NOT NULL AND name NOT LIKE 'sqlite_%'"):
        if is_fts_shadow(tbl):
            continue
        new_tbl = src_tables_map.get(tbl, tbl)
        sql = sql.replace(f'"{tbl}"', f'"{new_tbl}"').replace(f" ON {tbl} ", f" ON {new_tbl} ")
        dst.execute(sql)

def main():
    os.makedirs(OUT, exist_ok=True)
    if os.path.exists(DB):
        os.remove(DB)
    dst = sqlite3.connect(DB)
    dst.execute("PRAGMA foreign_keys=OFF")
    dst.execute("ATTACH DATABASE ? AS q", (f"{REF}/quranapp.db",))
    dst.execute("ATTACH DATABASE ? AS p", (f"{REF}/page_info.db",))
    dst.execute("ATTACH DATABASE ? AS t", (f"{REF}/topics.db",))

    maps = {}
    # gather + copy DDL per attached donor db
    for alias, path in (("q", f"{REF}/quranapp.db"), ("p", f"{REF}/page_info.db"), ("t", f"{REF}/topics.db")):
        sc = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        rows = sc.execute("SELECT name, sql FROM sqlite_master WHERE type='table' AND sql IS NOT NULL AND name NOT LIKE 'sqlite_%'").fetchall()
        tmap = {}
        for name, ddl in rows:
            if is_fts_shadow(name):
                continue
            new = RENAMES.get(name, name)
            tmap[name] = new
            copy_table(dst, alias, name, ddl, new)
        copy_indexes(dst, sc, tmap)
        maps.update(tmap)
        sc.close()

    # normalized Arabic search text from the donor FTS4 content table
    dst.execute("CREATE TABLE search_arabic(ayah_id INTEGER PRIMARY KEY, text TEXT NOT NULL)")
    dst.execute("INSERT INTO search_arabic SELECT c0ayah_id, c1text FROM q.arabic_search_content")

    # external-content FTS5 (index only; content lives in the base tables)
    dst.execute("CREATE VIRTUAL TABLE arabic_fts USING fts5(text, "
                "content='search_arabic', content_rowid='ayah_id', tokenize='unicode61')")
    dst.execute("INSERT INTO arabic_fts(rowid, text) SELECT ayah_id, text FROM search_arabic")
    dst.execute("CREATE VIRTUAL TABLE surah_alias_fts USING fts5(alias, "
                "content='surah_search_aliases', content_rowid='id', tokenize='unicode61')")
    dst.execute("INSERT INTO surah_alias_fts(rowid, alias) SELECT id, alias FROM surah_search_aliases")

    # Canonicalize topics.image_url: drop donor ghraw:// URL, reference assets.db
    cols=[r[1] for r in dst.execute("pragma table_info(topics)")]
    if "image_url" in cols:
        rows=dst.execute("select id,image_url from topics where image_url is not null and image_url<>''").fetchall()
        if "image_asset_id" not in cols: dst.execute("ALTER TABLE topics ADD COLUMN image_asset_id TEXT")
        for tid,iu in rows:
            dst.execute("UPDATE topics SET image_asset_id=? WHERE id=?",("images/"+iu.rsplit("/",1)[-1], tid))
        dst.execute("ALTER TABLE topics DROP COLUMN image_url")
    dst.execute("PRAGMA user_version = 1")
    dst.commit()
    verify(dst, maps)
    dst.close()

def verify(dst, maps):
    expect = {"surahs":114,"ayahs":6236,"scripts":5,"mushafs":5,"navigation_ranges":720,
              "similar_verses":3552,"mutashabihat_phrases":814,"mutashabihat_phrase_ayah":3555,
              "surah_search_aliases":37789,"mushaf_info":4,"mushaf_pages":37914,
              "topics":2512,"topic_ayahs":30687,"topic_localizations":3504,"relationships":1749}
    ok = True
    print("== row-count verification ==")
    for tbl, want in expect.items():
        got = dst.execute(f"SELECT count(*) FROM \"{tbl}\"").fetchone()[0]
        flag = "OK" if got == want else "MISMATCH"
        ok &= got == want
        print(f"  {tbl:24s} {got:7d} (want {want:7d}) {flag}")
    uw = dst.execute("SELECT count(*) FROM ayah_words").fetchone()[0]
    ut = dst.execute("SELECT count(*) FROM ayah_words WHERE script_id=1").fetchone()[0]
    mm = dst.execute("SELECT count(*) FROM mushaf_map").fetchone()[0]
    sa = dst.execute("SELECT count(*) FROM search_arabic").fetchone()[0]
    print(f"  ayah_words total={uw} uthmani={ut} (want 334660/83665)")
    print(f"  mushaf_map={mm} (want 35965)  search_arabic={sa}")
    ok &= uw==334660 and ut==83665 and mm==35965

    print("\n== text fidelity (byte compare vs donor) ==")
    d = sqlite3.connect(f"file:{REF}/quranapp.db?mode=ro", uri=True)
    for aid in (1001, 2255, 114001):
        want = "".join((r[0] or "") for r in d.execute(
            "SELECT text FROM ayah_words WHERE script_id=1 AND ayah_id=? ORDER BY word_index",(aid,)))
        got = "".join((r[0] or "") for r in dst.execute(
            "SELECT text FROM ayah_words WHERE script_id=1 AND ayah_id=? ORDER BY word_index",(aid,)))
        same = want==got
        ok &= same
        print(f"  ayah {aid}: {'IDENTICAL' if same else 'DIFF'}  ({len(got)} chars)")
    d.close()

    print("\n== FTS5 sanity (rebuilt) ==")
    for term in ("الرحمن","رحم","ملك"):
        n5 = dst.execute("SELECT count(*) FROM arabic_fts WHERE arabic_fts MATCH ?", (term,)).fetchone()[0]
        print(f"  arabic_fts MATCH {term!r} -> {n5} hits")
    n_alias = dst.execute("SELECT count(*) FROM surah_alias_fts WHERE surah_alias_fts MATCH 'Yusuf'").fetchone()[0]
    print(f"  surah_alias_fts MATCH 'Yusuf' -> {n_alias} hits")

    print(f"\nRESULT: {'ALL VERIFIED' if ok else 'CHECK FAILURES ABOVE'}")
    print(f"quran.db size: {os.path.getsize(DB)/1048576:.1f} MB -> {DB}")
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
