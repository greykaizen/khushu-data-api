# Turso Migration — Schema & Normalizer Plan (per pack)

Canonical store = plain SQLite (FTS5 where noted). Built with `sqlite3`/`pysqlite`
(has FTS5; `pyturso` does **not** — pyturso is only the cloud-sync/embedded reader
target, not the authoring tool). FTS5 is always **external-content** (index-only,
no duplicated source text) and **derived** (rebuildable, never canonical).
Donor `.db`s are authoritative; archived `inventory/`+`assets/` are coverage/value
reference only, never the schema. Audio/fonts/atlas stay files (path+sha256 in DB).

Packs (logically separated; merged only where the data is genuinely one unit):
`quran.db` · `sunnah_bukhari.db` … `sunnah_forty.db` (9, separate) ·
`scholars.db` · `translations.db` · `tafsir.db` · `dua.db` · `names.db` ·
`events.db` · `adhan.db` · `recitations.db` · `curated.db` · files/

## quran.db  (pack 1 — BUILD NOW)
Sources (authoritative): donor `quranapp.db`, `page_info.db`, `topics.db`.
These are one query unit (topic_ayahs.ayah_id → ayahs; mushaf_map/page_info ↔
ayah_words; navigation → surahs) → merged into `quran.db`.
Tables: surahs, surah_localizations, ayahs, scripts, ayah_words, mushafs,
mushaf_map, navigation_ranges, similar_verses, mutashabihat_phrases,
mutashabihat_phrase_ayah, surah_search_aliases, mushaf_info (=page_info.info),
mushaf_pages (=page_info.pages), topics, topic_ayahs, topic_localizations,
relationships.
Drop: donor FTS4 `arabic_search` + `surah_search_aliases_fts` (+shadow).
FTS5 (external-content):
  - `search_arabic(ayah_id PK, text)` ← donor `arabic_search_content(c0ayah_id,c1text)`
    → `arabic_fts` fts5(text, content=search_arabic, tokenize=unicode61).
  - `surah_alias_fts` fts5(alias, content=surah_search_aliases) for surah-name search.
Verify: 114/6236/334660(uthmani 83665)/35965/720/3552/814/2052/37789/37914(pages)/
2512/30687/3504/1749; text fidelity 1:1 & 2:255 & 114:1; FTS match parity vs donor.

## sunnah_<coll>.db  ×9  + scholars.db
Source: SunnahApp protobuf `deliverable.proto` (+ 9 gz deliverables) — already
mirrored 1:1 into donor→data-api `hadiths/*.db`. Keep the 12-table schema; drop the
per-book JSON dup from canonical. FTS5 external-content over hadith text (ar+en
content, `blocks_json` → extract plain text at build) per collection. scholars.db:
`scholars(...)` + FTS (bio/name) optional. Verify per-collection counts (bukhari
7277 …). FLAG: grades table empty in bukhari — confirm grades live elsewhere or
are genuinely sparse before assuming data loss.

## translations.db
Source: QuranApp 3 raw JSON (saheeh/clear/junagarhi) + 45 packs from api.quran.com.
Shape today: `{version, suras:[{index, ayas:[{id,index,translation,footnotes?}]}]}`,
markers inline (`<fn index=..>`, `<reference ..>`). Normalize to relational:
`packs(id PK, lang, book, author, display_name, version, source)`,
`translation_ayahs(pack_id, surah_no, ayah_no, text, footnotes_json)` PK
(pack_id,surah_no,ayah_no). FTS5 external over `text`. FLAG: footnotes/marker
markup pass-through — keep raw text + parsed footnotes side table; confirm marker
grammar stable across all 48 before parsing.

## tafsir.db  (353 MB, 2965 files)
Source: api.qurancdn/quran.com by_chapter. Per-book per-surah JSON. Normalize to
`tafsir_books(slug, name, author, lang)` + `tafsir_entries(slug, surah, ayah,
text)` (or keep chunked). FTS later (low priority). FLAG: 2965 files — enumerate
distinct books first; confirm ayah-key completeness vs 6236 per book.

## dua.db
Source: islamicapi.com (scraped). `dua_data.json` 491 rows, fields incl
HTML entities (`&#038;`). Normalize: `duas(id PK, post_id, title, category,
subcategory, arabic, repetition, translation, transliteration, virtue,
explanation, reference, audio_path)`, `dua_categories(...)`, `articles(...)`
(+ `articles_index.json`). **Unescape HTML entities at build.** FTS5 over
title+translation. FLAG: audio mirrors 488/491 (3 missing) — keep audio as files.

## names.db
Source: islamicapi.com `asma_data_{lang}.json` `{code,status,data:[...]}`. Normalize:
`names(lang, number, name, transliteration, translation, meaning, audio_path)` PK
(lang,number). No FTS (99 rows). FLAG: `{status}` wrapper — only ingest 200/data.

## events.db
Source: `assets/islamic_calendar/islamic_events.json` `{pack, events:[...]}`.
Normalize `events(id PK, title, hijri_month, hijri_day, category, recurrence,
source, confidence)`. No FTS.

## adhan.db
Source: `assets/adhan/adhan_index.json` (`_meta`,`entries`), 179 opus mirrored.
`adhans(id PK, reciter, region, style, path, bytes, sha256)` + audio files. No FTS.

## recitations.db
Source: `available_recitations_info_v2.json` (+ 28 timing `.gz`) — audio is
external CDN. `reciters(id,name,...)`, `recitation_timings(reciter, surah, ayah,
segments_json)`. Audio = external URL (not a file). FLAG: audio not local.

## curated.db
Source: QuranApp `verses/` (123 localized files) + `science/` (12 topics + per-lang).
`curated_sets(...)`, `curated_verses(...)`, `science_topics(...)`. HTML/img = files.

