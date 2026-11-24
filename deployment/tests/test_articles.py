"""Tests for the long-form article canonicalizer.

Run from the khushu-data-api repo root:
    python3 -m unittest discover -s deployment/tests -v
"""
from __future__ import annotations

import json
import os
import re
import unittest
from pathlib import Path

from deployment.canon.articles import (
    BULLET_MARK,
    PARAGRAPH,
    article_semantic_key,
    clean_html,
    clean_text,
)

ROOT = Path(__file__).resolve().parents[2]
ARTICLES = ROOT / "archive" / "assets" / "dua_dhikr" / "articles"
GOLDENS = ROOT / "deployment" / "goldens" / "article_semantic_keys.json"


def _files() -> list[Path]:
    return sorted(
        path
        for path in ARTICLES.rglob("*.json")
        if path.name != "index.json"
    )


class DestinationTests(unittest.TestCase):
    def test_bullet_paragraphs_become_a_list(self) -> None:
        self.assertEqual(
            "<ul><li>One</li><li>Two</li></ul>",
            clean_html("<p>•\tOne</p>\n<p>•\tTwo</p>"),
        )

    def test_dash_paragraphs_become_a_list(self) -> None:
        self.assertEqual(
            "<ul><li>First</li><li>Second</li></ul>",
            clean_html("<p>– First</p><p>– Second</p>"),
        )

    def test_numbered_paragraph_run_becomes_an_ordered_list(self) -> None:
        self.assertEqual(
            "<ol><li>One</li><li>Two</li></ol>",
            clean_html("<p>1. One</p><p>2. Two</p>"),
        )

    def test_numbered_run_starting_mid_list_keeps_its_start(self) -> None:
        self.assertEqual(
            '<ol start="4"><li>Four</li><li>Five</li></ol>',
            clean_html("<p>4. Four</p><p>5. Five</p>"),
        )

    def test_single_mid_list_number_stays_prose(self) -> None:
        self.assertEqual("<p>4. Four</p>", clean_html("<p>4. Four</p>"))

    def test_bold_only_heading_is_promoted(self) -> None:
        self.assertEqual(
            "<h3>When Leaving the Home</h3>",
            clean_html("<p><b>When Leaving the Home</b></p>"),
        )

    def test_lead_in_bold_and_callout_are_not_headings(self) -> None:
        for source in (
            "<p><b>Our beloved Prophet ﷺ would ask Allah:</b></p>",
            "<p><b>Read: Plan Your Ramadan</b></p>",
            "<p><b>How strong was his connection with His Lord!</b></p>",
            "<p><b>So what is a believer’s winter? And how does it differ?</b></p>",
        ):
            self.assertEqual(source, clean_html(source))

    def test_long_lone_quotation_becomes_a_blockquote(self) -> None:
        quote = (
            "“Allah is the Greatest. Allah is the Greatest. There is no god worthy "
            "of worship but Allah and Allah is the Greatest.”"
        )
        self.assertEqual(
            "<blockquote><p>%s</p></blockquote>" % quote,
            clean_html("<p>%s</p>" % quote),
        )

    def test_quote_lines_become_explicit_breaks(self) -> None:
        out = clean_html(
            "<p>“O you who are journeying to the Ancient House,\n"
            "You have journeyed with your bodies and we have journeyed with our hearts.”</p>"
        )
        self.assertIn("<br>", out)

    def test_long_quote_embedded_in_prose_becomes_a_blockquote(self) -> None:
        quote = (
            "“There are a hundred levels in Paradise which Allah has prepared for "
            "those who strive in His path. The distance between every two degrees "
            "is like the distance between the sky and the earth.”"
        )
        out = clean_html("<p>The Prophet ﷺ said, %s (Bukhārī).</p>" % quote)
        self.assertIn("<blockquote><p>%s</p><p>(Bukhārī).</p></blockquote>" % quote, out)
        self.assertTrue(out.startswith("<p>The Prophet ﷺ said,</p>"))

    def test_nested_quote_is_left_inline(self) -> None:
        source = (
            "<p>He said, “The man asked, “Why?” And the answer was long enough to "
            "read as a quotation but the inner sentence must stay intact.”</p>"
        )
        self.assertEqual(source, clean_html(source))

    def test_deep_heading_levels_are_normalised(self) -> None:
        self.assertEqual("<h3>Section</h3>", clean_html("<h4>Section</h4>"))
        self.assertEqual("<h3>Section</h3>", clean_html("<h6>Section</h6>"))

    def test_citations_are_typed(self) -> None:
        out = clean_html("<p>Allah says (2:255) and the Prophet ﷺ said (Bukhārī 6306).</p>")
        self.assertIn("<qref>2:255</qref>", out)
        self.assertIn('<ref id="bukhari">Bukhārī 6306</ref>', out)

    def test_combined_hadith_citations_are_both_typed(self) -> None:
        out = clean_html("<p>Reported by (Bukhārī 6316, Muslim 763).</p>")
        self.assertIn('<ref id="bukhari">Bukhārī 6316</ref>', out)
        self.assertIn('<ref id="muslim">Muslim 763</ref>', out)

    def test_nfc_composes_split_graphemes_and_honorifics(self) -> None:
        # The dot below the d is a combining mark in this source; NFC must
        # compose it before the honorific pattern can match.
        self.assertEqual("Anas رضي الله عنها", clean_text("Anas (raḍiy Allāhu ʿanhā)"))
        self.assertIn("آ", clean_html("<p>الْمَلَا</span>ٓئِكَةُ</p>"))

    def test_inline_spans_are_unwrapped(self) -> None:
        self.assertEqual("<p>one word</p>", clean_html("<p><span>one</span> <span>word</span></p>"))

    def test_text_spacing_is_typographic(self) -> None:
        self.assertEqual(
            "<p>He said, “Hi, there.”</p>",
            clean_html("<p>He said , “ Hi , there . ”</p>"),
        )

    def test_semantic_key_ignores_formatting(self) -> None:
        dirty = "<p>•\t<b>One</b> item</p><p>•\tTwo</p>"
        clean = "<ul><li><b>One</b> item</li><li>Two</li></ul>"
        self.assertEqual(article_semantic_key(dirty), article_semantic_key(clean))


class CorpusTests(unittest.TestCase):
    def test_every_article_is_idempotent(self) -> None:
        for path in _files():
            content = json.loads(path.read_text(encoding="utf-8"))["content"]
            once = clean_html(content)
            self.assertEqual(once, clean_html(once), path.name)

    def test_every_article_keeps_its_semantic_key(self) -> None:
        goldens = json.loads(GOLDENS.read_text(encoding="utf-8"))["records"]
        for path in _files():
            relative = path.relative_to(ARTICLES).as_posix()
            content = json.loads(path.read_text(encoding="utf-8"))["content"]
            self.assertEqual(
                goldens[relative],
                article_semantic_key(content),
                "%s changed content, not formatting" % relative,
            )

    def test_no_paragraph_starts_with_a_raw_list_marker(self) -> None:
        for path in _files():
            content = json.loads(path.read_text(encoding="utf-8"))["content"]
            for match in PARAGRAPH.finditer(content):
                text = re.sub(r"<[^>]+>", "", match.group(1)).strip()
                self.assertFalse(
                    BULLET_MARK.match(text),
                    "%s has a raw list marker in a paragraph: %s" % (path.name, text[:60]),
                )


if __name__ == "__main__":
    unittest.main()
