#!/usr/bin/env bash
# Import the 4 consolidated production DBs into the Turso group. DRY RUN unless APPLY=1.
# Also retires the pre-existing `quran` TEST db (byte-identical to canonical, verified)
# so the group holds exactly the 4 reproducible DBs. Scoped to $KHUSHU_TURSO_GROUP.
set -euo pipefail; cd "$(dirname "$0")/.."
[ -f .env ] && set -a && . ./.env && set +a
export TURSO_API_TOKEN="${KHUSHU_TURSO_API_TOKEN:?set KHUSHU_TURSO_API_TOKEN in .env}"
GROUP="${KHUSHU_TURSO_GROUP:-khushu}"; TURSO="${TURSO_BIN:-$HOME/.turso/turso}"
EXISTING="$("$TURSO" db list | awk 'NR>1{print $1}')"
exists(){ printf '%s\n' "$EXISTING" | grep -qx "$1"; }
for name in khushu-quran khushu-tafsir khushu-wbw khushu-hadith khushu-content khushu-audio; do
  f="data/db/$name.db"
  python3 -c "import sqlite3,sys;c=sqlite3.connect(sys.argv[1]);assert c.execute('pragma integrity_check').fetchone()[0]=='ok';assert c.execute('pragma journal_mode').fetchone()[0]=='wal';print('   verified',sys.argv[1])" "$f"
  if exists "$name"; then act=REPLACE; else act=CREATE; fi
  echo "  $name: $act"
  if [ "${APPLY:-0}" = "1" ]; then
    [ "$act" = REPLACE ] && "$TURSO" db destroy "$name" --yes
    "$TURSO" db import "$f" --group "$GROUP"
  fi
done
if [ "${APPLY:-0}" = "1" ] && exists "quran"; then
  echo "  retiring superseded test db 'quran' (its data now lives in khushu-quran)"
  "$TURSO" db destroy quran --yes || "$TURSO" db delete quran --yes || echo "  (manual: turso db delete quran)"
fi
[ "${APPLY:-0}" = "1" ] || echo "DRY RUN — no changes; set APPLY=1 to import the 4 + retire 'quran'."
