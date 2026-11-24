"""Block extraction for canonicalized dua fields.

Block structure lives here, not in HTML. The canonicalizer emits a list of
typed blocks; the orchestrator parses the JSON, and the app renders it with one
Compose renderer.
"""
from __future__ import annotations

import html
import re
import unicodedata

from .refs import split_reference_list, type_references
from .script_split import split_arabic_runs
from .text import (
    SPEECH_VERBS_RE,
    TAG_RE,
    inline_markup,
    normalize,
    strip_backticks,
    wrap_honorifics,
    bold_narrator,
    wrap_quotes,
)

RICH_FIELDS = {"arabic", "translation", "transliteration", "virtue", "explanation", "reference"}

# The corpus writes the basmala inline before each surah in a multi-surah dua
# (the 3 Quls). It is a display line of its own, centered by the host.
BISMILLAH_RE = re.compile(
    r"بِسْمِ\s+اللّٰهِ\s+الرَّحْمٰنِ\s+الرَّحِيْمِ\s*\."
)

# Known heading vocabulary in the corpus. Headings are only recognized from
# this closed list (plus a single italic subheading), never guessed.
_KNOWN_HEADINGS = {
    "brief commentary",
    "action points",
    "action points & benefits",
    "action points and benefits",
    "benefits & action points",
    "benefits and action points",
    "the virtues",
    "the greatest ayah",
    "three powerful surahs",
    "ask allah through his oneness",
    "living by ayat al-kursi",
    "recite it 8x a day",
    "a powerful source of protection",
    "virtues of ayat al-kursi",
}
_KNOWN_PREFIXES = (
    "brief commentary",
    "benefits & action points",
    "benefits and action points",
    "action points",
    "virtues of ",
    "what is ",
    "why do ",
    "why is ",
    "the secret of ",
    "an alternative meaning to ",
    "how to ",
    "when is ",
    "who is ",
    "the meaning of ",
)
_KNOWN_SUBHEADINGS = {"the greatest ayah"}


def _fold(text: str) -> str:
    """Accent-insensitive lowercase used only for heading recognition."""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return stripped.lower().strip()


def heading_level(raw: str) -> int | None:
    """Return 1 or 2 for recognized headings, else None.

    Level 1: known bold/plain heading vocabulary.
    Level 2: a whole italic run naming a known subheading (the corpus' *The
    Greatest Ayah*). A bare italic sentence is NOT a heading; only the closed
    subheading list is accepted, plus a short title-shaped italic run.
    """
    plain = TAG_RE.sub("", raw)
    plain = re.sub(r"[`*_]+", "", plain).strip()
    plain = re.sub(r"\s+", " ", plain)
    low = _fold(plain).rstrip(":")

    is_italic_only = (
        raw.strip().startswith("*")
        and not raw.strip().startswith("**")
        and raw.strip().endswith("*")
        and len(plain) <= 80
    )
    if is_italic_only:
        # Closed list first; also accept a short title-shaped phrase that does
        # not end like a sentence and has no comma.
        if low in _KNOWN_SUBHEADINGS:
            return 2
        if (
            len(plain) <= 60
            and not plain.endswith((".", "!", "?", ":", ";", ","))
            and "," not in plain
            and len(plain.split()) <= 8
        ):
            return 2
        return None

    if low in _KNOWN_HEADINGS or any(low.startswith(p) for p in _KNOWN_PREFIXES):
        return 1
    return None


def strip_heading_markers(raw: str) -> str:
    """Remove the outer bold/italic markers from a heading, preserving tags."""
    s = raw.strip()
    m = re.fullmatch(r"\*\*(.*?)\*\*", s, re.DOTALL)
    if m:
        return m.group(1).strip()
    m = re.fullmatch(r"\*(.*?)\*", s, re.DOTALL)
    if m:
        return m.group(1).strip()
    return s.strip("`").strip()


def is_block_quote(text: str) -> bool:
    """A long quotation that occupies a whole paragraph (optional attribution)."""
    plain = TAG_RE.sub("", text).strip()
    if not plain or plain[0] not in "“‘":
        return False
    close = "”" if plain[0] == "“" else "’"
    idx = plain.find(close, 1)
    if idx == -1:
        return False
    quoted = plain[1:idx]
    if len(quoted) < 60:
        return False
    tail = plain[idx + 1 :].strip()
    if len(tail) > 100:
        return False
    return True


