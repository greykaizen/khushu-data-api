"""Shared text primitives for Khushu content canonicalization.

Stdlib only. Everything here is deterministic and side-effect free except for
the optional `issues` list, which callers use to collect review warnings.

The canonical inline vocabulary is deliberately small:
    <b> <i> <sup> <br> <qref> <ref id="..."> <hon kind="...">

Block structure is stored in JSON, not in inline HTML.
"""
from __future__ import annotations

import html
import re
import unicodedata
from typing import Iterable

# Known canonical tags. Unknown tags are treated as literal text and escaped.
KNOWN_TAG_RE = re.compile(
    r"</?(?:br|b|i|sup|qref|ref|hon)\b[^>]*?/?>",
    re.IGNORECASE,
)
TAG_RE = KNOWN_TAG_RE
BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
HON_TAG_RE = re.compile(r"</?hon\b[^>]*>", re.IGNORECASE)

# Canonical Arabic honorifics. The source corpus mostly carries English
# transliterations; the canonical text replaces only those honorific tokens
# with their Arabic form, exactly as the Prophet's ligature ﷺ already does.
RA_ARABIC = {
    "u": "رَضِيَ اللَّهُ عَنْهُ",
    "ā": "رَضِيَ اللَّهُ عَنْهَا",
    "um": "رَضِيَ اللَّهُ عَنْهُمْ",
    "umā": "رَضِيَ اللَّهُ عَنْهُمَا",
}
SWT_ARABIC = "سُبْحَانَهُ وَتَعَالَى"
AWJ_ARABIC = "عَزَّ وَجَلَّ"
RH_ARABIC = "رَحِمَهُ اللَّهُ"
AS_ARABIC = "عَلَيْهِ السَّلَام"
JJ_ARABIC = "جَلَّ جَلَالُهُ"

# Honorific phrases, including the two Arabic ligatures and the canonical
# Arabic forms above. The key maps all of them to one token; the renderer keys
# off the typed <hon> wrapper instead.
HONORIFIC_RE = re.compile(
    r"(?:raḍiy\s+Allāhu\s+[‘ʿ']anh(?:umā|um|u|ā|au))"
    r"|(?:raḍiyallāhu\s+[‘ʿ']anh(?:umā|um|u|ā|au))"
    r"|(?:ṣall[aā](?:[-‑]?llāhu|\s+Allāhu)\s+ʿalayhi\s+wa\s+sallam)"
    r"|(?:subḥānahū\s+wa\s+ta[‘ʿ']ālā)"
    r"|(?:[‘ʿ']?azza\s+wa\s+jal{1,2})"
    r"|(?:raḥimahullāh)"
    r"|(?:[‘ʿ']alayhis-salām)"
    r"|رَضِيَ اللَّهُ عَنْهُمَا|رَضِيَ اللَّهُ عَنْهُمْ|رَضِيَ اللَّهُ عَنْهَا|رَضِيَ اللَّهُ عَنْهُ"
    r"|سُبْحَانَهُ وَتَعَالَى|عَزَّ وَجَلَّ|رَحِمَهُ اللَّهُ|عَلَيْهِ السَّلَام|جَلَّ جَلَالُهُ"
    r"|ﷺ|ﷻ",
    re.IGNORECASE,
)

QUOTE_DASH_MAP = str.maketrans(
    {
        "‘": "'",
        "’": "'",
        "“": '"',
        "”": '"',
        "–": "-",
        "—": "-",
        "‒": "-",
        "―": "-",
        "\u00a0": " ",
    }
)

# C0/C1 controls except LF (0x0A). CR is normalized to LF first.
CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")

NARRATOR_VERBS = (
    r"narrated|narrates|reported|reports|said|says|replied|mentions?|"
    r"relates?|informed|explained|stated|added|continued"
)
SPEECH_VERBS_RE = re.compile(
    r"\b(?:said|says|narrated|reported|replied|asked|supplicated|wrote|"
    r"mentioned|added|continued|explained|stated|commanded|prohibited|"
    r"warned|informed|teaches|taught)\b",
    re.IGNORECASE,
)
ARABIC_RE = re.compile(r"[\u0600-\u06FF]")
UNBALANCED_QUOTE_RE = re.compile(r"[“”]")


def nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def normalize(text: str) -> str:
    """Decode entities once, NFC-normalize, and normalize whitespace.

    Never NFKC/NFKD: those decompose the honorific ligatures ﷺ (U+FDFA) and
    ﷻ (U+FDFB). NFC preserves them.
    """
    if not text:
        return ""
    text = html.unescape(text)
    text = nfc(text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\t", " ")
    text = text.replace("\u00a0", " ")
    text = CONTROL_RE.sub("", text)

    lines: list[str] = []
    for line in text.split("\n"):
        line = re.sub(r"[ \u00a0]+", " ", line).strip()
        line = re.sub(r"\s+([,.;:!?،؛])", r"\1", line)
        # Only trim after a genuinely opening quote/bracket. A left single
        # quote after ?/./! is a source typo used as a closer; keep its space.
        line = re.sub(
            r"(?<![^\s\(\[\{])[“‘\(\[\{]\s+",
            lambda m: m.group(0).rstrip(),
            line,
        )
        lines.append(line)
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def strip_backticks(text: str) -> str:
    """Remove corpus backtick debris.

    The corpus has no code spans; backtick runs are paragraph separators (handled
    by the block extractor) or typos inside a word (e.g. `du`a`). Remove the
    rest.
    """
    return text.replace("`", "")


def escape_text(text: str) -> str:
    """Escape literal markup characters in a text run."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def inline_markup(
    text: str,
    emit_tags: bool = True,
    issues: list | None = None,
    literal_asterisk: bool = False,
) -> str:
    """Convert the corpus' markdown subset to canonical inline markup.

    `emit_tags=False` returns the plain projection instead (used by the
    semantic key and by the plain columns). Existing canonical tags are
    preserved when emitting tags and skipped when emitting plain text.

    Rules:
      ***text***  -> <b><i>text</i></b>  (paired) or a block boundary (unpaired)
      **text**    -> <b>text</b>
      *text*      -> <i>text</i>
      _text_      -> <i>text</i> at word boundaries only
      unmatched * -> literal &#42; (so it survives the parser as text)
    """
    out: list[str] = []
    i = 0
    n = len(text)

    while i < n:
        ch = text[i]

        # Existing canonical tag: preserve (tags mode) or skip (plain mode).
        if ch == "<":
            m = KNOWN_TAG_RE.match(text, i)
            if m:
                if emit_tags:
                    out.append(m.group(0))
                i = m.end()
                continue
            # Unknown '<' is literal text.
            out.append("&lt;" if emit_tags else "<")
            i += 1
            continue

        # *** — paired emphasis, or a verse-boundary collision.
        if text.startswith("***", i):
            close = text.find("***", i + 3)
            if close != -1:
                inner = inline_markup(text[i + 3 : close], emit_tags, issues, literal_asterisk)
                if emit_tags:
                    out.append(f"<b><i>{inner}</i></b>")
                else:
                    out.append(inner)
                i = close + 3
                continue
            if issues is not None:
                issues.append(
                    {
                        "severity": "warning",
                        "reason": "triple_asterisk_collision",
                        "excerpt": text[max(0, i - 50) : i + 70],
                    }
                )
            # A block boundary in tags mode; whitespace in plain mode so the
            # semantic key matches the paragraph split.
            out.append("\n\n" if emit_tags else " ")
            i += 3
            continue

        # ** — bold.
        if text.startswith("**", i):
            close = text.find("**", i + 2)
            while close != -1 and text.startswith("***", close):
                close = text.find("**", close + 3)
            if close != -1:
                inner = inline_markup(text[i + 2 : close], emit_tags, issues, literal_asterisk)
                if emit_tags:
                    out.append(f"<b>{inner}</b>")
                else:
                    out.append(inner)
                i = close + 2
                continue
            # Unmatched bold marker is debris; drop it.
            if issues is not None:
                issues.append(
                    {
                        "severity": "warning",
                        "reason": "unmatched_bold_marker",
                        "excerpt": text[max(0, i - 50) : i + 70],
                    }
                )
            i += 2
            continue

        # * — italic, or a literal asterisk.
        if ch == "*":
            j = i + 1
            close = -1
            while True:
                j = text.find("*", j)
                if j == -1:
                    break
                if text.startswith("**", j):
                    j += 2
                    continue
                close = j
                break
            if close != -1:
                inner = inline_markup(text[i + 1 : close], emit_tags, issues, literal_asterisk)
                if emit_tags:
                    out.append(f"<i>{inner}</i>")
                else:
                    out.append(inner)
                i = close + 1
                continue
            if literal_asterisk:
                # Corpus footnote marker (translation ids 37/61/88). Keep it as
                # an entity so ContentMarkup does not treat it as emphasis.
                out.append("&#42;" if emit_tags else "*")
            elif issues is not None:
                issues.append(
                    {
                        "severity": "warning",
                        "reason": "unmatched_italic_marker",
                        "excerpt": text[max(0, i - 50) : i + 70],
                    }
                )
            i += 1
            continue

        # _ — italic only at word boundaries; transliteration underscores stay.
        if ch == "_":
            close = text.find("_", i + 1)
            left_ok = i == 0 or not text[i - 1].isalnum()
            right_ok = close == -1 or close + 1 == n or not text[close + 1].isalnum()
            if close != -1 and left_ok and right_ok:
                inner = inline_markup(text[i + 1 : close], emit_tags, issues, literal_asterisk)
                if emit_tags:
                    out.append(f"<i>{inner}</i>")
                else:
                    out.append(inner)
                i = close + 1
                continue
            out.append("_")
            i += 1
            continue

        # Regular text run.
        j = i
        while j < n and text[j] not in "*_<":
            j += 1
        run = text[i:j]
        out.append(escape_text(run) if emit_tags else run)
        i = j

    return "".join(out)


def _normalize_honorific_spelling(text: str) -> str:
    text = re.sub(
        r"raḍiy\s*Allāhu\s*[‘ʿ']anh(umā|um|u|ā|au)",
        lambda m: f"raḍiy Allāhu ʿanh{'u' if m.group(1) == 'au' else m.group(1)}",
        text,
    )
    text = re.sub(
        r"raḍiyallāhu\s*[‘ʿ']anh(umā|um|u|ā|au)",
        lambda m: f"raḍiy Allāhu ʿanh{'u' if m.group(1) == 'au' else m.group(1)}",
        text,
    )
    text = re.sub(r"subḥānahū\s+wa\s+ta[‘ʿ']ālā", "subḥānahū wa taʿālā", text)
    # `jal` with a single l occurs once in the corpus (id 479); accept both
    # spellings so the honorific is not left as English transliteration.
    text = re.sub(r"[‘ʿ']?azza\s+wa\s+jal{1,2}\b", "ʿazza wa jall", text)
    text = re.sub(r"raḥimahullāh", "raḥimahullāh", text)
    text = re.sub(r"[‘ʿ']alayhis-salām", "ʿalayhis-salām", text)
    return text


def _wrap_honorific_text(text: str) -> str:
    text = _normalize_honorific_spelling(text)
    text = re.sub(
        r"raḍiy Allāhu ʿanh(umā|um|u|ā|au)",
        lambda m: f'<hon kind="ra">{RA_ARABIC.get(m.group(1), RA_ARABIC["u"])}</hon>',
        text,
    )
    text = re.sub(
        r"subḥānahū wa taʿālā",
        lambda _: f'<hon kind="swt">{SWT_ARABIC}</hon>',
        text,
    )
    text = re.sub(
        r"ʿazza wa jall", lambda _: f'<hon kind="awj">{AWJ_ARABIC}</hon>', text
    )
    text = re.sub(
        r"raḥimahullāh", lambda _: f'<hon kind="rh">{RH_ARABIC}</hon>', text
    )
    text = re.sub(
        r"ʿalayhis-salām", lambda _: f'<hon kind="as">{AS_ARABIC}</hon>', text
    )
    text = re.sub(
        r"ṣall[aā](?:[-‑]?llāhu|\s+Allāhu)\s+ʿalayhi\s+wa\s+sallam",
        lambda _: '<hon kind="saw">ﷺ</hon>',
        text,
    )
    text = text.replace("ﷺ", '<hon kind="saw">ﷺ</hon>')
    text = text.replace("ﷻ", '<hon kind="jj">ﷻ</hon>')
    return text


def wrap_honorifics(text: str, field: str, issues: list | None = None) -> str:
    """Wrap existing honorific phrases in typed <hon> spans.

    Only fields rendered through the block renderer are wrapped. Plain fields
    (`title`, `post_title`, `repetition`) and the Arabic body are not, because
    they are rendered as plain strings and would show the tag.

    Never adds an honorific that is not already present.
    """
    if field not in {"translation", "transliteration", "virtue", "explanation", "reference"}:
        return text

    parts = re.split(r"(</?hon\b[^>]*>)", text, flags=re.IGNORECASE)
    out: list[str] = []
    inside = False
    for part in parts:
        if re.match(r"<hon\b", part, re.IGNORECASE):
            inside = True
            out.append(part)
            continue
        if re.match(r"</hon\b", part, re.IGNORECASE):
            inside = False
            out.append(part)
            continue
        out.append(part if inside else _wrap_honorific_text(part))
    return "".join(out)


def bold_narrator(text: str, field: str, issues: list | None = None) -> str:
    """Bold the narrator/subject at the start of a virtue narration.

    Only the first paragraph and only when the prefix looks like a narrator
    (an honorific, a prophetic title, or a multi-word proper name). Never
    guesses inside commentary or explanation.
    """
    if field != "virtue":
        return text

    first, sep, rest = text.partition("\n\n")
    if first.lstrip().startswith("<b>"):
        return text
    if first.lstrip().startswith("“") or first.lstrip().startswith("‘"):
        return text

    m = re.match(
        r"^(?P<subject>[A-Z].*?)\s*(?P<verb>" + NARRATOR_VERBS + r")\b",
        first,
        re.DOTALL,
    )
    if not m:
        return text

    subject = m.group("subject").rstrip()
    subject_plain = TAG_RE.sub("", subject).strip()
    if not subject_plain or len(subject_plain) > 110:
        return text

    has_honorific = "<hon " in subject
    is_prophet = re.match(r"^(?:The Messenger of Allah|The Prophet)\b", subject_plain) is not None
    is_multiword_name = (
        re.match(r"^[A-Z][^\s]*(?:\s+[^\s]+)+", subject_plain) is not None
        and re.match(r"^(?:He|She|It|They|We|I)\b", subject_plain) is None
    )
    if not (has_honorific or is_prophet or is_multiword_name):
        return text

    # Keep a trailing comma outside the bold run: "Muʿādh …, narrated".
    suffix = ""
    if subject.endswith(","):
        subject = subject[:-1].rstrip()
        suffix = ","

    rest_first = first[m.end("subject") :].lstrip()
    new_first = f"<b>{subject}</b>{suffix} {rest_first}".rstrip()
    return new_first + (sep + rest if sep else "")


def wrap_quotes(text: str, field: str, issues: list | None = None) -> str:
    """Italicize direct-speech quotations in English virtue/explanation.

    Conservative: balanced non-nested “...” only, only when a speech verb is
    nearby or the quote stands alone, never Arabic/Quranic text, never across
    a paragraph break. Nested or unbalanced quotes are left untouched (and
    reported) rather than wrapped partially.
    """
    if field not in {"virtue", "explanation"}:
        return text

    opens = text.count("“")
    closes = text.count("”")
    if opens != closes and issues is not None:
        issues.append(
            {
                "severity": "warning",
                "reason": "unbalanced_double_quote",
                "excerpt": text[:120],
            }
        )

    # Pair quotes with a stack. A quote that contains another quote is nested;
    # skip the whole nested pair so we never wrap half a quotation.
    stack: list[int] = []
    nested: set[int] = set()
    spans: list[tuple[int, int, str, bool]] = []
    for i, ch in enumerate(text):
        if ch == "“":
            stack.append(i)
        elif ch == "”" and stack:
            start = stack.pop()
            if stack:
                for outer in stack:
                    nested.add(outer)
                continue
            spans.append((start, i + 1, text[start + 1 : i], start in nested))

    if issues is not None:
        for start, end, inner, is_nested in spans:
            if is_nested:
                issues.append(
                    {
                        "severity": "warning",
                        "reason": "nested_quote",
                        "excerpt": text[max(0, start - 40) : end + 20],
                    }
                )

    out: list[str] = []
    pos = 0
    for start, end, inner, is_nested in spans:
        if is_nested:
            continue
        if text[max(0, start - 3) : start].lower() == "<i>" and text[
            end : end + 4
        ].lower() == "</i>":
            continue
        inner_plain = TAG_RE.sub("", inner)
        if not inner_plain.strip():
            continue
        if "\n\n" in inner_plain:
            continue
        # Arabic honorifics are not Quranic text; exclude them before deciding
        # whether the quotation itself is Arabic.
        quote_plain = HONORIFIC_RE.sub("", inner_plain)
        if ARABIC_RE.search(quote_plain) or "﴿" in quote_plain or "﴾" in quote_plain:
            continue
        before = TAG_RE.sub("", text[max(0, start - 120) : start])
        standalone = not before.strip() or before.strip().endswith((":", "،"))
        if not (SPEECH_VERBS_RE.search(before) or standalone):
            continue
        out.append(text[pos:start])
        out.append(f"<i>“{inner}”</i>")
        pos = end
    out.append(text[pos:])
    return "".join(out)


def semantic_key(text: str) -> str:
    """Formatting-insensitive content fingerprint used as the build gate.

    It removes only formatting: tags, markdown markers, bullets, backticks,
    quote/dash presentation variants, and honorific spelling variants. Letters,
    words, diacritics, digits and order are preserved. A literal asterisk (the
    corpus' three footnote markers) is preserved.
    """
    text = html.unescape(text or "")
    text = nfc(text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\t", " ").replace("\u00a0", " ")
    # The one heading splice that is **bold** + *italic* sharing a *** run.
    text = re.sub(r"\*\*(.+?)\*\*\*(.+?)\*", r"\1 \2", text, flags=re.DOTALL)
    text = inline_markup(text, emit_tags=False, literal_asterisk=True)
    # A lone * is formatting debris except the corpus' footnote marker, which
    # is always followed by ]. Paired *...* was already consumed above.
    text = re.sub(r"\*(?!\])", "", text)
    text = HONORIFIC_RE.sub(" HONORIFIC ", text)
    text = text.translate(QUOTE_DASH_MAP)
    # Separator backticks become whitespace; inside-word backticks vanish.
    text = re.sub(r"(?<!\w)`+(?!\w)", " ", text)
    text = text.replace("`", "")
    text = text.replace("•", " ")
    # Spacing around punctuation is formatting.
    text = re.sub(r"\s+([,.;:!?،؛])", r"\1", text)
    text = re.sub(r"([“‘\(\[\{])\s+", r"\1", text)
    # A script boundary is formatting, not content. The source runs an Arabic
    # duʿāʾ straight into the English around it (`وَعَصَبِي(O Allah…`,
    # `said:اَللّٰهُمَّ`); splitting the run into its own block necessarily
    # inserts whitespace there. Collapse whitespace at every script boundary
    # on BOTH sides of the comparison, so the gate measures words, not
    # spacing. (Zero-or-more, not one-or-more: the source sometimes already
    # has a space, and both sides must normalise to the same thing.)
    text = re.sub(r"(?<=[\u0600-\u06FF])\s*(?=[(\[]?[A-Za-z])", "", text)
    text = re.sub(r"(?<=[A-Za-z:;,.!?])\s*(?=[\u0600-\u06FF])", "", text)
    # Bidi control marks (LRM/RLM) are invisible formatting by definition, so
    # whitespace next to a SINGLE mark is presentation too. The source writes
    # `،‏أنت` (comma, RLM, word); a block split may render it `، ‏أنت`.
    # A run of marks is left alone: `، ‏‏‏‏ولا` carries a real space that the
    # source intended, and collapsing it would change the text.
    text = re.sub(r"\s*([\u200E\u200F])(?![\u200E\u200F])\s*", r"\1", text)
    # The 3 Quls source runs a surah straight into the next basmala
    # (`أَحَدٌ.بِسْمِ`). Splitting it into blocks inserts whitespace; remove
    # only that boundary so the source key still matches (other Arabic
    # sentence spacing is left untouched).
    text = re.sub(r"\.\s+(?=بِسْمِ)", ".", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def has_forbidden_markup(text: str) -> bool:
    """True if a plain projection still contains markup or control debris."""
    if not text:
        return False
    if any(ch in text for ch in ("\r", "\t", "\u00a0", "`")):
        return True
    if "**" in text or "&#" in text:
        return True
    if TAG_RE.search(text):
        return True
    return False


def count_issues(issues: Iterable[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for issue in issues:
        counts[issue["severity"]] = counts.get(issue["severity"], 0) + 1
    return counts
