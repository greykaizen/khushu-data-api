"""Record-level dua canonicalization and verification."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from .blocks import canonical_blocks, plain_projection
from .text import has_forbidden_markup, normalize, semantic_key

# Fields that are rendered as plain strings, not blocks.
PLAIN_FIELDS = ("title", "post_title", "repetition")
# Fields that get a typed block representation. Arabic is included so the
# host can center each basmala and keep surah boundaries on their own lines;
# its plain column remains the clean copy/FTS projection.
BLOCK_FIELDS = (
    "arabic",
    "translation",
    "transliteration",
    "virtue",
    "explanation",
    "reference",
)
NORMALIZED_PLAIN_FIELDS = ()
ALL_TEXT_FIELDS = PLAIN_FIELDS + NORMALIZED_PLAIN_FIELDS + BLOCK_FIELDS

BLOCKS_SCHEMA = 1


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _issue(record_id: int, field: str, severity: str, reason: str, excerpt: str) -> dict:
    return {
        "id": record_id,
        "field": field,
        "severity": severity,
        "reason": reason,
        "excerpt": excerpt[:240],
    }


def canonicalize_record(record: dict[str, Any], issues: list[dict]) -> dict[str, Any]:
    """Return a copy of `record` with clean plain columns and typed blocks."""
    record_id = record.get("id", 0)
    out = dict(record)
    block_map: dict[str, list[dict]] = {}

    for field in ALL_TEXT_FIELDS:
        raw = record.get(field) or ""
        field_issues: list[dict] = []
        try:
            if field in PLAIN_FIELDS:
                out[field] = normalize(raw)
            else:
                blocks = canonical_blocks(field, raw, field_issues)
                out[field] = plain_projection(blocks)
                block_map[field] = blocks
        except Exception as exc:  # pragma: no cover - defensive build gate
            raise RuntimeError(f"canonicalization failed for id={record_id} field={field}: {exc}") from exc

        if has_forbidden_markup(out[field]):
            field_issues.append(
                {
                    "severity": "error",
                    "reason": "markup_in_plain_projection",
                    "excerpt": out[field][:160],
                }
            )
        for issue in field_issues:
            issues.append(_issue(record_id, field, **issue))

    # Non-text fields are copied unchanged (post_id, category, audio_url, ...).
    out["blocks"] = {"schema": BLOCKS_SCHEMA, "fields": block_map}
    return out


def verify_semantic_keys(
    original: dict[str, Any],
    canonical: dict[str, Any],
    *,
    strict: bool = True,
) -> list[dict]:
    """Compare formatting-insensitive keys before vs after.

    Returns a list of mismatch dicts. With `strict`, raises on the first one.
    """
    record_id = original.get("id", 0)
    mismatches: list[dict] = []
    for field in ALL_TEXT_FIELDS:
        src_key = semantic_key(original.get(field) or "")
        dst_key = semantic_key(canonical.get(field) or "")
        if src_key != dst_key:
            mismatches.append(
                {
                    "id": record_id,
                    "field": field,
                    "source_key": src_key,
                    "canonical_key": dst_key,
                }
            )
    if strict and mismatches:
        first = mismatches[0]
        raise ValueError(
            f"semantic key mismatch id={first['id']} field={first['field']}\n"
            f"  source:    {first['source_key'][:300]}\n"
            f"  canonical: {first['canonical_key'][:300]}"
        )
    return mismatches


def build_goldens(records: list[dict[str, Any]], source_sha256: str) -> dict[str, Any]:
    """Freeze per-field keys from the untouched source."""
    out: dict[str, Any] = {
        "schema": 1,
        "source_sha256": source_sha256,
        "fields": list(ALL_TEXT_FIELDS),
        "records": {},
    }
    for record in records:
        rid = str(record.get("id"))
        out["records"][rid] = {field: semantic_key(record.get(field) or "") for field in ALL_TEXT_FIELDS}
    return out


def verify_against_goldens(
    records: list[dict[str, Any]],
    goldens: dict[str, Any],
    *,
    strict: bool = True,
) -> list[dict]:
    """Verify canonical records against the frozen source keys."""
    mismatches: list[dict] = []
    expected = goldens.get("records", {})
    if len(expected) != len(records):
        raise ValueError(f"golden record count {len(expected)} != canonical record count {len(records)}")
    for record in records:
        rid = str(record.get("id"))
        if rid not in expected:
            raise ValueError(f"record id={rid} missing from goldens")
        for field, key in expected[rid].items():
            actual = semantic_key(record.get(field) or "")
            if actual != key:
                mismatches.append(
                    {
                        "id": record.get("id"),
                        "field": field,
                        "source_key": key,
                        "canonical_key": actual,
                    }
                )
    if strict and mismatches:
        first = mismatches[0]
        raise ValueError(
            f"golden mismatch id={first['id']} field={first['field']}\n"
            f"  golden:    {first['source_key'][:300]}\n"
            f"  canonical: {first['canonical_key'][:300]}"
        )
    return mismatches


def dump_json(path: str, payload: Any) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