def _arabic_blocks(text: str, issues: list) -> list[dict]:
    """Split the Arabic body at each basmala.

    The basmala is emitted as its own block so the host can center it on a new
    line; the surah/dua text between basmalas stays a normal right-aligned
    paragraph. Without this the 3 Quls source ran `...أَحَدٌ.بِسْمِ...` together
    and the reader saw the second basmala split across the previous line.
    """
    blocks: list[dict] = []
    pos = 0

    def add_arabic(part: str) -> None:
        for para in re.split(r"\n{2,}", part):
            para = para.strip()
            if para:
                blocks.append({"type": "arabic", "text": inline_markup(para, True, issues)})

    for match in BISMILLAH_RE.finditer(text):
        add_arabic(text[pos : match.start()])
        blocks.append({"type": "bismillah", "text": match.group(0).strip()})
        pos = match.end()
    add_arabic(text[pos:])
    return blocks


def _split_inline_quote(part: str) -> tuple[str, str, str] | None:
    """Split a long direct quotation that follows its attribution.

    Only a top-level double-quoted span of 120+ characters is considered, and
    only when a speech verb (or a colon/comma) introduces it. Short quoted
    terms and nested quotations stay inline.
    """
    stack: list[int] = []
    pairs: list[tuple[int, int]] = []
    for i, ch in enumerate(part):
        if ch == "“":
            stack.append(i)
        elif ch == "”" and stack:
            start = stack.pop()
            if not stack:
                pairs.append((start, i + 1))
    for start, end in pairs:
        quote = part[start:end]
        if len(TAG_RE.sub("", quote[1:-1])) < 120:
            continue
        before = part[:start].strip()
        after = part[end:].strip()
        # wrap_quotes() puts <i> around direct speech; the quote block owns the
        # italic styling, so take those tags off the surrounding prose.
        if before.endswith("<i>"):
            before = before[:-3].rstrip()
        if after.startswith("</i>"):
            after = after[4:].lstrip()
        # A stray quote immediately after the closer is a source typo; keeping
        # the paragraph intact avoids inventing a space before it.
        if after.startswith(("’", "'", "”")):
            continue
        before_plain = TAG_RE.sub("", before)
        if not before_plain or not (
            SPEECH_VERBS_RE.search(before_plain) or before_plain.endswith((":", "،", ","))
        ):
            continue
        return before, quote, after
    return None


def _split_leading_quote(part: str) -> tuple[str, str] | None:
    """Split a paragraph that opens with a long quotation followed by prose.

    Books put a long du'a/hadith quotation on its own indented line even when
    an attribution follows it. Only quotes of 60+ characters are split; short
    quoted terms ("Allah", "One") stay inline.
    """
    s = part.strip()
    # Single quotes are ambiguous in English (apostrophes in names and
    # transliterations), so only a double-quoted opening is split here.
    if not s or s[0] != "“":
        return None
    close = "”"
    idx = s.find(close, 1)
    if idx == -1:
        return None
    if len(TAG_RE.sub("", s[1:idx])) < 60:
        return None
    tail = s[idx + 1 :].strip()
    if not tail:
        return None
    return s[: idx + 1], tail


def _append_part(
    part: str, blocks: list[dict], issues: list, *, split_quote: bool = False
) -> None:
    lvl = heading_level(part)
    if lvl:
        blocks.append({"type": "heading", "level": lvl, "text": strip_heading_markers(part)})
        return
    if split_quote:
        lead = _split_leading_quote(part)
        if lead:
            quote, tail = lead
            blocks.append({"type": "quote", "text": quote})
            _append_part(tail, blocks, issues)
            return
        inline = _split_inline_quote(part)
        if inline:
            before, quote, after = inline
            blocks.append({"type": "paragraph", "text": before})
            blocks.append({"type": "quote", "text": quote})
            if after:
                _append_part(after, blocks, issues)
            return
    if is_block_quote(part):
        # A quote block is italicized by the renderer; drop a redundant outer
        # <i> only when the whole part is wrapped.
        text = re.sub(r"^<i>(.*)</i>$", r"\1", part.strip(), flags=re.DOTALL)
        blocks.append({"type": "quote", "text": text})
        return
    blocks.append({"type": "paragraph", "text": part})


def _split_triple(part: str, blocks: list[dict], issues: list) -> bool:
    """Handle *** inside one paragraph. Returns True if it was split."""
    if part.count("***") == 2:
        # Paired emphasis; convert and keep as one block.
        part = re.sub(r"\*\*\*(.+?)\*\*\*", r"<b><i>\1</i></b>", part, flags=re.DOTALL)
        _append_part(part, blocks, issues)
        return True
    if "***" in part:
        issues.append(
            {
                "severity": "warning",
                "reason": "triple_asterisk_boundary",
                "excerpt": part[:140],
            }
        )
        for sub in re.split(r"\*\*\*", part):
            sub = sub.strip()
            if sub:
                _append_part(sub, blocks, issues)
        return True
    return False


