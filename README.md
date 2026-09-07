# khushu-data-api

[![License](https://img.shields.io/badge/license-GPL--3.0-blue.svg)](LICENSE)

> ⚠️ **RETIRED AS A LIBRARY (v1.4.0).** This repo is now the family **content
> store** — the corpus (`inventory/`, `assets/`) served over raw CDN, plus the
> pipeline tools (`tools/`) that generate it. The retrieval API
> (`com.khushu.data.*`) was absorbed into
> [khushu-orchestrator](https://github.com/greykaizen/khushu-orchestrator);
> hosts add ONE coordinate there and never depend on this repo as a library.
> The JitPack badge/coordinates below are historical — do not add them to a
> build.

Content store for Khushu-family apps. Every byte of Quran text, hadith
corpus, dua, adhan audio, bookmark, glyph atlas, and translation — served
from this checkout, retrievable through the orchestrator's transport, and
deletable by the host via its caching layer.

Part of the [Khushu](https://github.com/greykaizen/khushu) project — see
[the family](#the-khushu-project-family) below.

## What it provides

| Namespace | What it does | Key APIs |
|---|---|---|
| **quran** | Ayah texts (4 scripts), word registries, translations (48 packs), tafsirs (23 books × 13 languages), word-by-word (14 languages), chapter info, navigation, search, similar verses, topics, curated sets, recitation timings, glyph-atlas bundles, page layouts | `ayahTexts`, `words`, `ayahBundle`, `translationTexts`, `tafsirForSurah`, `wbwForSurah`, `atlas.placementsByWord`, `glyphTable` |
| **sunnah** | 9 hadith collections (Bukhari, Muslim, Tirmidhi, …) with grades, narrators, references + FTS5 search with diacritic-insensitive Arabic | `attachSunnah`, `hadith`, `search` |
| **dua** | 491 duas across 30 categories, 99 Names × 11 languages, 186 reading articles (raw HTML passthrough), local audio mirrors | `duas`, `categories`, `bySubcategory`, `articles`, `asmaPack`, `asmaName`, `localAudioPath` |
| **adhan** | 178 catalogued adhan recordings (reciter/region/style parsed, sha256 per file), opus bytes on demand | `entries`, `reciters`, `byReciter`, `audio`, `standard` |
| **catalogs** | Discovery for fonts, atlas bundles, translations, tafsirs, wbw packs, recitations + project web links | `translations`, `tafsirs`, `wbw`, `fonts`, `webLinks` |
| **curated** | Curated verse sets (situational/major sins), recommended recitations, Quran-science topics | `exclusiveVerses`, `recommendedRules`, `scienceTopics` |
| **islamicEvents** | Islamic event display data (title, category, source, confidence) — computation stays canonical in khushu-engine | `all`, `forHijriMonth` |
| **downloads** | Persistent download tracking + space management — per-category byte totals, delete by filter, reconcile after manual clears | `summary`, `totalBytes`, `deleteWhere`, `clearAll`, `reconcile` |

## Adding it to your project

### JitPack

```kotlin
repositories {
    maven { url = uri("https://jitpack.io") }
}
dependencies {
    implementation("com.github.greykaizen.khushu-data-api:khushu-data-api:1.1.0")
}
```

### Maven Local (offline)

```bash
./gradlew :api:publishToMavenLocal
```
coordinate: `com.khushu:api:1.1.0`.

## Quickstart

```kotlin
import com.khushu.data.repo.KhushuContent
import com.khushu.data.transport.ContentFetcher

// Online transport (host-supplied HTTP) or offline LocalFetcher(checkoutRoot)
val root = "https://raw.githubusercontent.com/greykaizen/khushu-data-api/master/"
val fetcher = ContentFetcher { path -> http.get(root + path).body() }

KhushuContent(fetcher).use { content ->
    // Individual retrievals
    val words = content.quran.words(surahNo = 2, script = "uthmani")
    val atlas = content.quran.atlas.placementsByWord("uthmani")

    // Grouped: everything about one ayah — texts, side-by-side translations,
    // word-by-word, tafsir segments, recitation word timings.
    val bundle = content.quran.ayahBundle(
        surahNo = 2, ayahNo = 255,
        translationPacks = listOf("en_pickthall", "en_yusuf-ali"),
        tafsirSlugs = listOf("en-tafisr-ibn-kathir"),
    )

    val duas = content.dua.duas()                 // 491 duas + asma + articles
    val adhan = content.adhan.reciters()          // 178 catalogued recordings

    val sunnah = content.attachSunnah(corporaRoot = File("inventory/hadiths"))
    val hadith = sunnah.hadith("bukhari_urn_100010", lang = "en")
}

// Download tracking + space management (opt-in):
val caching = CachingFetcher(File(context.cacheDir, "khushu"), fetcher)
KhushuContent(caching).use { content ->
    val used = content.downloads.summary()          // items + bytesByCategory
    content.downloads.deleteWhere { it.category == "inventory/tafsirs" }
}
```

See [docs/formats.md](docs/formats.md) for every pack format and the full
API surface, and [LICENSE-CONTENT.md](LICENSE-CONTENT.md) for content terms.

## Layout

- `api/` — Kotlin/JVM retrieval module (`com.khushu.data`)
- `inventory/` — distribution tier (1.5 GB: quran_metadata, quran_scripts, mushaf_layout, atlas, fonts, translations, tafsirs, wbw, hadiths, recitations, topics, similar, curated, quran_search, chapters, other)
- `assets/` — always-shipped content (276 MB: dua/dhikr, asma-ul-husna, adhan audio, islamic calendar)
- `docs/` — format documentation
- `tools/` — extraction/mirror scripts

## The Khushu project family

| Repo | Role |
|---|---|
| [khushu-engine](https://github.com/greykaizen/khushu-engine) | Computation — prayer times, astronomy, calendar, qibla, zakat, tasbih, observance, qada |
| [khushu-data-api](https://github.com/greykaizen/khushu-data-api) | **You are here** — content: Quran text, hadith corpora, duas, adhan audio, bookmarks, download tracking |
| [khushu](https://github.com/greykaizen/khushu) | The app — Android (Kotlin/Compose), consuming both libraries |

## License

Code: GPLv3. Content: per-pack terms in [LICENSE-CONTENT.md](LICENSE-CONTENT.md).


## Role (2026-09): content store

The retrieval API (api/, com.khushu.data.*) was absorbed into khushu-orchestrator v1.4.0 — that coordinate is retired. This repo is now the pure content store: inventory/, assets/, pipeline tools, and manifests. Runtime consumers fetch files over HTTP at these exact paths; nobody clones it for builds.
