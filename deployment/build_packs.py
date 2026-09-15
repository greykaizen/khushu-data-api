#!/usr/bin/env python3
"""Slice 1 — pack-fragment builder.

The 6 Turso DBs are the *query* topology; the *offline download unit* is a
pack/collection/book/language. This emits **versioned, self-contained pack-level
SQLite files** (data/packs/*.db) derived from data/db/*.db, so "download this
translation / tafsir-book / hadith-collection / wbw-language" never has to fetch a
whole 188 MB DB, and the same files serve as the APK pre-bundle.

Principles
- Same table names as the master (no re-prefix): identical SQL runs against a local
  fragment OR the Turso remote. Fragments keep the master's rowids so external-content
  FTS stays consistent and joins are stable.
- FTS is rebuilt per fragment: external-content tables via ('rebuild'); contentless
  tables (translation_fts, dua_fts) by re-populating from the filtered base.
- Binary blobs are NOT here (they're the GH asset releases); the small `assets`
  registry rides inside content/quran-core so asset_id resolution works offline.
- Deterministic given data/db. Emitted + hashed into data/manifest/packs.json.

Tiers (consumption contract for the app):
  prebundle  -> shipped in the APK (content, audio, quran-core, en_sahih translation)
  first_run  -> fetched on first launch (wbw english)
  on_demand  -> user-initiated download from GH releases
"""
import sqlite3, os, re, sys, json, hashlib, glob
from collections import OrderedDict

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DB   = os.path.join(ROOT, "data", "db")
PACKS= os.path.join(ROOT, "data", "packs")
MANIFEST = os.path.join(ROOT, "data", "manifest", "packs.json")
VERSION = "v2026.09"
USER_VERSION = 202609
TAG = re.compile(r"<[^>]+>")

COLLS = ["bukhari","muslim","abu_dawud","tirmidhi","nasai","ibn_majah","malik","riyadussalihin","forty"]
# tables excluded from quran-core (the translation bulk, delivered as its own packs)
QURAN_NON_CORE_PREFIX = ("translation_",)
PREBUNDLE_PACKS = {"en_saheeh-international"}
FIRST_RUN = {"wbw-en"}

def _sha(path):
    h = hashlib.sha256()
    with open(path,"rb") as f:
        for b in iter(lambda: f.read(1<<20), b""): h.update(b)
    return h.hexdigest()

def _connect(name):
    return sqlite3.connect(os.path.join(DB, name))

def _copy_tables_ddl(frag, master, tables):
    """Create table DDL (verbatim, same names) + non-FTS indexes in the fragment."""
    for t in tables:
        row = master.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (t,)).fetchone()
        if not row: sys.exit(f"missing table {t}")
        frag.execute(row[0])
    for t in tables:
        for (idxsql,) in master.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name=? AND sql IS NOT NULL", (t,)):
            try: frag.execute(idxsql)
            except Exception as e: print(f"   idx skip {t}: {e}")

def _copy_rows(frag, master, table, where=None, params=()):
    cols = [c[1] for c in master.execute(f"PRAGMA table_info('{table}')")]
    quoted = ",".join(chr(34)+c+chr(34) for c in cols)
    has_rowid = master.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? AND sql NOT LIKE '%WITHOUT ROWID%'",(table,)).fetchone()
    w = f" WHERE {where}" if where else ""
    if has_rowid:
        frag.execute(f'INSERT INTO "{table}"(rowid,{quoted}) SELECT rowid,{quoted} FROM src."{table}"{w}', params)
    else:
        frag.execute(f'INSERT INTO "{table}"({quoted}) SELECT {quoted} FROM src."{table}"{w}', params)
    return frag.execute('SELECT changes()').fetchone()[0]

def _new_frag(pid, masterfile=None):
    os.makedirs(PACKS, exist_ok=True)
    path = os.path.join(PACKS, pid + ".db")
    if os.path.exists(path): os.remove(path)
    f = sqlite3.connect(path); f.execute("PRAGMA user_version=%d" % USER_VERSION)
    if masterfile:
        f.execute("ATTACH DATABASE ? AS src", (os.path.join(DB, masterfile),))
    return path, f

def _finish(path, f, tables, fts):
    f.commit(); f.execute("VACUUM"); 
    ic = f.execute("PRAGMA integrity_check").fetchone()[0]
    f.close()
    return ic, tables, fts

def list_fts(master):
    rows=master.execute("SELECT name,sql FROM sqlite_master WHERE type='table' AND sql LIKE '%fts5%' AND name NOT LIKE 'sqlite_%'").fetchall()
    return [n for n,s in rows if "fts5" in (s or "").lower()]

