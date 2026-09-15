# Device-Validation Checklist — the gate before the orchestrator libSQL rewrite

**Architecture (corrected 2026-09-15): there is NO database sync in the user path.**
- **Admin (us) only:** build/update canonical DBs → `turso db import`/upload into Turso. Users never write to the canonical DBs.
- **Users:** read-only. **Online** → remote libSQL query against Turso. **Offline** → open a downloaded prebuilt **pack-level SQLite file** locally.
- **Turso Sync / Embedded Replicas / partial-sync are NOT part of the user architecture** (they're for local-first read/write replicas — not our case). Do not build `SqlBackend` around them. Adding sync later = a separate admin/ops concern behind the same download abstraction, only if it ever earns its keep.
- So the *only* thing this gate must validate is: **Android's local SQLite/libSQL opens our packs + runs our FTS5** (and secondarily the read-only remote query). It does **not** gate on any sync feature.

This is the single blocking step between "data layer done" and "app consumes it". Run on a **real
Android 12+ device or API-31+ emulator** (not just the JVM unit tests) before rewriting any repo.

## Add to `orchestrator` (JVM/Android) temporarily as a spike, or to `Khushu/app` androidTest
```kotlin
// build.gradle.kts
implementation("tech.turso.libsql:libsql:0.0.1")   // or latest; Technical Preview, Android Gradle only
// local files are also openable with the STABLE androidx.sqlite — use whichever is present.
```

## Pull fragments (from `data/packs/` — the app's prebundle floor)
`content.db`, `audio.db`, `quran-core.db`, `translation-en_saheeh-international.db` (~44 MB) + `wbw-en.db`.

## Assert on device
1. **Opens**: `androidx.sqlite`/`SQLiteDatabase.openDatabase(path)` on a fragment → no error, `PRAGMA integrity_check` = ok.
2. **FTS5 EXTERNAL-CONTENT** (quran-core, hadith, translations):
   - `SELECT COUNT(*) FROM quran_arabic_fts WHERE quran_arabic_fts MATCH 'الرحمن'` → **45**.
   - `SELECT COUNT(*) FROM bukhari_hadith_fts WHERE bukhari_hadith_fts MATCH 'prayer'` → **1043**.
   - `SELECT rowid, plain FROM translation_fts WHERE translation_fts MATCH 'merciful' LIMIT 1` then join back `translation_ayahs` by rowid → text returned.
   - **Contentless** `translation_fts`/`dua_fts`: `MATCH` returns rowids but you **cannot** `SELECT` its columns — verify the app reads text from the base table via the rowid join (matches the design).
3. **FTS5 works with the Android system SQLite** — this is the risk. If the bundled SQLite lacks FTS5, use the libSQL file engine for local reads too.
4. **Remote via libSQL preview**:
   ```kotlin
   val db = Libsql.open(url = "libsql://khushu-content-syedali.aws-us-east-1.turso.io", authToken = RO_TOKEN)
   db.connect().use { it.query("SELECT COUNT(*) FROM names_names") }   // 1089
   ```
   Same SQL as local — this is the fallback path after a pack is deleted.
5. **Embedded replica / `sync()`** — optional now; **partial-sync is NOT in the Android SDK yet** (TS/Py/Go only), so don't gate on it.
6. **Latency**: time the 5 FTS queries + 3 remote queries; record cold/warm.

## Outcomes
- All green → proceed to orchestrator rewrite (§3 of the plan): retire `data.transport`, add
  `data.libsql` (SqlBackend/LocalStore/TursoRemote/PackManager/AssetResolver), rewrite repos domain-by-domain, quran first.
- FTS5 fails on local androidx.sqlite → read local fragments with the **libSQL** engine instead (still no JDBC/Room).
- Remote libSQL preview is unstable → ship **GH packs only** first (local reads), add Turso remote as opt-in later; `SqlBackend` makes this a flag, not a rewrite.

## Config the app needs (from `.env` → BuildConfig, CI-injected)
- `KHUSHU_TURSO_RO_TOKEN_*` (6) + `KHUSHU_TURSO_URL_*` (6) — read-only per-DB (write already DENIED by token).
- `KHUSHU_ASSET_URL_TEMPLATE` (assets-<kind>) and `pack_url_template` (packs-<family>).
