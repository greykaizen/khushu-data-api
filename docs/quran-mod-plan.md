# khushu-data-api — Quran Module Plan (v0.1)

> Full execution plan for transforming `greykaizen/khushu-quran-data` into
> **`greykaizen/khushu-data-api`** — a repo-based content distribution +
> retrieval-API project serving every Khushu-family app and any external
> consumer. Repo-based distribution only (GitHub raw + git tags); no Maven.
>
> Status: PLANNED · Sequencing: rename → hygiene → supply-chain → /api Quran
> slice → verify. Sunnah track is a separate follow-up session.

---

## 1. GitHub rename

```bash
gh repo rename khushu-data-api -R greykaizen/khushu-quran-data --yes
git -C ~/AndroidStudioProjects/khushu-quran-data remote set-url origin \
    https://github.com/greykaizen/khushu-data-api.git
```

- GitHub auto-redirects old raw URLs:
  `raw.githubusercontent.com/greykaizen/khushu-quran-data/master/<path>` keeps
  resolving during the grace period → Osprey's current build does not break.
- Osprey's hardcoded constant (`QuranAppConfig.REMOTE_BASE_URL`) updates at
  host-transplant, not now.
- Canonical base going forward:
  `https://raw.githubusercontent.com/greykaizen/khushu-data-api/master/`

## 2. Root hygiene + licensing

### 2.1 LICENSE file (most urgent — public repo redistributes copyrighted content)

Two-part license scheme at repo root:

```
LICENSE                     ← GPLv3 for all CODE in /api (matches engine)
LICENSE-CONTENT.md          ← per-pack content terms table (see 2.2)
```

### 2.2 Content-license table (`LICENSE-CONTENT.md` skeleton)

| Content | Source | License/Terms | Redistribution |
|---|---|---|---|
| Arabic Quran text (Uthmani/Indopak/KFQPC) | Tanzil / qurancomplex | public text; verify per script | permitted |
| Translations (Saheeh Intl, Clear Quran, Junagarhi …) | varies per pack | **individually copyrighted** — record author + permission source per pack | per-pack entry required |
| Tafsirs | per book | varies | per-book entry |
| Hadith corpora | sunnah.com-derived | sunnah.com terms + per-collection notes | per-collection entry |
| WBW data | AlfaazPlus-derived | GPLv3 (same upstream family) | permitted |
| Recitations metadata | per reciter | audio hosted externally; index-only | permitted |
| Adhan audio | recorded assets | verify per file | per-file entry |
| Asma-ul-Husna JSON+audio | own pipeline | engine-project owned | permitted |
| islamic_events.json | exported from engine (D15 contract) | project owned | permitted |

Rule enforced by review checklist: **no pack ships without a row in this
table.** The `/api` catalog parser will eventually expose this table
programmatically (`PackLicense(termsUrl, permittedRedistribution)`).

### 2.3 Cleanup

- Delete `versions/*.json` (stale QuranApp Play-Store update pointer — repo is
  no longer an app-update channel)
- Delete empty `split_quran_scripts.py`
- Review `download_all_languages.py`: either finish (proper downloader with
  manifest validation) or move to `tools/legacy/`
- Add `.gitattributes` (`*.db binary`, `*.gz binary`, `*.zip binary`,
  `*.png binary`)

## 3. Supply-chain independence (break AlfaazPlus)

QuranApp hardwires these AlfaazPlus URLs (verified in source):

| Artifact | AlfaazPlus URL pattern | Mirror target |
|---|---|---|
| Atlas glyph bundles | `ghraw://AlfaazPlus/QuranAppInventory/master/atlas/{script}/{density}x.zip` | `inventory/atlas/{script}/{density}x.zip` |
| QPC font binaries | `github.com/AlfaazPlus/QuranAppInventory/releases/download/qpc/{file}` | `inventory/fonts/qpc/{file}` |
| KFQPC fonts | same releases path | `inventory/fonts/kfqpc_v1/…` (partially present — complete) |
| WBW translation packs | `ghraw://…/wbw/wbw_{lang}.json.gz` | `inventory/wbw/packs/wbw_{lang}.json.gz` |
| WBW audio timings | `ghraw://…/wbw_timings/wbw_a1.json.gz` | `inventory/wbw/timings/wbw_a{surah}.json.gz` |

Steps:
1. Download each artifact set to `inventory/…` (verify sizes <100 MB/file;
   Git LFS for anything larger — density zips expected ~10–60 MB each)
