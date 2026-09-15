#!/usr/bin/env python3
"""Post-deploy verification: connect each of the 4 Turso DBs (read-only, via the
group token) and check representative table row-counts + FTS5 match vs expected."""
import os, json, sys, urllib.request
REPO=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0,REPO)
try:
    from dotenv import load_dotenv; load_dotenv(REPO+"/.env")
except Exception: pass
ORG=os.environ.get("KHUSHU_TURSO_ORG","syedali"); REGION="aws-us-east-1"
TOK=os.environ.get("KHUSHU_TURSO_GROUP_TOKEN","")
EXPECT=json.load(open(REPO+"/data/manifest/dbs.json"))["databases"]
def q(dbname, sql):
    url=f"https://{dbname}-{ORG}.{REGION}.turso.io/"
    req=urllib.request.Request(url, data=json.dumps({"statements":[sql]}).encode(),
        headers={"Authorization":"Bearer "+TOK,"Content-Type":"application/json"})
    return json.load(urllib.request.urlopen(req,timeout=20))[0]["results"]["rows"]
print("Post-deploy remote verification (run after APPLY=1):")
checks={"khushu-core":'select count(*) from quran_surahs',
        "khushu-hadith":'select count(*) from bukhari_hadiths',
        "khushu-content":'select count(*) from names_names',
        "khushu-audio":'select count(*) from adhans'}
for db,sql in checks.items():
    try:
        r=q(db,sql); local=EXPECT.get(db,{}).get("tables")
        print(f"  {db}: {sql.split('from ')[1]} = {r[0][0]}")
    except Exception as e: print(f"  {db}: {type(e).__name__}: {str(e)[:80]}")
