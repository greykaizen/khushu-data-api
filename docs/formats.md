# Content Pack Formats

Every format in khushu-data-api, documented for developers and AI agents.
All inventory paths are relative to `inventory/`. Every file listed in the
MANIFEST is covered by `inventory/MANIFEST.sha256`.

## Retrieval API surface (`api/`, `com.khushu.data`)

Single entry point — `KhushuContent(fetcher)` over any injected
`transport.ContentFetcher` (host-supplied HTTP, or `LocalFetcher` for a
checkout):

```kotlin
KhushuContent(fetcher).use { content ->
    content.quran.surahs()                 // 114, 18 localization languages
    content.quran.ayahTexts(surahNo, script = "uthmani")
    content.quran.words(surahNo, script = "indopak")
    content.quran.translationPacks("en"); content.quran.translationText(packId, surahNo)
    content.quran.navigation(NavigationType.JUZ)
    content.quran.pageLines("qpc", page); content.quran.pageOfAyah("qpc", 2, 255)
    content.quran.wordRegistry("uthmani")  // 83,665 words
    content.quran.similarTo(ayahId); content.quran.topicsForAyah(ayahId)
    content.quran.search().search("الرحمن الرحيم")      // on-device FTS5
    content.quran.atlas.bundles(); content.quran.atlas.placementsByWord("uthmani")

    val sunnah = content.attachSunnah(File("inventory/hadiths"))
    sunnah.hadith("bukhari_urn_100010", "en"); sunnah.grades(id)
    sunnah.search(query, "en", limit)      // per-language FTS5 side index
}
```

## Quran metadata (`quran_metadata/`)

Exported once from the donor QuranApp (`tools/export_quran_structure.py`);
anchors verified at export (114 surahs · 6236 ayahs · `ayah_id =
surah_no*1000 + ayah_no`).

| File | Shape |
|---|---|
| `surahs.json` | `{_meta, surahs:[{number, ayah_count, revelation_order, revelation_type, rukus_count, names:{lang:{name, meaning}}}]}` |
| `ayahs.json` | `{_meta, columns, ayahs:[[ayah_id, surah_no, ayah_no, juz_no, hizb_no, rub_no, manzil_no, ruku_no, sajdah_type], ...]}` |
| `navigation_ranges.json` | `{ranges: {juz\|hizb\|rub\|manzil: {unit: [[surah, from_ayah, to_ayah], ...]}}}` |
| `mushafs.json` | `{scripts:[{id, code, display_name, parent_id}], mushafs:[{id, code, no_of_pages, lines_per_page, layout_sources}]}` |
| `surah_search_aliases.json` | `{aliases: {surah_no: {lang: [alias, ...]}}}` |

## Quran scripts (`quran_scripts/{script}/{NNN}.json`)

Per-surah word-level JSON. Each file is a JSON array of verses:

```json
[
  {
    "chapter_number": 2,
    "verse_number": 1,
    "words": [
      {"position": 1, "text": "الٓمٓ", "location": "2:1:1"},
      {"position": 2, "text": "١", "location": "2:1:2"}
    ]
  }
]
```

Scripts available: `uthmani/`, `indopak/` (per-surah) and the monolithic
`script_kfqpc_v1.json` shaped `{suras:[{index, ayas:[{id,index,text,page}]}]}`
(ayah text only — the API derives words by whitespace split).

## Mushaf layout (`mushaf_layout/`)

The page-rendering spec, two addressing schemes + canonical word registries:

- `page_info/{code}.json` — word-id-addressed lines (`{mushaf, name, pages,
  lines_per_page, columns, lines:[[page, line, type, centered, first_word_id,
  last_word_id, surah_no], ...]}`). Used by `qpc` (QCF), `indopak_13/15/16`.
  Only populated lines are stored; `lines_per_page` is the capacity.
- `mushaf_map/{code}.json` — ayah+word-index-addressed lines for
  `indopak_15/16`, `kfqpc_v1`, `qpc`. Word indices are 0-based within ayah.
