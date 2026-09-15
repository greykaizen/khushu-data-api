#!/usr/bin/env python3
"""Pack: catalog.db — FONT PACK metadata (the one catalog listing not otherwise in a
domain table). Translations/tafsirs/wbw are already derivable from translation_packs /
tafsir_books / wbw_packs; web links from `links`. Font catalog carries display names,
usage notes, per-file weight/provenance that the assets table (blob registry only) does
NOT, so we preserve it verbatim to keep the migration lossless. Donor:
archive/inventory/fonts/available_fonts_info.json {fonts:[{id,display_name,usage,
files:[{id,display_name,path,format,weight,provenance}]}]}."""
import sqlite3, os, json, sys
API="/home/kaizen/AndroidStudioProjects/khushu-data-api/archive"
OUT=os.path.abspath(os.path.join(os.path.dirname(__file__),"..","..","data","build"))

def main():
    db=OUT+"/catalog.db"
    if os.path.exists(db): os.remove(db)
    c=sqlite3.connect(db)
    c.executescript("""CREATE TABLE font_packs(id TEXT PRIMARY KEY, display_name TEXT, usage TEXT);
      CREATE TABLE font_files(id TEXT, pack TEXT, display_name TEXT, asset_path TEXT, format TEXT,
        weight INTEGER, provenance TEXT, PRIMARY KEY(pack,id));""")
    d=json.load(open(f"{API}/inventory/fonts/available_fonts_info.json"))
    packs=0; files=0
    for p in d["fonts"]:
        c.execute("INSERT INTO font_packs VALUES(?,?,?)",(p["id"],p.get("display_name",""),p.get("usage")))
        packs+=1
        for f in p.get("files",[]):
            c.execute("INSERT INTO font_files VALUES(?,?,?,?,?,?,?)",
                (f["id"],p["id"],f.get("display_name") or f["id"],f.get("path",""),f.get("format","ttf"),
                 f.get("weight",400),f.get("provenance")))
            files+=1
    c.execute("PRAGMA user_version=1"); c.commit()
    np=c.execute("select count(*) from font_packs").fetchone()[0]
    nf=c.execute("select count(*) from font_files").fetchone()[0]
    assert np==3, f"font packs {np}"
    c.close(); print(f"  catalog.db: {np} font packs / {nf} font files")

if __name__=="__main__": main()
