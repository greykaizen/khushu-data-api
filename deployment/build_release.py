#!/usr/bin/env python3
"""Generate the release artifact set from assets.db WITHOUT uploading.
Adds a collision-free `release_name` (= asset_id with '/'->'__') to assets.db,
writes data/manifest/assets.json + assets.csv (the consumer-facing manifest),
and hardlinks a flat staging tree data/assets/<release_name> -> archive file,
so `gh release upload` gets deterministic, unique asset names. App resolves:
   url = ASSET_BASE_URL + release_name  (base_url swap = one value; no per-row URL)."""
import sqlite3, os, json, csv, shutil
REPO="/home/kaizen/AndroidStudioProjects/khushu-data-api"
API=REPO+"/archive"
OUT=REPO+"/data"; MAN=OUT+"/manifest"; STAGE=OUT+"/assets"
VERSION=os.environ.get("KHUSHU_ASSET_RELEASE_TAG","assets-v2026.09")
def main():
    db=OUT+"/db/assets.db"; c=sqlite3.connect(db)
    cols=[r[1] for r in c.execute("pragma table_info(assets)")]
    if "release_name" not in cols:
        c.execute("ALTER TABLE assets ADD COLUMN release_name TEXT")
    rows=c.execute("select asset_id,relative_path,sha256,size_bytes,mime_type,kind,version from assets order by asset_id").fetchall()
    seen={}
    for (aid,rel,sha,size,mime,kind,ver) in rows:
        rn=aid.replace("/","__")
        assert rn not in seen, f"collision {rn}"
        seen[rn]=aid
        c.execute("UPDATE assets SET release_name=? WHERE asset_id=?",(rn,aid))
    c.commit()
    os.makedirs(MAN,exist_ok=True); 
    if os.path.isdir(STAGE): shutil.rmtree(STAGE)
    os.makedirs(STAGE)
    total=0; entries=[]
    for (aid,rel,sha,size,mime,kind,ver) in rows:
        rn=aid.replace("/","__"); src=API+"/"+rel
        if not os.path.exists(src): print("MISSING",src); continue
        dst=STAGE+"/"+aid                    # canonical ORGANIZED dir tree
        os.makedirs(os.path.dirname(dst),exist_ok=True)
        try: os.link(src,dst)
        except OSError: shutil.copy2(src,dst)
        total+=size; entries.append(dict(asset_id=aid,release_name=rn,relative_path=rel,sha256=sha,size=size,mime=mime,kind=kind))
    json.dump({"version":VERSION,"asset_base_url":f"https://github.com/greykaizen/khushu-data-api/releases/download/{VERSION}/","count":len(entries),"total_bytes":total,"assets":entries}, open(MAN+"/assets.json","w"), ensure_ascii=False, separators=(",",":"))
    with open(MAN+"/assets.csv","w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=["asset_id","release_name","size","sha256","kind","mime"]); w.writeheader(); [w.writerow({k:e[k] for k in ["asset_id","release_name","size","sha256","kind","mime"]}) for e in entries]
    print(f"release_name: {len(entries)} unique, {total/1048576:.1f} MB staged in data/assets/ (hardlinks)")
    print("manifest:",MAN+"/assets.json")
    print("collision check on 6x.zip atlas names:", [e['release_name'] for e in entries if e['asset_id'].endswith('6x.zip')])
if __name__=="__main__": main()