- `words/{script}.json.gz` — canonical word registry in rendered order:
  `{script, columns:[ayah_id, word_index, text], words:[[...], ...]}` for
  `uthmani`, `dk_indopak`, `kfqpc_v1`, `kfqpc_v2`.
- Precedence: `page_info` wins when both exist (it matches the atlas glyph
  pipeline); `mushaf_map` is the fallback.

`mushafs.json` `layout_sources` says which specs cover each mushaf.

## Atlas glyph bundles (`atlas/`)

Pre-rendered glyph textures for pixel-perfect mushaf rendering without font
shaping. Catalog: `atlas/available_atlas_info.json`.

Bundles: `uthmani/6x.zip`, `dk_indopak/6x.zip`, `dk_indopak_v2/6x.zip`.
Each zip contains:

| Entry | Content |
|---|---|
| `meta.json` | `{schema_version, kind: word_glyph_atlas, font:{units_per_em, ascender_fu, descender_fu, height_fu, line_gap_fu}, base_ppem, layout:{kind, file}, sizes:[{label, scale, ppem, atlas, textures[]}]}` |
| `layout.json` (`meta.layout.file`) | `{documents: {docId: {text, glyphs:[{g, xa, ya, xo, yo}]}}}` — placements per word text, fu |
| `atlas.json` | `{ppem, textures:[{index, width, height, padding, channels, format, image}], glyphs:{glyphId:{atlas, x, y, w, h, bearing_x, bearing_y, advance}}}` |
| `atlas_N.png` | texture pages (grayscale) |

Feed these 1:1 into khushu-engine `engine-mushaf` (`AtlasSpec` +
`GlyphPlacement`) for line fitting (`Mushaf.fitPageScale`) and glyph
placement (`Mushaf.layoutAyah`). Word texts in the documents are unique per
bundle, so word-text is the lookup key (donor `AtlasWordShapeEntity` scheme).

## Translations (`translations/`)

- Catalog: `available_translations_info.json` →
  `{translations: {lang: {packId: {langCode, book, author, displayName, langName, version, downloadPath}}}}`
- Packs: flat files `{lang}/{lang}_{translator}.json` shaped
  `{version, suras:[{index, ayas:[{id, index, translation, footnotes?}]}]}`.
  Footnote markers inline as `<fn index=…>` in text; cross-references as
  `<reference chapter=… verses=…>…</reference>`. Both pass through raw —
  hosts resolve markers against each ayah's `footnotes` map.

## Tafsirs (`tafsirs/`)

- Catalog: `available_tafsirs_info.json`
- Per-book per-surah split JSON for lazy loading (`{lang}/{book}/split/{NNN}.json`)

## WBW (`wbw/`)

- Catalogs: `available_wbw_info.json` (v1) / `available_wbw_info_v2.json`
- `packs/wbw_{lang}.json.gz` (v1), `packs_v2/` (v2: + transliteration flags)
- `timings/wbw_a{surah}.json.gz` — per-word audio timing anchors

## Recitations (`recitations/`)

- `available_recitations_info_v2.json` / `available_recitation_translations_info_v2.json`
- `timings/{reciter}.json.gz` — per-ayah audio timing anchors

## Similarity & mutashabihat (`similar/`)

- `similar_verses.json` — `{pairs: {source_ayah_id: [[matched_ayah_id,
  matched_words_count, coverage, score, match_words], ...]}}`
- `mutashabihat.json` — `{phrases:[[phrase_id, surahs_count, ayahs_count,
  occurrence_count, source_ayah_id, word_from, word_to], ...],
  occurrences: {phrase_id: [[ayah_id, word_ranges, in_ayah_order], ...]}}`

## Topics (`topics/topics.json`)

