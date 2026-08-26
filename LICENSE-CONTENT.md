# Content License Table

Every pack in this repository MUST have a row here. Packs without a row
will be rejected by the API's license-completeness check.

| Directory | Content | Source/Author | License/Terms | Redistribution |
|---|---|---|---|---|
| `assets/asma_ul_husna/` | Names of Allah JSON + audio | khushu project | Project-owned | ✅ Free |
| `assets/adhan/` | Adhan audio recordings | Various reciters | Per-reciter permission | ✅ With attribution |
| `assets/dua_dhikr/` | Duas, dhikr, articles JSON + audio | khushu pipeline (scraped from public sources) | Public religious text; presentation © khushu | ✅ Free |
| `assets/islamic_calendar/` | Islamic events JSON | Exported from khushu-engine core | Project-owned | ✅ Free |
| `inventory/translations/*/` | Quran translations | Individual translators/publishers | **Per-pack copyright** — see each manifest.json `author` field | ⚠️ Verify per pack |
| `inventory/tafsirs/*/` | Tafsir books | Individual authors/publishers | **Per-book copyright** | ⚠️ Verify per book |
| `inventory/hadiths/*.db` | Hadith corpora (ar+en) | sunnah.com-derived data | sunnah.com terms apply to derived data | ⚠️ Non-commercial |
| `inventory/wbw/` | Word-by-word packs | AlfaazPlus/QuranAppInventory (GPLv3 family) | GPLv3 | ✅ Free |
| `inventory/quran_scripts/` | Quran script text JSONs | AlfaazPlus/QuranAppInventory (GPLv3 family); underlying text public domain | GPLv3 / public text | ✅ Free |
| `inventory/fonts/` | Mushaf rendering fonts | KFQPC / AlfaazPlus | Per-font license (KFQPC: free for non-commercial) | ⚠️ Non-commercial |
| `inventory/recitations/` | Recitation index metadata | Per-reciter | Index-only; audio hosted externally | ✅ Metadata only |
| `inventory/chapters/` | Chapter metadata | AlfaazPlus/QuranAppInventory | GPLv3 | ✅ Free |

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
