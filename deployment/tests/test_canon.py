"""Unit + corpus tests for the dua canonicalizer.

Run from the khushu-data-api repo root:
    python3 -m unittest discover -s deployment/tests -v
"""
from __future__ import annotations

import json
import os
import unittest

from deployment.canon.blocks import canonical_blocks, heading_level, plain_projection
from deployment.canon.dua import canonicalize_record, verify_semantic_keys
from deployment.canon.text import (
    bold_narrator,
    inline_markup,
    normalize,
    semantic_key,
    wrap_honorifics,
    wrap_quotes,
)

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ORIGINAL = os.path.join(ROOT, "archive/assets/dua_dhikr/dua_data.original.json")
CANONICAL = os.path.join(ROOT, "archive/assets/dua_dhikr/dua_data.canonical.json")


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class NormalizeTests(unittest.TestCase):
    def test_entities_crlf_nbsp_nfc(self):
        self.assertEqual(normalize("Marriage &#038; Children"), "Marriage & Children")
        self.assertEqual(normalize("a\r\nb\r\n\r\nc"), "a\nb\n\nc")
        self.assertEqual(normalize("a\u00a0\u00a0b"), "a b")
        self.assertEqual(normalize("  a  \n  b  "), "a\nb")
        self.assertEqual(normalize("a\x0bb"), "ab")

    def test_does_not_decompose_honorific_ligatures(self):
        self.assertIn("ﷺ", normalize("The Prophet ﷺ said"))
        self.assertIn("ﷻ", normalize("Allah ﷻ"))


class InlineMarkupTests(unittest.TestCase):
    def test_emphasis(self):
        self.assertEqual(inline_markup("**bold**"), "<b>bold</b>")
        self.assertEqual(inline_markup("*italic*"), "<i>italic</i>")
        self.assertEqual(inline_markup("***both***"), "<b><i>both</i></b>")

    def test_literal_asterisk_is_preserved_as_entity(self):
        self.assertEqual(inline_markup("upon a Muslim*].", literal_asterisk=True), "upon a Muslim&#42;].")

    def test_unmatched_italic_marker_is_debris_by_default(self):
        self.assertEqual(inline_markup("text *debris"), "text debris")

    def test_known_tags_survive(self):
        self.assertEqual(
            inline_markup('<hon kind="saw">ﷺ</hon>', emit_tags=True),
            '<hon kind="saw">ﷺ</hon>',
        )
        self.assertEqual(inline_markup('<hon kind="saw">ﷺ</hon>', emit_tags=False), "ﷺ")

    def test_unknown_tag_is_escaped(self):
        self.assertEqual(inline_markup("<script>x</script>"), "&lt;script&gt;x&lt;/script&gt;")


class HonorificTests(unittest.TestCase):
    def test_wraps_existing_honorifics_as_arabic(self):
        out = wrap_honorifics(
            "The Prophet ﷺ said; Allah ﷻ; raḍiy Allāhu ‘anhu; subḥānahū wa taʿālā; ʿazza wa jall",
            "virtue",
        )
        self.assertIn('<hon kind="saw">ﷺ</hon>', out)
        self.assertIn('<hon kind="jj">ﷻ</hon>', out)
        self.assertIn('<hon kind="ra">رَضِيَ اللَّهُ عَنْهُ</hon>', out)
        self.assertIn('<hon kind="swt">سُبْحَانَهُ وَتَعَالَى</hon>', out)
        self.assertIn('<hon kind="awj">عَزَّ وَجَلَّ</hon>', out)

    def test_ra_plural_and_feminine_forms(self):
        out = wrap_honorifics(
            "The Companions (raḍiy Allāhu ʿanhum) and ʿĀ’ishah (raḍiy Allāhu ʿanhā)",
            "explanation",
        )
        self.assertIn("رَضِيَ اللَّهُ عَنْهُمْ", out)
        self.assertIn("رَضِيَ اللَّهُ عَنْهَا", out)

    def test_does_not_wrap_title_or_arabic(self):
        self.assertEqual(wrap_honorifics("The Prophet ﷺ", "title"), "The Prophet ﷺ")
        self.assertEqual(wrap_honorifics("ﷺ", "arabic"), "ﷺ")


class NarratorTests(unittest.TestCase):
    def test_bolds_first_virtue_narrator(self):
        out = bold_narrator("Anas bin Mālik (raḍiy Allāhu ʿanhu) narrated that ...", "virtue")
        self.assertTrue(out.startswith("<b>Anas bin Mālik (raḍiy Allāhu ʿanhu)</b> narrated"))

    def test_keeps_comma_outside_bold(self):
        out = bold_narrator("Muʿādh b. ʿAbdullāh, narrated from his father", "virtue")
        self.assertTrue(out.startswith("<b>Muʿādh b. ʿAbdullāh</b>, narrated"))

    def test_does_not_touch_explanation_or_pronoun(self):
        self.assertEqual(
            bold_narrator("Anas bin Mālik narrated ...", "explanation"),
            "Anas bin Mālik narrated ...",
        )
        self.assertEqual(bold_narrator("He said: something", "virtue"), "He said: something")


class QuoteTests(unittest.TestCase):
    def test_wraps_direct_speech(self):
        out = wrap_quotes('He said: “Peace be upon you.”', "virtue")
        self.assertIn("<i>“Peace be upon you.”</i>", out)

    def test_leaves_mention_quote_plain(self):
        text = 'He described Allah as “the Ever Living”.'
        self.assertEqual(wrap_quotes(text, "explanation"), text)

    def test_skips_nested_quote_instead_of_partial_wrap(self):
        text = 'He said: “Outer “inner” outer.”'
        self.assertEqual(wrap_quotes(text, "virtue"), text)


