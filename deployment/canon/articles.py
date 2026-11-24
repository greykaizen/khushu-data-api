#!/usr/bin/env python3
"""Canonical cleanup for the long-form reading corpus.

The source pages were captured as rendered HTML. The app renders them with a
native block reader (headings, paragraphs, lists, quotes, tables, inline
emphasis and Arabic runs), so the only useful work here is to make the HTML
express the structure the source actually has:

* transliterated devotional formulas (``raḍiy Allāhu ʿanhu``, ``subḥānahū wa
  taʿālā``) read as untranslated English inside an otherwise Arabic-aware
  article. NFC-compose the text first, then replace them with their Arabic form;
* ``•`` / ``–`` / ``—`` paragraphs and numbered paragraph runs are lists that
  lost their markup. Rebuild ``<ul>`` / ``<ol>`` so the app can hang-indent them;
* a short bold-only paragraph is a heading (``<p><b>When Leaving the Home</b>
  </p>``); promote it to ``<h3>`` instead of leaving it as body text;
* a paragraph that is one long quotation becomes a ``<blockquote>`` so the
  reader can style it as a quote;
* ``<span>`` / ``<font>`` / ``<bdi>`` wrappers in this corpus carry no
  attributes; unwrap them so inline text is not split into meaningless runs;
* collapse source whitespace, NBSP, tabs and spaces around punctuation in text
  nodes only (never in tags or attributes).

The transformation is intentionally formatting-only: prose, quotations, links
and all content markup are preserved. ``article_semantic_key`` is the guard
that proves it; ``freeze`` writes the keys before a run and ``main`` refuses to
report success if any key changes.
"""
from __future__ import annotations

import html
import glob
import json
import re
import sys
import unicodedata
from pathlib import Path

try:  # package import (tests / build_dua)
    from .refs import type_references
except ImportError:  # direct `python3 deployment/canon/articles.py`
    from refs import type_references

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


HONORIFIC_WORDS = r"(?:رضي الله (?:عنها|عنهما|عنهم|عنه)|سبحانه وتعالى|رحمه الله|عليه السلام|عز وجل|ﷺ)"
HONORIFIC_FORM = re.compile(HONORIFIC_WORDS)
HONORIFIC_PARENS = re.compile(r"\(\s*(%s)\s*\)" % HONORIFIC_WORDS)
HONORIFIC_OPEN = re.compile(r"\(\s*(?=%s)" % HONORIFIC_WORDS)
HONORIFIC_CLOSE = re.compile(r"(%s)\s*\)" % HONORIFIC_WORDS)

COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
SCRIPT_OR_STYLE = re.compile(
    r"<(script|style)\b[^>]*>.*?</\1\s*>",
    re.IGNORECASE | re.DOTALL,
)
TAG_SPLIT = re.compile(r"(<[^>]+>)")
INLINE_WRAPPER = re.compile(r"</?(?:span|font|bdi)\b[^>]*>", re.IGNORECASE)
BR = re.compile(r"<\s*br\s*/?\s*>", re.IGNORECASE)
PARAGRAPH = re.compile(r"<p\b[^>]*>(.*?)</p>", re.IGNORECASE | re.DOTALL)
LIST_ITEM = re.compile(r"<li\b[^>]*>(.*?)</li>", re.IGNORECASE | re.DOTALL)
BULLET_MARK = re.compile(r"^\s*(?:<b>|<strong>)?\s*[•–—]\s*(?:</b>|</strong>)?\s*", re.IGNORECASE)
NUMBER_MARK = re.compile(r"^\s*(?:<b>|<strong>)?\s*\(?(\d{1,2})[.)]\)?\s*(?:</b>|</strong>)?\s*", re.IGNORECASE)
BOLD_ONLY = re.compile(r"^\s*<(b|strong)>(.*?)</\1>\s*$", re.IGNORECASE | re.DOTALL)
EMPTY_BLOCK = re.compile(r"<p\b[^>]*>\s*</p>|<div\b[^>]*>\s*</div>", re.IGNORECASE)
EMBEDDED_QUOTE = re.compile(r"“[^“”]{180,}”", re.DOTALL)
CITATION_ONLY = re.compile(r"^[\s).;,]*(?:\([^)]{1,60}\))?[\s.;,)]*$")
ARABIC_LETTER = re.compile(r"[\u0600-\u06FF]")
LATIN_LETTER = re.compile(r"[A-Za-z]")


