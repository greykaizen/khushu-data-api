#!/usr/bin/env bash
# Publish offline pack fragments to GitHub Releases.
#
# GitHub caps a single release at 1000 assets; we have ~104, so ONE release works,
# but we group by family for clean versioning + partial re-release (matches the
# pack_url_template packs-<family>-<rev> in data/manifest/packs.json).
#
# DRY-RUN BY DEFAULT. This publishes ~830 MB of generated binaries — pass APPLY=1
# to actually create/overwrite the releases. Kept gated: do NOT publish packs to GH
# until the app's libSQL client + FTS5 are validated on a real Android device
# (see docs/data-milestone-turso-plan.md §4 gate). The 6 master DBs + 7 asset
# releases are already live; packs are additive and safe to iterate.
set -euo pipefail; cd "$(dirname "$0")/.."
REV="${KHUSHU_ASSET_REV:-v2026.09}"
REPO="${KHUSHU_ASSET_REPO:-greykaizen/khushu-data-api}"
MAN="data/manifest/packs.json"
PACKS="data/packs"
[ -f "$MAN" ] || { echo "no packs.json — run: python3 deployment/build_packs.py"; exit 1; }
APPLY="${APPLY:-0}"

# group files by family
python3 - "$MAN" "$PACKS" <<'PY' > /tmp/packfams.$$
import json,sys,os
m,pdir=json.load(open(sys.argv[1])),sys.argv[2]
fam={}
for p in m["packs"]:
    fam.setdefault(p["family"],[]).append(os.path.join(pdir,p["file"]))
for f,files in sorted(fam.items()):
    total=sum(os.path.getsize(x) for x in files)
    print(f"{f}\t{len(files)}\t{total}\t"+" ".join(files))
PY

echo "== packs to publish (rev=$REV repo=$REPO) APPLY=$APPLY =="
while IFS=$'\t' read -r fam n size files; do
  tag="packs-$fam-$REV"
  printf "  %-12s %3d files  %6.1f MB  -> release %s\n" "$fam" "$n" "$(awk -v s="$size" 'BEGIN{print s/1048576}')" "$tag"
  if [ "$APPLY" = "1" ]; then
    # idempotent: delete+recreate so re-running updates cleanly
    gh release delete "$tag" --yes --cleanup-tag 2>/dev/null || true
    # shellcheck disable=SC2086
    gh release create "$tag" $files --title "Khushu offline packs ($fam) $REV" \
      --notes "Prebuilt pack-level SQLite fragments ($fam). GPLv3 corpus. Open with libSQL/SQLite; FTS5 included where applicable. See data/manifest/packs.json."
    echo "    ✔ published $tag"
  fi
done < /tmp/packfams.$$
rm -f /tmp/packfams.$$
[ "$APPLY" = "1" ] && echo "DONE — all pack releases live." || echo "DRY RUN — re-run with APPLY=1 to publish (after device validation)."
