"""Split long Arabic runs out of English prose into their own blocks.

The corpus embeds full Arabic duʿāʾ text inside English narration:

    ... and then said لَا إِلٰهَ إِلَّا اللّٰهُ وَحْدَهُ ... وَهَزَمَ الْأَحْزَابَ وَحْدَهُ.
    He then made duʿā’ in between ...

Rendered as one paragraph, bidi reorders the line: the Arabic run gets pushed
to the left edge and the surrounding English wraps around it unpredictably.
The fix is structural, not cosmetic — the Arabic becomes its own `arabic`
block, which the host already right-aligns.

Rules:

* Only a *long* run counts. Inline honorifics (`رَضِيَ اللَّهُ عَنْهُ`) and the
  Prophet's ligature are short and belong inside the sentence; splitting them
  would wreck the prose. The threshold is 25 Arabic letters.
* Honorific spans are excluded from the measurement, so a paragraph with many
  honorifics but no embedded duʿāʾ is left alone.
* Only `paragraph` blocks are split. A bullet keeps its structure (splitting it
  would leave an orphan bullet marker); those are reported instead.
* The split is whitespace-only: the plain projection still reads the same
  sentence, so the semantic-key gate stays green.
"""
from __future__ import annotations

import re

# Fields whose prose can carry an embedded Arabic duʿāʾ.
SPLIT_FIELDS = {"virtue", "explanation", "translation"}

# A contiguous Arabic run: Arabic letters plus the marks and punctuation that
# belong to them. Deliberately excludes Latin, so runs stop at the prose.
_ARABIC_RUN_RE = re.compile(
    r"[\u0600-\u06FF][\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF"
    r"\s\u064B-\u065F\u0670\u06D6-\u06ED\u060C\u061B\u061F.!]*"
)

_HON_RE = re.compile(r"<hon\b[^>]*>.*?</hon>", re.S)
_TAG_RE = re.compile(r"<[^>]+>")

# A run must carry at least this many Arabic letters to be worth its own block.
MIN_ARABIC_LETTERS = 25


def _arabic_letter_count(text: str) -> int:
    """Count Arabic LETTERS, not marks.

    Diacritics (U+064B–U+065F, U+0670, U+06D6–U+06ED) and the tatweel live
    inside the Arabic block but are not letters; a run of them alone must not
    qualify as an embedded duʿāʾ.
    """
    return len(re.findall(r"[\u0620-\u063F\u0641-\u064A\u066E-\u066F\u0671-\u06D3\u06FA-\u06FC]", text))


def find_arabic_run(text: str) -> tuple[int, int] | None:
    """Return the (start, end) of the longest qualifying Arabic run, if any.

    Honorific spans are masked out before measuring, so `(<hon …>)` never
    counts toward the threshold and never becomes a split candidate.
    """
    masked = _HON_RE.sub(lambda m: " " * len(m.group(0)), text)
    best: tuple[int, int] | None = None
    best_len = 0
    for match in _ARABIC_RUN_RE.finditer(masked):
        run = match.group(0)
        # Trailing whitespace belongs to the prose, not the run.
        start, end = match.start(), match.start() + len(run.rstrip())
        if _arabic_letter_count(run) < MIN_ARABIC_LETTERS:
            continue
        if end - start > best_len:
            best, best_len = (start, end), end - start
    return best


def split_arabic_runs(blocks: list[dict], field: str, issues: list | None = None) -> list[dict]:
    """Promote an embedded Arabic duʿāʾ to its own `arabic` block.

    Idempotent: a block that is already `arabic` is never re-examined, and the
    split output contains no paragraph with a qualifying run.
    """
    if field not in SPLIT_FIELDS:
        return blocks

    out: list[dict] = []
    for block in blocks:
        if block.get("type") != "paragraph":
            # A bullet with an embedded duʿāʾ keeps its structure; report it so
            # the count is visible rather than silently ignored.
            if block.get("type") == "bullet" and find_arabic_run(block.get("text", "")):
                if issues is not None:
                    issues.append(
                        {
                            "severity": "warning",
                            "reason": "arabic_run_in_bullet",
                            "excerpt": block.get("text", "")[:120],
                        }
                    )
            out.append(block)
            continue

        text = block.get("text", "")
        span = find_arabic_run(text)
        if span is None:
            out.append(block)
            continue

        start, end = span
        before = text[:start].strip()
        arabic = text[start:end].strip()
        after = text[end:].strip()

        if before:
            out.append({"type": "paragraph", "text": before})
        out.append({"type": "arabic", "text": arabic})
        if after:
            out.append({"type": "paragraph", "text": after})
        if issues is not None:
            issues.append(
                {
                    "severity": "info",
                    "reason": "arabic_run_split",
                    "excerpt": arabic[:80],
                }
            )
    return out