`{topics:[[id, slug, type, image_url, icon, flags], ...],
localizations:{id:{lang:[title, short, desc]}}, ayahs:{id:[ayah_id, ...]},
relationships:[[src, tgt, type, sort_order], ...]}`

## Quran search (`quran_search/arabic_text.json`)

Diacritic-stripped normalized text for all 6236 ayahs
(`{ayahs:[[ayah_id, text], ...]}`). The API builds an in-memory or
file-backed FTS5 index on demand (`QuranApi.search(indexDb)`).

## Curated (`curated/`)

- `verses/{type0,type1,type2,major_sins}/{lang}/{set}.json` + `map.json`
  (id → "surah:ayah-range" refs) — situational remedies, duas, etiquettes,
  major sins
- `verses/recommended/rules.json` + `lang_{lang}.json` — time-based
  recommendation rules
- `science/index.json` + `*.html` — Quran-science topical pages

## Dua & dhikr assets (`assets/dua_dhikr/`)

The lifewithallah corpus — retrieval via `content.dua.*` (`DuaApi`):

- `dua_data.json` — 491 duas: `{id, post_id, post_title, category,
  subcategory, title, arabic, repetition, translation, transliteration,
  virtue, explanation, audio_url, reference}`. Categories:
  `main-adhkar` (12 subcategories) + `other-adhkar` (18). Pure structured
  JSON — no HTML. Audio: 489 remote URLs + local mirrors `dua_{id}.opus`
  (2 entries have no audio).
- `articles_index.json` — 12 categories → **186 index entries = 169
  unique articles + 17 double-indexed** (same article under two
  categories — donor index property). Entry: `{id, title, slug, link,
  file_path}`.
- `articles/{cat}/{slug}.json` + `related-articles/{cat}/{slug}.json` —
  `{id, title, slug, link, content}` where `content` is **raw HTML**
  (standard tags: p/b/span/div/h2/blockquote/…; zero custom tags) —
  passthrough contract: hosts render with their own markup stack.
- `dhikr-dua/{main,other}-adhkar/{sub}.json` — same entries split per
  subcategory (alternative access, + `local_id`).

## Asma ul-husna assets (`assets/asma_ul_husna/`)

`asma_data_{lang}.json` × 11 languages (ar,bn,de,en,es,fa,fr,id,ru,tr,ur):
`{code, status, data: {title, description, hadith, recitation_benefits,
total: 99, names: [{number, name, transliteration, translation, meaning,
audio}]}}`. Pure JSON — retrieval via `content.dua.asmaPack(lang)` /
`asmaName(lang, number)`.

## Catalogs

Discovery manifests: `translations/available_translations_info.json`,
`tafsirs/available_tafsirs_info.json`, `wbw/available_wbw_info*.json`,
`recitations/available_recitations_info_v2.json`,
`atlas/available_atlas_info.json`. Parsed by `CatalogParser` /
`AtlasCatalogSource` → typed entries; download-state tracking via
`SyncTracker` (`CatalogApi.pendingUpdates`).

## Fonts (`fonts/`)

QPC/KFQPC TTF/WOFF binaries for non-atlas rendering paths (`fonts/qpc/`,
including by-page tars). 660 MB — Git LFS recommended for clones.

Icon/text font packs: catalog `fonts/available_fonts_info.json` →
- `fonts/quran_icons/` — surah header icons (`suracon.ttf`, U+E900–E972),
  bismillah / title frames / juz glyphs / meccan-medinan markers
  (`quran_common.ttf`). Pair with the PUA codepoint table below.
- `fonts/quran_text/` — non-atlas Quran text fallback (`uthmanic_hafs.ttf`).
- `fonts/sunnah/` — hadith + tafsir prose fonts: KFGQPC Uthman Taha Naskh
  (400 + 700; covers ﷺ U+FDFA — the only special glyph the hadith corpora
  use — and ornate brackets ﴿﴾), Noto Nastaliq Urdu, Noto Serif Bengali
  (400 + 700), Scheherazade New (tafsir prose).

