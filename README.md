# khushu-data-api

Content distribution + retrieval API for Khushu-family apps.
Formerly `khushu-quran-data`. Repo-based distribution: consume content via
`raw.githubusercontent.com/greykaizen/khushu-data-api/master/<path>` (online)
or downloaded packs (offline).

## Adding it to your project

### JitPack

```kotlin
repositories {
    maven { url = uri("https://jitpack.io") }
}
dependencies {
    implementation("com.github.greykaizen.khushu-data-api:khushu-data-api:1.0.0")
}
```

### Maven Local (offline / machine-local)

```bash
./gradlew :api:publishToMavenLocal
```
coordinate: `com.khushu:api:1.0.0`.


## Layout
- `api/` — Kotlin/JVM retrieval module (`com.khushu.data`) — typed models,
  `ContentRepository` contracts, markup parser, Quran/Sunnah/Atlas sources
- `inventory/` — distribution tier (quran_metadata · quran_scripts ·
  mushaf_layout · translations · tafsirs · wbw · hadiths · recitations ·
  atlas · topics · similar · curated · quran_search · fonts) + `MANIFEST.sha256`
- `assets/` — small always-shipped content (dua/dhikr, asma-ul-husna,
  islamic_calendar, adhan)
- `docs/` — plans & format documentation (`quran-mod-plan.md`,
  `sunnah-plan.md`, `formats.md`)
- `tools/` — one-off extraction/mirror scripts (`export_quran_structure.py`,
  `mirror-alfaazplus.sh`)

## Quickstart
```kotlin
import com.khushu.data.repo.KhushuContent
import com.khushu.data.transport.ContentFetcher

// Online transport (host-supplied HTTP) or offline LocalFetcher(checkoutRoot)
val root = "https://raw.githubusercontent.com/greykaizen/khushu-data-api/master/"
val fetcher = ContentFetcher { path -> http.get(root + path).body() }

KhushuContent(fetcher).use { content ->
    val words = content.quran.words(surahNo = 2, script = "uthmani")
    val packs = content.quran.translationPacks("en")
    val atlas = content.quran.atlas.placementsByWord("uthmani") // engine render spec

    // Grouped: everything about one ayah — texts, side-by-side translations,
    // word-by-word, tafsir segments, recitation word timings.
    val bundle = content.quran.ayahBundle(
        surahNo = 2, ayahNo = 255,
        scripts = listOf("uthmani"),
        translationPacks = listOf("en_pickthall", "en_yusuf-ali"),
        tafsirSlugs = listOf("en-tafisr-ibn-kathir"),
    )

    val duas = content.dua.duas()                 // 491 duas + asma + articles
    val adhan = content.adhan.reciters()          // 178 catalogued recordings
    val audio = content.adhan.audio(adhan[0].entries[0].id) // opus bytes

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

## Licenses
Code: GPLv3. Content: per-pack terms in `LICENSE-CONTENT.md`.
