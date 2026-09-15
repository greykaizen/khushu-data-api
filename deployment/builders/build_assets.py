#!/usr/bin/env python3
"""Central ASSET manifest — canonical organized tree + single source of truth.
`asset_id` = canonical logical path (e.g. names/muqaddim.opus, fonts/kfqpc/…);
`relative_path` = provenance source under archive/ (kept for provenance only).
Domain DBs reference asset_id. The flat GitHub `release_name` lives in the
build_release manifest, NOT here. Font dedup: kfqpc loose page-TTFs ≡
qpc_v1_by_page.tar.zst ≡ kfqpc zips (604/604 hash-verified) → keep the pages,
drop the duplicate archives; keep the distinct tajweed bundle; drop tar.gz stubs.
Recitation audio stays external (not here)."""
import sqlite3, os, glob, hashlib, sys, json, re
API="/home/kaizen/AndroidStudioProjects/khushu-data-api/archive"
OUT=os.path.abspath(os.path.join(os.path.dirname(__file__),"..","..","data","build"))
VERSION=os.environ.get("KHUSHU_ASSETS_VERSION","assets-v2026.09")
MIME={".opus":"audio/opus",".ttf":"font/ttf",".otf":"font/otf",".zip":"application/zip",
 ".tar.zst":"application/x-zstd",".webp":"image/webp",".png":"image/png",".jpg":"image/jpeg",
 ".gif":"image/gif",".html":"text/html",".css":"text/css",".js":"text/javascript",".svg":"image/svg+xml"}
def sha(p):
    h=hashlib.sha256()
    with open(p,"rb") as f:
        for b in iter(lambda:f.read(1<<20),b""): h.update(b)
    return h.hexdigest()
def canonical_and_kind(rel):
    """source-rel (from archive) -> (canonical asset_id, kind). None => excluded."""
    if rel.startswith("assets/adhan/"): return "adhan/"+os.path.basename(rel),"adhan-audio"
    if rel.startswith("assets/dua_dhikr/"): return "dua/"+os.path.basename(rel),"dua-audio"
    if rel.startswith("assets/asma_ul_husna/"): return "names/"+os.path.basename(rel),"names-audio"
    if rel.startswith("inventory/atlas/"): return "atlas/"+rel[len("inventory/atlas/"):],"glyph-atlas"
    if rel.startswith("inventory/topics/images/"): return "images/"+rel[len("inventory/topics/images/"):],"topic-image"
    if rel.startswith("inventory/curated/science/"):
        sub=rel[len("inventory/curated/science/"):]
        if sub.endswith(".json"): return None
        return "curated/science/"+sub,"curated-science"
    if rel.startswith("inventory/fonts/"):
        s=rel[len("inventory/fonts/"):]
        if s.startswith("quran_icons/"): return "fonts/"+s,"font"
        if s.startswith("quran_text/"):  return "fonts/"+s,"font"
        if s.startswith("sunnah/"):      return "fonts/"+s,"font"
        if s.startswith("kfqpc_v1/"):
            fn=os.path.basename(s)
            if s.endswith(".zip"): return None                       # dup of pages
            if fn.upper().endswith(".TTF"):
                num=re.search(r"(\d+)",fn); return "fonts/kfqpc/page_%s.ttf"%(num.group(1) if num else fn),"font"
        if s.startswith("qpc/"):
            if s=="qpc/qpc_v1_by_page.tar.zst": return None          # 604 pages identical to kfqpc
            if s.endswith(".tar.gz"): return None
            if s=="qpc/qpc_v4_tajweed_by_page.tar.zst": return "fonts/qpc/tajweed_v4.tar.zst","font"
            return None                                              # v2 stub etc.
        return None
    return None
def sources():
    pats=["assets/adhan/*.opus","assets/dua_dhikr/*.opus","assets/asma_ul_husna/*.opus",
          "inventory/atlas/**/*.zip","inventory/topics/images/**/*","inventory/curated/science/**/*",
          "inventory/fonts/quran_icons/*","inventory/fonts/quran_text/*","inventory/fonts/sunnah/*",
          "inventory/fonts/kfqpc_v1/*","inventory/fonts/qpc/*"]
    for pat in pats:
        for p in glob.glob(f"{API}/{pat}",recursive=True):
            if os.path.isfile(p): yield os.path.relpath(p,API)
def main():
    os.makedirs(OUT,exist_ok=True); db=OUT+"/assets.db"
    if os.path.exists(db): os.remove(db)
    c=sqlite3.connect(db)
    c.executescript("""CREATE TABLE assets(
      asset_id TEXT PRIMARY KEY, relative_path TEXT NOT NULL, sha256 TEXT NOT NULL,
      size_bytes INTEGER NOT NULL, mime_type TEXT NOT NULL, kind TEXT NOT NULL, version TEXT NOT NULL);
      CREATE INDEX ix_assets_kind ON assets(kind);""")
    rows=[]
    for rel in sources():
        cc=canonical_and_kind(rel)
        if not cc: continue
        aid,kind=cc
        ext=os.path.splitext(rel)[1].lower()
        mime=MIME.get(ext, "application/octet-stream")
        rows.append((aid, rel, sha(f"{API}/{rel}"), os.path.getsize(f"{API}/{rel}"), mime, kind, VERSION))
    # de-dup by canonical asset_id (guard against kfqpc naming collisions -> keep first, but flag)
    seen={}
    for r in rows:
        if r[0] in seen:
            if seen[r[0]][1:]!=r[1:]: raise SystemExit("canon id collision w/ different file: "+r[0])
            continue
        seen[r[0]]=r
    c.executemany("INSERT INTO assets VALUES(?,?,?,?,?,?,?)", list(seen.values()))
    c.execute("PRAGMA user_version=1"); c.commit(); report(c)
def report(c):
    print("== assets.db (canonical organized tree) ==")
    for k,n,s in c.execute("select kind,count(*),sum(size_bytes) from assets group by kind order by 3 desc"):
        print(f"  {k:16s} {n:5d} files  {s/1048576:7.1f} MB")
    t=c.execute("select count(*),sum(size_bytes) from assets").fetchone()
    print(f"  TOTAL {t[0]} files  {t[1]/1048576:.1f} MB  version={VERSION}")
    print("  sample ids:", [r[0] for r in c.execute("select asset_id from assets order by asset_id limit 4").fetchall()])
    print("  fonts tree:", [r[0] for r in c.execute("select asset_id from assets where kind='font' order by asset_id limit 3")])
main()
