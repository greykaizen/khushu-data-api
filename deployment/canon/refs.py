"""Reference typing: turn bare Quran/hadith citations into typed spans.

The corpus cites verses inline as plain text — `(2:255)`, `(2:285-6)`,
`(See Qur'an 3:85)`, `(Quran: 3:190)` — and hadith as `(Muslim 899)`,
`(Tirmidhī 3173)`. `<qref>` / `<ref>` already exist in the vocabulary and the
orchestrator already parses them into typed spans, but nothing ever emitted
them, so every citation rendered as dead text.

Rules (deliberately conservative — never invent a reference):

* Only a citation *context* matches: the number pair must be wrapped in
  parentheses, optionally with a `Quran`/`Qur'an`/`See` prefix. A bare `3:190`
  in prose is left alone.
* Surah must be 1..114 and ayah >= 1, else the text is untouched.
* The parenthesis stays outside the tag, so the plain projection still reads
  `(2:255)` and copy/FTS are byte-identical.
* Ranges keep their raw form: `<qref>2:285-6</qref>`.
* Hadith collections become `<ref id="muslim">Muslim 899</ref>`.
"""
from __future__ import annotations

import re

# Surah:ayah, optionally a range (`2:285-6`, `23:1-10`).
_QURAN_NUM = r"\d{1,3}\s*:\s*\d{1,3}(?:\s*[-–]\s*\d{1,3})?"

# A citation context: parenthesised, with an optional Quran-ish prefix inside.
#   (2:255)   (2:285-6)   (Quran: 3:190)   (See Qur'an 3:85)   (See 69:17)
# The prefix is captured separately and kept OUTSIDE the tag: the plain
# projection must stay byte-identical, so only the number pair is wrapped.
_QURAN_CITE_RE = re.compile(
    r"\(\s*"
    r"(?P<prefix>"
    r"(?:(?:see\s+|cf\.?\s+)?"
    r"(?:(?:the\s+)?qur[’'ʿ]?[āa]n\s*[:,]?\s*)?)"
    r")"
    r"(?P<ref>" + _QURAN_NUM + r")"
    r"\s*\)",
    re.IGNORECASE,
)

# Hadith collections. The slug is the host collection id (`SunnahRepository.collections`),
# not a display label: `abu_dawud` and `ibn_majah` are what opens a pack.
_HADITH_COLLECTIONS = {
    "bukhari": "bukhari",
    "bukhārī": "bukhari",
    "bukharī": "bukhari",
    "muslim": "muslim",
    "tirmidhi": "tirmidhi",
    "tirmidhī": "tirmidhi",
    "abu dawud": "abu_dawud",
    "abu dāwūd": "abu_dawud",
    "abū dāwūd": "abu_dawud",
    "abū dawud": "abu_dawud",
    "nasai": "nasai",
    "nasā’ī": "nasai",
    "nasā'ī": "nasai",
    "nasāī": "nasai",
    "ibn majah": "ibn_majah",
    "ibn mājah": "ibn_majah",
    "ibnmajah": "ibn_majah",
    "malik": "malik",
    "mālik": "malik",
    "riyadussalihin": "riyadussalihin",
    "forty": "forty",
}

_HADITH_CITE_RE = re.compile(
    r"\(\s*(?P<coll>"
    + "|".join(sorted((re.escape(k) for k in _HADITH_COLLECTIONS), key=len, reverse=True))
    + r")\s+(?P<num>\d{1,5}[a-z]?)\s*\)",
    re.IGNORECASE,
)

# One citation inside a parenthesised comma/semicolon list, without the parens.
_HADITH_PART_RE = re.compile(
    r"^\s*(?P<coll>"
    + "|".join(sorted((re.escape(k) for k in _HADITH_COLLECTIONS), key=len, reverse=True))
    + r")\s+(?P<num>\d{1,5}[a-z]?)\s*$",
    re.IGNORECASE,
)

_QURAN_PART_RE = re.compile(
    r"^\s*"
    r"(?:(?:see\s+|cf\.?\s+)?(?:(?:the\s+)?qur[’'ʿ]?[āa]n\s*[:,]?\s*)?)"
    r"(?P<ref>" + _QURAN_NUM + r")\s*$",
    re.IGNORECASE,
)

# `(Bukhārī 6316, Muslim 763)` / `(2:255; 3:190)`: every piece must be a
# real citation, otherwise the whole parenthesis is left as prose.
_CITATION_GROUP_RE = re.compile(r"\((?P<body>[^()<>]{3,200})\)")

