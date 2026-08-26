# Content Pack Formats

Every format in khushu-data-api, documented for developers and AI agents.

## Quran Scripts (`inventory/quran_scripts/{script}/{NNN}.json`)

Per-surah word-level JSON. Each file is a JSON array of verses.

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

Scripts available: `uthmani`, `indopak`, `kfqpc_v1`.

## Translation Packs (`inventory/translations/{lang}/{pack}/`)

- `manifest.json`: `{book, author?, displayName, langCode, langName?, version, downloadPath?}`
- Data files: flat JSON array of `{surah/chapter_number, ayah/verse_number, text}` objects
- Footnote markers inline as `<fn index>` in text

## Tafsir Packs (`inventory/tafsirs/{lang}/{book}/`)

Per-surah split JSON files for lazy loading (e.g. `split/82.json`).

## Hadith Corpora (`inventory/hadiths/{collection}.db`)

SQLite databases mirroring the CorpusBundle schema (see
`reference/SunnahApp/app/src/main/proto/sunnahapp/deliverable/v1/deliverable.proto`).

| Table | Key fields |
|---|---|
| `hadiths` | id PK, urn, collection_id, book_id, chapter_id, number |
| `hadith_contents` | hadith_id FK, lang, blocks_json |
| `books` | id PK, collection_id FK, number |
| `chapters` | id PK, book_id FK, number |
| `collections` | id PK, type, sort_order, has_volumes/books/chapters |
| `hadith_grades` | hadith_id FK, grade_id, label, lang |
| `hadith_narrators` | hadith_id FK, source, narrator_id, position |
| `hadith_references` | hadith_id FK, type, value |
| `hadith_related` | hadith_id FK, related_hadith_id |

### Blocks JSON taxonomy

Exactly four types exist across all 9 collections:

| type | count | semantics |
|---|---|---|
| matn | 151,881 | body text |
| sanad | 71,322 | chain-of-narration text |
| narrator | 66,952 | empty positional marker (aligns with hadith_narrators.position) |
| note | 26 | editorial notes (forty + ibnmajah only) |

### Inline markup vocabulary

Six tags verified across all corpora:

| Tag | Count | Meaning |
|---|---|---|
| `<br>` | 15,553 | line break |
| `<qref>` | 9,080 | Quran reference (custom — linkable ayah) |
| `<b>` | 3,924 | bold |
| `<ref>` | 212 | hadith/cross reference (custom) |
| `<sup>` | 156 | superscript |
| `<i>` | 88 | italic |

Parse via `ContentMarkup.parse(text)` → typed `ContentSpan`s.
Unknown tags pass through as literal text.

## Catalogs (`inventory/{translations,tafsirs,wbw}/available_*.json`)

Discovery manifests listing available packs per language with version numbers
and download URLs. Parsed by `CatalogParser.parse()` → `List<CatalogEntry>`.

## Islamic Events (`assets/islamic_calendar/islamic_events.json`)

Exported from khushu-engine core. Schema proven end-to-end (D15 contract).

## Scholars (`scholars_info.db`)

Single `scholars` table: id, short_name, full_name, arabic, rank,
birth_date/place, death_date/place, bio, teachers, students, kunya.
JOins to `hadith_narrators(narrator_id)` for narrator→bio lookup.