def list_non_fts_tables(master):
    fts=list_fts(master)
    shadows=set()
    for name in fts:
        for suf in ("data","idx","docsize","config","content"):
            shadows.add(f"{name}_{suf}")
    rows = master.execute("SELECT name,sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()
    return [n for n,s in rows if "fts5" not in (s or "").lower() and n not in shadows]

def fts_ddl(master, name):
    return master.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()[0]

# ---------------------------------------------------------------- builders
def build_content():
    MF="khushu-content.db"; m=_connect(MF); pid="content"
    tables=list_non_fts_tables(m)
    path,f=_new_frag(pid,MF); _copy_tables_ddl(f,m,tables)
    for t in tables: _copy_rows(f,m,t)
    fts=list_fts(m); built=[]
    for ft in fts:
        f.execute(fts_ddl(m,ft)); built.append(ft)
        # dua_fts is contentless(text) keyed to dua_items.id
        if ft=="dua_fts":
            for rid,ti,tr,tx in f.execute("SELECT id,title,translation,transliteration FROM dua_items"):
                f.execute("INSERT INTO dua_fts(rowid,text) VALUES(?,?)",(rid," ".join(x for x in (ti,tr,tx) if x)))
    ic,tb,fb=_finish(path,f,tables,built); return _pack(pid,"content","khushu-content.db",tb,fb,"prebundle",path,ic)

def build_audio():
    MF="khushu-audio.db"; m=_connect(MF); pid="audio"
    tables=list_non_fts_tables(m)
    path,f=_new_frag(pid,MF); _copy_tables_ddl(f,m,tables)
    for t in tables: _copy_rows(f,m,t)
    ic,tb,fb=_finish(path,f,tables,[]); return _pack(pid,"audio","khushu-audio.db",tb,fb,"prebundle",path,ic)

def build_quran_core():
    MF="khushu-quran.db"; m=_connect(MF); pid="quran-core"
    tables=[t for t in list_non_fts_tables(m) if not t.startswith(QURAN_NON_CORE_PREFIX)]
    path,f=_new_frag(pid,MF); _copy_tables_ddl(f,m,tables)
    for t in tables: _copy_rows(f,m,t)
    built=[]
    # external-content fts (arabic on quran_search_arabic.ayah_id ; alias on aliases.id)
    for ft,content,rowid,col in [("quran_arabic_fts","quran_search_arabic","ayah_id","text"),
                                 ("quran_surah_alias_fts","quran_surah_search_aliases","id","alias")]:
        if ft in list_fts(m):
            f.execute(f"CREATE VIRTUAL TABLE \"{ft}\" USING fts5({col}, content='{content}', content_rowid='{rowid}', tokenize='unicode61')")
            f.execute(f"INSERT INTO \"{ft}\"(\"{ft}\") VALUES('rebuild')"); built.append(ft)
    ic,tb,fb=_finish(path,f,tables,built); return _pack(pid,"quran-core","khushu-quran.db",tb,fb,"prebundle",path,ic)

def build_translation_packs():
    MF="khushu-quran.db"; m=_connect(MF)
    packs=[r[0] for r in m.execute("SELECT pack_id FROM translation_packs ORDER BY pack_id")]
    out=[]
    for pk in packs:
        pid=f"translation-{pk}"
        path,f=_new_frag(pid,MF)
        _copy_tables_ddl(f,m,["translation_packs","translation_ayahs","translation_footnotes"])
        _copy_rows(f,m,"translation_packs","pack_id=?", (pk,))
        # preserve global rowids so translation_fts rowid->verse join is stable within the file
        _copy_rows(f,m,"translation_ayahs","pack_id=?", (pk,))
        _copy_rows(f,m,"translation_footnotes","pack_id=?", (pk,))
        # contentless fts, repopulated for THIS pack (strip html), keyed to translation_ayahs.rowid
        f.execute("CREATE VIRTUAL TABLE translation_fts USING fts5(plain, content='', tokenize='unicode61')")
        for rid,tr in f.execute("SELECT rowid,translation FROM translation_ayahs"):
            f.execute("INSERT INTO translation_fts(rowid,plain) VALUES(?,?)",(rid,TAG.sub("",tr or "")))
        tier = "prebundle" if pk in PREBUNDLE_PACKS else "on_demand"
        ic,tb,fb=_finish(path,f,["translation_packs","translation_ayahs","translation_footnotes"],["translation_fts"])
        out.append(_pack(pid,"translation","khushu-quran.db",tb,fb,tier,path,ic,detail={"pack_id":pk}))
    return out

def build_wbw_packs():
    MF="khushu-wbw.db"; m=_connect(MF)
    langs=[r[0] for r in m.execute("SELECT DISTINCT lang_code FROM wbw_packs ORDER BY lang_code")]
    out=[]
    for lg in langs:
        pid=f"wbw-{lg}"; path,f=_new_frag(pid,MF)
        _copy_tables_ddl(f,m,["wbw_packs","wbw_words"])
        _copy_rows(f,m,"wbw_packs","lang_code=?",(lg,))
        _copy_rows(f,m,"wbw_words","lang_code=?",(lg,))
        tier="first_run" if pid in FIRST_RUN else "on_demand"
        ic,tb,fb=_finish(path,f,["wbw_packs","wbw_words"],[])
        out.append(_pack(pid,"wbw","khushu-wbw.db",tb,fb,tier,path,ic,detail={"lang":lg}))
    return out

def build_tafsir_packs():
    MF="khushu-tafsir.db"; m=_connect(MF)
    books=[r[0] for r in m.execute("SELECT slug FROM tafsir_books ORDER BY slug")]
    out=[]
    for slug in books:
        pid=f"tafsir-{slug}"; path,f=_new_frag(pid,MF)
        _copy_tables_ddl(f,m,["tafsir_books","tafsir_entries"])
        _copy_rows(f,m,"tafsir_books","slug=?",(slug,))
        _copy_rows(f,m,"tafsir_entries","book=?",(slug,))
        ic,tb,fb=_finish(path,f,["tafsir_books","tafsir_entries"],[])
        out.append(_pack(pid,"tafsir","khushu-tafsir.db",tb,fb,"on_demand",path,ic,detail={"book":slug}))
    return out

def build_hadith_packs():
    MF="khushu-hadith.db"; m=_connect(MF); out=[]
    for coll in COLLS:
        pid=f"hadith-{coll}"; path,f=_new_frag(pid,MF)
        tabs=[t for t in list_non_fts_tables(m) if t.startswith(coll+"_")]
        _copy_tables_ddl(f,m,tabs)
        for t in tabs: _copy_rows(f,m,t)
        built=[]
        ft=f"{coll}_hadith_fts"
        if ft in list_fts(m):
            f.execute(f"CREATE VIRTUAL TABLE \"{ft}\" USING fts5(matn, content='{coll}_hadith_text', tokenize='unicode61')")
            f.execute(f"INSERT INTO \"{ft}\"(\"{ft}\") VALUES('rebuild')"); built.append(ft)
        ic,tb,fb=_finish(path,f,tabs,built)
        out.append(_pack(pid,"hadith","khushu-hadith.db",tb,fb,"on_demand",path,ic,detail={"collection":coll}))
    # shared narrator-bio table (cross-collection) as its own lazy pack
    pid="hadith-scholars"; path,f=_new_frag(pid,MF)
    _copy_tables_ddl(f,m,["scholars"]); _copy_rows(f,m,"scholars")
    ic,tb,fb=_finish(path,f,["scholars"],[])
    out.append(_pack(pid,"hadith","khushu-hadith.db",tb,fb,"on_demand",path,ic,detail={"component":"scholars"}))
    return out

def _pack(pid,family,origin,tables,fts,tier,path,ic,detail=None):
    st=os.stat(path); 
    assert ic=="ok", f"{pid} integrity={ic}"
    return OrderedDict(id=pid,family=family,origin_db=origin,tier=tier,tables=tables,fts=fts,
                       file=os.path.basename(path),bytes=st.st_size,sha256=_sha(path),
                       version=VERSION,**({"detail":detail} if detail else {}))

def main():
    packs=[]
    packs.append(build_content())
    packs.append(build_audio())
    packs.append(build_quran_core())
    packs += build_translation_packs()
    packs += build_wbw_packs()
    packs += build_tafsir_packs()
    packs += build_hadith_packs()
    by_tier={"prebundle":0,"first_run":0,"on_demand":0}
    for p in packs: by_tier[p["tier"]]+=p["bytes"]
    man=OrderedDict(version=VERSION,user_version=USER_VERSION,
        pack_url_template="https://github.com/greykaizen/khushu-data-api/releases/download/packs-{family}-"+VERSION+"/{file}",
        total_packs=len(packs), total_bytes=sum(p["bytes"] for p in packs),
        tier_bytes={k:v for k,v in by_tier.items()},
        prebundle_ids=[p["id"] for p in packs if p["tier"]=="prebundle"],
        first_run_ids=[p["id"] for p in packs if p["tier"]=="first_run"],
        packs=packs)
    os.makedirs(os.path.dirname(MANIFEST),exist_ok=True)
    json.dump(man,open(MANIFEST,"w"),indent=1,ensure_ascii=False)
    MB=1048576
    print(f"built {len(packs)} packs -> {PACKS}")
    print(f"  prebundle = {by_tier['prebundle']/MB:.1f} MB  ({', '.join(man['prebundle_ids'])})")
    print(f"  first_run = {by_tier['first_run']/MB:.1f} MB  ({', '.join(man['first_run_ids'])})")
    print(f"  on_demand = {by_tier['on_demand']/MB:.1f} MB  across {sum(1 for p in packs if p['tier']=='on_demand')} packs")
    print(f"  total     = {man['total_bytes']/MB:.1f} MB")
    floor=by_tier["prebundle"]/MB
    assert 30 < floor < 45, f"prebundle floor off: {floor:.1f} MB (expected ~37.6)"
    print(f"  prebundle floor check OK (~{floor:.1f} MB)")

if __name__=="__main__":
    main()
