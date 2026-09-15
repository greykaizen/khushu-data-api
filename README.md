# khushu-data

Khushu's content distribution. **Four** consolidated SQLite databases live in
Turso; all audio/font/atlas/image blobs live on a configurable static host
(GitHub Releases now, R2/CDN later); Quran recitation audio stays on its
external CDN. Consumers resolve a file from a DB `asset_id` + one base URL —
never a hardcoded URL.

> Historical source corpus (`inventory/`, `assets/`, extraction `tools/`,
> format `docs/`) is preserved under [`archive/`](archive/) for provenance only —
> it is **not** the runtime source. The JitPack library was retired (absorbed
> into [khushu-orchestrator](https://github.com/greykaizen/khushu-orchestrator)).

## Production topology — 6 databases
```
Khushu app
  ├─ khushu-quran.db    Quran (text/words/layout/nav/topics/similar/search FTS5) +
  │                     translations (markers preserved, FTS5) + `assets` registry. ~187 MB
  ├─ khushu-tafsir.db   Tafsir (verbatim HTML, range-keyed). Loaded on the tafsir feature. ~328 MB
  ├─ khushu-wbw.db      Word-by-word glosses + translit. Loaded on wbw/mushaf feature. ~118 MB
  ├─ khushu-hadith.db   9 Sunnah collections (namespaced bukhari_*…) + scholars, per-collection FTS5. ~188 MB
  ├─ khushu-content.db  dua (FTS5) + articles + 99 Names + events + curated/science + `assets`. ~3 MB
  └─ khushu-audio.db    reciter metadata (external audio URLs) + timings + adhan metadata + `assets`. ~8 MB
GitHub Release assets   audio/fonts/atlas/images  (asset_id → release_name → base URL)
External CDN            Quran recitation audio (quranicaudio.com) — by design
```
Table inventory + FTS list per DB is generated in `data/manifest/dbs.json`.

## Asset model (the contract)
`asset_id` (canonical logical path, e.g. `names/muqaddim.opus`, `fonts/kfqpc/page_151.ttf`)
→ stored in domain tables (e.g. `names_names.audio_asset_id`, `dua_items.audio_asset_id`,
`adhans.asset_id`, `quran_topics.image_asset_id`) → resolved against the **`assets`**
table (in `khushu-core`): `asset_id, release_name, relative_path, sha256, size, mime, version`.
App resolves `https://github.com/<repo>/releases/download/assets-<kind>-<rev>/<release_name>`
(assets ship as **7 per-kind releases** — GitHub caps 1000 assets/release and we
have 1,489 files) and verifies `sha256`. `kind`/`release_name` come from the
`assets` table; `release_name` is a flat path-encoded name generated at publish
so `data/assets/` stays an organized canonical tree.
Swapping GitHub → R2 is a **single base-URL change**. Intentional external URLs
(recitation CDN, article source links) are stored as-is and documented, never
routed through the asset host.

## Repository layout
```
data/
  db/            THE 4 production .db files (gitignored; rebuilt by build_all.sh)
  build/         21 intermediate per-domain DBs (gitignored)
  manifest/      dbs.json · assets.json · assets.csv · schema-plan.md
  assets/        canonical organized staging tree (gitignored; hardlinks)
deployment/
  builders/      build_*.py (donor → per-domain DB, donor-first + verified)
  consolidate.py builds the 4 from the 21 with namespacing + FTS rebuild (not file concat)
  build_all.sh   source → data/build → data/db (4) → WAL; deterministic
  build_release.py  asset manifest + collision-free release_name + staging
  make_turso_ready.py  WAL + checkpoint so `turso db import` accepts them
  publish_assets.sh / import_to_turso.sh / verify_deploy.py   (all DRY RUN unless APPLY=1)
archive/         historical source corpus + tools + docs (provenance only)
.env.example     variable names/placeholders   .env  real creds (gitignored)
```

## Local development
Requires: `python3` (system sqlite ≥3.35 → FTS5 + `DROP COLUMN`; this repo uses 3.53),
`gh` (authenticated), `turso` CLI (`curl -sSfL https://get.tur.so/install.sh | bash`).
```bash
bash deployment/build_all.sh                       # rebuild the 4 DBs from source
sqlite3 data/db/khushu-core.db "select count(*) from quran_surahs"      # 114
sqlite3 data/db/khushu-hadith.db "select count(*) from bukhari_hadiths"  # 7277
```
Regenerate the asset manifest/staging: `python3 deployment/build_release.py`.

## Deployment (each script is DRY RUN unless `APPLY=1`)
```bash
bash deployment/publish_assets.sh            # report file count + bytes + plan
APPLY=1 bash deployment/publish_assets.sh    # gh release create + upload assets
bash deployment/import_to_turso.sh           # verify + plan (retires stale 'quran' test db)
APPLY=1 bash deployment/import_to_turso.sh   # import the 4; destroy+replace, retire 'quran'
python3 deployment/verify_deploy.py           # remote table/FTS checks after APPLY
```
The asset release tag must match `KHUSHU_ASSET_RELEASE_TAG`, `assets.version`, and
`asset_base_url` (one value; `assets.json` records it).

## App integration
Host [Khushu](https://github.com/greykaizen/khushu) consumes exactly four logical
DB endpoints (`core`/`hadith`/`content`/`audio`), configured centrally — never
scattered per feature. Asset resolution: `db → asset_id → assets.release_name →
ASSET_BASE_URL`. Recitation audio + article source links are external by design.

## Content licensing
Code GPLv3; per-pack content terms in [LICENSE-CONTENT.md](LICENSE-CONTENT.md)
(translations/tafsir/hadith carry per-publisher non-commercial terms + attribution).