## Quran glyph tables (`quran_metadata/quran_glyphs.json`)

PUA codepoint tables for decorative Quran glyphs, exported verbatim from
the donor's hardcoded `QuranGlyphs.kt` (parse, not transcription):

- `special` — `bismillah` U+FDFD · `title_frame` U+E000 · `meccan` U+E073 ·
  `medinan` U+E075 · `sejda` U+06E9 (each with a `*_cp` field).
- `reference_decorations` — ornate parens `﴿` U+FD3F / `﴾` U+FD3E (inline
  ayah references, donor `ReaderItemsBuilder.kt`), `salawat` ﷺ U+FDFA
  (hadith corpora), and `rtl_mark`/`ltr_mark` control chars (U+200F/E,
  embedded throughout donor text; no glyph needed).
- `chapter_icon` — `prefix` (U+E903, APPENDED after the number glyph in
  visual order — donor `ChapterIcon.kt` does `base += prefix` in RTL
  context) and `by_surah` 1..114 (NOT sequential: e.g. surah 48 → U+E902).
- `juz_icon` — `by_juz` 1..30, rendered with the `quran_common` font.

Rendering: surah icon = `by_surah[N].glyph + prefix` in `suracon`; juz =
`by_juz[N].glyph` in `quran_common`; bismillah/frame likewise in
`quran_common`. Hosts load the fonts from the `fonts/` packs and look up
codepoints here — no hardcoded tables left in app code.

## Hadith corpora (`hadiths/{collection}.db`)

SQLite databases mirroring the CorpusBundle schema (flattened from the
donor SunnahApp `deliverable.proto` protobuf bundles). Collections:
`bukhari, muslim, malik, nasai, ibnmajah, abudawud, tirmidhi,
riyadussalihin, forty`.

| Table | Key fields |
|---|---|
| `collections` | id PK, type, sort_order, has_volumes/books/chapters, numbering_source |
| `collections_translations` | collection_id FK, lang, title, intro, description |
| `books` / `chapters` | id PK, parent FK, number (+ `_translations`) |
| `hadiths` | id PK (e.g. `bukhari_urn_100010`), urn, collection_id, book_id, chapter_id, number |
| `hadith_contents` | hadith_id FK, lang, blocks_json |
| `hadith_grades` | hadith_id FK, grade_id, label, lang |
| `hadith_narrators` | hadith_id FK, source, narrator_id, position |
| `hadith_references` | hadith_id FK, type, value |
| `hadith_related` | hadith_id FK, related_hadith_id (nullable targets OK) |

`LocalHadithRepository` routes any corpus id by longest installed-prefix
match. `HadithSearchRepository` builds per-language FTS5 indexes in a SIDE
database (`search_index.db`), fingerprint-cached.

### Blocks JSON taxonomy

Exactly four types exist across all 9 collections:

| type | count | semantics |
|---|---|---|
| matn | 151,881 | body text |
| sanad | 71,322 | chain-of-narration text |
| narrator | 66,952 | empty positional marker (aligns with hadith_narrators.position) |
| note | 26 | editorial notes (forty + ibnmajah only) |

### Inline markup vocabulary

Six tags verified across all corpora: `<br>` (15,553) · `<qref>` (9,080,
Quran reference) · `<b>` (3,924) · `<ref>` (212, cross reference) · `<sup>`
(156) · `<i>` (88). Parse via `ContentMarkup.parse(text)` → typed
`ContentSpan`s. Unknown tags pass through as literal text.

## Scholars (`hadiths/scholars_info.db`)

Single `scholars` table: id, short_name, full_name, arabic, rank,
birth_date/place, death_date/place, bio, teachers, students, kunya.
Joins to `hadith_narrators(narrator_id)` for narrator→bio lookup.

## Integrity

`MANIFEST.sha256` — sha256 of every inventory file
(`find . -type f ! -name MANIFEST.sha256 -exec sha256sum {} \;`,
regenerate on any inventory change).

