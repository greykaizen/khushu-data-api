"""Command line entry point for dua content canonicalization.

Usage (from the khushu-data-api repo root):

    python3 -m deployment.canon.cli freeze
    python3 -m deployment.canon.cli canonicalize
    python3 -m deployment.canon.cli check

The source JSON is never modified. The first `freeze` copies it byte-for-byte
to `dua_data.original.json` and records its SHA-256; every later step abort if
the original or the source changes.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from .blocks import RICH_FIELDS
from .dua import (
    ALL_TEXT_FIELDS,
    build_goldens,
    canonicalize_record,
    dump_json,
    sha256_file,
    verify_against_goldens,
    verify_semantic_keys,
)
from .text import has_forbidden_markup, semantic_key

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = ROOT / "archive/assets/dua_dhikr/dua_data.json"
DEFAULT_ORIGINAL = ROOT / "archive/assets/dua_dhikr/dua_data.original.json"
DEFAULT_CANONICAL = ROOT / "archive/assets/dua_dhikr/dua_data.canonical.json"
DEFAULT_GOLDENS = ROOT / "deployment/goldens/dua_semantic_keys.json"
DEFAULT_REPORT_DIR = ROOT / "deployment/reports"


def _load(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _paths(args: argparse.Namespace) -> dict[str, Path]:
    return {
        "source": Path(args.source),
        "original": Path(args.original),
        "canonical": Path(args.canonical),
        "goldens": Path(args.goldens),
        "report_dir": Path(args.report_dir),
    }


def _ensure_original(paths: dict[str, Path]) -> str:
    source = paths["source"]
    original = paths["original"]
    if not original.exists():
        original.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, original)
        print(f"created {original.relative_to(ROOT)} (byte-for-byte copy)")
    src_sha = sha256_file(source)
    orig_sha = sha256_file(original)
    if src_sha != orig_sha:
        raise SystemExit(
            "source and original differ; refusing to continue.\n"
            f"  source:   {src_sha}\n"
            f"  original: {orig_sha}\n"
            "Restore the source from git or investigate before re-freezing."
        )
    return src_sha


def cmd_freeze(args: argparse.Namespace) -> int:
    paths = _paths(args)
    source_sha = _ensure_original(paths)
    records = _load(paths["original"])
    if not isinstance(records, list):
        raise SystemExit("dua_data.original.json must be a JSON array")
    goldens = build_goldens(records, source_sha)
    paths["goldens"].parent.mkdir(parents=True, exist_ok=True)
    dump_json(str(paths["goldens"]), goldens)
    print(
        f"froze {len(records)} records x {len(ALL_TEXT_FIELDS)} fields -> "
        f"{paths['goldens'].relative_to(ROOT)}"
    )
    print(f"source sha256: {source_sha}")
    return 0


def _issue_counts(issues: list[dict]) -> dict[str, int]:
    return dict(Counter(i["severity"] for i in issues))


def _block_counts(records: list[dict]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for field in sorted(RICH_FIELDS):
        blocks = Counter()
        heading_levels = Counter()
        record_count = 0
        for rec in records:
            field_blocks = rec.get("blocks", {}).get("fields", {}).get(field, [])
            if field_blocks:
                record_count += 1
            for b in field_blocks:
                blocks[b["type"]] += 1
                if b["type"] == "heading":
                    heading_levels[str(b.get("level"))] += 1
        out[field] = {
            "records": record_count,
            "blocks": dict(blocks),
            "heading_levels": dict(heading_levels),
        }
    return out


def _write_report(
    paths: dict[str, Path],
    records: list[dict],
    issues: list[dict],
    mismatches: list[dict],
    source_sha: str,
    canonical_sha: str,
) -> None:
    paths["report_dir"].mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": 1,
        "source_sha256": source_sha,
        "canonical_sha256": canonical_sha,
        "record_count": len(records),
        "issue_counts": _issue_counts(issues),
        "issues": issues,
        "mismatches": mismatches,
        "blocks": _block_counts(records),
    }
    json_path = paths["report_dir"] / "dua_canonicalization_report.json"
    dump_json(str(json_path), payload)

    lines = [
        "# Dua canonicalization report",
        "",
        f"- records: {len(records)}",
        f"- source sha256: `{source_sha}`",
        f"- canonical sha256: `{canonical_sha}`",
        f"- issues: {_issue_counts(issues)}",
        f"- semantic-key mismatches: {len(mismatches)}",
        "",
        "## Block structure",
        "",
        "| field | records | blocks | headings |",
        "| --- | ---: | --- | --- |",
    ]
    for field, info in payload["blocks"].items():
        blocks = ", ".join(f"{k}={v}" for k, v in sorted(info["blocks"].items()))
        headings = ", ".join(f"h{k}={v}" for k, v in sorted(info["heading_levels"].items()))
        lines.append(f"| {field} | {info['records']} | {blocks} | {headings} |")

    lines += ["", "## Issues", ""]
    if not issues:
        lines.append("None.")
    else:
        for issue in issues:
            lines.append(
                f"- **{issue['severity']}** id={issue['id']} `{issue['field']}` "
                f"{issue['reason']}: {issue['excerpt'][:120]!r}"
            )

    lines += ["", "## Semantic-key mismatches", ""]
    if not mismatches:
        lines.append("None.")
    else:
        for m in mismatches:
            lines.append(f"- id={m['id']} `{m['field']}`")
            lines.append(f"  - source: `{m['source_key'][:200]}`")
            lines.append(f"  - canonical: `{m['canonical_key'][:200]}`")

    md_path = paths["report_dir"] / "dua_canonicalization_report.md"
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {json_path.relative_to(ROOT)}")
    print(f"wrote {md_path.relative_to(ROOT)}")


def _check_plain(records: list[dict]) -> list[dict]:
    bad: list[dict] = []
    for rec in records:
        for field in ALL_TEXT_FIELDS:
            value = rec.get(field) or ""
            if has_forbidden_markup(value):
                bad.append(
                    {
                        "id": rec.get("id"),
                        "field": field,
                        "reason": "markup_in_plain_projection",
                        "excerpt": value[:160],
                    }
                )
    return bad


def cmd_canonicalize(args: argparse.Namespace) -> int:
    paths = _paths(args)
    source_sha = _ensure_original(paths)
    goldens = _load(paths["goldens"])
    if goldens.get("source_sha256") != source_sha:
        raise SystemExit(
            "golden source sha256 does not match the original; run `freeze` first "
            "or restore the original."
        )
    originals = _load(paths["original"])
    issues: list[dict] = []
    canonical: list[dict] = []
    mismatches: list[dict] = []
    for original in originals:
        rec = canonicalize_record(original, issues)
        mismatches.extend(verify_semantic_keys(original, rec, strict=False))
        canonical.append(rec)

    if mismatches:
        first = mismatches[0]
        raise SystemExit(
            f"semantic key mismatch id={first['id']} field={first['field']}\n"
            f"  source:    {first['source_key'][:300]}\n"
            f"  canonical: {first['canonical_key'][:300]}"
        )

    verify_against_goldens(canonical, goldens, strict=True)
    plain_bad = _check_plain(canonical)
    if plain_bad:
        raise SystemExit(f"plain projection still contains markup: {plain_bad[:3]}")

    dump_json(str(paths["canonical"]), canonical)
    canonical_sha = sha256_file(paths["canonical"])
    print(f"wrote {paths['canonical'].relative_to(ROOT)} ({len(canonical)} records)")
    _write_report(paths, canonical, issues, mismatches, source_sha, canonical_sha)
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    paths = _paths(args)
    goldens = _load(paths["goldens"])
    canonical = _load(paths["canonical"])
    originals = _load(paths["original"])
    if len(canonical) != len(originals):
        raise SystemExit("canonical and original record counts differ")
    mismatches = verify_against_goldens(canonical, goldens, strict=False)
    plain_bad = _check_plain(canonical)
    if mismatches or plain_bad:
        for m in mismatches[:5]:
            print(f"MISMATCH id={m['id']} {m['field']}: {m['source_key'][:120]!r} != {m['canonical_key'][:120]!r}")
        for b in plain_bad[:5]:
            print(f"MARKUP id={b['id']} {b['field']}: {b['excerpt'][:120]!r}")
        raise SystemExit(f"check failed: {len(mismatches)} mismatches, {len(plain_bad)} markup violations")
    print(
        f"OK: {len(canonical)} records, {len(ALL_TEXT_FIELDS)} fields each, "
        "semantic keys match and plain projections are clean"
    )
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    paths = _paths(args)
    canonical = _load(paths["canonical"])
    goldens = _load(paths["goldens"])
    originals = _load(paths["original"])
    issues: list[dict] = []
    for original in originals:
        canonicalize_record(original, issues)
    mismatches = verify_against_goldens(canonical, goldens, strict=False)
    canonical_sha = sha256_file(paths["canonical"])
    _write_report(paths, canonical, issues, mismatches, goldens["source_sha256"], canonical_sha)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=str(DEFAULT_SOURCE))
    parser.add_argument("--original", default=str(DEFAULT_ORIGINAL))
    parser.add_argument("--canonical", default=str(DEFAULT_CANONICAL))
    parser.add_argument("--goldens", default=str(DEFAULT_GOLDENS))
    parser.add_argument("--report-dir", default=str(DEFAULT_REPORT_DIR))
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("freeze", help="copy the source once and freeze semantic keys")
    sub.add_parser("canonicalize", help="build the canonical JSON and report")
    sub.add_parser("check", help="verify canonical JSON against the frozen keys")
    sub.add_parser("report", help="regenerate the report from canonical JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return {
        "freeze": cmd_freeze,
        "canonicalize": cmd_canonicalize,
        "check": cmd_check,
        "report": cmd_report,
    }[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
