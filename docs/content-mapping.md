# Content Mapping Provenance — reference apps → khushu-data-api

Extraction completed 2026-08-28 by `tools/export_quran_structure.py` (kept in-repo
for re-runs). After this extraction the repo is **self-contained**: hosts never
need `reference/QuranApp`, `reference/SunnahApp`, or AlfaazPlus infrastructure
at runtime.

## QuranApp assets → inventory mapping

| Source (reference/QuranApp) | Inventory target | Format decision |
|---|---|---|
| `db/quranapp.db surahs+surah_localizations` | `quran_metadata/surahs.json` | 114 surahs + names/meanings in 18 langs |
| `db/quranapp.db ayahs` | `quran_metadata/ayahs.json` | compact arrays; `ayah_id = surah*1000 + ayah`; juz/hizb/rub/manzil/ruku/sajdah |
| `db/quranapp.db navigation_ranges` | `quran_metadata/navigation_ranges.json` | unit → contiguous `[surah, from, to]` segments (720 rows) |
| `db/quranapp.db scripts+mushafs` | `quran_metadata/mushafs.json` | registry incl. `layout_sources` coverage per mushaf |
| `db/quranapp.db surah_search_aliases` | `quran_metadata/surah_search_aliases.json` | 23 langs |
| `db/quranapp.db mushaf_map` | `mushaf_layout/mushaf_map/{code}.json` | per-mushaf line layout, ayah-addressed; **indopak_13 has no rows in donor** (page_info only) |
| `db/page_info.db info+pages` | `mushaf_layout/page_info/{code}.json` | word-id-addressed layout; word ids = 1-based running order of `ayah_words` for the rendered script |
| `db/quranapp.db ayah_words` | `mushaf_layout/words/{script}.json.gz` | 4 scripts × 83,665 words (uthmani, kfqpc_v1, kfqpc_v2, dk_indopak) |
| `db/quranapp.db arabic_search` | `quran_search/arabic_text.json` | normalized (diacritic-stripped) text; hosts build FTS on-device |
| `db/quranapp.db similar_verses` | `similar/similar_verses.json` | 3,552 pairs + word ranges/coverage/score |
| `db/quranapp.db mutashabihat_*` | `similar/mutashabihat.json` | 814 phrases + 3,555 occurrences |
| `db/topics.db` | `topics/topics.json` | 2,512 topics, 30,687 ayah links, ar/en localizations, parent/ontology edges |
| `assets/verses/` | `curated/verses/` (as-is) | type0/1/2 situational sets, major_sins (+map), recommended (+rules) — 123 localized files |
| `assets/science/` | `curated/science/` (as-is) | topical webview packs |
| `assets/atlas/uthmani/6x.zip` | `atlas/uthmani/6x.zip` (REPLACED ours) | reference bundle carries `layout.json` (schema_version 1); ours was older words.json variant |

Verified anchors at export: 114 surahs · 6236 ayahs · qpc page 1 line 2 = word
ids 1..5 = al-Fatihah 1:1 (4 words + ayah-end marker).

## SunnahApp → inventory mapping

| Source | Target | Notes |
|---|---|---|
| `corpus.pb.gz` bundles (9 collections) | `inventory/hadiths/*.db` | already done pre-extraction: SQLite mirrors the proto schema 1:1 (12 tables); `docs/deliverable.proto` now committed here as the schema of record |
| scholars data | `inventory/hadiths/scholars_info.db` | 25,260 rows; joins via `hadith_narrators(source, narrator_id)` |
| per-book splits | `inventory/hadiths/{collection}/books/*.json` | legacy offline path; `.db` is canonical |

## AlfaazPlus/QuranAppInventory mirrors (supply chain closed)

Verified byte-identical (sha256) where mirrored:

- `atlas/{dk_indopak,dk_indopak_v2}/6x.zip` — identical to upstream
- `wbw/packs/` — all 14 catalog languages complete
- `wbw/packs_v2/` — all 14 v2 packs (catalog `url` fields rewritten repo-relative)
- `wbw/timings/wbw_a1.json.gz` — single file covers all 114 suras (77,429 word timings)
- `fonts/qpc/` — release `qpc` assets; `.tar.zst` tracked (smaller), `.tar.gz` duplicates gitignored
- `recitations/timings/` — 28 reciter timing files (18 v2 + 10 translations)
- `topics/images/` — 65 webp images

Upstream has NO atlas bundles for kfqpc/nastaleeq scripts (404-verified) —
those scripts render via `fonts/` TTFs, not atlases. `kfqpc_v2`/`kfqpc_v4_tajweed`
word registries are exported from `ayah_words`; their glyph rendering tier is
font-based.

## Decisions

1. Catalog `url` / `timing_url` / topic `image_url` fields are **repo-root-relative
   paths** (`inventory/...`). Hosts prefix their base URL (or LocalFetcher resolves
   directly). External audio stays external (verses.quran.com templates).
2. `words/*.json.gz` are gzipped (repo size); API layer gunzips at fetch.
3. Layout specs ship in BOTH donor addressing schemes (mushaf_map =
   ayah+word-index; page_info = global word-id) — the API unifies them; see
   `docs/formats.md`.
4. `inventory/versions/` (Play-Store update pointers) deleted — this repo is no
   longer an app-update channel.
