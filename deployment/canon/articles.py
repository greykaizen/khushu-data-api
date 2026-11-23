#!/usr/bin/env python3
"""Canonical cleanup for the long-form reading corpus.

The source pages were captured as rendered HTML. Two classes of defects matter
for the app's native reader:

* transliterated devotional formulas (``raḍiy Allāhu ʿanhu``, ``subḥānahū wa
  taʿālā``) read as untranslated English inside an otherwise Arabic-aware
  article. They are replaced with their Arabic form;
* some pages wrap their whole body in an invalid ``<p><div>…</div></p>``
  shell. The native parser tolerates it, but it produces an artificial leading
  paragraph and a stray trailing one. Remove only that outer wrapper.

The transformation is intentionally narrow: prose, quotations, links and all
other markup are preserved verbatim.
"""
from __future__ import annotations

import glob
import json
import re
import sys
from pathlib import Path

HONORIFICS: list[tuple[re.Pattern[str], str | callable]] = [
    (
        re.compile(
            r"\b(?:ra[ḍd][iī](?:y|ya)?|radhi|radi)(?:\s*all[aā]h[uū]?)?\s*[‘'ʿ]?\s*(anh[uū]|anh[aā]|anhum[aā]?|anhum|anuhm[aā])\b",
            re.IGNORECASE,
        ),
        lambda m: "رضي الله " + {
            "anha": "عنها", "anhā": "عنها",
            "anhuma": "عنهما", "anhumā": "عنهما", "anuhmā": "عنهما",
            "anhum": "عنهم",
        }.get(m.group(1).lower(), "عنه"),
    ),
    (
        re.compile(
            r"\b(?:all[aā]h[uū]?\s+)?(?:sub[ḥh][aā](?:na)?(?:h[uū])?)\s*(?:wa\s+)?ta[‘'ʿ]?[aā]l[aā]\b",
            re.IGNORECASE,
        ),
        "سبحانه وتعالى",
    ),
    (re.compile(r"\(\s*swt\s*\)", re.IGNORECASE), "سبحانه وتعالى"),
    (
        re.compile(
            r"\b(?:ṣall[aā]|sall[aā]|sal)[aā]?h?u?\s*all[aā]h[uū]?\s*[‘'ʿ]?\s*alayhi\s*(?:wa\s*)?sallam\b",
            re.IGNORECASE,
        ),
        "ﷺ",
    ),
    (re.compile(r"\(\s*saw\s*\)", re.IGNORECASE), "ﷺ"),
    (re.compile(r"\bpeace be upon him\b", re.IGNORECASE), "ﷺ"),
    (re.compile(r"\bra[ḥh][iī]mahull[aā]h\b", re.IGNORECASE), "رحمه الله"),
    (re.compile(r"\b[‘'ʿ]?alayhi(?:s|hi)?[- ]?sal[aā]m\b", re.IGNORECASE), "عليه السلام"),
    (re.compile(r"\b[‘'ʿ]?azza wa jall\b", re.IGNORECASE), "عز وجل"),
]


HONORIFIC_WORDS = r"(?:رضي الله (?:عنه|عنها|عنهما|عنهم)|سبحانه وتعالى|رحمه الله|عليه السلام|عز وجل|ﷺ)"
HONORIFIC_PARENS = re.compile(r"\(\s*(%s)\s*\)" % HONORIFIC_WORDS)
HONORIFIC_OPEN = re.compile(r"\(\s*(?=%s)" % HONORIFIC_WORDS)
HONORIFIC_CLOSE = re.compile(r"(%s)\s*\)" % HONORIFIC_WORDS)


def clean_text(value: str) -> str:
    out = value or ""
    for pattern, replacement in HONORIFICS:
        out = pattern.sub(replacement, out)
    out = HONORIFIC_PARENS.sub(r"\1", out)
    out = HONORIFIC_OPEN.sub("", out)
    return HONORIFIC_CLOSE.sub(r"\1", out)


def clean_html(value: str) -> str:
    out = clean_text(value or "")
    out = re.sub(r"(?i)</?br\s*/?>", "<br>", out)
    # Invalid outer paragraph around block content (47 source pages).
    stripped = out.strip()
    if stripped.lower().startswith("<p><div") and stripped.endswith("</p>"):
        inner = stripped[3:-4].strip()
        if inner.startswith("<div") and inner.endswith("</div>"):
            out = inner
    # A paragraph directly around a table is equally invalid.
    out = re.sub(r"(?is)<p>\s*(<table\b.*?</table>)\s*</p>", r"\1", out)
    return out


def clean_article(path: Path) -> bool:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return False
    changed = False
    for field in ("title", "content"):
        if isinstance(data.get(field), str):
            cleaned = clean_html(data[field]) if field == "content" else clean_text(data[field])
            if cleaned != data[field]:
                data[field] = cleaned
                changed = True
    if changed:
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return changed


def _article_files(root: Path) -> list[Path]:
    return [
        Path(p)
        for p in glob.glob(str(root / "**" / "*.json"), recursive=True)
        if Path(p).name != "index.json"
        and any("articles" in part for part in Path(p).parts)
    ]


def main(argv: list[str]) -> int:
    roots = [Path(arg) for arg in argv[1:]]
    if not roots:
        roots = [Path(__file__).resolve().parents[2] / "archive" / "assets" / "dua_dhikr"]
    changed = 0
    total = 0
    for root in roots:
        for path in _article_files(root):
            total += 1
            if clean_article(path):
                changed += 1
    print(f"cleaned {changed}/{total} article files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