2. Rewrite every catalog `url` field (`available_wbw_info*.json`, future
   catalogs) from `ghraw://AlfaazPlus/…` → relative repo paths or canonical
   base URL
3. Add `inventory/MANIFEST.sha256` — sha256sum of every mirrored file
   (integrity baseline + mechanical diffing on updates)
4. Result: **zero runtime dependencies on AlfaazPlus infrastructure**

## 4. Repository layout (post-transformation)

```
khushu-data-api/
├── LICENSE                       GPLv3 (code)
├── LICENSE-CONTENT.md            per-pack content terms table
├── README.md                     project intro + quickstart for devs/agents
├── .gitattributes                binary markers (db/gz/zip/png/mp3)
├── api/                          Kotlin/JVM module (the retrieval API)
│   ├── build.gradle.kts          kotlin("jvm") 2.4.10 · kotlinx-serialization · okio
│   ├── src/main/kotlin/com/khushu/data/
│   │   ├── model/                typed content models (see §5)
│   │   ├── repo/                 ContentRepository + Remote/Local sources
│   │   ├── catalog/              available_*_info.json discovery/state
│   │   ├── quran/                Quran query surface (slice 1)
│   │   └── transport/            injected fetch interfaces
│   └── src/test/kotlin/          tests against real repo files
├── docs/
│   ├── formats.md                every pack format documented (devs/agents)
│   ├── quran-mod-plan.md         this document
│   └── sunnah-plan.md            (follow-up session)
├── inventory/                    distribution tier (912 MB+, unchanged structure
│                                 plus new mirrors from §3)
├── assets/                       small always-shipped content (unchanged)
└── tools/                        download_all_languages.py etc.
```

## 5. `/api` module design — Quran slice

### 5.1 Technology decisions

| Concern | Choice | Why |
|---|---|---|
| Language/toolchain | Kotlin 2.4.10 · JVM 21 | match engine |
| Serialization | kotlinx-serialization-json | matches engine + QuranApp precedent |
| File access | okio | path abstraction, testable, KMP-ready later |
| DB access | plain SQLite via injected connection | distribution .db files stay portable; SQLDelight only if a typed store is added later |
| Publishing | none — consumed via git (submodule/subtree/copy) or GitHub raw | user decision: repo-based distribution |
| Group/id | not applicable (no Maven) | tag-based: `data-api-v0.x.y` |

### 5.2 Transport abstraction (engine purity preserved)

```kotlin
/** How bytes are obtained. Implementations live OUTSIDE this module. */
fun interface ContentFetcher {
    suspend fun fetch(path: String): ByteArray   // path relative to repo root
}

object RemoteFetcher : ContentFetcher { /* host provides HTTP client */ }
class LocalFetcher(val repoRoot: okio.Path) : ContentFetcher { /* direct file read */ }
```

The API module itself contains **zero network code** — hosts inject an HTTP
implementation for online mode; offline mode reads local files. This keeps the
module pure-JVM-testable (tests use LocalFetcher against checked-out repo).

### 5.3 Core interfaces

```kotlin
interface ContentRepository {
    val quran: QuranRepository
    val translations: TranslationRepository
    val catalogs: CatalogRepository
    val sync: SyncRepository
}

interface QuranRepository {
    fun surahs(): List<Surah>
    fun surah(number: Int): Surah?
    fun ayahs(surahNumber: Int, script: ScriptId): List<AyahText>
    fun words(surahNumber: Int): List<AyahWord>          // word-level, feeds page layout
    fun mushafScripts(): List<MushafScript>              // qpc_604, indopak_13/15/16, kfqpc_v1
    fun pageLayout(script: ScriptId, page: Int): List<PageLine>  // page_info semantics
    fun navigationRanges(): List<NavigationRange>        // juz/hizb/rub/manzil
    fun similarVerses(ayahKey: String): List<String>
}

interface TranslationRepository {
    fun availablePacks(lang: String? = null): List<TranslationPackInfo>
    fun pack(id: String): TranslationPackInfo?
    fun verses(packId: String, surahNumber: Int): List<TranslatedAyah>  // incl footnote refs
    fun footnotes(packId: String, surahNumber: Int): Map<Int, String>
}

interface CatalogRepository {
    fun translationCatalog(): List<CatalogEntry>          // available_translations_info.json
    fun tafsirCatalog(): List<CatalogEntry>
    fun wbwCatalog(): List<WbwEntry>                      // incl rewritten url fields
    fun licenses(): List<PackLicense>                     // from LICENSE-CONTENT table
}

interface SyncRepository {
    fun downloadedPacks(): List<DownloadState>
    fun markDownloaded(packId: String, version: Int, localPath: okio.Path)
    fun pendingUpdates(): List<DownloadState>             // catalog version > downloaded version
}
```

