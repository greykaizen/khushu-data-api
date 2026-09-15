#!/usr/bin/env bash
# Publish hosted binary assets as SEVEN kind-scoped GitHub Releases (GitHub caps
# a single release at 1000 assets; 1489 exceeds it). Kind counts (from manifest):
#   adhan-audio 178 | dua-audio 488 | names-audio 99 | font 614 | glyph-atlas 3
#   topic-image 65  | curated-science 43    → every per-kind release is well
# under 1000 and per-file random access is preserved (no client-side tarballs).
#
# Release tag scheme: assets-<kind>-<rev>  (rev = KHUSHU_ASSET_RELEASE_REV).
# Asset URL template stored in .env / manifest: ASSET_BASE_URL_TEMPLATE.
# DRY RUN unless APPLY=1.
set -euo pipefail; cd "$(dirname "$0")/.."
[ -f .env ] && set -a && . ./.env && set +a
REPO="${KHUSHU_ASSET_REPO:-greykaizen/khushu-data-api}"
REV="${KHUSHU_ASSET_RELEASE_REV:-v2026.09}"
STAGE="data/assets"
MANIFEST="data/manifest/assets.json"
python3 - "$MANIFEST" "$STAGE" "$REV" <<'PY'   # flatten to release-name per kind -> data/assets/.upload/<kind>/
import json,os,sys,shutil
manifest,stage,rev=sys.argv[1],sys.argv[2],sys.argv[3]
m=json.load(open(manifest)); out=".upload"; 
if os.path.isdir(out): shutil.rmtree(out); os.makedirs(out)
byk={}
for e in m["assets"]:
    src=os.path.join(stage,e["asset_id"])
    if not os.path.exists(src): print("MISS",src); continue
    k=e["kind"]; os.makedirs(os.path.join(out,k),exist_ok=True)
    shutil.copy2(src, os.path.join(out,k,e["release_name"]))
    byk.setdefault(k,0); byk[k]+=1
print("staged:",byk,"total:",sum(byk.values()))
PY
upload(){ local kind="$1" rev="$2"; local tag="assets-${kind}-${rev}"; local dir=".upload/${kind}"; [ -d "$dir" ] || return
  local count=$(ls "$dir" | wc -l)
  echo ">> $kind ($count files) -> $tag"
  if [ "${APPLY:-0}" = "1" ]; then
    gh release view "$tag" --repo "$REPO" >/dev/null 2>&1 \
      || gh release create "$tag" --repo "$REPO" --title "Khushu assets $kind $rev" --notes "Kind-scoped asset release (GitHub caps 1000 assets/release)."
    find "$dir" -maxdepth 1 -type f -print0 | xargs -0 -n 200 gh release upload "$tag" --repo "$REPO" --clobber
  fi
}
if [ "${APPLY:-0}" != "1" ]; then echo "DRY RUN — would create up to 7 releases (assets-<kind>-$REV). Set APPLY=1 to publish."; exit 0; fi
for k in adhan-audio dua-audio names-audio font glyph-atlas topic-image curated-science; do upload "$k" "$REV"; done
echo "base URL template: https://github.com/$REPO/releases/download/assets-{kind}-$REV/{release_name}"
