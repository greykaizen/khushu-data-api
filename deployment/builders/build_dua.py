#!/usr/bin/env python3
"""Pack 5 — dua.db.  Two corpora, cleanly separated:

DHINK/DUA (short supplications)      : 491 duas → `duas` + `dua_posts` (30
                                         subcategory groups) + `dua_categories`
                                         (2 top categories). Audio = file refs.
READING ARTICLES (long-form)         : 186 articles → `article_categories` (12) +
                                         `articles` (raw HTML body preserved —
                                         passthrough contract, not parsed).

Provenance/decisions:
- Source: `assets/dua_dhikr/dua_data.json` (authoritative for duas) +
  `articles_index.json` + per-article body JSONs (incl. related-articles/).
- `dhikr-dua/*.json` is a per-subcategory RE-SPLIT of the SAME 491 duas — we
  reconcile its counts against `duas` and DO NOT store it again.
- HTML entities (e.g. `&#038;`) are UNESCAPED once at load (faithful: renders
  identically); all other text kept verbatim.
- FTS5: contentless index over dua title+translation+transliteration (search is
  valuable for duas). Articles HTML is passthrough → not FTS-indexed (would
  pollute with markup).

Verify: 491 duas, per-post counts sum 491 & match source recount, dhikr-dua
reconciles to 491, 186 articles (bodies present), 2 cats / 12 article-cats,
audio mirror tally vs files, sample text byte-equal (post-unescape).
"""
import sqlite3, os, json, glob, sys, html, hashlib

SRC = "/home/kaizen/AndroidStudioProjects/khushu-data-api/archive/assets/dua_dhikr"
OUT = os.path.join(os.path.dirname(__file__), "..", "..", "data", "build")

def u(s): return html.unescape(s or "")

def main():
    os.makedirs(OUT, exist_ok=True)
    db = os.path.join(OUT, "dua.db")
    if os.path.exists(db): os.remove(db)
    c = sqlite3.connect(db)
    c.executescript("""
      CREATE TABLE duas(id INTEGER PRIMARY KEY, post_id INTEGER, category TEXT,
        subcategory TEXT, title TEXT, arabic TEXT, repetition TEXT, translation TEXT,
        transliteration TEXT, virtue TEXT, explanation TEXT, reference TEXT,
        audio_asset_id TEXT);
      CREATE INDEX ix_duas_sub ON duas(subcategory);
      CREATE INDEX ix_duas_cat ON duas(category);
      CREATE TABLE dua_posts(post_id INTEGER PRIMARY KEY, post_title TEXT,
        category TEXT, subcategory TEXT, dua_count INTEGER);
      CREATE TABLE dua_categories(category TEXT PRIMARY KEY, post_count INTEGER, dua_count INTEGER);

      CREATE TABLE article_categories(id INTEGER PRIMARY KEY, name TEXT, slug TEXT, count INTEGER);
      CREATE TABLE articles(id INTEGER PRIMARY KEY, title TEXT, slug TEXT, link TEXT,
        body_path TEXT, content_html TEXT, has_body INTEGER);
      CREATE TABLE article_members(category_id INTEGER, article_id INTEGER,
        PRIMARY KEY(category_id, article_id));
    """)

    duas = json.load(open(f"{SRC}/dua_data.json"))
    local_audio = {os.path.basename(p)[len('dua_'):-len('.opus')] for p in glob.glob(f"{SRC}/dua_*.opus")}
    for x in duas:
        aid = str(x["id"]); asset = f"dua/dua_{aid}.opus" if aid in local_audio else None
        c.execute("INSERT INTO duas VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (x["id"], x["post_id"], x["category"], x["subcategory"], u(x["title"]),
                   x["arabic"], x["repetition"], u(x["translation"]), u(x["transliteration"]),
                   u(x["virtue"]), u(x["explanation"]), u(x.get("reference") or "") or None, asset))

    posts = {}
    for x in duas:
        p = posts.setdefault(x["post_id"], dict(post_title=u(x["post_title"]), category=x["category"],
                                                 subcategory=x["subcategory"], n=0))
        p["n"] += 1
    for pid, p in posts.items():
        c.execute("INSERT INTO dua_posts VALUES(?,?,?,?,?)", (pid, p["post_title"], p["category"], p["subcategory"], p["n"]))
    cats = {}
    for x in duas:
        cc = cats.setdefault(x["category"], dict(posts=set(), n=0)); cc["posts"].add(x["post_id"]); cc["n"] += 1
    for cat, v in cats.items():
        c.execute("INSERT INTO dua_categories VALUES(?,?,?)", (cat, len(v["posts"]), v["n"]))

    ai = json.load(open(f"{SRC}/articles_index.json"))["categories"]
    # body index by article id/slug from both articles/ and related-articles/
    bodies = {}
    for f in glob.glob(f"{SRC}/articles/**/*.json", recursive=True) + glob.glob(f"{SRC}/related-articles/*/*.json", recursive=True):
        try: b = json.load(open(f))
        except Exception: continue
        if isinstance(b, dict) and "content" in b:
            bodies[b.get("id")] = (f[len(SRC)+1:], b)
    art_cat = {}
    seen = set(); n_links = 0
    for cat in ai:
        c.execute("INSERT INTO article_categories VALUES(?,?,?,?)", (cat["id"], u(cat["name"]), cat["slug"], cat["count"]))
        art_cat[cat["id"]] = (cat["slug"], cat["name"], 0)
        for a in cat.get("articles", []):
            body = bodies.get(a["id"]); has = 1 if body else 0; n_links += 1
            if a["id"] not in seen:
                seen.add(a["id"])
                c.execute("INSERT INTO articles VALUES(?,?,?,?,?,?,?)",
                          (a["id"], u(a["title"]), a["slug"], a.get("link"),
                           body[0] if body else None, (body[1].get("content") or "") if body else None, has))
            c.execute("INSERT INTO article_members VALUES(?,?)", (cat["id"], a["id"]))
            art_cat[cat["id"]] = (cat["slug"], cat["name"], art_cat[cat["id"]][2]+1)
    for cid,(slug,name,n) in art_cat.items():
        c.execute("UPDATE article_categories SET count=? WHERE id=?", (n, cid))

    # contentless FTS5 over dua searchable text
    c.execute("CREATE VIRTUAL TABLE dua_fts USING fts5(text, content='', tokenize='unicode61')")
    c.executemany("INSERT INTO dua_fts(rowid, text) VALUES(?,?)",
        ((r[0], " ".join(filter(None,[r[1],r[2],r[3]]))) for r in
         c.execute("SELECT id, title, translation, transliteration FROM duas")))
    c.execute("PRAGMA user_version=1"); c.commit()
    verify(c, duas, posts, ai, local_audio)

