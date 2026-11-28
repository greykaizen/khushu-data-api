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
REPO="${KHUSHU_ASSET_REPO:-greykaizen/khushu-data-api}"
ONLY_FAMILY="${ONLY_FAMILY:-}"
MAN="data/manifest/packs.json"
PACKS="data/packs"
[ -f "$MAN" ] || { echo "no packs.json — run: python3 deployment/build_packs.py"; exit 1; }
APPLY="${APPLY:-0}"

# Group files by (family, pack version) just like audit_release.py.
python3 - "$MAN" "$PACKS" "$ONLY_FAMILY" "/tmp/packrev.$$" <<'PY' > /tmp/packfams.$$
import json, sys, os
m, pdir, only, rev_path = json.load(open(sys.argv[1])), sys.argv[2], sys.argv[3], sys.argv[4]
target_rev = m.get("version", "v2026.11")
fam = {}
for p in m["packs"]:
    if only and p["family"] != only:
        continue
    key = (p["family"], p.get("version") or target_rev)
    fam.setdefault(key, []).append(os.path.join(pdir, p["file"]))
for (f, ver), files in sorted(fam.items()):
    total = sum(os.path.getsize(x) for x in files)
    print(f"{f}\t{ver}\t{len(files)}\t{total}\t" + " ".join(files))
with open(rev_path, "w") as rf:
    rf.write(target_rev)
PY
TARGET_REV="$(cat /tmp/packrev.$$)"; rm -f /tmp/packrev.$$
REV="${KHUSHU_ASSET_REV:-$TARGET_REV}"

echo "== packs to publish (target_rev=$REV repo=$REPO only=${ONLY_FAMILY:-all}) APPLY=$APPLY =="
while IFS=$'\t' read -r fam ver n size files; do
  tag="packs-$fam-$ver"
  printf "  %-12s %-8s %3d files  %6.1f MB  -> release %s\n" "$fam" "$ver" "$n" "$(awk -v s="$size" 'BEGIN{print s/1048576}')" "$tag"
  if [ "$APPLY" = "1" ]; then
    # Published revisions are immutable: hosts and prebundle stamps key off the
    # tag, so overwriting one leaves every installed copy silently stale while
    # reporting the "same" version. Unchanged older revisions skip cleanly; the
    # target bump refuses to overwrite unless FORCE=1.
    if gh release view "$tag" --repo "$REPO" >/dev/null 2>&1; then
      if [ "${FORCE:-0}" != "1" ]; then
        if [ "$ver" != "$REV" ] && [ -z "$ONLY_FAMILY" ]; then
          echo "    - skip immutable $tag (already live)"
          continue
        fi
        echo "ERROR: release $tag already exists." >&2
        echo "       Bump pack version (e.g. v2026.13) for changed pack bytes." >&2
        echo "       FORCE=1 is only for repairing a broken upload of the same bytes." >&2
        exit 1
      fi
      gh release delete "$tag" --repo "$REPO" --yes --cleanup-tag 2>/dev/null || true
    fi
    # shellcheck disable=SC2086
    gh release create "$tag" $files --repo "$REPO" --title "Khushu offline packs ($fam) $ver" \
      --notes "Prebuilt pack-level SQLite fragments ($fam). GPLv3 corpus. Open with libSQL/SQLite; FTS5 included where applicable. See data/manifest/packs.json."
    echo "    ✔ published $tag"
  fi
done < /tmp/packfams.$$
rm -f /tmp/packfams.$$
[ "$APPLY" = "1" ] && echo "DONE — all pack releases live. Verify with: python3 deployment/audit_release.py" || echo "DRY RUN — re-run with APPLY=1 to publish (after device validation)."