# Fields that carry citations worth typing.
REFERENCE_FIELDS = {"translation", "virtue", "explanation", "reference"}


def _valid_quran_ref(ref: str) -> bool:
    m = re.match(r"(\d{1,3})\s*:\s*(\d{1,3})", ref)
    if not m:
        return False
    surah, ayah = int(m.group(1)), int(m.group(2))
    return 1 <= surah <= 114 and ayah >= 1


def _type_citation_group(match: re.Match) -> str:
    body = match.group("body")
    pieces = re.split(r"(\s*[,;]\s*)", body)
    if len(pieces) < 3:
        return match.group(0)
    values = pieces[0::2]
    separators = pieces[1::2]
    typed: list[str] = []
    for value in values:
        quran = _QURAN_PART_RE.match(value)
        if quran and _valid_quran_ref(quran.group("ref")):
            typed.append(f"<qref>{quran.group('ref')}</qref>")
            continue
        hadith = _HADITH_PART_RE.match(value)
        if hadith:
            slug = _HADITH_COLLECTIONS.get(hadith.group("coll").lower())
            if slug:
                typed.append(f'<ref id="{slug}">{value.strip()}</ref>')
                continue
        return match.group(0)
    if len(typed) != len(values):
        return match.group(0)
    out = ["("]
    for index, value in enumerate(typed):
        out.append(value)
        if index < len(separators):
            out.append(separators[index])
    out.append(")")
    return "".join(out)


def type_references(text: str, field: str, issues: list | None = None) -> str:
    """Wrap bare Quran/hadith citations in typed spans.

    Idempotent: an already-tagged citation is skipped, so running the pipeline
    twice cannot double-wrap.
    """
    if field not in REFERENCE_FIELDS or not text:
        return text

    def quran_sub(m: re.Match) -> str:
        ref = m.group("ref")
        prefix = m.group("prefix") or ""
        if not _valid_quran_ref(ref):
            if issues is not None:
                issues.append(
                    {
                        "severity": "warning",
                        "reason": "quran_ref_out_of_range",
                        "excerpt": m.group(0)[:80],
                    }
                )
            return m.group(0)
        # Preserve the source spacing inside the citation; the host parser
        # tolerates `2 : 255` and the semantic key must not change.
        return f"({prefix}<qref>{ref}</qref>)"

    def hadith_sub(m: re.Match) -> str:
        coll = m.group("coll").lower()
        slug = _HADITH_COLLECTIONS.get(coll)
        raw = f"{m.group('coll')} {m.group('num')}"
        if slug:
            return f'(<ref id="{slug}">{raw}</ref>)'
        return f"(<ref>{raw}</ref>)"

    # Skip anything already inside a tag so the transform is idempotent.
    parts = re.split(r"(<[^>]+>)", text)
    out: list[str] = []
    for part in parts:
        if part.startswith("<") and part.endswith(">"):
            out.append(part)
            continue
        part = _CITATION_GROUP_RE.sub(_type_citation_group, part)
        part = _QURAN_CITE_RE.sub(quran_sub, part)
        part = _HADITH_CITE_RE.sub(hadith_sub, part)
        out.append(part)
    return "".join(out)


def parse_quran_ref(raw: str) -> tuple[int, int] | None:
    """`2:255` / `2:285-6` -> (2, 255). Used by tests and the verifier."""
    m = re.match(r"\s*(\d{1,3})\s*:\s*(\d{1,3})", raw or "")
    if not m:
        return None
    surah, ayah = int(m.group(1)), int(m.group(2))
    if not (1 <= surah <= 114 and ayah >= 1):
        return None
    return surah, ayah


def split_reference_list(text: str) -> list[str]:
    """Split a `;`-joined citation list into one entry per source.

    `Bukhārī 3371; Bukhārī 3280` is two citations rendered as one run-on line.
    Each becomes its own entry so the reference sheet is scannable.

    The separator stays attached to the entry before it. Dropping it would
    change the plain projection (`A; B` -> `A B`) and the semantic-key gate
    would correctly reject that as a content change; a trailing `;` on a
    bullet is the honest rendering of a continued list.
    """
    if ";" not in text:
        return [text]
    parts = [p.strip() for p in re.split(r"(?<=;)\s*", text)]
    # A piece that is only a separator (`A; ; B`) is not a citation.
    parts = [p for p in parts if p and p.strip(";").strip()]
    return parts or [text]
