#!/usr/bin/env bash
# Mirror AlfaazPlus/QuranAppInventory artifacts into this repo.
# Requires: curl · sha256sum
set -euo pipefail

BASE_RAW="https://raw.githubusercontent.com/AlfaazPlus/QuranAppInventory/master"
BASE_REL="https://github.com/AlfaazPlus/QuranAppInventory/releases/download"
DEST="$(cd "$(dirname "$0")/.." && pwd)/inventory"

echo "NOTE: verify actual paths against QuranApp source before running."
echo "  AtlasDownloadWorker.kt → atlas/{script}/{density}x.zip under master/atlas/"
echo "  ScriptFontsDownloadWorker.kt → releases/download/qpc/{file}"

download() {
    local url="$1" dest="$2"
    if [ -f "$dest" ]; then echo "SKIP $dest"; return; fi
    mkdir -p "$(dirname "$dest")"
    echo "GET  $url → $dest"
    curl -sL --retry 3 -o "$dest" "$url" || { echo "FAIL $url"; rm -f "$dest"; }
}

# Atlas bundles — uncomment after verifying paths:
# for script in qpc_hafs indopak_13 indopak_15 indopak_16 kfqpc_v1; do
#     for density in 1x 2x 3x; do
#         download "$BASE_RAW/atlas/$script/$density.zip" "$DEST/atlas/$script/$density.zip"
#     done
# done

# QPC fonts from releases:
# for f in KFGQPC-Uthmanic-Script-HAFS.zip; do
#     download "$BASE_REL/qpc/$f" "$DEST/fonts/qpc/$f"
# done

# WBW packs:
# for lang in en ur id fr; do
#     download "$BASE_RAW/wbw/wbw_${lang}.json.gz" "$DEST/wbw/packs/wbw_${lang}.json.gz"
# done

echo "=== regenerating MANIFEST.sha256 ==="
cd "$DEST" && find . -type f ! -name MANIFEST.sha256 -exec sha256sum {} \; > MANIFEST.sha256
echo "done."
