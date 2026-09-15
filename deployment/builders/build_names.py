#!/usr/bin/env python3
"""Pack 6 — names.db (Asma ul-Husna, the 99 Names of Allah).
Source: assets/asma_ul_husna/asma_data_{lang}.json  {code,status,data:{names[99],
title,arabic_title,description,recitation_benefits,hadith,total}} — 11 langs.
Each name's `audio` is a remote path (/audio/asma-ul-husna/<slug>.mp3); the 99
local .opus are named by that SAME slug basename -> join is exact (99/99 verified),
so we link number -> local opus by basename(remote audio), not transliteration.
No FTS5: 99 rows, linear filter is enough. Audio stays files (path+sha256)."""
import sqlite3, os, json, glob, sys, hashlib
SRC="/home/kaizen/AndroidStudioProjects/khushu-data-api/archive/assets/asma_ul_husna"
OUT=os.path.join(os.path.dirname(__file__), "..", "..", "data", "build")
def main():
    if os.path.exists(OUT+"/names.db"): os.remove(OUT+"/names.db")
    c=sqlite3.connect(OUT+"/names.db")
    c.executescript("""
      CREATE TABLE asma_packs(lang_code TEXT PRIMARY KEY, language_name TEXT, title TEXT,
        arabic_title TEXT, description TEXT, recitation_benefits TEXT, hadith TEXT, total INTEGER);
      CREATE TABLE names(id INTEGER PRIMARY KEY, lang_code TEXT, number INTEGER,
        name TEXT, transliteration TEXT, translation TEXT, meaning TEXT,
        audio_asset_id TEXT);
      CREATE UNIQUE INDEX ux_name ON names(lang_code, number);
    """)
    opus={os.path.basename(p)[:-5]: p for p in glob.glob(f"{SRC}/*.opus")}
    langs=0
    for f in sorted(glob.glob(f"{SRC}/asma_data_*.json")):
        lang=os.path.basename(f)[len('asma_data_'):-len('.json')]
        d=json.load(open(f))["data"]
        c.execute("INSERT INTO asma_packs VALUES(?,?,?,?,?,?,?,?)",
                  (lang,d.get("language"),d.get("title"),d.get("arabic_title"),
                   d.get("description"),d.get("recitation_benefits"),d.get("hadith"),d.get("total")))
        for n in d["names"]:
            slug=os.path.basename(n.get("audio","")).rsplit(".",1)[0]
            op=opus.get(slug); aid=("names/"+os.path.basename(op)) if op else None
            c.execute("INSERT INTO names(lang_code,number,name,transliteration,translation,meaning,audio_asset_id) VALUES(?,?,?,?,?,?,?)",
                      (lang,n["number"],n["name"],n["transliteration"],n["translation"],n["meaning"],aid))
        langs+=1
    c.execute("PRAGMA user_version=1"); c.commit(); verify(c,langs)
def verify(c,langs):
    ok=True
    nn=c.execute("select count(*) from names").fetchone()[0]
    print(f"  langs={c.execute('select count(*) from asma_packs').fetchone()[0]}/{langs} (want 11)")
    per=c.execute("select lang_code,count(*) from names group by lang_code order by lang_code").fetchall()
    bad=[l for l,n in per if n!=99]; ok &= not bad and langs==11 and nn==11*99
    print(f"  names total={nn} (want 1089); per-lang all 99: {not bad}")
    lj=c.execute("select count(*) from names where lang_code='en' and audio_asset_id is not null").fetchone()[0]
    print(f"  en local-audio joined: {lj}/99"); ok &= lj==99
    print(f"  distinct langs: {c.execute('select count(distinct lang_code) from names').fetchone()[0]}")
    print(f"\nRESULT {'ALL VERIFIED' if ok else 'FAILURES'} | names.db {os.path.getsize(OUT+'/names.db')/1048576:.1f} MB")
    sys.exit(0 if ok else 1)
main()
