#!/usr/bin/env python3
"""Export QuranApp's hardcoded glyph tables (QuranGlyphs.kt) into the
canonical khushu-data-api JSON: inventory/quran_metadata/quran_glyphs.json.

Extracted VERBATIM from donor code so no codepoint is mistyped; the donor
file is parsed, not transcribed by hand. Provenance recorded in _meta.
"""
import json
import re
from pathlib import Path

DONOR = Path(
    "/home/kaizen/AndroidStudioProjects/Osprey/reference/QuranApp/"
    "app/src/main/java/com/quranapp/android/utils/quran/QuranGlyphs.kt"
)
OUT = Path(
    "/home/kaizen/AndroidStudioProjects/khushu-quran-data/"
    "inventory/quran_metadata/quran_glyphs.json"
)

src = DONOR.read_text(encoding="utf-8")

def unescape(s: str) -> str:
    if s.startswith("\\u"):
        return chr(int(s[2:], 16))
    return s

def parse_array(name: str) -> list[str]:
    m = re.search(
        rf"object {name} \{{.*?private val icons = arrayOf\((.*?)\)",
        src, re.S,
    )
    if not m:
        raise SystemExit(f"icons array not found for {name}")
    body = m.group(1)
    return [unescape(x) for x in re.findall(r'"(\\u[0-9A-Fa-f]{4})"', body)]

def parse_special() -> dict[str, str]:
    out = {}
    m = re.search(r"object Special \{(.*?)\n    \}", src, re.S)
    if not m:
        raise SystemExit("Special object not found")
    for key, esc in re.findall(
        r'const val (\w+) = "(\\u[0-9A-Fa-f]{4}|[^"]+)"', m.group(1)
    ):
        if esc.startswith("\\u"):
            val = chr(int(esc[2:], 16))
        else:
            # literal non-ASCII char (e.g. SEJDA ۩) — take as-is
            val = esc
        out[key.lower()] = val
        out[key.lower() + "_cp"] = f"U+{ord(val):04X}"
    return out

chapter = parse_array("Chapter")
juz = parse_array("Juz")

# Donor semantics: chapter[0] is the PREFIX appended AFTER the number glyph
# in visual order (RTL context — ChapterIcon.kt does base += prefix).
# chapter[1..114] map to surah numbers 1..114. Juz array is indexed juz-1
# (JuzIcon.kt calls get(juzNo - 1)) and uses the quran_common font.
special = parse_special()

if len(chapter) != 115:
    raise SystemExit(f"expected 115 chapter entries (prefix + 114), got {len(chapter)}")
if len(juz) != 30:
    raise SystemExit(f"expected 30 juz entries, got {len(juz)}")

def cp(s: str) -> str:
    return f"U+{ord(s):04X}"

data = {
    "_meta": {
        "exported_at": "2026-08-30",
        "source": (
            "QuranApp app/src/main/java/com/quranapp/android/utils/quran/"
            "QuranGlyphs.kt (hardcoded PUA tables), verbatim parse; "
            "ornate brackets from ReaderItemsBuilder.kt (quran reference "
            "decorations); salawat from the SunnahApp corpora"
        ),
        "extractor": "tools/export_quran_glyphs.py",
        "note": (
            "canonical khushu-data-api export; reference app no longer "
            "required at runtime. Fonts live in inventory/fonts/quran_icons/"
        ),
        "notes": (
            "chapter prefix is APPENDED after the number glyph in visual "
            "order (donor ChapterIcon.kt: base += prefix, RTL context); "
            "juz array is 0-indexed (donor JuzIcon.kt: get(juzNo - 1))"
        ),
    },
    "fonts": {
        "surah_icon": "inventory/fonts/quran_icons/suracon.ttf",
        "common": "inventory/fonts/quran_icons/quran_common.ttf",
    },
    "special": special,
    "reference_decorations": {
        # Unicode standard chars used around inline ayah references in
        # reader/tafsir UIs (donor ReaderItemsBuilder.kt:1004). Fonts:
        # both icon-font Arabic stacks and the hadith Naskh cover them.
        "ornate_paren_left": {"glyph": "\uFD3F", "cp": "U+FD3F"},
        "ornate_paren_right": {"glyph": "\uFD3E", "cp": "U+FD3E"},
        # SALAWAT ligature — the ONLY special glyph the hadith corpora use
        # (verified across all 9 collections; e.g. bukhari x12636).
        "salawat": {"glyph": "\uFDFA", "cp": "U+FDFA"},
        # RLM/LRM direction marks embedded in donor text (U+200F x2566 in
        # bukhari-ar alone) — control chars, no glyph needed, listed for
        # parser awareness.
        "rtl_mark": {"glyph": "\u200F", "cp": "U+200F", "control": True},
        "ltr_mark": {"glyph": "\u200E", "cp": "U+200E", "control": True},
    },
    "chapter_icon": {
        "prefix": chapter[0],
        "prefix_cp": cp(chapter[0]),
        # surah number -> glyph (chapter[1..114])
        "by_surah": {
            str(n): {"glyph": g, "cp": cp(g)} for n, g in enumerate(chapter[1:], start=1)
        },
    },
    "juz_icon": {
        # juz number (1..30) -> glyph (donor indexes with juzNo - 1)
        "by_juz": {
            str(n): {"glyph": g, "cp": cp(g)} for n, g in enumerate(juz, start=1)
        },
    },
}

OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"wrote {OUT} ({len(chapter)-1} surahs, {len(juz)} juz, "
      f"{len(special)//2} special glyphs)")
