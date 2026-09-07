#!/usr/bin/env python3
"""Generate inventory/downloads_manifest.json — the batch-download ledger.

One row per downloadable file: repo-relative path, size in bytes, sha256.
Consumed by khushu-data-api's DownloadsApi to show byte totals BEFORE download
and verify integrity AFTER (CachingFetcher.ManifestRow.sha256).

Scope = real file units the host can plan against:
  inventory/hadiths/*/books{,_*}/  per-book hadith JSONs (per-language)
  inventory/hadiths/*.db           consolidated per-collection corpora (FTS)
  assets/dua_dhikr/dua_data.json   dua corpus (data)
  assets/dua_dhikr/dua_*.opus      dua audio
  inventory/asma_ul_husna/         per-language packs
  inventory/translations/*/        translation packs
  inventory/tafsirs/*/             tafsir packs
  inventory/wbw/                   word-by-word packs
  inventory/recitations/           recitation audio + timings
  inventory/quran_scripts/*.json.gz  script texts
Skips: _meta-only dirs, .git, build outputs, tools/.
"""
import hashlib
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "inventory" / "downloads_manifest.json"

INCLUDE_DIRS = [
    "inventory/hadiths",
    "assets/asma_ul_husna",
    "inventory/translations",
    "inventory/tafsirs",
    "inventory/wbw",
    "inventory/recitations",
    "inventory/quran_scripts",
    "inventory/fonts",
    "inventory/mushaf_layout",
    "inventory/atlas",
    "inventory/chapters",
    "inventory/other",
    "assets/dua_dhikr",
    "assets/islamic_calendar",
    "assets/adhan",
]
EXCLUDE_NAMES = {".git", "build", "tools", "docs", "url_tmp"}
EXCLUDE_FILES = {"downloads_manifest.json", "MANIFEST.sha256"}


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    rows = []
    for inc in INCLUDE_DIRS:
        root = REPO / inc
        if not root.exists():
            print(f"skip (missing): {inc}", file=sys.stderr)
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in EXCLUDE_NAMES and not d.startswith(".")]
            for name in filenames:
                if name in EXCLUDE_FILES or name.endswith((".tmp", ".zip.part")):
                    continue
                p = Path(dirpath) / name
                rel = p.relative_to(REPO).as_posix()
                rows.append(
                    {
                        "path": rel,
                        "bytes": p.stat().st_size,
                        "sha256": sha256_of(p),
                    }
                )

    rows.sort(key=lambda r: r["path"])
    total = sum(r["bytes"] for r in rows)
    doc = {
        "_meta": {
            "version": 1,
            "note": "batch-download ledger: one row per downloadable file; "
            "DownloadsApi plans + byte totals + sha256 verification read this",
            "rows": len(rows),
            "total_bytes": total,
        },
        "files": rows,
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")))
    print(f"rows={len(rows)} total={total/1e6:.1f} MB → {OUT.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
