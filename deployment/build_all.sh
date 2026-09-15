#!/usr/bin/env bash
# Reproducible build pipeline: donor/archived source -> 21 domain DBs (data/build)
# -> 6 consolidated production DBs (data/db) -> WAL-ready. Deterministic; no deploy.
set -euo pipefail; cd "$(dirname "$0")/.."
mkdir -p data/build data/db
for b in build_assets build_quran build_sunnah build_translations build_tafsir build_dua build_names build_chapters build_rest build_catalog; do
  echo ">> $b"; python3 "deployment/builders/$b.py" >/dev/null
done
echo ">> consolidate (21 -> 4)"; python3 deployment/consolidate.py >/dev/null
echo ">> WAL + integrity (data/db)"; python3 deployment/builders/make_turso_ready.py
echo ">> offline pack fragments (data/packs -> 104)"; python3 deployment/build_packs.py
echo ">> verify packs are lossless re-shard"; python3 deployment/validate_packs.py
echo "Done: 6 production DBs in data/db/
