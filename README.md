# khushu-data-api

Content distribution + retrieval API for Khushu-family apps.
Formerly `khushu-quran-data`. Repo-based distribution: consume via
`raw.githubusercontent.com/greykaizen/khushu-data-api/master/<path>` (online)
or downloaded packs (offline).

## Layout
- `api/` — Kotlin/JVM retrieval module (`com.khushu.data`) — typed models,
  `ContentRepository` contracts, markup parser, Quran/Sunnah sources
- `inventory/` — distribution tier (translations · tafsirs · wbw · hadiths ·
  quran_scripts · fonts · recitations · atlas) + `MANIFEST.sha256`
- `assets/` — small always-shipped content (dua/dhikr, asma-ul-husna,
  islamic_calendar, adhan)
- `docs/` — plans & format documentation (`quran-mod-plan.md`,
  `sunnah-plan.md`, `formats.md`)

## Quickstart
```kotlin
val root = "https://raw.githubusercontent.com/greykaizen/khushu-data-api/master/"
val src = QuranScriptSource(fetcher = { path -> http.get(root + path).body() })
val words = src.words("uthmani", surahNumber = 2)   // word-level ayahs
```

## Licenses
Code: GPLv3. Content: per-pack terms in `LICENSE-CONTENT.md`.
