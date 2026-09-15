#!/usr/bin/env python3
"""Consolidate the 21 per-domain intermediates (data/build) into SIX production
databases (data/db), namespaced so boundaries are self-explanatory. NOT file
concatenation: base tables re-created with a domain prefix and repopulated
(rowid-preserved); FTS5 rebuilt from consolidated bases (external-content) or
re-derived (contentless); the small `assets` registry is embedded in the three
DBs that carry asset_id refs (quran/content/audio) so each is self-contained
for offline/replica use. Deterministic given the source files.

Topology: khushu-quran (quran+translations+assets) · khushu-tafsir · khushu-wbw ·
khushu-hadith (9 collections+scholars) · khushu-content (dua/articles/names/
calendar/curated +assets) · khushu-audio (recitations+adhan +assets)."""
import sqlite3, os, re, sys
BUILD="data/build"; OUT="data/db"
COLLS=["bukhari","muslim","abu_dawud","tirmidhi","nasai","ibn_majah","malik","riyadussalihin","forty"]
COLL_SRC={"bukhari":"sunnah_bukhari","muslim":"sunnah_muslim","abu_dawud":"sunnah_abudawud",
 "tirmidhi":"sunnah_tirmidhi","nasai":"sunnah_nasai","ibn_majah":"sunnah_ibnmajah",
 "malik":"sunnah_malik","riyadussalihin":"sunnah_riyadussalihin","forty":"sunnah_forty"}
QURAN_MAP={t:"quran_"+t for t in ["surahs","ayahs","ayah_words","mushafs","mushaf_map","mushaf_info",
  "mushaf_pages","scripts","navigation_ranges","surah_localizations","surah_search_aliases",
  "similar_verses","mutashabihat_phrases","mutashabihat_phrase_ayah","topics","topic_ayahs",
  "topic_localizations","relationships","search_arabic"]}
TRANS_MAP={"packs":"translation_packs","tr_ayahs":"translation_ayahs","tr_footnotes":"translation_footnotes"}
TAFSIR_MAP={"tafsir_books":"tafsir_books","tafsir_entries":"tafsir_entries"}
WBW_MAP={"wbw_packs":"wbw_packs","wbw_words":"wbw_words"}
ASSETS_MAP={"assets":"assets"}
CONTENT_MAP={"duas":"dua_items","dua_posts":"dua_posts","dua_categories":"dua_categories",
  "articles":"article_items","article_categories":"article_categories","article_members":"article_members",
  "names":"names_names","asma_packs":"names_packs","events":"calendar_events","event_packs":"calendar_packs",
  "curated_sets":"curated_sets","curated_refs":"curated_refs","science_topics":"curated_science_topics",
  "science_topic_ayahs":"curated_science_topic_ayahs"}
AUDIO_MAP={"reciters":"recitation_reciters","recitation_timings":"recitation_timings","adhan_audio":"adhans"}
HADITH_TABLES=["collections","collection_translations","books","book_translations","chapters",
  "chapter_translations","hadiths","hadith_contents","hadith_references","hadith_related",
  "hadith_grades","hadith_narrators","hadith_text","bundle_meta"]

def rewrite_names(ddl, name_map):
    for tok in sorted(name_map, key=len, reverse=True):
        ddl=re.sub(r'(?<![\w."])'+re.escape(tok)+r'(?![\w"])', name_map[tok], ddl)
        ddl=re.sub(r'"'+re.escape(tok)+r'"', '"'+name_map[tok]+'"', ddl)
    return ddl

def attach(dst, srcfile, name_map, tag):
    dst.execute(f"ATTACH DATABASE '{BUILD}/{srcfile}' AS s")
    fts=set(r[0] for r in dst.execute("select name from s.sqlite_master where sql like '%fts5%' and type='table'").fetchall())
    def shadow(n): return any(n==p or n.startswith(p+"_") for p in fts)
    tables=dst.execute("select name,sql from s.sqlite_master where type='table' and sql is not null and name not like 'sqlite_%'").fetchall()
    indexes=dst.execute("select name,sql,tbl_name from s.sqlite_master where type='index' and sql is not null and name not like 'sqlite_%'").fetchall()
    for name,sql in tables:
        if name not in name_map or shadow(name) or "fts5" in (sql or "").lower(): continue
        dst.execute(rewrite_names(sql,name_map))
        cols=[c[1] for c in dst.execute(f"pragma s.table_info('{name}')").fetchall()]
        ph=",".join('"'+c+'"' for c in cols)
        dst.execute(f'INSERT INTO main."{name_map[name]}"({ph}) SELECT {ph} FROM s."{name}"')
    for name,sql,tbl in indexes:
        if tbl not in name_map or sql is None: continue
        ndl=rewrite_names(sql,name_map)
        ndl=re.sub(r'CREATE( UNIQUE)? INDEX ("?[^\s(]+"?) ON', lambda m,f=f'CREATE{{0}} INDEX "i_{tag}_{name}" ON':f, ndl, count=1) if False else ndl
        ndl=re.sub(r'CREATE( UNIQUE)? INDEX ("?[^\s(]+"?) ON', lambda m: ('CREATE%s INDEX "i_%s_%s" ON'%((m.group(1) or ''),tag,name)), ndl, count=1)
        try: dst.execute(ndl)
        except Exception as e: print("   idx skip",tag,name)
    dst.commit(); dst.execute("DETACH s")