## Adhan audio (`assets/adhan/`)

178 donor-collected adhan recordings (mono Opus, mixed 16–48 kHz, per-reciter
permissions in LICENSE-CONTENT.md). Catalog: `adhan_index.json` —
`{id (hash-stripped filename stem), reciter, region, style ("Fajr"/"Eid
Takbir"/null), file, format, sampleRateHz, channels, sizeBytes, sha256}`.
Retrieval: `content.adhan.*` (`entries/reciters/byReciter/entry/audio(id)`).
Audio stays byte-identical to donors (no re-encode). **Playback**: Android
Media3/ExoPlayer decodes Opus on every API 21+ device (Khushu targets 12+);
the legacy MediaPlayer's pre-Android-10 Opus gap does not apply.

## Islamic events display data (`assets/islamic_calendar/`)

`islamic_events.json` — the engine's event set exported with
display/provenance fields (`title, hijriMonth, hijriDay, category,
recurrence, source, confidence`). **Canonical computation stays in
khushu-engine `calendar.events`** — this file is the localization/provenance
companion hosts overlay on engine-computed dates. Retrieval:
`content.islamicEvents.all()/forHijriMonth(month)`.

## Dua local audio mirrors (`assets/dua_dhikr/dua_{id}.opus`)

488 of the 491 duas carry local byte-identical opus mirrors. Retrieval:
`content.dua.localAudioPath(id)` / `content.dua.audio(id)` (null for the 3
mirrorless entries).

## Download tracking & space management

Wrap the transport to enable durable tracking + disk caching:

```kotlin
val caching = CachingFetcher(cacheDir, fetcher)   // cacheDir: host-provided
val content = KhushuContent(caching)
content.downloads.summary()        // items + totalBytes + bytesByCategory
content.downloads.deleteWhere { it.category == "inventory/tafsirs" }
content.downloads.clearAll()       // returns count removed
content.downloads.reconcile()      // drops rows whose files vanished
```

- The manifest (`downloads_manifest.json`) lives inside the cache dir —
  clearing the dir clears everything atomically.
- Categories = first two path segments (`assets/adhan`, `inventory/fonts`,
  …) — per-tier deletion is one filter.
- Android dir guidance: `context.cacheDir` (OS-managed) or
  `getExternalFilesDir` (user-visible); desktop suggestion
  `~/.khushu/content-cache`. The API records/deletes; hosts own policy.
- With a bare (non-caching) fetcher, `downloads` reports empty and deletes
  nothing — no silent surprises.

## Grouped composite (`quran.ayahBundle`)

One call, every tier about one ayah — independent multi-selection:

```kotlin
content.quran.ayahBundle(
    surahNo = 2, ayahNo = 255,
    scripts = listOf("uthmani", "kfqpc_v1"),
    translationPacks = listOf("en_pickthall", "en_yusuf-ali"),  // side-by-side
    wbwLanguages = listOf("en"),
    tafsirSlugs = listOf("en-tafisr-ibn-kathir"),
    reciters = listOf("abdul_basit"),                            // word timings
)
// → AyahBundle(texts, translations, wbw, tafsirs, recitationTimings)
```

Composes the per-surah lazy sources — the same fetch granularity as
individual calls, batched for the host.

## Size tiers (download planning)

| Tier | Size | Granularity |
|---|---|---|
| fonts (KFQPC per-page + tars) | 665 MB | per-script, on demand |
| hadiths | 301 MB | per-collection .db |
| adhan | 164 MB | per-reciter file (0.3–1.3 MB) |
| dua_dhikr | 110 MB | corpus JSON ~1 MB + per-file audio |
| tafsirs | 353 MB | **per-surah split** (lazy winner) |
| translations | 102 MB | per-pack |
| wbw | 21 MB | per-language gz |
| everything else (metadata/scripts/atlas/recitations/…) | < 30 MB | load-once |