class HeadingTests(unittest.TestCase):
    def test_known_headings(self):
        self.assertEqual(heading_level("**Brief Commentary (Surah al-Ikhlas)**"), 1)
        self.assertEqual(heading_level("**Action Points & Benefits**"), 1)
        self.assertEqual(heading_level("**Living by Āyat al-Kursī**"), 1)
        self.assertEqual(heading_level("*The Greatest Ayah*"), 2)

    def test_unknown_bold_is_not_a_heading(self):
        self.assertIsNone(heading_level('**“Allah”**'))


class BlockTests(unittest.TestCase):
    def test_heading_splice(self):
        blocks = canonical_blocks(
            "explanation",
            "**Benefits & Action Points***The Greatest Ayah*",
            [],
        )
        self.assertEqual([b["type"] for b in blocks], ["heading", "heading"])
        self.assertEqual([b["level"] for b in blocks], [1, 2])
        self.assertEqual(blocks[0]["text"], "Benefits &amp; Action Points")
        self.assertEqual(blocks[1]["text"], "The Greatest Ayah")

    def test_triple_collision_splits_bullet_and_paragraph(self):
        raw = "• Intro ***“O Allah, I ask You.”"
        blocks = canonical_blocks("explanation", raw, [])
        self.assertEqual(blocks[0]["type"], "bullet")
        self.assertIn("Intro", blocks[0]["text"])
        self.assertEqual(blocks[1]["type"], "paragraph")
        self.assertTrue(blocks[1]["text"].startswith("“O Allah"))

    def test_bullets_and_paragraph_projection(self):
        blocks = canonical_blocks("explanation", "**Brief Commentary**• One• Two", [])
        self.assertEqual([b["type"] for b in blocks], ["heading", "bullet", "bullet"])
        self.assertEqual(plain_projection(blocks), "Brief Commentary\n\n• One\n• Two")

    def test_literal_asterisk_survives_plain_projection(self):
        blocks = canonical_blocks(
            "translation", "and upon a Muslim*].", []
        )
        self.assertEqual(plain_projection(blocks), "and upon a Muslim*].")


class SemanticKeyTests(unittest.TestCase):
    def test_formatting_is_ignored(self):
        source = "**Brief Commentary**• *One* and `two`"
        canonical = "Brief Commentary\n\n• One and two"
        self.assertEqual(semantic_key(source), semantic_key(canonical))

    def test_literal_asterisk_is_preserved(self):
        self.assertIn("*", semantic_key("upon a Muslim*]."))

    def test_honorific_spelling_variants_are_equal(self):
        self.assertEqual(
            semantic_key("raḍiy Allāhu ‘anhu"),
            semantic_key("raḍiy Allāhu ʿanhu"),
        )


@unittest.skipUnless(os.path.exists(ORIGINAL) and os.path.exists(CANONICAL), "canonical data not generated")
class CorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = _load(ORIGINAL)
        cls.canonical = _load(CANONICAL)
        cls.by_id = {r["id"]: r for r in cls.canonical}

    def test_all_semantic_keys_match(self):
        issues = []
        for src in self.original:
            rec = canonicalize_record(src, issues)
            self.assertEqual(verify_semantic_keys(src, rec, strict=False), [], f"id={src['id']}")

    def test_all_plain_projections_are_markup_free(self):
        for rec in self.canonical:
            for field in ("title", "post_title", "arabic", "repetition", "translation",
                          "transliteration", "virtue", "explanation", "reference"):
                value = rec.get(field) or ""
                self.assertNotIn("**", value, f"id={rec['id']} {field}")
                self.assertNotIn("`", value, f"id={rec['id']} {field}")

    def test_golden_heading_splice(self):
        for rid in (80, 167, 174):
            blocks = self.by_id[rid]["blocks"]["fields"]["explanation"]
            found = [(b["type"], b.get("level"), b["text"]) for b in blocks]
            self.assertIn(("heading", 1, "Benefits &amp; Action Points"), found)
            self.assertIn(("heading", 2, "The Greatest Ayah"), found)

    def test_golden_collision_splits(self):
        for rid in (57, 83, 176):
            blocks = self.by_id[rid]["blocks"]["fields"]["explanation"]
            self.assertTrue(any(b["type"] == "quote" and b["text"].startswith("“O Allah") for b in blocks))

    def test_golden_arabic_basmala_blocks(self):
        for rid in (33, 57):
            blocks = self.by_id[rid]["blocks"]["fields"]["arabic"]
            self.assertEqual([b["type"] for b in blocks], ["bismillah", "arabic"] * 3)
            self.assertTrue(all(b["text"].startswith("بِسْمِ اللّٰهِ") for b in blocks[::2]))

    def test_golden_bullets_and_narrator(self):
        self.assertEqual(self.by_id[17]["blocks"]["fields"]["explanation"][0]["text"], "Brief Commentary")
        self.assertTrue(self.by_id[17]["virtue"].startswith("Abū Saʿīd al-Khudrī (رَضِيَ اللَّهُ عَنْهُ) narrated"))
        self.assertTrue(self.by_id[2]["blocks"]["fields"]["virtue"][0]["text"].startswith("<b>Anas bin Mālik"))


if __name__ == "__main__":
    unittest.main()
