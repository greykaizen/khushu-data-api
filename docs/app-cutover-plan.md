# App Cutover Plan — Turso/packs consumption (2026-09-16)

Companion to [data-milestone-turso-plan.md](data-milestone-turso-plan.md). The data layer,
engine validation, and every content domain's SQL source are DONE + tested. This doc is the
**application-integration** plan: flip `KhushuContent` from the JSON `ContentFetcher` path to
`SqlStore`-backed sources, wire the app, and replace the `SEAM(list-data)` fixture screens with
real data — in verified increments, never a blind big-bang.

## Reality established during planning (recalibrates the TODO)
- **Screens are fixtures**, not live `orch.content.*` calls (only Calendar/Home VMs use the
  orchestrator, and only for *computation*). So "flip a screen" = **build its data-backed
  VM→screen binding**, not re-point an existing call. Lower risk to live UI, more per-screen work.
- **`KhushuContent(fetcher)`** = ~10 `*Api` classes composing JSON `*Source(fetcher)`, ~115 methods.
  The ~18 SQL sources already built cover the bulk; the **gaps** are mushaf **layout**, **glyphs/PUA**,
  **chapterInfo**, **search** (mushaf layout + chapterInfo + search ARE in the DB now; glyphs are NOT).
- **No DI framework**: singletons (`KhushuOrchestratorProvider.get(ctx)`) + VMs built inline in
  `AppNavHost.kt` via `viewModel { Vm(deps…) }`. The pack-era store seam is `KhushuCorpus` + a
  host-injected `SqlStoreResolver` (the JVM orchestrator can't construct Android libSQL).
- **Decision (glyphs)**: add a `quran_glyphs` table to the DB (build-time), so the offline reader is
  fully SQL-backed. Requires a content-DB rebuild/redeploy.
- **Decision (prebundle)**: the 4 prebundle packs ship as **APK assets** copied to `filesDir/packs`
  on first run (`ensureFromAsset`), AND a **declarative first-run download policy** exists alongside
  (currently empty) so switching a pack to download-later (smaller APK) is data, not a rewrite.
- **Decision (storage UI)**: dedicated `AppRoute.Storage` + a global Settings card (Phase 3, later).

## Core mechanism — the resolver seam (no big-bang)
`KhushuOrchestrator`/`KhushuContent` gain an optional `resolver: SqlStoreResolver?`. Each `*Api`
builds its SQL source **when a store resolves** for that domain's pack, else keeps the JSON source.
Public method signatures never change → app + existing screens keep compiling throughout. JSON is
retired per-domain only once every screen using it is migrated.

```kotlin
fun interface SqlStoreResolver { suspend fun resolve(packId: String): SqlStore? }
// app: resolver = SqlStoreResolver { KhushuCorpus.store(it) }  // local pack -> remote Turso -> null
```

## Phases

### Phase 0 — Foundations (JVM-tested → `orchestrator-v1.7.4`, pin bump)
- **data-api**: `build_quran.py` emits `quran_glyphs` (PUA: surah/juz icon codepoints + ayah-reference
  rules) from `quran_metadata/quran_glyphs.json`; `consolidate.py` maps into `khushu-quran`; rebuild
  masters → re-import `khushu-quran` to Turso → republish `packs-quran-core`. Re-run
  `validate_packs.py` + `FtsPackValidator` + 9-point spot check (integrity + row/bytes parity BEFORE
  any destroy, given the prior auth incident).
- **orchestrator** (`com.khushu.data.store` / `quran`):
  - `SqlStoreResolver` fun-interface + ctor param on `KhushuContent`/`KhushuOrchestrator` (default null).
  - New sources vs real packs (JVM tests): `SqlGlyphSource` (glyphTable/surahIcon/juzIcon/ayahReference),
    `SqlMushafLayoutSource` (pageLines/linesOfAyah/pageOfAyah/mushafScript/wordRegistry over
    `quran_mushaf_map`/`_pages`/`_navigation_ranges`), `SqlChapterInfoSource` (`quran_chapter_info`),
    `SqlSearchSource` (arabic `quran_arabic_fts` + per-pack `translation_fts`).
- Gate: orchestrator ~170 tests green; `:app:compileDebugKotlin` on the new tag (no localFamily).

### Phase 1 — App wiring skeleton (device-verified)
- `app/build.gradle.kts`: `prebundlePacks` task fetches the 4 prebundle pack files from the GH pack
  releases into `src/main/assets/packs/` (gitignored) at build time → no 44 MB committed.
- `PackBootstrapper`: `PrebundlePolicy` (list of pack ids to seed from assets → `ensureFromAsset`)
  and `FirstRunPolicy` (list to download on first launch; empty now) — the smaller-APK switch later.
- `KhushuApplication.onCreate` → launch `KhushuCorpus.init()` then bootstrapper; expose `KhushuCorpus`
  + `SqlStoreResolver` via a CompositionLocal/factory so `AppNavHost` constructs content VMs.
- Gate: cold start on device → 4 packs on disk, `KhushuCorpus.store("content")` opens.

### Phase 2 — Domain flips, smallest-complete-vertical first (one PR each, device-tested)
Order: **2a Asma** (proof-of-pattern) → 2b Dua/Events/Adhan/Catalog → 2c **Quran reader** (biggest:
core+layout+translations+wbw+tafsir+recitation+search+glyphs) → 2d Sunnah/hadith. Each: build the
`XViewModel` over `KhushuCorpus.store(...)`, replace fixtures, keep the AppRoute, one instrumented
test per screen.
- **2a Asma**: `AsmaViewModel` → `SqlAsmaSource` (99 names + audio via `AssetResolver`, first-run
  download on tap). Replaces the Asma list+detail `SEAM(list-data)`.

### Phase 3 — Downloads + Storage Settings UI (Compose, M3)
- `AppRoute.Storage` + Settings card; `StorageViewModel` over `KhushuCorpus.packApi()`: per-family/tier
  list, installed vs `plannedBytes`, install with `onProgress`, delete → `PackStoreProvider.release` →
  StoreRouter routes to `TursoStore`. Strings as resources; no stub empty-states.

### Phase 4 — Retire JSON
Once every screen is source-backed + instrumented green: delete `KhushuContent` JSON sources, the
`content-v2026.09` tag refs, and placeholder `app/src/main/assets/*.json`. Keep orchestrator
*computation* (DayModel etc.); only retrieval migrates.

## Method → SQL mapping (per domain; existing SQL source → the *Api method it backs)
| Api | Methods | SQL source (built?) |
|---|---|---|
| QuranApi.metadata | surahs/surah/ayahMeta/navigation/registry/searchAliases | `SqlQuranSource` ✅ |
| QuranApi.words/texts/bundle | uthmani/ayah words | `SqlQuranSource` (partial) ✅ |
| QuranApi.glyphs | glyphTable/surahIcon/juzIcon/ayahReference | `SqlGlyphSource` ⛔ Phase 0 (+ glyphs table) |
| QuranApi.layout | pageLines/linesOfAyah/pageOfAyah/mushafScript/wordRegistry | `SqlMushafLayoutSource` ⛔ Phase 0 |
| QuranApi.chapterInfo | chapterInfo/variants | `SqlChapterInfoSource` ⛔ Phase 0 |
| QuranApi.translations | translationPacks/translationText | `SqlTranslationSource` ✅ |
| QuranApi.tafsir / wbw / recitations / similar / topics | … | `SqlTafsirSource`/`SqlWbwSource`/`SqlRecitationSource`/`SqlSelectionSource`/`SqlTopicsSource` ✅ |
| QuranApi.search | searchQuran | `SqlSearchSource` ⛔ Phase 0 |
| DuaApi | duas/dua/categories/bySubcategory/articles | `SqlDuaSource` ✅ (articles = curated JSON later) |
| DuaApi asma | pack/name | `SqlAsmaSource` ✅ |
| AdhanApi | entries/reciters/standard | `SqlAdhanSource` ✅ (+ audio asset) |
| SunnahApi | collections/books/chapters/hadith/search/scholar | `SqlHadithSource`/`SqlScholarSource` ✅ |
| CatalogApi | translations/tafsirs/wbw/fonts/weblinks | `SqlCatalogSource` ✅ |
| CuratedApi | verses/recommended/science | `SqlCuratedSource`/`SqlRecommendedSource`/`SqlScienceSource` ✅ |
| IslamicEventsApi | all/forHijriMonth | `SqlEventsSource` ✅ |
| QuranAtlasApi | atlas catalog/bundles/meta | ⚠️ binary asset + small json → Phase 4/low |

## Verification matrix (every increment)
1. `validate_packs.py` → lossless re-shard, 104/104 integrity.
2. `FtsPackValidator` (xerial) → FTS5 second-engine parity.
3. 9-point remote spot check (all 6 Turso DBs) via the read-only HTTP tokens.
4. orchestrator `:orchestrator:test` green; consumer `:app:compileDebugKotlin` on the published tag.
5. Khushu `connectedDebugAndroidTest` per vertical (real pack + real store + domain models).
6. `gh release` asset byte-size == local pack (post redeploy).

## Guardrails (from this session's lessons)
- **Never blind big-bang** the aggregate; resolver seam keeps both paths until a domain is done.
- **Redeploy carefully**: verify master integrity + row/byte parity *before* any `turso db destroy`;
  re-check HTTP 200 + write-denied after; `.env` writes are atomic + checked (past truncation incident).
- **Secrets**: only the 6 per-DB **read-only** tokens in BuildConfig (CI/local.properties, gitignored);
  admin token never ships.
- **No stub architecture**: a screen stays a fixture until its source is wired; settings sheets use the
  registry seam (empty state is honest).

## Progress log
- **Phase 0 DONE** — glyphs table (data-api `17ba9c9`, redeployed: Turso `khushu-quran` re-imported + `packs-quran-core` republished, all-6 spot check green, write DENIED). Orchestrator gap sources `SqlGlyphSource/SqlMushafLayoutSource/SqlChapterInfoSource/SqlSearchSource` + `SqlStoreResolver` (`2414b9a`, tag **v1.7.4**, 167 tests green).
- **Phase 1 DONE** — `KhushuApplication` (manifest) boots `PackBootstrapper` (PrebundlePolicy + FirstRunPolicy) + `KhushuCorpus.init`; Gradle `fetchPacks` pulls the 4 prebundle packs → `assets/packs/` (gitignored; `KHUSHU_SKIP_PREBUNDLE` opt-out); Khushu pinned v1.7.4. Consumer build + APK asset layout verified on emulator.
- **Phase 2a Asma DONE** (`7729968`) — `AsmaRepository`+`AsmaViewModel`+screen → 99 names, live search. Emulator green.
- **Phase 2b Dua DONE** (`5c80801`) — `DuaRepository`+`DuaViewModel`+screen → 491 duas, subcategory chips, search. Emulator green.
- **Phase 3 Downloads/Storage DONE** (`d53b803`) — `AppRoute.SettingsStorage` + `StorageViewModel`/`StorageScreen` over `PackApi` (all 104 packs, family-grouped, install/progress/delete, byte total; delete → remote fallback). Emulator green.
- **Note:** Quran *browse* list already real (generated `QuranStatic.surahMetas`); `SEAM(list-data)` there is the **reader** (per-ayah mushaf/translation), not the list.
- **2026-09-21 (host session): SQLite engine swap + resolver wiring landed.**
  - **Turso → bundled SQLite (host)**: the 16 KB-page issue killed libsql on Android; `LibsqlSqlStore` replaced by `BundledSqlStore` (androidx `sqlite-bundled`, FTS5 + 16 KB out of the box) behind a compat typealias. Pack files unchanged; byte-verified identical (491 duas, integrity ok).
  - **Java 21 toolchain (host)**: family artifacts are class-file 65 → `jvmToolchain(21)` + `VERSION_21` in `app/build.gradle.kts`; unblocked `testDebugUnitTest` (DuaUiStateTest 4/4 green).
  - **DuaVerticalTest contract refreshed**: section-isolation (DuaUiState) means the default section serves `main-adhkar` only; test now derives section counts from the corpus (335/156) instead of asserting 491 in one section. 11/11 instrumented green on Pixel 10 emulator.
  - **RESOLVER GATE CLEARED (orchestrator-v1.7.5, `233e7dd`)**: `KhushuContent`/`KhushuOrchestrator` accept the host `SqlStoreResolver`; `DuaApi` resolves the `content` store per call (duas/dua/categories/bySubcategory + adaptive corpus). Tests: pack-served dua with a dead JSON transport, JSON default/fallback parity, DayModel parity over both paths. 170 orchestrator tests green; pin bumped in Khushu (`libs.versions.toml` → v1.7.5) and resolver injected at `KhushuOrchestratorProvider` (`{ KhushuCorpus.store(it) }`).
  - **Offline proof (device)**: airplane mode + `cacheDir/content` wiped + cold start → DayModel builds from the pack; zero `dua_data.json` fetch attempts; Home renders live prayer times. The JSON transport is off the app's request path for the dua/DayModel aggregate.
  - **Remaining for full JSON retirement**: content namespaces still JSON-backed where no domain flip exists (asma/adhan/events already SQL-served host-side via `KhushuCorpus` repos; quran/sunnah repos likewise). Next upstream increments: resolver into remaining `*Api`s (quran, adhan, events, catalog, curated) then delete `ContentFetcher` + `content-v2026.09` refs + placeholder assets (Phase 4 tail).

## Remaining (unchanged from the phase list — deliberately NOT blind-merged)
- **Phase 2c Quran reader** — `SurahDetail`/`Read` panes over `SqlQuranSource` (words/text) + `SqlTranslationSource` + `SqlMushafLayoutSource` + `SqlGlyphSource` (+ recitation timings). Design-heavy (mushaf pagination, glyph/atlas rendering, translation picker) → needs the running app + visual review.
- **Phase 2d Sunnah** — collection/book/chapter + hadith content + FTS search over `SqlHadithSource`/`SqlScholarSource`.
- **Phase 2b Events/Adhan** — 11 islamic events surfaced in the calendar + adhan picker in prayer settings (both are UX decisions, not pure data-mechanical).
- **Atlas** source (glyph binary + catalog json) — low priority, reader-gated.
- **Phase 4 JSON retirement** — only after every screen above is off `KhushuContent`'s JSON path; delete `content-v2026.09` tag refs + placeholder assets then.