def clean_text(value: str) -> str:
    """NFC-compose, then replace transliterated honorifics with Arabic.

    NFC matters: several source spellings use a combining dot below the ``d``
    (``raḍiy`` as d + U+0323), which the precomposed-character patterns below
    did not match. Normalizing first is what makes those 47 occurrences convert.
    """
    out = unicodedata.normalize("NFC", value or "")
    for pattern, replacement in HONORIFICS:
        out = pattern.sub(replacement, out)
    out = HONORIFIC_PARENS.sub(r"\1", out)
    out = HONORIFIC_OPEN.sub("", out)
    return HONORIFIC_CLOSE.sub(r"\1", out)


def _normalize_text_node(text: str) -> str:
    if not text:
        return text
    text = unicodedata.normalize("NFC", text)
    text = (
        text.replace("\u00a0", " ")
        .replace("\u2007", " ")
        .replace("\u202f", " ")
        .replace("\t", " ")
        .replace("\r", " ")
        .replace("\n", " ")
    )
    text = re.sub(r"\s+", " ", text)
    # Typographic spacing: never a space before punctuation, always a space
    # after a comma/semicolon/colon that is followed by a word. This fixes the
    # source's ``says,“ Do`` / ``Paradise .`` artifacts without touching digits
    # (citations like 2:255 stay intact).
    text = re.sub(r"\s+([,.;:!?%])", r"\1", text)
    text = re.sub(r"([,;:])(?=[A-Za-z“”‘’])", r"\1 ", text)
    text = re.sub(r"([“‘(])\s+", r"\1", text)
    text = re.sub(r"\s+([”’)\]])", r"\1", text)
    return text


def normalize_text_nodes(value: str) -> str:
    """Normalize text between tags, leaving tags and attributes untouched."""
    parts = TAG_SPLIT.split(value)
    for index in range(0, len(parts), 2):
        parts[index] = _normalize_text_node(parts[index])
    return "".join(parts)


def _inside_blockquote(value: str, position: int) -> bool:
    before = value[:position].lower()
    return before.count("<blockquote") > before.count("</blockquote")


def _strip_list_markers(value: str) -> str:
    def item(match: re.Match[str]) -> str:
        inner = match.group(1)
        inner = re.sub(r"</p>\s*<p\b[^>]*>", "<br>", inner, flags=re.IGNORECASE)
        inner = re.sub(r"</?p\b[^>]*>", "", inner, flags=re.IGNORECASE)
        prefix = BULLET_MARK.match(inner)
        if prefix:
            inner = inner[prefix.end():]
        return "<li>%s</li>" % inner

    return LIST_ITEM.sub(item, value)


def _list_paragraphs(value: str) -> str:
    """Turn bullet/numbered paragraph runs into real ``ul`` / ``ol`` lists."""
    candidates: list[tuple[re.Match[str], str, int, int | None]] = []
    for match in PARAGRAPH.finditer(value):
        if _inside_blockquote(value, match.start()):
            continue
        inner = match.group(1)
        bullet = BULLET_MARK.match(inner)
        number = NUMBER_MARK.match(inner)
        if bullet:
            candidates.append((match, "ul", bullet.end(), None))
        elif number:
            candidates.append((match, "ol", number.end(), int(number.group(1))))

    groups: list[list[tuple[re.Match[str], str, int, int | None]]] = []
    for candidate in candidates:
        match, kind, _, number = candidate
        if groups:
            previous = groups[-1][-1]
            between = value[previous[0].end():match.start()]
            same_kind = previous[1] == kind
            adjacent = re.fullmatch(r"\s*", between) is not None
            sequential = kind != "ol" or (previous[3] is not None and number == previous[3] + 1)
            if same_kind and adjacent and sequential:
                groups[-1].append(candidate)
                continue
        groups.append([candidate])

    edits: list[tuple[int, int, str]] = []
    for group in groups:
        kind = group[0][1]
        # Ordered runs that start mid-list (e.g. 4,5 after a different block)
        # cannot be renumbered safely; leave them as paragraphs.
        if kind == "ol" and len(group) < 2:
            continue
        start = group[0][3] or 1
        start_attr = ' start="%d"' % start if kind == "ol" and start != 1 else ""
        items = "".join(
            "<li>%s</li>" % match.group(1)[mark:]
            for match, _, mark, _ in group
        )
        edits.append(
            (
                group[0][0].start(),
                group[-1][0].end(),
                "<%s%s>%s</%s>" % (kind, start_attr, items, kind),
            )
        )

    for start, end, replacement in reversed(edits):
        value = value[:start] + replacement + value[end:]
    return value


