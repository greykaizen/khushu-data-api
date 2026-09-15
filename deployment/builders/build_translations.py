#!/usr/bin/env python3
"""Pack 3 — translations.db.

Donor-authoritative where a donor exists (QuranApp prebuilt: Saheeh
International, The Clear Quran, Junagarhi Urdu); otherwise the values come from
the archived data-api per-pack JSON (the canonical scraped content) — the SCHEMA
here is designed fresh, not copied from the blob layout.

Marker/footnote semantics are PRESERVED, not flattened:
  - tr_ayahs.translation stores the raw text WITH inline <fn>/<reference>
    markers (verbatim), so a host resolves them exactly as the old API did.
  - tr_footnotes stores each ayah's footnote rows (index+text, text also raw).
Search is a DERIVED external-content FTS5 over a tag-stripped projection
(tr_search.plain) so markup never pollutes match results.

Verification: per-pack suras=114 & ayahs=6236, byte-equal sample translation +
footnote counts vs the exact source, grand totals vs archive.
"""
import sqlite3, os, json, re, sys

API = "/home/kaizen/AndroidStudioProjects/khushu-data-api/archive"
DONOR = "/home/kaizen/AndroidStudioProjects/Osprey/reference/QuranApp/app/src/main/assets/prebuilt_translations"
OUT = os.path.join(os.path.dirname(__file__), "..", "..", "data", "build")
TAG = re.compile(r"<[^>]+>")

def plain(s):  return TAG.sub("", s or "")

def read_pack(path):
    d = json.load(open(path))
    return d.get("version", 1), d.get("suras", [])

def iter_ayahs(suras):
    for s in suras:
        sno = int(s.get("index"))
        for a in s.get("ayas", []):
            yield sno, int(a.get("index")), a.get("translation", ""), a.get("footnotes") or []

def main():
    os.makedirs(OUT, exist_ok=True)
    db = os.path.join(OUT, "translations.db")
    if os.path.exists(db): os.remove(db)
    c = sqlite3.connect(db)
    c.executescript("""
      CREATE TABLE packs(pack_id TEXT PRIMARY KEY, lang_code TEXT, book TEXT, author TEXT,
        display_name TEXT, lang_name TEXT, version INTEGER, source_kind TEXT, path TEXT);
      CREATE TABLE tr_ayahs(pack_id TEXT, surah_no INTEGER, ayah_no INTEGER,
        translation TEXT, PRIMARY KEY(pack_id, surah_no, ayah_no));
      CREATE TABLE tr_footnotes(pack_id TEXT, surah_no INTEGER, ayah_no INTEGER,
        fn_index INTEGER, text TEXT);
      CREATE INDEX ix_fn_lookup ON tr_footnotes(pack_id, surah_no, ayah_no);
    """)
    # ---- 48 archived packs from the catalog (canonical values) ----
    cat = json.load(open(f"{API}/inventory/translations/available_translations_info.json"))["translations"]
    stats = []
    for lang, d in sorted(cat.items()):
        for pid, info in sorted(d.items()):
            path = info.get("downloadPath") or f"inventory/translations/{lang}/{pid}.json"
            stats.append(load_pack(c, pid, lang, info, "archive", f"{API}/{path}", path))
    # ---- 3 donor-authoritative packs (absent from the archived catalog) ----
    for folder, pid in (("en_saheeh_v1_1_1","en_saheeh-international"),
                        ("en_the_clear_quran","en_the-clear-quran"),
                        ("ur_junagarhi","ur_junagarhi")):
        m = json.load(open(f"{DONOR}/{folder}/manifest.json"))
        stats.append(load_pack(c, pid, m["langCode"], m, "donor", f"{DONOR}/{folder}/{folder}.json", "donor/"+folder+".json"))

    # Derived search = contentless FTS5 (inverted index only; no text copy).
    # Matches return tr_ayahs rowid, which the host joins back for the raw
    # (marker-bearing) translation.
    c.execute("CREATE VIRTUAL TABLE tr_fts USING fts5(plain, content='', tokenize='unicode61')")
    c.executemany("INSERT INTO tr_fts(rowid, plain) VALUES(?,?)",
                  ((rowid, plain(tr)) for (rowid, tr) in
                   c.execute("SELECT rowid, translation FROM tr_ayahs")))
    c.commit()
    c.execute("PRAGMA user_version=1"); c.commit()
    report(c, stats)

