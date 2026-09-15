#!/usr/bin/env python3
"""Packs: wbw, recitations, adhan, events, curated. Same donor-first + exact
verification standard. Domain DBs store asset_id (= repo-relative path, the
assets.db PK) instead of duplicating sha/size. External URLs (recitation audio,
remote dua/name mp3) stay in the domain DB as refs; hosted files point at assets.db."""
import sqlite3, os, glob, gzip, json, hashlib, sys
API="/home/kaizen/AndroidStudioProjects/khushu-data-api/archive"
OUT=os.path.join(os.path.dirname(__file__), "..", "..", "data", "build")
def sha(p):
    h=hashlib.sha256()
    with open(p,"rb") as f:
        for b in iter(lambda:f.read(1<<20),b""): h.update(b)
    return h.hexdigest()
def fresh(name, ddl):
    db=OUT+"/"+name
    if os.path.exists(db): os.remove(db)
    c=sqlite3.connect(db); c.executescript(ddl); return c,db

# ---- events.db ----
def build_events():
    c,db=fresh("events.db","""CREATE TABLE event_packs(id TEXT PRIMARY KEY, title TEXT, source TEXT);
      CREATE TABLE events(id TEXT PRIMARY KEY, title TEXT, hijri_month INTEGER, hijri_day INTEGER,
        category TEXT, recurrence TEXT, source TEXT, confidence TEXT);""")
    d=json.load(open(f"{API}/assets/islamic_calendar/islamic_events.json"))
    for e in d.get("pack",{}).items() if isinstance(d.get("pack"),dict) else []: pass
    pk=d.get("pack"); c.execute("INSERT INTO event_packs VALUES(?,?,?)",(str(pk.get("id","khushu-core-islamic-events")),str(pk.get("title","")),str(pk.get("source",""))) if isinstance(pk,dict) else None) if isinstance(pk,dict) else None
    for e in d["events"]:
        c.execute("INSERT INTO events VALUES(?,?,?,?,?,?,?,?)",(e["id"],e["title"],e.get("hijriMonth"),e.get("hijriDay"),e.get("category"),e.get("recurrence"),e.get("source"),e.get("confidence")))
    n=c.execute("select count(*) from events").fetchone()[0]
    assert n==11, f"events {n}"
    c.execute("PRAGMA user_version=1");c.commit();c.close(); print(f"  events.db: {n} events")

# ---- adhan.db (asset_id refs) ----
def build_adhan():
    c,db=fresh("adhan.db","""CREATE TABLE adhan_audio(asset_id TEXT PRIMARY KEY, adhan_id TEXT, reciter TEXT, region TEXT, style TEXT,
      format TEXT, sample_rate_hz INTEGER, channels INTEGER);""")
    d=json.load(open(f"{API}/assets/adhan/adhan_index.json"))
    for e in d["entries"]:
        c.execute("INSERT INTO adhan_audio VALUES(?,?,?,?,?,?,?,?)",
          ("adhan/"+os.path.basename(e["file"]),e["id"],e["reciter"],e.get("region"),e.get("style"),e.get("format"),e.get("sampleRateHz"),e.get("channels")))
    n=c.execute("select count(*) from adhan_audio").fetchone()[0]
    assert n==178, f"adhan {n}"
    c.execute("PRAGMA user_version=1");c.commit();c.close(); print(f"  adhan.db: {n} entries (asset_id -> assets.db)")

# ---- recitations.db (reciters + timing blobs; audio external) ----
def build_recitations():
    c,db=fresh("recitations.db","""CREATE TABLE reciters(id TEXT PRIMARY KEY, reciter TEXT, style TEXT,
      url_template TEXT, audio_version INTEGER, timing_version INTEGER, translations_json TEXT);
      CREATE TABLE recitation_timings(reciter TEXT, version INTEGER, timing_gz BLOB, sha256 TEXT, PRIMARY KEY(reciter,version));""")
    r=json.load(open(f"{API}/inventory/recitations/available_recitations_info_v2.json"))
    for x in r["reciters"]:
        c.execute("INSERT INTO reciters VALUES(?,?,?,?,?,?,?)",(x["id"],x["reciter"],x.get("style"),x.get("url_template"),x.get("audio_version"),x.get("timing_version"),json.dumps(x.get("translations",{}),ensure_ascii=False)))
    tn=0
    for f in glob.glob(f"{API}/inventory/recitations/timings/*.json.gz"):
        rec=os.path.basename(f)[:-len(".json.gz")]
        blob=open(f,"rb").read()
        c.execute("INSERT INTO recitation_timings VALUES(?,?,?,?)",(rec,1,blob,hashlib.sha256(blob).hexdigest())); tn+=1
    nr=c.execute("select count(*) from reciters").fetchone()[0]
    assert nr==18 and tn==28, f"reciters {nr} timings {tn}"
    c.execute("PRAGMA user_version=1");c.commit();c.close(); print(f"  recitations.db: {nr} reciters + {tn} timing blobs (audio=external URL refs)")