def fts_external(dst, fts_new, content_new, rowid, col):
    dst.execute(f"CREATE VIRTUAL TABLE main.\"{fts_new}\" USING fts5({col}, content='{content_new}', content_rowid='{rowid}', tokenize='unicode61')")
    dst.execute(f"INSERT INTO main.\"{fts_new}\"(\"{fts_new}\") VALUES('rebuild')")
def fts_external_plain(dst, fts_new, content_new, col):
    dst.execute(f"CREATE VIRTUAL TABLE main.\"{fts_new}\" USING fts5({col}, content='{content_new}', tokenize='unicode61')")
    dst.execute(f"INSERT INTO main.\"{fts_new}\"(\"{fts_new}\") VALUES('rebuild')")

def new_target(name):
    out=f"{OUT}/{name}.db"
    if os.path.exists(out): os.remove(out)
    return sqlite3.connect(out)

def build():
    # 1) khushu-quran
    c=new_target("khushu-quran")
    attach(c,"quran.db",QURAN_MAP,"quran"); attach(c,"translations.db",TRANS_MAP,"tr"); attach(c,"assets.db",ASSETS_MAP,"assets"); attach(c,"chapters.db",{"chapter_info":"quran_chapter_info"},"chap")
    fts_external(c,"quran_arabic_fts","quran_search_arabic","ayah_id","text")
    fts_external(c,"quran_surah_alias_fts","quran_surah_search_aliases","id","alias")
    c.execute("CREATE VIRTUAL TABLE main.translation_fts USING fts5(plain, content='', tokenize='unicode61')")
    TAG=re.compile(r"<[^>]+>"); 
    for rid,tr in c.execute("select rowid, translation from translation_ayahs"): c.execute("INSERT INTO main.translation_fts(rowid,plain) VALUES(?,?)",(rid,TAG.sub("",tr or "")))
    c.commit(); c.close()
    # 2) khushu-tafsir
    c=new_target("khushu-tafsir"); attach(c,"tafsir.db",TAFSIR_MAP,"tafsir"); c.commit(); c.close()
    # 3) khushu-wbw
    c=new_target("khushu-wbw"); attach(c,"wbw.db",WBW_MAP,"wbw"); c.commit(); c.close()
    # 4) khushu-hadith
    c=new_target("khushu-hadith")
    for coll in COLLS:
        nm={t:f"{coll}_{t}" for t in HADITH_TABLES}
        attach(c,f"{COLL_SRC[coll]}.db",nm,coll)
        fts_external_plain(c,f"{coll}_hadith_fts",f"{coll}_hadith_text","matn")
    attach(c,"scholars.db",{"scholars":"scholars"},"scholars"); c.commit(); c.close()
    # 5) khushu-content
    c=new_target("khushu-content"); attach(c,"dua.db",CONTENT_MAP,"content")
    for srcf,nm,tag in [("names.db",{"names":"names_names","asma_packs":"names_packs"},"names"),
                        ("events.db",{"events":"calendar_events","event_packs":"calendar_packs"},"cal"),
                        ("curated.db",{"curated_sets":"curated_sets","curated_titles":"curated_titles","recommended_rules":"recommended_rules","recommended_defaults":"recommended_defaults","recommended_texts":"recommended_texts","science_topics":"curated_science_topics"},"cur")]:
        attach(c,srcf,nm,tag)
    attach(c,"assets.db",ASSETS_MAP,"assets")   # embedded registry for offline resolution
    attach(c,"catalog.db",{"font_packs":"font_packs","font_files":"font_files"},"fonts")   # font catalog metadata (blob registry lives in assets)
    c.execute("CREATE VIRTUAL TABLE main.dua_fts USING fts5(text, content='', tokenize='unicode61')")
    for rid,ti,tr,tx in c.execute("select id, title, translation, transliteration from dua_items"):
        c.execute("INSERT INTO main.dua_fts(rowid,text) VALUES(?,?)",(rid," ".join(x for x in [ti,tr,tx] if x)))
    # web links (from archive/inventory/other/urls.json) -> small config table
    import json as _json
    u=_json.load(open("archive/inventory/other/urls.json"))
    c.execute("CREATE TABLE main.links(key TEXT PRIMARY KEY, url TEXT)")
    c.executemany("INSERT INTO main.links VALUES(?,?)", list(u.items()))
    c.commit(); c.close()
    # 6) khushu-audio
    c=new_target("khushu-audio"); attach(c,"recitations.db",{"reciters":"recitation_reciters","recitation_timings":"recitation_timings"},"rec")
    attach(c,"adhan.db",{"adhan_audio":"adhans"},"adhan"); attach(c,"assets.db",ASSETS_MAP,"assets")
    c.commit(); c.close()

if __name__=="__main__":
    os.makedirs(OUT,exist_ok=True); build(); print("consolidated 6 into data/db/")