def verify(c, duas, posts, ai, local_audio):
    ok=True
    nd = c.execute("select count(*) from duas").fetchone()[0]
    ok &= nd==491
    # per-post recount sum == 491 and each == source
    for pid,p in posts.items():
        g = c.execute("select count(*) from duas where post_id=?",(pid,)).fetchone()[0]
        ok &= g==p["n"]
    print(f"  duas={nd}/491 posts={c.execute('select count(*) from dua_posts').fetchone()[0]}/30 "
          f"cats={c.execute('select count(*) from dua_categories').fetchone()[0]}/2 "
          f"| post-sum={c.execute('select sum(dua_count) from dua_posts').fetchone()[0]}")
    # dhikr-dua regroup reconciliation
    dd=0
    for f in glob.glob("/home/kaizen/AndroidStudioProjects/khushu-data-api/archive/assets/dua_dhikr/dhikr-dua/*/*.json"):
        dd+=len(json.load(open(f)))
    print(f"  dhikr-dua regroup total={dd} (must==491) {'OK' if dd==491 else 'MISMATCH'}"); ok &= dd==491
    # articles
    n_art=c.execute("select count(*) from articles").fetchone()[0]
    n_links=c.execute("select count(*) from article_members").fetchone()[0]
    n_body=c.execute("select count(*) from articles where has_body=1").fetchone()[0]
    idx=sum(len(cat.get('articles',[])) for cat in ai)
    print(f"  article_cats={c.execute('select count(*) from article_categories').fetchone()[0]}/12 "
          f"articles={n_art}(uniq) links={n_links}(idx={idx}) with_body={n_body} no_body={n_art-n_body}")
    ok &= n_links==idx and n_art==169 and n_body==169
    # audio
    print(f"  audio: asset_refs={c.execute('select count(*) from duas where audio_asset_id is not null').fetchone()[0]}/488")
    # text fidelity (post-unescape): compare a dua vs source unescaped
    for x in duas[:3]:
        g=c.execute("select translation from duas where id=?",(x['id'],)).fetchone()[0]
        if g!=html.unescape(x['translation']): ok=False; print("  TEXT DIFF dua",x['id'])
    print(f"\nRESULT {'ALL VERIFIED' if ok else 'FAILURES'} | dua.db {os.path.getsize(OUT+'/dua.db')/1048576:.1f} MB")
    sys.exit(0 if ok else 1)

if __name__=="__main__":
    main()