## files/ (never rows)
fonts (ttf/zip/tar.zst), atlas glyph `.zip`, adhan/dua/names opus, topic/curated
webp, recitation audio (external CDN). Referenced by repo-relative path + sha256.

## Unresolved provenance / coverage flags (to close during each pack)
1. Sunnah `hadith_grades` empty (bukhari) — where do grades live? verify not lost.
2. Translations marker grammar (fn/reference) — confirm identical across 48.
3. Tafsir book enumeration + ayah coverage vs 6236.
4. Dua HTML-entity scope; 3 audio-mirrorless duas.
5. Recitation audio = external only (no local files) — confirm hosts tolerate.
6. Topics: images referenced by webp under topics/images — keep file rows.
7. WBW: v1/v2 packs + timings — decide quran.db vs translations.db ownership.

---
## Progress status
- [x] **Pack 1 quran.db** — 29.1 MB. 15 tables verbatim + 29 idx; FTS4→external-content FTS5 (arabic+alias); donor+archive verified; text byte-identical.
- [x] **Pack 2 sunnah_{9}.db + scholars.db** — all 13 tables/coll row-exact, matn byte-identical, FTS5 external over matn. **Grades investigation:** empty in bukhari/muslim/malik/forty/riyad is CORRECT (all-authentic collections; archive has no grades arrays) — not loss; tirmidhi/ibnmajah/nasai 1:1, abudawud 2-per-hadith (Albani+Darussalam) preserved.
- [x] **Pack 3 translations.db** — 157 MB, 51 packs (48 archive + 3 donor), 318,036 ayahs (=51×6236), 50,811 footnotes. Markers `<fn>`/`<reference>` stored VERBATIM in tr_ayahs.translation + tr_footnotes.text (not flattened). Search = **contentless FTS5** (index-only, no text copy) over tag-stripped projection; matches resolve via rowid→tr_ayahs. Note: contentless chosen over external-content to avoid a duplicate full-text copy (saved ~78 MB).
- [ ] Pack 4 tafsir.db — next.
- [x] **Pack 4 tafsir.db** — 328.5 MB. 26 books / 12 langs / **143,629 entries**, `tafsir_entries(book,surah,from_verse,to_verse,text)` storing **verbatim HTML** (not flattened, not forced per-ayah). Per-book counts preserved and **correctly non-uniform** (full books=6236; but muyassar 5278, al-saddi 6177, tabari 6196, ibn-kathir-ar 6205, bn-ibn-kaseer 1914, urdu 2101, tazkir 1558/1952) — proving range/partial coverage kept, not padded to 6236. text byte-equal sample. **No FTS5** (reasoned: tafsir is (book,surah,verse-range) lookup, HTML-heavy; free-text index = big duplication, negligible value).
- [ ] Pack 5 dua.db (unescape HTML entities; markers/footnotes preserved; FTS over title/translation).
- [x] **Pack 5 dua.db** — 2.8 MB. Two corpora cleanly separated: **duas** (491 → `duas` + `dua_posts`(30) + `dua_categories`(2)) and **articles** (`article_categories`(12) + unique `articles`(169, raw HTML body preserved) + `article_members`(186 links)). `dhikr-dua/*` proven to be a regrouping of the same 491 (reconciles, NOT double-stored). HTML entities unescaped once (faithful), arabic/translation byte-exact (0 mismatches). Audio = file refs (`dua_audio` cols + 488 sha256/paths verified present; 2 url-less). contentless FTS5 over dua title+translation+transliteration.

## Mandatory export step (learned the hard way)
`make_turso_ready.py` runs after every build: `PRAGMA journal_mode=WAL` +
`wal_checkpoint(TRUNCATE)` + `synchronous=NORMAL`. **Turso Cloud `db import`
requires WAL mode** (docs.turso.tech/cloud/migrate-to-turso) — a rollback-journal
(.db in `delete` mode) is REJECTED (the "WAL error"). All 14 DBs converted & re-verified.
- [x] **Pack 6 names.db** — 0.3 MB. `asma_packs`(11 langs) + `names`(1089 = 11×99) with meaning/transliteration/translation. Audio join via **remote-basename→local .opus (99/99 exact)**, sha256 per file. No FTS (99 rows).
- [x] **assets.db (central registry)** — 1,496 hosted files / 521 MB (574−tar.gz dupes−json). `asset_id(=repo path) PK, relative_path, sha256, size, mime, kind, version='assets-v2026.09'`. Domain DBs store `asset_id` only; base_url swap (GitHub→R2) is client-side.
- [x] **Pack names.db / dua.db refactored** → `audio_asset_id` (→assets.db), per-row sha removed (single manifest). 1089 / 488 refs, 0 unresolved.
- [x] **wbw.db** — separate pack (14 lang ×2 versions = 28 packs), 2,310,112 per-word rows (ayah_id×ordinal, JSON word payload). NOT in translations.
- [x] **recitations.db** — 18 reciters (external audio URL templates + translations) + 28 timing BLOBs (per reciter·version, gz, sha). Audio stays external CDN.
- [x] **adhan.db** — 178 entries → `asset_id`→assets.db (reciter/region/style/rate/channels); audio hosted.
- [x] **events.db** — 11 hijri events (month/day/category/recurrence/confidence) + pack meta. No FTS.
- [x] **curated.db** — 225 sets / 1,510 ayah refs (type0/1/2, recommended×lang, major_sins) + 12 science topics (+translations). Science html/img via assets.db.
- All 21 DBs run through `make_turso_ready.py` (WAL) → `turso db import` compatible. Referential: 1089+488+178 asset refs, 0 missing.