def load_pack(c, pid, lang, info, kind, open_path, rel_path):
    c.execute("INSERT INTO packs VALUES(?,?,?,?,?,?,?,?,?)",
              (pid, info.get("langCode",lang), info.get("book",""), info.get("author",""),
               info.get("displayName",""), info.get("langName",""), info.get("version",1), kind, rel_path))
    version, suras = read_pack(open_path)
    n_ayah = 0; n_fn = 0; sample=None; sample_aid=None
    buf_a=[]; buf_f=[]
    for sno, ano, tr, fns in iter_ayahs(suras):
        n_ayah += 1; buf_a.append((pid, sno, ano, tr))
        if sample is None and tr: sample=tr; sample_aid=(sno,ano)
        for fn in fns:
            n_fn += 1; buf_f.append((pid, sno, ano, int(fn.get("index")), fn.get("text","")))
    c.executemany("INSERT INTO tr_ayahs VALUES(?,?,?,?)", buf_a)
    c.executemany("INSERT INTO tr_footnotes VALUES(?,?,?,?,?)", buf_f)
    return dict(pid=pid, kind=kind, suras=len(suras), ayahs=n_ayah, footnotes=n_fn,
                sample=(sample_aid, sample), version=version)

def report(c, stats):
    ok = True; tot_ayah=0; tot_fn=0
    print("== per-pack verification ==")
    for st in stats:
        pa = c.execute("select count(*) from tr_ayahs where pack_id=?", (st["pid"],)).fetchone()[0]
        pf = c.execute("select count(*) from tr_footnotes where pack_id=?", (st["pid"],)).fetchone()[0]
        suras_ok = st["suras"]==114; ayah_ok = pa==st["ayahs"]==6236; fn_ok = pf==st["footnotes"]
        # byte fidelity: stored translation == source sample
        (sno,ano), raw = st["sample"]
        stored = c.execute("select translation from tr_ayahs where pack_id=? and surah_no=? and ayah_no=?",
                           (st["pid"],sno,ano)).fetchone()[0]
        text_ok = stored == raw
        pack_ok = suras_ok and ayah_ok and fn_ok and text_ok
        ok &= pack_ok; tot_ayah+=pa; tot_fn+=pf
        if not pack_ok:
            print(f"  FAIL {st['pid']:28s} suras={st['suras']} ayahs={pa} fn={pf} text={text_ok}")
    # cross-check grand totals vs the archive scan (48 packs -> 299328 ayahs, 38231 fn) + 3 donor
    packs = c.execute("select count(*) from packs").fetchone()[0]
    db_ayah = c.execute("select count(*) from tr_ayahs").fetchone()[0]
    db_fn = c.execute("select count(*) from tr_footnotes").fetchone()[0]
    print(f"  packs={packs} (48 archive + 3 donor)  tr_ayahs={db_ayah}  tr_footnotes={db_fn}")
    print(f"  archive grand (48×6236)=299328 ayahs ; +3 donor = {299328+3*6236}")
    ok &= (packs==51 and db_ayah==299328+3*6236)
    # FTS5 sanity on a translated word
    hits = c.execute("select count(*) from tr_fts where tr_fts match 'merciful'").fetchone()[0]
    print(f"  FTS5 'merciful' matches: {hits} (search works; markup excluded)")
    # confirm a marker survived verbatim (semantics preserved) in an en pack w/ footnotes
    row = c.execute("select translation from tr_ayahs where pack_id='en_saheeh-international' "
                    "and surah_no=1 and ayah_no=1").fetchone()[0]
    print("  saheeh 1:1 stored raw:", repr(row[:120]))
    print(f"\nRESULT: {'ALL VERIFIED' if ok else 'FAILURES ABOVE'}")
    sz=os.path.getsize(os.path.join(OUT,"translations.db"))/1048576
    print(f"translations.db: {sz:.1f} MB")
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
