"""Tests for reference typing: bare Quran/hadith citations -> typed spans.

Run from the khushu-data-api repo root:
    python3 -m unittest discover -s deployment/tests -v
"""
from __future__ import annotations

import unittest

from deployment.canon.refs import parse_quran_ref, type_references


class QuranCitationTest(unittest.TestCase):
    def test_plain_parenthesised(self):
        self.assertEqual(
            type_references("the Magnificent. (2:255)", "translation"),
            "the Magnificent. (<qref>2:255</qref>)",
        )

    def test_range_keeps_raw_form(self):
        self.assertEqual(
            type_references("the people.” (2:285-6)", "translation"),
            "the people.” (<qref>2:285-6</qref>)",
        )

    def test_quran_prefix_stays_literal(self):
        # The prefix is prose, not part of the reference: the plain projection
        # must stay byte-identical, so only the number pair is wrapped.
        self.assertEqual(
            type_references("acceptable to Allah (See Qur'an 3:85).", "explanation"),
            "acceptable to Allah (See Qur'an <qref>3:85</qref>).",
        )

    def test_quran_colon_prefix(self):
        self.assertEqual(
            type_references("understanding.” (Quran: 3:190), to the end", "virtue"),
            "understanding.” (Quran: <qref>3:190</qref>), to the end",
        )

    def test_see_only_prefix(self):
        self.assertEqual(
            type_references("in the Qur’ān (See 69:17).", "explanation"),
            "in the Qur’ān (See <qref>69:17</qref>).",
        )

    def test_out_of_range_surah_is_left_alone(self):
        text = "(999:1) is not a surah"
        self.assertEqual(type_references(text, "translation"), text)

    def test_bare_number_pair_without_parens_is_left_alone(self):
        text = "He said 3:190 without parentheses"
        self.assertEqual(type_references(text, "translation"), text)

    def test_prose_numbers_are_left_alone(self):
        for text in ("Recite it 3 times a day", "A ratio of 2:1 in the text"):
            self.assertEqual(type_references(text, "translation"), text)

    def test_plain_fields_are_not_typed(self):
        text = "(2:255)"
        self.assertEqual(type_references(text, "title"), text)
        self.assertEqual(type_references(text, "arabic"), text)

    def test_idempotent(self):
        once = type_references("(2:255) and (Muslim 899)", "virtue")
        self.assertEqual(type_references(once, "virtue"), once)


class HadithCitationTest(unittest.TestCase):
    def test_collection_gets_slug(self):
        self.assertEqual(
            type_references("give us rain” (46:24). (Muslim 899)", "virtue"),
            'give us rain” (<qref>46:24</qref>). (<ref id="muslim">Muslim 899</ref>)',
        )

    def test_diacritic_collection_name(self):
        self.assertEqual(
            type_references("ten verses (23:1-10).’”  (Tirmidhī 3173)", "virtue"),
            'ten verses (<qref>23:1-10</qref>).’”  (<ref id="tirmidhi">Tirmidhī 3173</ref>)',
        )


class ParseQuranRefTest(unittest.TestCase):
    def test_single_ayah(self):
        self.assertEqual(parse_quran_ref("2:255"), (2, 255))

    def test_range_uses_first_ayah(self):
        self.assertEqual(parse_quran_ref("2:285-6"), (2, 285))

    def test_invalid(self):
        self.assertIsNone(parse_quran_ref("999:1"))
        self.assertIsNone(parse_quran_ref("nonsense"))
        self.assertIsNone(parse_quran_ref(""))


class SemanticKeyTest(unittest.TestCase):
    def test_tags_do_not_change_the_key(self):
        from deployment.canon.text import semantic_key

        plain = semantic_key("the Magnificent. (2:255)")
        typed = semantic_key("the Magnificent. (<qref>2:255</qref>)")
        self.assertEqual(plain, typed)


if __name__ == "__main__":
    unittest.main()
