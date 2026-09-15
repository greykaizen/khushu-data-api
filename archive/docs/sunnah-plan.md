# Sunnah Module Plan (khushu-data-api · slice 2)

> Companion to `docs/quran-mod-plan.md`. Everything here is grounded in a
> FULL empirical scan of all 9 shipped collections (every row of
> `hadith_contents` read; counts below are exact, not samples).

---

## 1. Verified corpus facts

| Collection | hadiths (ar/en) | books | chapters |
|---|---|---|---|
| buhari | 7277 / 7277 | 97 | 3979 |
| muslim | 7459 / 7458 | — | — |
| nasai | 5768 / 5768 | — | — |
| abudawud | 5276 / 5276 | — | — |
| tirmidhi | 4053 / 4053 | — | — |
| ibnmajah | 4345 / 4345 | — | — |
| malik | 1860 ar / 1848 en ⚠ | — | — |
| riyadussalihin | 1896 / 1896 | — | — |
| forty | 122 / 122 | — | — |

⚠ malik/muslim en-counts lag ar by 1–12 rows — API must treat per-language
availability as a fact, never assume parity.

### 1.1 Blocks taxonomy — COMPLETE (full scan, not sampled)

Exactly **four types** exist across every collection:

| type | count | semantics |
|---|---|---|
| `matn` | 151,881 | hadith body text |
| `sanad` | 71,322 | chain-of-narration text |
| `narrator` | 66,952 | **empty-text positional marker** aligning with `hadith_narrators(position)` rows |
| `note` | 26 | editorial notes (forty, ibnmajah only) |

Any future type must flow through unchanged (open enum + raw passthrough).

### 1.2 Inline markup vocabulary — COMPLETE (exact global counts)

```
<br>   ×15,553   line breaks
<qref> ×9,080    Quran reference (custom tag → linkable ayah)
<b>    ×3,924    bold
<ref>  ×212      hadith/cross reference (custom tag)
<sup>  ×156      superscript (footnote-ish)
<i>    ×88       italic
```

**This closes the Osprey rendering failure**: the failure happened because the
tag vocabulary was never enumerated. It is now. The `/api` module parses these
six tags into typed inline spans so hosts render them WITHOUT any HTML engine.

## 2. Canonical model decision (locked)

SQLite `.db` = distribution format; models are proto-shaped
(`CorpusBundle` schema v1, `deliverable.proto` committed at
`reference/SunnahApp/app/src/main/proto/sunnahapp/deliverable/v1/`).
The `.db` tables map 1:1 onto bundle messages (verified field-by-field).

**2026-08-28 update — protobuf decode adapter RETIRED.** The upstream
`.pb.gz` corpora were flattened into the `.db` files and no `.pb.gz`
remains in the repo, so the planned optional importer has nothing to
read. Each corpus instead carries `bundle_meta(schema_version,
content_version)` stamped into the `.db` itself (§6), making the
distribution format self-describing. A decode adapter will only be
introduced if a new distribution format ever appears.

## 3. `/api` surface

```kotlin
// Models (translation joins resolved per langCode; per-lang availability explicit)
data class HadithCollection(id, type, sortOrder, hasVolumes, hasBooks,
                            hasChapters, numberingSource, title?, intro?)
data class Book(id, collectionId, number, title?, intro?, preamble?, notes?)
data class Chapter(id, collectionId, bookId, number, title?)
data class ContentSpan sealed: Text(text) · LineBreak · Bold(children) ·
                          Italic(children) · Superscript(children) ·
                          QuranRef(raw) · HadithRef(raw)
data class ContentBlock(type: BlockType /*MATN,SANAD,NARRATOR,NOTE,UNKNOWN*/,
                        rawType: String, spans: List<ContentSpan>, rawText: String)
data class Hadith(id, urn: Long?, collectionId, bookId, chapterId?, number,
                  blocks: List<ContentBlock>, references: List<Reference>,
                  relatedIds: List<String>, grades: List<Grade>,
                  narratorRefs: List<NarratorRef>)
data class Scholar(id, shortName, fullName, arabicName, rank?, birthDate?,
                   birthPlace?, deathDate?, deathPlace?, bio?, teachers?, students?)

interface HadithRepository {
    fun collections(lang: String): List<HadithCollection>
    fun books(collectionId: String, lang: String): List<Book>
    fun chapters(bookId: String, lang: String): List<Chapter>
    fun byId(id: String, lang: String): Hadith?
    fun byIds(ids: List<String>, lang: String): List<Hadith>
    fun forBook(bookId: String, lang: String): List<Hadith>        // paging host-side or via limit/offset params
    fun random(lang: String, gradeFilter: String? = null): Hadith?
    fun narratorsOf(hadithId: String): List<Scholar>               // narrator position join → scholars_info.db
    fun related(hadithId: String, installed: Set<String>): List<Hadith?>  // id-stubs for uninstalled targets
}

interface HadithSearchRepository {
    fun buildIndex(lang: String, rebuildIfStale: Boolean = true): IndexBuildResult
    fun search(query: String, lang: String, limit: Int, offset: Int): SearchResult
}
```

## 4. Inline-markup parser (the Osprey fix)

Pure function in the API: `ContentMarkup.parse(text): List<ContentSpan>`
- Recognizes exactly the six verified tags; unknown tags pass through as
  literal Text with a warning flag (never dropped, never rendered as markup)
- `<qref>`/`<ref>` carry raw inner content for the host to resolve into links
- Nested `<b><i>` handled recursively
- Unit-tested against the exact counts above (parser round-trips the corpus
  without losing a single character)

## 5. Scholars integration

`scholars_info.db` (single rich table) joined via `hadith_narrators`
(source, narrator_id, position) — `narrator` blocks' ordinal positions align
with these rows, enabling tap-on-narrator → scholar bio.

## 6. Versioning & sync

Every corpus carries `schema_version`/`content_version`, stored in a
`bundle_meta(key, value)` table stamped into each `.db` at ingestion
(schema_version = CorpusBundle schema generation, content_version =
sha256 prefix of the ingested file — upstream version numbers were lost
in the flatten, so content identity is content-addressed). Exposed on
`HadithCollection.schemaVersion`/`.contentVersion`.
`SyncRepository` (shared from Quran slice) tracks downloaded versions.

## 7. Testing anchors

- Per-collection hadith counts tabled above (ar vs en deltas flagged for
  malik/muslim)
- Full-parse invariant: sum of span text lengths ≥ raw length (markup replaced,
  nothing lost); zero parse exceptions across ALL rows
- Narrator-position alignment spot checks
- Search index build/query round-trip per language
