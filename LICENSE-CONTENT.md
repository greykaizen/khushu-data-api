# Content License Table

Every pack in this repository MUST have a row here. Packs without a row
will be rejected by the API's license-completeness check.

| Directory | Content | Source/Author | License/Terms | Redistribution |
|---|---|---|---|---|
| `assets/asma_ul_husna/` | Names of Allah JSON + audio | khushu project | Project-owned | ✅ Free |
| `assets/adhan/` | Adhan audio recordings (178 opus; catalog `adhan_index.json` with reciter/region/style/sha256) | Various reciters | Per-reciter permission | ✅ With attribution |
| `assets/dua_dhikr/` | Duas, dhikr, articles JSON + audio | khushu pipeline (scraped from public sources) | Public religious text; presentation © khushu | ✅ Free |
| `assets/islamic_calendar/` | Islamic events JSON | Exported from khushu-engine core | Project-owned | ✅ Free |
| `inventory/translations/*/` | Quran translations (flat `{version, suras}` JSONs) | Individual translators/publishers | **Per-pack copyright** — see `available_translations_info.json` `author` field | ⚠️ Verify per pack |
| `inventory/tafsirs/*/` | Tafsir books | Individual authors/publishers | **Per-book copyright** | ⚠️ Verify per book |
| `inventory/hadiths/*.db` | Hadith corpora (ar+en) + `scholars_info.db` | sunnah.com-derived data; schema mirrors SunnahApp `deliverable.proto` | sunnah.com terms apply to derived data | ⚠️ Non-commercial |
| `inventory/wbw/` | Word-by-word packs (v1 packs/, v2 packs_v2/) + word audio timings | AlfaazPlus/QuranAppInventory (GPLv3 family) | GPLv3 | ✅ Free |
| `inventory/quran_scripts/` | Quran script text JSONs | AlfaazPlus/QuranAppInventory (GPLv3 family); underlying text public domain | GPLv3 / public text | ✅ Free |
| `inventory/quran_metadata/` | Surahs/ayahs/juz-hizb-rub/manzil/nav ranges/mushaf registry/names/aliases | Extracted from QuranApp `quranapp.db` (GPLv3 family); Quran text facts public domain | GPLv3 / public data | ✅ Free |
| `inventory/mushaf_layout/` | Mushaf line layouts (`mushaf_map`, `page_info`) + per-script word registries | Extracted from QuranApp `quranapp.db` + `page_info.db` | GPLv3 | ✅ Free |
| `inventory/atlas/` | Glyph texture atlases + glyph metrics | Mirrored from AlfaazPlus/QuranAppInventory; uthmani bundle = QuranApp shipped artifact | GPLv3 | ✅ Free |
| `inventory/quran_search/` | Normalized Arabic text for on-device search index | Extracted from QuranApp `arabic_search` table | GPLv3 / public text | ✅ Free |
| `inventory/similar/` | Similar verses + mutashabihat phrase data | Extracted from QuranApp `quranapp.db` | GPLv3 | ✅ Free |
| `inventory/topics/` | Topic taxonomy, localizations, ayah links, topic images | Extracted from QuranApp `topics.db`; images mirrored from AlfaazPlus/QuranAppInventory | GPLv3 | ✅ Free |
| `inventory/curated/verses/` | Curated verse sets (situational/major sins/recommended) — localized | QuranApp assets (GPLv3 family) | GPLv3 | ✅ Free |
| `inventory/curated/science/` | Topical Quran-science webview packs | QuranApp assets (GPLv3 family) | GPLv3 | ✅ Free |
| `inventory/fonts/` | Mushaf rendering fonts (`qpc/`, `kfqpc_v1/`) + icon fonts (`quran_icons/`: suracon, quran_common) + Quran text fallback (`quran_text/`: uthmanic_hafs) + hadith/tafsir text fonts (`sunnah/`: KFGQPC Uthman Taha Naskh, Noto Nastaliq Urdu, Noto Serif Bengali, Scheherazade New) | KFQPC / AlfaazPlus (GPLv3 family apps, fonts redistributed with them) / Google Noto (OFL) / SIL (Scheherazade OFL) | Per-font: KFQPC free for non-commercial; Noto+Scheherazade = OFL | ⚠️ KFQPC non-commercial; ✅ Noto/Scheherazade OFL |
| `inventory/recitations/` | Recitation index metadata + per-reciter ayah audio timings | Per-reciter; timings mirrored from AlfaazPlus/QuranAppInventory | Index + timings: GPLv3 family; audio hosted externally (verses.quran.com etc.) | ✅ Metadata/timings |
| `inventory/chapters/` | Chapter metadata | AlfaazPlus/QuranAppInventory | GPLv3 | ✅ Free |
| `inventory/other/` | Reference DB dumps (quranapp/page_info/topics + WBW/ayahsearch JSON exports) + rewritten CDN URL index | Extracted from QuranApp assets (GPLv3 family); urls.json rewrite project-owned | GPLv3 / project-owned | ✅ Free |

## Key notes

- **Code** in `/api` is GPLv3.
- **Quran Arabic text** is public domain as a religious text.
- **Translations** are individually copyrighted — Saheeh International,
  Clear Quran, etc. retain their own terms. Redistribution is permitted
  under their published policies for non-commercial use with attribution,
  but commercial use requires per-publisher permission.
- **Hadith English translations** carry similar per-translator terms.
- This repository does NOT host recitation audio directly — only metadata
  indexes pointing at external CDN URLs.
