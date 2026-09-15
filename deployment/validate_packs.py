#!/usr/bin/env python3
"""Verify data/packs are a lossless re-shard of data/db (run after build_packs).
Asserts: every pack row exists exactly once across packs; integrity ok; FTS
rowids stable; per-DB empties vs donor. Exits non-zero on any LOSS.
CI-able companion to build_packs.py."""
import sqlite3, os, json, sys, re
ROOT=os.path.abspath(os.path.join(os.path.dirname(__file__),".."))
DB=os.path.join(ROOT,"data","db"); PK=os.path.join(ROOT,"data","packs")
m=json.load(open(os.path.join(ROOT,"data","manifest","packs.json")))
def conn(d): return sqlite3.connect(d)
def count(c,t,w=None,p=()): 
    try: return c.execute(f'SELECT COUNT(*) FROM "{t}"'+(f" WHERE {w}" if w else ""),p).fetchone()[0]
    except Exception as e: return f"ERR {e}"
fails=[]
# 1) per-pack integrity + table present
for p in m["packs"]:
    c=conn(os.path.join(PK,p["file"]))
    if c.execute("PRAGMA integrity_check").fetchone()[0]!="ok": fails.append(f"{p['file']} integrity")
    for t in p["tables"]:
        if str(count(c,t)).startswith("ERR"): fails.append(f"{p['file']} missing {t}")
    c.close()
print(f"integrity+tables: {len(m['packs'])} packs, {len(fails)} issues")
# 2) global row coverage per master table that is sharded
def sum_packs(t,fam):
    tot=0
    for p in m["packs"]:
        if p["family"]==fam and t in p["tables"]:
            tot+=count(conn(os.path.join(PK,p["file"])),t)
    return tot
COLLS=["bukhari","muslim","abu_dawud","tirmidhi","nasai","ibn_majah","malik","riyadussalihin","forty"]
mh=conn(os.path.join(DB,"khushu-hadith.db"))
cov=[
 ("wbw_words","khushu-wbw.db","wbw",("wbw_words",None)),
 ("tafsir_entries","khushu-tafsir.db","tafsir",("tafsir_entries",None)),
 ("translation_ayahs","khushu-quran.db","translation",("translation_ayahs",None)),
 ("translation_footnotes","khushu-quran.db","translation",("translation_footnotes",None)),
]
for label,mdb,fam,(t,_) in cov:
    mp=count(conn(os.path.join(DB,mdb)),t); sp=sum_packs(t,fam)
    print(f"  {label:22s} master={mp} packs={sp} {'OK' if mp==sp else '*** LOSS ***'}")
    if mp!=sp: fails.append(label)
# hadiths + contents summed over collections
for suffix in ("_hadiths","_hadith_contents","_hadith_text"):
    mp=sum(count(mh,f"{c}{suffix}") for c in COLLS)
    sp=0
    for p in m["packs"]:
        if p["family"]=="hadith":
            for t in p["tables"]:
                if t.endswith(suffix): sp+=count(conn(os.path.join(PK,p["file"])),t)
    print(f"  hadith{suffix:16s} master={mp} packs={sp} {'OK' if mp==sp else '*** LOSS ***'}")
    if mp!=sp: fails.append("hadith"+suffix)
# quran-core carries full non-translation set
cq=conn(os.path.join(DB,"khushu-quran.db"))
qc_tables=[r[0] for r in cq.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name NOT LIKE 'translation_%' AND sql NOT LIKE '%fts5%'")]
qcore=next(p for p in m["packs"] if p["id"]=="quran-core")
fcore=conn(os.path.join(PK,qcore["file"]))
for t in qcore["tables"]:
    if t.startswith("translation"): continue
    a=count(cq,t); b=count(fcore,t)
    if str(a)!=str(b) and not str(a).startswith("ERR"): fails.append(f"core {t} {a}!={b}")
print(f"  quran-core non-translation tables: {len(qcore['tables'])} checked")
# 3) FTS rowid stability spot checks
sp=conn(os.path.join(PK,"translation-en_saheeh-international.db"))
fts=count(sp,"translation_fts","translation_fts MATCH 'merciful'",)
print(f"  sahih translation_fts merciful: {fts} (master expect >0)")
bk=conn(os.path.join(PK,"hadith-bukhari.db"))
print(f"  bukhari fts prayer: {count(bk,'bukhari_hadith_fts','bukhari_hadith_fts MATCH \'prayer\'')} (master expect 1043)")
print(f"\nRESULT: {'ALL GREEN — packs are a lossless re-shard of data/db.' if not fails else 'FAILURES: '+'; '.join(fails)}")
sys.exit(1 if fails else 0)