### 5.4 Concrete implementations (slice 1)

```kotlin
class LocalContentRepository(
    private val fetcher: ContentFetcher,     // LocalFetcher or RemoteFetcher
    private val localState: SyncStateStore?, // null = stateless online mode
) : ContentRepository {
    // quran: parses quranapp.db-style SQLite when pointed at a downloaded db,
    //        OR inventory/quran_scripts/*.json for script text packs
    // translations: manifest.json + flat ayah JSON per pack
    // catalogs: available_*_info.json parsing
}
```

Two backend adapters in slice 1:
1. `SqliteAyahSource` — for downloaded `quranapp.db`-shaped files (read-only,
   opened via `mode=ro`)
2. `JsonScriptSource` — for `inventory/quran_scripts/{script}/{NNN}.json`
   (one file per surah; each is a list of verses:
   `[{chapter_number, verse_number, words:[{position, text, location:"2:1:1"}]}]`
   — word-level with page-embedded locations, verified in audit).
   NOTE: this shape already carries word-level granularity, overlapping
   `ayah_words` from quranapp.db — the API should unify both behind
   AyahWord so consumers don't care which backend served them.

### 5.5 Typed models (slice 1 set)

```kotlin
data class Surah(number, nameArabic, nameLocalized?, ayahCount, revelationOrder,
                 revelationType, rukusCount)
data class AyahText(surahNo, ayahNo, text, pageIndex?)
data class AyahWord(wordId, surahNo, ayahNo, wordPosition, text, pageNumber?)
data class MushafScript(id, displayName, pageCount, lineCount)
data class PageLine(script, pageNumber, lineNumber, lineType, isCentered,
                    firstWordId?, lastWordId?, surahNumber?)
data class NavigationRange(type /*JUZ|HIZB|RUB|MANZIL*/, number, startAyahKey, endAyahKey)
data class TranslationPackInfo(id, bookName, author, displayName, langCode,
                               langName, version, downloadPath, licenseRef?)
data class TranslatedAyah(packId, surahNo, ayahNo, text, footnoteRefs: List<Int>)
data class CatalogEntry(id, langCode?, displayName, version, url, sizeBytes?,
                        sha256?, licenseRef?)
data class DownloadState(packId, version, localPath?, downloadedAt?, status)
```

## 6. Testing strategy

1. **Local-first**: all tests run against the checked-out repo via
   `LocalFetcher(repoRoot)` — no network in CI ever
2. Fixture anchors: surah count == 114, ayah total == 6236, Bismillah prefix on
   113 surahs (not 1/9), Ramadan-1446 anchor dates already proven elsewhere
3. Round-trip: `hijriToGregorian` parity with engine calendar module (already
   golden-tested there — spot-check here)
4. Catalog parse: every `url` field must resolve within-repo OR be explicitly
   whitelisted external (recitation audio)
5. License completeness: every `inventory/*` directory appears in
   LICENSE-CONTENT.md table (automated check in module tests)

## 7. Definition of done (Quran slice)

- [ ] Renamed on GitHub; local remotes updated; redirect verified with curl
- [ ] LICENSE + LICENSE-CONTENT.md committed; cleanup items removed
- [ ] Supply-chain mirrors committed + MANIFEST.sha256; catalogs rewritten;
      grep proves zero `AlfaazPlus` references remain in catalog url fields
- [ ] `/api` module compiles, tests green against real repo content
- [ ] `docs/formats.md` documents: quran_scripts JSON shape, translation pack
      layout, catalog manifests, hadith .db high-level schema (full Sunnah
      schema doc comes with slice 2), atlas meta/layout/placement JSON shapes
- [ ] README quickstart works copy-paste for a fresh consumer
- [ ] Tagged `data-api-v0.1.0`

## 8. Explicitly deferred (Sunnah session + later)

- Sunnah protobuf-vs-SQLite decision (locked: SQLite distribution, proto-shaped
  models) + implementation
- scholars linkage, grades/narrators surface
- Search implementation beyond interface (FTS rebuild strategy)
- Mushaf glyph-layout math module (`mushaf-layout`) — post-transplant,
  design-first, license-cleared (GPLv3 family confirmed)
- Recitation audio hosting/mirroring (index-only today)
- KMP multiplatform targets