def _quote_paragraphs(value: str) -> str:
    """Make long quotations (standalone or embedded) block quotes.

    One paragraph can contain more than one quotation, so repeat until no
    paragraph changes. A quotation that contains another ``“...”`` is left
    inline: splitting at the first closing mark would tear the inner sentence
    apart.
    """

    def paragraph(match: re.Match[str], source: str) -> str:
        if _inside_blockquote(source, match.start()):
            return match.group(0)
        inner = match.group(1).strip()
        text = re.sub(r"<[^>]+>", "", inner)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) < 80:
            return match.group(0)
        if text[:1] in "“\"" and text[-1:] in "”\"":
            inner = BR.sub("<br>", inner).replace("\n", "<br>")
            return "<blockquote><p>%s</p></blockquote>" % inner

        # A long quotation embedded in a prose paragraph (usually a hadith or
        # verse introduced by "The Prophet ﷺ said:") deserves the same quote
        # surface as a standalone one. Split only when the quotation is long
        # enough to read as a passage and both the lead-in and the tail are
        # real text; a short trailing citation stays inside the quote.
        quote = EMBEDDED_QUOTE.search(inner)
        if quote is None:
            return match.group(0)
        quote_text = re.sub(r"<[^>]+>", "", quote.group(0))
        quote_text = re.sub(r"\s+", " ", quote_text).strip()
        if len(quote_text) < 180:
            return match.group(0)
        before = inner[:quote.start()].strip()
        after = inner[quote.end():].strip()
        after_text = re.sub(r"<[^>]+>", "", after).strip()
        quote_block = "<blockquote><p>%s</p>" % BR.sub("<br>", quote.group(0))
        if after and CITATION_ONLY.fullmatch(after_text):
            quote_block += "<p>%s</p>" % after
            after = ""
        quote_block += "</blockquote>"
        out = ("<p>%s</p>" % before if before else "") + quote_block
        if after:
            out += "<p>%s</p>" % after
        return out

    for _ in range(20):
        edits: list[tuple[int, int, str]] = []
        for match in PARAGRAPH.finditer(value):
            replacement = paragraph(match, value)
            if replacement != match.group(0):
                edits.append((match.start(), match.end(), replacement))
        if not edits:
            break
        for start, end, replacement in reversed(edits):
            value = value[:start] + replacement + value[end:]
    return value


def _normalize_heading_levels(value: str) -> str:
    """The source's h4-h6 headings are ordinary section headings, not footnotes.

    The reader maps levels 4-6 to `titleSmall`, which is too small on a phone;
    normalise them to h3 and keep the article's heading hierarchy legible.
    """
    return re.sub(r"<(/?)h[456]\b([^>]*)>", r"<\1h3\2>", value, flags=re.IGNORECASE)


def _promote_headings(value: str) -> str:
    """Promote short bold-only paragraphs that are shaped like headings."""

    def paragraph(match: re.Match[str]) -> str:
        if _inside_blockquote(value, match.start()):
            return match.group(0)
        bold = BOLD_ONLY.match(match.group(1))
        if not bold:
            return match.group(0)
        inner = bold.group(2).strip()
        text = re.sub(r"<[^>]+>", "", inner)
        text = re.sub(r"\s+", " ", text).strip()
        if not (3 <= len(text) <= 80):
            return match.group(0)
        if text[-1:] in ".:;,”“’\"":
            return match.group(0)
        if text[:1] in "[•–—“\"":
            return match.group(0)
        # Callout labels and exclamatory sentences are body text, not headings.
        lowered = text.lower()
        if lowered.startswith(("read:", "next:", "previous")):
            return match.group(0)
        if "!" in text or "? " in text or ". " in text:
            return match.group(0)
        if re.match(r"^\d{1,2}[.)]\s", text) or re.match(r"^[a-z]\)\s", text, re.IGNORECASE):
            return match.group(0)
        arabic = len(ARABIC_LETTER.findall(text))
        latin = len(LATIN_LETTER.findall(text))
        if arabic and arabic >= latin:
            return match.group(0)
        if len(text.split()) == 1 and not text[:1].isupper():
            return match.group(0)
        return "<h3>%s</h3>" % inner

    return PARAGRAPH.sub(paragraph, value)