# ---- wbw.db (per-ayah word rows; v1 + v2) ----
def build_wbw():
    c,db=fresh("wbw.db","""CREATE TABLE wbw_packs(lang_code TEXT, version INTEGER, n_verses INTEGER, PRIMARY KEY(lang_code,version));
      CREATE TABLE wbw_words(lang_code TEXT, version INTEGER, ayah_id INTEGER, ordinal INTEGER, word_json TEXT, PRIMARY KEY(lang_code,version,ayah_id,ordinal));""")
    tot_verse=0
    for ver,d in (("v1",f"{API}/inventory/wbw/packs/wbw_*.json.gz"),("v2",f"{API}/inventory/wbw/packs_v2/wbw_*.json.gz")):
        v=1 if ver=="v1" else 2
        for f in glob.glob(d):
            lang=os.path.basename(f)[len('wbw_'):-len('.json.gz')]; w=json.loads(gzip.open(f).read()); vs=w["verses"]; n=0
            for aid,words in vs.items():
                for i,wd in enumerate(words):
                    c.execute("INSERT INTO wbw_words VALUES(?,?,?,?,?)",(lang,v,int(aid),i,json.dumps(wd,ensure_ascii=False))); n+=1
                c.execute("INSERT OR IGNORE INTO wbw_packs VALUES(?,?,?)",(lang,v,0))
                tot_verse+=1
            c.execute("UPDATE wbw_packs SET n_verses=? WHERE lang_code=? AND version=?",(len(vs),lang,v))
    np=c.execute("select count(*) from wbw_packs").fetchone()[0]; nw=c.execute("select count(*) from wbw_words").fetchone()[0]
    assert np==28 and nw>0
    c.execute("PRAGMA user_version=1");c.commit();c.close(); print(f"  wbw.db: {np} packs (14 lang×2) / {nw} word rows")

# ---- curated.db (verse sets + recommended rules + science) ----
# Source-of-truth fidelity: `map.json` values are RANGE STRINGS ("2:153,3:173"),
# `recommended/lang_*.json` values are {title,description} dicts, `rules.json` has
# {schema,defaults,rules:[{id,priority,when:{clauses},ref:{segments}}]}. Store each
# VERBATIM (parse AyahRef / when / segments in the read layer) — never enumerate a
# string/dict as if it were a list (the original bug that char-split refs).
def build_curated():
    c,db=fresh("curated.db","""
      CREATE TABLE curated_sets(kind TEXT, entry_id TEXT, refs TEXT, PRIMARY KEY(kind,entry_id));
      CREATE TABLE curated_titles(kind TEXT, entry_id TEXT, lang TEXT, title TEXT, PRIMARY KEY(kind,entry_id,lang));
      CREATE TABLE recommended_rules(id TEXT PRIMARY KEY, priority INTEGER, when_json TEXT, segments_json TEXT);
      CREATE TABLE recommended_defaults(key TEXT PRIMARY KEY, value TEXT);
      CREATE TABLE recommended_texts(lang TEXT, id TEXT, title TEXT, description TEXT, PRIMARY KEY(lang,id));
      CREATE TABLE science_topics(id TEXT PRIMARY KEY, title TEXT, references_count INTEGER, path TEXT, translations_json TEXT);""")
    verses=f"{API}/inventory/curated/verses"
    # curated verse sets: map.json (per-entry range string) + per-lang titles
    nsets=0
    for mf in glob.glob(f"{verses}/type*/map.json")+glob.glob(f"{verses}/major_sins/map.json"):
        kind=os.path.basename(os.path.dirname(mf)); mm=json.load(open(mf))
        for sid,ref in mm.items():
            c.execute("INSERT INTO curated_sets VALUES(?,?,?)",(kind,sid,ref)); nsets+=1
            for tf in glob.glob(f"{verses}/{kind}/*/*.json"):
                lang=os.path.basename(os.path.dirname(tf))
                try: td=json.load(open(tf))
                except Exception: continue
                if isinstance(td,dict) and sid in td:
                    t=td[sid]; title=t if isinstance(t,str) else (t.get("title") if isinstance(t,dict) else str(t))
                    if title: c.execute("INSERT OR REPLACE INTO curated_titles VALUES(?,?,?,?)",(kind,sid,lang,title))
    # recommended: rules.json (verbatim when/segments) + defaults + lang texts
    r=json.load(open(f"{verses}/recommended/rules.json"))
    for k,v in (r.get("defaults") or {}).items():
        c.execute("INSERT OR REPLACE INTO recommended_defaults VALUES(?,?)",(k,json.dumps(v,ensure_ascii=False)))
    nrules=0
    for rule in r.get("rules",[]):
        c.execute("INSERT INTO recommended_rules VALUES(?,?,?,?)",(
            rule["id"], rule.get("priority",0),
            json.dumps(rule.get("when",{}),ensure_ascii=False),
            json.dumps((rule.get("ref") or {}).get("segments",[]),ensure_ascii=False)))
        nrules+=1
    ntxt=0
    for lf in glob.glob(f"{verses}/recommended/lang_*.json"):
        lang=os.path.basename(lf)[len('lang_'):-5]; d=json.load(open(lf))
        for name,val in d.items():
            title=(val.get("title") if isinstance(val,dict) else None) or ""
            desc=(val.get("description") if isinstance(val,dict) else None)
            c.execute("INSERT OR REPLACE INTO recommended_texts VALUES(?,?,?,?)",(lang,name,title,desc)); ntxt+=1
    # science topics (index has path=html; the per-topic ayahs live in the html, no list table)
    si=json.load(open(f"{API}/inventory/curated/science/index.json"))
    for t in si:
        c.execute("INSERT INTO science_topics VALUES(?,?,?,?,?)",(t["id"],t["title"],t.get("referencesCount"),t.get("path"),json.dumps(t.get("translations",{}),ensure_ascii=False)))
    st=c.execute("select count(*) from science_topics").fetchone()[0]
    c.execute("PRAGMA user_version=2");c.commit();c.close()
    print(f"  curated.db: {nsets} verse-sets / {nrules} recommended rules / {ntxt} texts / {st} science topics")

for f in (build_events,build_adhan,build_recitations,build_wbw,build_curated): f()
print("OK")
