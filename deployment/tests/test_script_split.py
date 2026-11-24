"""Tests for splitting an embedded Arabic duʿāʾ out of English prose.

Run from the khushu-data-api repo root:
    python3 -m unittest discover -s deployment/tests -v
"""
from __future__ import annotations

import unittest

from deployment.canon.script_split import (
    MIN_ARABIC_LETTERS,
    find_arabic_run,
    split_arabic_runs,
)

# A real embedded duʿāʾ from the corpus (id 28).
DHIKR = (
    "لَا إِلٰهَ إِلَّا اللّٰهُ وَحْدَهُ لَا شَرِيْكَ لَهُ، لَهُ الْمُلْكُ وَلَهُ الْحَمْدُ، "
    "وَهُوَ عَلَىٰ كُلِّ شَيْءٍ قَدِيْرٌ، لَا إِلٰهَ إِلَّا اللّٰهُ، أَنْجَزَ وَعْدَهُ، "
    "وَنَصَرَ عَبْدَهُ، وَهَزَمَ الْأَحْزَابَ وَحْدَهُ"
)
HON = '<hon kind="ra">رَضِيَ اللَّهُ عَنْهُ</hon>'


class FindRunTest(unittest.TestCase):
    def test_finds_embedded_dhikr(self):
        text = f"and then said {DHIKR}. He then made duʿā’ in between."
        span = find_arabic_run(text)
        self.assertIsNotNone(span)
        start, end = span
        self.assertIn("لَا إِلٰهَ", text[start:end])

    def test_honorific_alone_is_not_a_run(self):
        text = f"Anas ({HON}) narrated that the Prophet ﷺ said something."
        self.assertIsNone(find_arabic_run(text))

    def test_short_arabic_is_not_a_run(self):
        text = "He said سُبْحَانَ اللّٰه and continued with a long English sentence."
        self.assertIsNone(find_arabic_run(text))

    def test_threshold_is_letters_not_characters(self):
        # Diacritics are not letters; a run of them alone must not qualify.
        text = "x " + "ً" * 60 + " y"
        self.assertIsNone(find_arabic_run(text))
        self.assertGreater(MIN_ARABIC_LETTERS, 0)


class SplitTest(unittest.TestCase):
    def test_splits_into_three_blocks(self):
        text = f"and then said {DHIKR}. He then made duʿā’ in between."
        out = split_arabic_runs([{"type": "paragraph", "text": text}], "virtue", [])
        self.assertEqual([b["type"] for b in out], ["paragraph", "arabic", "paragraph"])
        self.assertTrue(out[1]["text"].startswith("لَا إِلٰهَ"))

    def test_leading_run_has_no_empty_paragraph(self):
        text = f"{DHIKR} then he stopped."
        out = split_arabic_runs([{"type": "paragraph", "text": text}], "virtue", [])
        self.assertEqual([b["type"] for b in out], ["arabic", "paragraph"])

    def test_honorific_only_paragraph_untouched(self):
        text = f"Anas ({HON}) narrated that the Prophet ﷺ said something long."
        blocks = [{"type": "paragraph", "text": text}]
        self.assertEqual(split_arabic_runs(blocks, "virtue", []), blocks)

    def test_bullet_is_reported_not_split(self):
        text = f"• He said {DHIKR} and stopped."
        issues: list[dict] = []
        blocks = [{"type": "bullet", "text": text}]
        out = split_arabic_runs(blocks, "explanation", issues)
        self.assertEqual(out, blocks)
        self.assertTrue(any(i["reason"] == "arabic_run_in_bullet" for i in issues))

    def test_heading_untouched(self):
        blocks = [{"type": "heading", "level": 1, "text": "Brief Commentary"}]
        self.assertEqual(split_arabic_runs(blocks, "explanation", []), blocks)

    def test_idempotent(self):
        text = f"and then said {DHIKR}. He stopped."
        once = split_arabic_runs([{"type": "paragraph", "text": text}], "virtue", [])
        twice = split_arabic_runs(once, "virtue", [])
        self.assertEqual(once, twice)

    def test_plain_fields_untouched(self):
        text = f"and then said {DHIKR}."
        blocks = [{"type": "paragraph", "text": text}]
        self.assertEqual(split_arabic_runs(blocks, "reference", []), blocks)


class SemanticKeyTest(unittest.TestCase):
    def test_split_does_not_change_the_key(self):
        from deployment.canon.text import semantic_key

        text = f"and then said {DHIKR}. He then made duʿā’ in between."
        out = split_arabic_runs([{"type": "paragraph", "text": text}], "virtue", [])
        joined = " ".join(b["text"] for b in out)
        self.assertEqual(semantic_key(text), semantic_key(joined))


if __name__ == "__main__":
    unittest.main()