def canonical_blocks(field: str, raw: str, issues: list) -> list[dict]:
    """Split one field into typed blocks and canonicalize inline markup."""
    # Backtick runs are paragraph separators in this corpus, even when the
    # source forgot the blank line (e.g. "...imagine.` `` `**Benefits...").
    # Inside-word backticks are left for strip_backticks to preserve.
    raw = re.sub(r"(?<!\w)`+(?!\w)", "\n\n", raw or "")
    text = normalize(raw)
    text = strip_backticks(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    if field == "arabic":
        return _arabic_blocks(text, issues)

    if field not in RICH_FIELDS:
        # Non-rich plain fields (if any) are paragraphs on blank lines.
        blocks: list[dict] = []
        for part in re.split(r"\n{2,}", text):
            part = part.strip()
            if part:
                blocks.append({"type": "paragraph", "text": inline_markup(part, True, issues)})
        return blocks

    # Inline semantic transforms first, then block structure.
    text = wrap_honorifics(text, field, issues)
    text = bold_narrator(text, field, issues)
    text = wrap_quotes(text, field, issues)
    # Citations last: honorific/quote transforms may have rewritten the
    # surrounding prose, and a citation must never be split by them.
    text = type_references(text, field, issues)

    if field in {"virtue", "explanation"}:
        # Bullets are paragraph markers in this corpus, never inline glyphs.
        text = re.sub(r"\s*•\s*", "\n\n• ", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()

        blocks = []
        for part in re.split(r"\n{2,}", text):
            part = part.strip()
            if not part:
                continue
            if part.startswith("• "):
                body = part[2:].strip()
                if not body:
                    issues.append(
                        {
                            "severity": "warning",
                            "reason": "empty_bullet",
                            "excerpt": part[:80],
                        }
                    )
                    continue
                # A *** collision inside a bullet ends the bullet: the text
                # after it is a new paragraph, not a continuation of the list.
                if "***" in body and body.count("***") % 2 == 1:
                    issues.append(
                        {
                            "severity": "warning",
                            "reason": "triple_asterisk_boundary",
                            "excerpt": body[:140],
                        }
                    )
                    chunks = re.split(r"\*\*\*", body)
                    first = chunks[0].strip()
                    if first:
                        blocks.append({"type": "bullet", "text": first})
                    for chunk in chunks[1:]:
                        chunk = chunk.strip()
                        if chunk:
                            _append_part(chunk, blocks, issues, split_quote=True)
                    continue
                blocks.append({"type": "bullet", "text": body})
                continue

            # The one heading splice: **Level 1***Level 2*
            m = re.fullmatch(r"\*\*(.+?)\*\*\*(.+?)\*", part, re.DOTALL)
            if m:
                blocks.append({"type": "heading", "level": 1, "text": m.group(1).strip()})
                blocks.append({"type": "heading", "level": 2, "text": m.group(2).strip()})
                continue

            if _split_triple(part, blocks, issues):
                continue
            _append_part(part, blocks, issues, split_quote=True)

        # Inline pass on the extracted text (headings keep their tags).
        for b in blocks:
            b["text"] = inline_markup(b["text"], True, issues)
        # An Arabic duʿāʾ embedded mid-sentence becomes its own block so the
        # host can right-align it instead of letting bidi push it left.
        return split_arabic_runs(blocks, field, issues)

    # translation / transliteration / reference: paragraphs on blank lines,
    # single LF preserved as a line break inside the paragraph.
    blocks = []
    for part in re.split(r"\n{2,}", text):
        part = part.strip()
        if not part:
            continue
        # A citation list (`Bukhārī 3371; Bukhārī 3280`) is one source per
        # bullet, not a run-on line. Only the reference field is a list.
        entries = split_reference_list(part) if field == "reference" else [part]
        for entry in entries:
            blocks.append(
                {
                    "type": "bullet" if field == "reference" and len(entries) > 1 else "paragraph",
                    "text": inline_markup(
                        entry, True, issues, literal_asterisk=(field == "translation")
                    ),
                }
            )
    # An Arabic duʿāʾ embedded mid-sentence becomes its own block so the host
    # can right-align it instead of letting bidi push it to the left edge.
    return split_arabic_runs(blocks, field, issues)


def plain_projection(blocks: list[dict]) -> str:
    """Clean, tag-free text for FTS/copy/accessibility.

    Paragraphs are blank-line separated; bullets are consecutive `• ` lines.
    """
    lines: list[str] = []
    for b in blocks:
        text = inline_markup(b["text"], emit_tags=False, issues=None)
        text = html.unescape(text)
        text = re.sub(r"[ \t]+", " ", text).strip()
        if not text:
            continue
        if b["type"] == "bullet":
            lines.append("• " + text)
        else:
            if lines and lines[-1] != "":
                lines.append("")
            lines.append(text)
            lines.append("")
    return "\n".join(lines).strip()
