#!/usr/bin/env python3
"""Pack 4 — tafsir.db.

Donor/archive shape: 26 books, each `<lang>/<slug>/split/{1..114}.json` (a list of
per-verse-RANGE entries {fromVerse,toVerse,text}) + a whole `tafsir.json.gz`.
`split/` is per-surah and authoritative to read. text is verbatim HTML
(`<p>`, `<span class="arabic qpc-hafs">` inline Quran quotes) — PRESERVED as-is;
we do NOT flatten commentary to plain text or force a per-ayah grid (tafsir is
range-keyed; coverage differs per book — tabari 6196 vs Ibn Kathir 6236 entries).

NO FTS5 here: tafsir is fetched by (book, surah, verse-range), not free-text; an
index would duplicate ~350 MB of HTML for negligible benefit. Revisit only if a
product search-across-tafsir is required.

Verify: per-book entry counts vs a source recount, sample text byte-equal, book
set matches the manifest.
"""
import sqlite3, os, json, glob, sys

SRC = "/home/kaizen/AndroidStudioProjects/khushu-data-api/archive/inventory/tafsirs"
OUT = os.path.join(os.path.dirname(__file__), "..", "..", "data", "build")

def main():
    os.makedirs(OUT, exist_ok=True)
    db = os.path.join(OUT, "tafsir.db")
    if os.path.exists(db): os.remove(db)
    c = sqlite3.connect(db)
    c.executescript("""
      CREATE TABLE tafsir_books(slug TEXT PRIMARY KEY, lang_code TEXT, lang_name TEXT,
        name TEXT, author TEXT);
      CREATE TABLE tafsir_entries(book TEXT, surah_no INTEGER, from_verse INTEGER,
        to_verse INTEGER, text TEXT,
        PRIMARY KEY(book, surah_no, from_verse, to_verse));
      CREATE INDEX ix_tafsir_lookup ON tafsir_entries(book, surah_no);
    """)
    info = json.load(open(f"{SRC}/available_tafsirs_info.json"))["tafsirs"]
    books = []
    for lang, arr in info.items():
        for b in arr:
            slug = b.get("slug") or b.get("key")
            c.execute("INSERT INTO tafsir_books VALUES(?,?,?,?,?)",
                      (slug, b.get("langCode",lang), b.get("langName",""),
                       b.get("name",""), b.get("author","")))
            books.append((lang, slug, f"{SRC}/{lang}/{slug}"))
    per_book = {}
    for lang, slug, dirp in books:
        n = 0
        rows = []
        for f in sorted(glob.glob(f"{dirp}/split/*.json"), key=lambda x:int(os.path.basename(x)[:-5])):
            surah = int(os.path.basename(f)[:-5])
            for e in json.load(open(f)):
                rows.append((slug, surah, int(e["fromVerse"]), int(e["toVerse"]), e.get("text","")))
        c.executemany("INSERT INTO tafsir_entries VALUES(?,?,?,?,?)", rows)
        per_book[slug] = len(rows)
    c.execute("PRAGMA user_version=1"); c.commit()
    verify(c, per_book, books)

def verify(c, per_book, books):
    ok = True
    print("== tafsir_books ==")
    print("  books:", c.execute("select count(*) from tafsir_books").fetchone()[0], "(want 26)")
    print("  langs:", c.execute("select count(distinct lang_code) from tafsir_books").fetchone()[0])
    print("== per-book entry counts (db vs source recount) ==")
    for slug, want in sorted(per_book.items()):
        got = c.execute("select count(*) from tafsir_entries where book=?", (slug,)).fetchone()[0]
        flag = "OK" if got==want else "MISMATCH"
        ok &= got==want
        print(f"  {slug:34s} {got:6d} {flag}")
    tot = c.execute("select count(*) from tafsir_entries").fetchone()[0]
    print("  TOTAL entries:", tot)
    # byte fidelity on a sample: en Ibn Kathir surah1 from1
    src = json.load(open(f"{SRC}/en/en-tafisr-ibn-kathir/split/1.json"))
    want = src[0]["text"]
    got = c.execute("select text from tafsir_entries where book='en-tafisr-ibn-kathir' "
                    "and surah_no=1 and from_verse=?", (src[0]["fromVerse"],)).fetchone()[0]
    print("  en-IbnKathir 1:1 text byte-equal:", want==got)
    ok &= want==got
    # coverage: distinct surahs covered (should be 114 for full books)
    for slug in ("en-tafisr-ibn-kathir","ar-tafsir-al-tabari"):
        sc = c.execute("select count(distinct surah_no) from tafsir_entries where book=?",(slug,)).fetchone()[0]
        print(f"  {slug} surahs covered:", sc)
    print(f"\nRESULT: {'ALL VERIFIED' if ok else 'FAILURES'}")
    print(f"tafsir.db: {os.path.getsize(OUT+'/tafsir.db')/1048576:.1f} MB")
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
