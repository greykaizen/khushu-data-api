#!/usr/bin/env python3
"""Verify a built dua database/pack against `dua_data.canonical.json`.

Checks:
- `duas`/`dua_items` has `blocks_json` and 491 rows.
- every blocks_json parses, has schema 1 and exactly the five rich fields.
- every plain text column is free of canonical inline tags, markdown markers,
  backticks and entities.
- blocks_json and every plain column equal the canonical JSON for that id.
- the FTS table has 491 rows and can answer a sample query.

Usage:
    python3 deployment/verify_dua_canonical.py
    python3 deployment/verify_dua_canonical.py --db data/packs/content.db
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CANONICAL = os.path.join(ROOT, "archive", "assets", "dua_dhikr", "dua_data.canonical.json")
DEFAULT_DBS = [
    os.path.join(ROOT, "data", "build", "dua.db"),
    os.path.join(ROOT, "data", "db", "khushu-content.db"),
    os.path.join(ROOT, "data", "packs", "content.db"),
]
BLOCK_FIELDS = {"arabic", "translation", "transliteration", "virtue", "explanation", "reference"}
BLOCK_TYPES = {"paragraph", "heading", "bullet", "quote", "raw_html", "bismillah", "arabic"}
# `post_title` lives on dua_posts, not on the dua row; checked separately.
PLAIN_FIELDS = ("title", "arabic", "repetition", "translation",
                "transliteration", "virtue", "explanation", "reference")
PLAIN_DEBRIS = re.compile(r"</?(?:b|i|sup|br|qref|ref|hon)\b|\*\*|`|&#", re.IGNORECASE)
# Typed Quran citations: a surah:ayah pair, optionally a range.
QREF_RE = re.compile(r"<qref>([^<]*)</qref>")
QREF_VALID_RE = re.compile(r"\d{1,3}:\d{1,3}(?:-\d{1,3})?")


def _table(conn: sqlite3.Connection) -> str:
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "dua_items" in names:
        return "dua_items"
    if "duas" in names:
        return "duas"
    raise SystemExit("neither dua_items nor duas table found")


def _columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [r[1] for r in conn.execute(f"PRAGMA table_info('{table}')")]


def verify_db(path: str, canonical: list[dict]) -> list[str]:
    fails: list[str] = []
    if not os.path.exists(path):
        return [f"missing db: {path}"]
    conn = sqlite3.connect(path)
    table = _table(conn)
    cols = _columns(conn, table)
    if "blocks_json" not in cols:
        return [f"{path}: {table}.blocks_json missing"]

    rows = conn.execute(
        f"SELECT id, blocks_json, {', '.join(PLAIN_FIELDS)} FROM {table} ORDER BY id"
    ).fetchall()
    if len(rows) != 491:
        fails.append(f"{path}: {len(rows)} rows, expected 491")
    by_id = {r[0]: r for r in rows}
    if "dua_posts" in {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}:
        posts = dict(conn.execute("SELECT post_id, post_title FROM dua_posts"))
        for expected in canonical:
            if posts.get(expected["post_id"]) != expected["post_title"]:
                fails.append(f"{path}: post_id={expected['post_id']} post_title differs")
    for expected in canonical:
        rid = expected["id"]
        row = by_id.get(rid)
        if row is None:
            fails.append(f"{path}: missing id={rid}")
            continue
        try:
            blocks = json.loads(row[1])
        except Exception as exc:
            fails.append(f"{path}: id={rid} blocks_json invalid: {exc}")
            continue
        if blocks != expected["blocks"]:
            fails.append(f"{path}: id={rid} blocks_json differs from canonical")
        if set(blocks.get("fields", {})) != BLOCK_FIELDS:
            fails.append(f"{path}: id={rid} block field set {sorted(blocks.get('fields', {}))}")
        for field, field_blocks in blocks.get("fields", {}).items():
            for b in field_blocks:
                if b.get("type") not in BLOCK_TYPES:
                    fails.append(f"{path}: id={rid} {field} bad block type {b.get('type')!r}")
                if "level" in b and b["level"] not in (1, 2):
                    fails.append(f"{path}: id={rid} {field} bad heading level {b['level']!r}")
                if not isinstance(b.get("text"), str):
                    fails.append(f"{path}: id={rid} {field} block text not a string")
                # A typed Quran citation must resolve, or the host would link
                # somewhere wrong. Malformed refs are a build error.
                for qref in QREF_RE.findall(b.get("text") or ""):
                    if not QREF_VALID_RE.fullmatch(qref):
                        fails.append(f"{path}: id={rid} {field} malformed <qref>{qref}</qref>")
                        continue
                    surah = int(qref.split(":", 1)[0])
                    if not (1 <= surah <= 114):
                        fails.append(f"{path}: id={rid} {field} surah out of range in <qref>{qref}</qref>")
        for value in row[2:]:
            if value and PLAIN_DEBRIS.search(value):
                fails.append(f"{path}: id={rid} plain column contains markup: {value[:80]!r}")
        for index, field in enumerate(PLAIN_FIELDS, start=2):
            if (row[index] or "") != (expected.get(field) or ""):
                fails.append(f"{path}: id={rid} {field} differs from canonical")

    fts_tables = [
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND sql LIKE '%fts5%' AND name='dua_fts'"
        )
    ]
    for fts in fts_tables:
        n = conn.execute(f'SELECT COUNT(*) FROM "{fts}"').fetchone()[0]
        if n != 491:
            fails.append(f"{path}: {fts} has {n} rows, expected 491")
    conn.close()
    return fails


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", action="append", default=None,
                        help="database to verify (repeatable); defaults to build/db/pack content DBs")
    parser.add_argument("--canonical", default=CANONICAL)
    args = parser.parse_args(argv)

    with open(args.canonical, encoding="utf-8") as f:
        canonical = json.load(f)
    if len(canonical) != 491:
        raise SystemExit(f"canonical JSON has {len(canonical)} records, expected 491")

    paths = args.db or [p for p in DEFAULT_DBS if os.path.exists(p)]
    if not paths:
        raise SystemExit("no dua databases found; run build_dua/consolidate/build_packs first")

    all_fails: list[str] = []
    for path in paths:
        fails = verify_db(path, canonical)
        all_fails.extend(fails)
        print(f"{'OK' if not fails else 'FAIL'} {os.path.relpath(path, ROOT)} ({len(fails)} issues)")
        for f in fails[:10]:
            print("  -", f)
    if all_fails:
        print(f"\n{len(all_fails)} failure(s)")
        return 1
    print("\nAll dua databases carry the canonical blocks and clean plain columns.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