def clean_html(value: str) -> str:
    out = value or ""
    out = COMMENT.sub("", out)
    out = SCRIPT_OR_STYLE.sub("", out)
    out = clean_text(out)
    out = BR.sub("<br>", out)
    # Invalid outer paragraph around block content (47 source pages).
    stripped = out.strip()
    if stripped.lower().startswith("<p><div") and stripped.endswith("</p>"):
        inner = stripped[3:-4].strip()
        if inner.startswith("<div") and inner.endswith("</div>"):
            out = inner
    # A paragraph directly around a table is equally invalid.
    out = re.sub(r"(?is)<p>\s*(<table\b.*?</table>)\s*</p>", r"\1", out)
    # Unwrap before normalization: these wrappers split a word or a spacing
    # boundary across two text nodes, and normalizing each node first leaves
    # the joined result unnormalized (and NFC-composes Arabic too late).
    out = INLINE_WRAPPER.sub("", out)
    out = _quote_paragraphs(out)
    out = _strip_list_markers(out)
    out = normalize_text_nodes(out)
    out = _list_paragraphs(out)
    out = _promote_headings(out)
    out = _normalize_heading_levels(out)
    out = type_references(out, "explanation")
    out = EMPTY_BLOCK.sub("", out)
    return out.strip()


def article_semantic_key(value: str) -> str:
    """Formatting-only fingerprint: tags, list markers and spacing removed."""
    text = value or ""
    text = COMMENT.sub("", text)
    text = SCRIPT_OR_STYLE.sub("", text)
    # Block boundaries are word boundaries; inline tags are not (a word or even
    # one Arabic grapheme can be split by <span> in this corpus, and the app
    # joins it back). Strip tags BEFORE NFC so a split grapheme composes.
    text = re.sub(
        r"(?is)</?(?:p|div|h[1-6]|li|ul|ol|blockquote|table|thead|tbody|tr|td|th|br|hr)\b[^>]*>",
        " ",
        text,
    )
    text = re.sub(r"</?[a-zA-Z][^>]*>", "", text)
    text = html.unescape(text)
    text = unicodedata.normalize("NFC", text)
    for pattern, replacement in HONORIFICS:
        text = pattern.sub(" HONORIFIC ", text)
    text = HONORIFIC_FORM.sub(" HONORIFIC ", text)
    text = HONORIFIC_PARENS.sub(" HONORIFIC ", text)
    text = HONORIFIC_OPEN.sub("", text)
    text = HONORIFIC_CLOSE.sub(" HONORIFIC ", text)
    text = re.sub(r"\(\s*HONORIFIC\s*\)", "HONORIFIC", text)
    text = re.sub(r"\(\s*\d{1,2}\s*\)", " ", text)
    text = re.sub(r"(?:^|\s)\d{1,2}[.)]\s+", " ", text)
    text = re.sub(r"[•–—]", " ", text)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s*([,.;:!?])\s*", r"\1", text)
    text = re.sub(r"([“‘(])\s*", r"\1", text)
    text = re.sub(r"\s*([”’)\]])", r"\1", text)
    return text.strip()


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


def freeze_keys(root: Path, out: Path) -> dict[str, str]:
    keys = {
        path.relative_to(root).as_posix(): article_semantic_key(
            json.loads(path.read_text(encoding="utf-8")).get("content") or ""
        )
        for path in _article_files(root)
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"schema": 1, "records": keys}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return keys


def main(argv: list[str]) -> int:
    args = argv[1:]
    if args and args[0] == "--freeze":
        root = Path(args[1]) if len(args) > 1 else Path(__file__).resolve().parents[2] / "archive" / "assets" / "dua_dhikr" / "articles"
        out = Path(args[2]) if len(args) > 2 else Path(__file__).resolve().parents[2] / "deployment" / "goldens" / "article_semantic_keys.json"
        keys = freeze_keys(root, out)
        print(f"froze {len(keys)} article keys -> {out}")
        return 0

    roots = [Path(arg) for arg in args]
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
