#!/usr/bin/env python3
"""Regenerate per-book hadith JSON text fields from the consolidated .db corpora.

WHY: the original per-book split stripped inline markup (qref/ref/br/i/sup)
from translation_text/arabic_text — the ONLINE reading path lost Quran
references inside hadith text, while the OFFLINE .db path (attachSunnah →
ContentMarkup) kept them. This tool rebuilds the two text fields from
hadith_contents.blocks_json with markup PRESERVED, in a canonical format:

  translation_text = "\\n\\n" + narrator + "\\n" + matn blocks joined by "\\n"
  arabic_text      = sanad + "\\n" + matn blocks joined by "\\n"

Every rewritten row is verified for SEMANTIC equality against the db source:
whitespace-insensitive, markup-tag-insensitive text must match exactly —
a mismatch aborts the tool (content is sacred, formatting is not).

Only files whose bytes change are rewritten. All other row fields untouched.
"""
import glob
import json
import re
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
COLLECTIONS = ["bukhari", "muslim", "abudawud", "tirmidhi", "nasai",
               "ibnmajah", "malik", "riyadussalihin", "forty"]

TAGS = re.compile(r"<[a-zA-Z]+[^>]*>|</[a-zA-Z]+>")
WS = re.compile(r"\s+")


COMMENTS = re.compile(r"<!--[\s\S]*?-->")


def semantic(text: str) -> str:
    """Whitespace-, markup- and comment-insensitive content fingerprint
    (HTML comments are pipeline annotations, never rendered content)."""
    return WS.sub("", TAGS.sub("", COMMENTS.sub("", text)))


def rebuild(blocks: list[dict]) -> list[str]:
    """Non-empty block texts in ORIGINAL order (a hadith may carry multiple
    sanad/matn segments — grouping by type would reorder the narration)."""
    return [b["text"].strip() for b in blocks if b["text"].strip()]


def variant_field(variant: str) -> str:
    """Translation-variant books carry their language in translation_text."""
    return "translation_text"


def main() -> int:
    total_changed = 0
    total_rows = 0
    for coll in COLLECTIONS:
        db_path = REPO / f"inventory/hadiths/{coll}.db"
        if not db_path.exists():
            print(f"skip (no db): {coll}")
            continue
        conn = sqlite3.connect(db_path)
        contents = {(h, l): b for h, l, b in conn.execute("SELECT hadith_id, lang, blocks_json FROM hadith_contents")}
        changed_files = 0
        changed_rows = 0
        for book_file in sorted(glob.glob(str(REPO / f"inventory/hadiths/{coll}/books*/**.json"), recursive=True)):
            rows = json.load(open(book_file, encoding="utf-8"))
            file_changed = False
            for row in rows:
                norm = book_file.replace("\\", "/")
                variant = ("ar" if "books_ar/" in norm else
                           "bn" if "books_bn/" in norm else
                           "fr" if "books_fr/" in norm else
                           "ur" if "books_ur/" in norm else None)
                rebuilt = {}
                total_rows += 1
                if variant is None:
                    # default books/: arabic_text ← ar blocks, translation_text ← en blocks
                    ar_b = contents.get((row["id"], "ar"))
                    en_b = contents.get((row["id"], "en"))
                    if ar_b:
                        parts = rebuild(json.loads(ar_b))
                        if parts: rebuilt["arabic_text"] = "\n".join(parts)
                    if en_b:
                        parts = rebuild(json.loads(en_b))
                        if parts: rebuilt["translation_text"] = "\n\n" + "\n".join(parts)
                else:
                    blocks_json = contents.get((row["id"], variant))
                    if blocks_json is None:
                        continue  # db carries no such lang — file keeps its own text
                    parts = rebuild(json.loads(blocks_json))
                    if parts: rebuilt["translation_text"] = "\n\n" + "\n".join(parts)
                # semantic verification — abort hard on any content drift
                for field, new in rebuilt.items():
                    if semantic(new) != semantic(row.get(field, "")):
                        print(f"FATAL content drift: {coll} {row['id']} field={field}", file=sys.stderr)
                        print("  db :", repr(semantic(new))[:120], file=sys.stderr)
                        print("  old:", repr(semantic(row.get(field, '')))[:120], file=sys.stderr)
                        return 1
                text_changed = any(row.get(k) != v for k, v in rebuilt.items())
                if text_changed:
                    for k, v in rebuilt.items():
                        row[k] = v
                    file_changed = True
                    changed_rows += 1
            if file_changed:
                with open(book_file, "w", encoding="utf-8") as f:
                    json.dump(rows, f, ensure_ascii=False)
                changed_files += 1
        print(f"{coll}: {changed_rows} rows restored, {changed_files} files rewritten")
        total_changed += changed_files
    print(f"TOTAL: {total_changed} files rewritten, {total_rows} rows verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
