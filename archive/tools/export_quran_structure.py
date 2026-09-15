#!/usr/bin/env python3
"""One-off migration: extract the Quran structural/layout/content tier from the
reference QuranApp assets into canonical khushu-data-api inventory JSONs.

Sources (reference only — after this export the repo is self-contained):
  <QuranApp>/app/src/main/assets/db/quranapp.db
  <QuranApp>/app/src/main/assets/db/page_info.db
  <QuranApp>/app/src/main/assets/db/topics.db
  <QuranApp>/app/src/main/assets/verses/   (curated packs, copied as-is)
  <QuranApp>/app/src/main/assets/science/  (topical webview packs, copied as-is)

Usage:
  python3 tools/export_quran_structure.py <path-to-QuranApp> [repo-root]

Anchors verified at export (hard-fail if violated):
  114 surahs · 6236 ayahs · ayah_id = surah*1000 + ayah_no
  qpc page 1 line 2 == words 1..5 == al-Fatihah 1:1 (4 words + ayah-end marker)
"""
import gzip
import json
import shutil
import sqlite3
import sys
from datetime import date, timezone, datetime
from pathlib import Path

RO = "?mode=ro"
TODAY = date.today().isoformat()


def meta(source: str, rows: int, notes: str = "") -> dict:
    m = {
        "exported_at": TODAY,
        "source": source,
        "rows": rows,
        "extractor": "tools/export_quran_structure.py",
        "note": "canonical khushu-data-api export; reference app no longer required at runtime",
    }
    if notes:
        m["notes"] = notes
    return m


def dump(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
    print(f"  wrote {path.relative_to(path.parents[2]) if len(path.parents) > 2 else path}  ({path.stat().st_size:,} B)")


def dump_gz(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode()
    with gzip.open(path, "wb", compresslevel=9) as f:
        f.write(raw)
    print(f"  wrote {path.name}  ({len(raw):,} -> {path.stat().st_size:,} B gz)")


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    ref = Path(sys.argv[1]).resolve()
    repo = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else Path(__file__).resolve().parents[1]
    db_dir = ref / "app/src/main/assets/db"
    assets = ref / "app/src/main/assets"
    inv = repo / "inventory"

    quran = sqlite3.connect(f"file:{db_dir / 'quranapp.db'}{RO}", uri=True)
    qc = quran.cursor()
    pinfo = sqlite3.connect(f"file:{db_dir / 'page_info.db'}{RO}", uri=True)
    pc = pinfo.cursor()
    page_info_codes = {r[0] for r in pc.execute("SELECT script FROM info")}

    # ── 1. surahs + localized names ─────────────────────────────────────────
    print("== quran_metadata ==")
    names = {}
    for no, lang, name, meaning in qc.execute("SELECT surah_no, lang_code, name, meaning FROM surah_localizations"):
        names.setdefault(str(no), {})[lang] = {k: v for k, v in (("name", name), ("meaning", meaning)) if v}
    surahs = [
        {
            "number": no, "ayah_count": ac, "revelation_order": ro,
            "revelation_type": rt, "rukus_count": rk,
            "names": names.get(str(no), {}),
        }
        for no, ac, ro, rk, rt in qc.execute(
            "SELECT surah_no, ayah_count, revelation_order, rukus_count, revelation_type FROM surahs ORDER BY surah_no")
    ]
    assert len(surahs) == 114
    dump(inv / "quran_metadata/surahs.json",
         {"_meta": meta("quranapp.db surahs+surah_localizations", 114,
                        "18 localization languages"), "surahs": surahs})

    # ── 2. ayahs (juz/hizb/rub/manzil/ruku/sajdah) ─────────────────────────
    ayah_rows = qc.execute(
        "SELECT ayah_id, surah_no, ayah_no, juz_no, hizb_no, rub_no, manzil_no, ruku_no, sajdah_type "
        "FROM ayahs ORDER BY ayah_id").fetchall()
    assert len(ayah_rows) == 6236
    assert all(aid == s * 1000 + a for aid, s, a, *_ in ayah_rows), "ayah_id convention broken"
    dump(inv / "quran_metadata/ayahs.json",
         {"_meta": meta("quranapp.db ayahs", 6236,
                        "ayah_id = surah_no*1000 + ayah_no; sajdah: 0=none 1=sajdah 2=sajdah-mandatory?"),
          "columns": ["ayah_id", "surah_no", "ayah_no", "juz_no", "hizb_no", "rub_no",
                       "manzil_no", "ruku_no", "sajdah_type"],
          "ayahs": [list(r) for r in ayah_rows]})

    # ── 3. navigation ranges ────────────────────────────────────────────────
    nav: dict = {}
    for typ, unit, surah, sa, ea in qc.execute(
            "SELECT type, unit_no, surah_no, start_ayah, end_ayah FROM navigation_ranges"):
        nav.setdefault(typ, {}).setdefault(str(unit), []).append([surah, sa, ea])
    dump(inv / "quran_metadata/navigation_ranges.json",
         {"_meta": meta("quranapp.db navigation_ranges", 720,
                        "unit -> contiguous [surah, from_ayah, to_ayah] segments"), "ranges": nav})

    # ── 4. scripts + mushafs registry ───────────────────────────────────────
    scripts = [{"id": i, "code": c, "display_name": d, "parent_id": p}
               for i, c, d, p in qc.execute("SELECT script_id, code, display_name, parent FROM scripts")]
    mushafs = [{"id": i, "code": c, "no_of_pages": p, "lines_per_page": l}
               for i, c, p, l in qc.execute("SELECT mushaf_id, mushaf_code, no_of_pages, lines_per_page FROM mushafs")]
    map_cov = dict(qc.execute("SELECT mushaf_id, COUNT(*) FROM mushaf_map GROUP BY mushaf_id"))
    for m in mushafs:
        sources = []
        if map_cov.get(m["id"], 0):
            sources.append("mushaf_map")
        if m["code"] in page_info_codes:
            sources.append("page_info")
        m["layout_sources"] = sources
    dump(inv / "quran_metadata/mushafs.json",
         {"_meta": meta("quranapp.db scripts+mushafs", len(scripts) + len(mushafs),
                        "layout_sources: which mushaf_layout/ specs cover this mushaf "
                        "(indopak_13 has no mushaf_map rows in the donor — page_info only)"),
          "scripts": scripts, "mushafs": mushafs})

    # ── 5. search aliases ───────────────────────────────────────────────────
    aliases: dict = {}
    for no, lang, alias in qc.execute("SELECT surah_no, lang_code, alias FROM surah_search_aliases ORDER BY surah_no"):
        aliases.setdefault(str(no), {}).setdefault(lang, []).append(alias)
    n_alias = sum(len(v) for sura in aliases.values() for v in sura.values())
    dump(inv / "quran_metadata/surah_search_aliases.json",
         {"_meta": meta("quranapp.db surah_search_aliases", n_alias,
                        "surah_no -> lang -> aliases (arabic + latin transliterations)"), "aliases": aliases})

    # ── 6. mushaf_map (per-mushaf line layout, ayah-addressed) ─────────────
    print("== mushaf_layout ==")
    (inv / "mushaf_layout/mushaf_map").mkdir(parents=True, exist_ok=True)
    for mid, code, pages, lpp in qc.execute("SELECT mushaf_id, mushaf_code, no_of_pages, lines_per_page FROM mushafs").fetchall():
        rows = qc.execute(
            "SELECT page_number, line_number, line_type, is_centered, start_ayah_id, start_word_index, "
            "end_ayah_id, end_word_index, surah_no FROM mushaf_map WHERE mushaf_id=? ORDER BY page_number, line_number",
            (mid,)).fetchall()
        if not rows:
            print(f"  skip mushaf_map/{code}.json — no rows in donor (layout via page_info only)")
            continue
        dump(inv / f"mushaf_layout/mushaf_map/{code}.json",
             {"_meta": meta("quranapp.db mushaf_map", len(rows),
                            "word indices are 0-based within the ayah"),
              "mushaf": code, "pages": pages, "lines_per_page": lpp,
              "columns": ["page", "line", "type", "centered", "start_ayah_id",
                           "start_word_index", "end_ayah_id", "end_word_index", "surah_no"],
              "lines": [[p, l, t, c, sa, sw, ea, ew, s] for p, l, t, c, sa, sw, ea, ew, s in rows]})

    # ── 7. page_info.db (word-id-addressed layout) ─────────────────────────
    (inv / "mushaf_layout/page_info").mkdir(parents=True, exist_ok=True)
    for code, name, pages, lpp in pc.execute("SELECT script, name, number_of_pages, lines_per_page FROM info").fetchall():
        rows = pc.execute(
            "SELECT page_number, line_number, line_type, is_centered, first_word_id, last_word_id, surah_number "
            "FROM pages WHERE script=? ORDER BY page_number, line_number", (code,)).fetchall()

        def to_int(v):
            return int(v) if isinstance(v, int) or (isinstance(v, str) and v.isdigit()) else None

        lines = [[p, l, t, c, to_int(fw), to_int(lw), s] for p, l, t, c, fw, lw, s in rows]
        dump(inv / f"mushaf_layout/page_info/{code}.json",
             {"_meta": meta("page_info.db pages", len(rows),
                            "word ids: 1-based running word order of the rendered script "
                            "(matches ayah_words order for that script)"),
              "mushaf": code, "name": name, "pages": pages, "lines_per_page": lpp,
              "columns": ["page", "line", "type", "centered", "first_word_id", "last_word_id", "surah_no"],
              "lines": lines})

    # ── 8. word registries (per script, gzipped) ───────────────────────────
    scripts_with_words = qc.execute(
        "SELECT DISTINCT script_id FROM ayah_words ORDER BY script_id").fetchall()
    script_code = {i: c for i, c, *_ in qc.execute("SELECT script_id, code FROM scripts")}
    max_word_id = {}
    for (sid,) in scripts_with_words:
        words = qc.execute(
            "SELECT ayah_id, word_index, text FROM ayah_words WHERE script_id=? ORDER BY ayah_id, word_index",
            (sid,)).fetchall()
        code = script_code[sid]
        max_word_id[code] = len(words)
        dump_gz(inv / f"mushaf_layout/words/{code}.json.gz",
                {"_meta": meta("quranapp.db ayah_words", len(words),
                               "word position within ayah is 0-based"),
                 "script": code,
                 "columns": ["ayah_id", "word_index", "text"],
                 "words": [list(w) for w in words]})

    # anchor: qpc (QCF V2) renders uthmani words; page1 line2 = words 1..5 = 1:1
    pi_qpc = json.loads((inv / "mushaf_layout/page_info/qpc.json").read_text())
    l2 = [l for l in pi_qpc["lines"] if l[0] == 1 and l[1] == 2][0]
    assert l2[4] == 1 and l2[5] == 5, f"qpc p1 l2 word ids unexpected: {l2}"
    with gzip.open(inv / "mushaf_layout/words/uthmani.json.gz") as f:
        w5 = json.load(f)["words"][0:5]
    assert all(w[0] == 1001 for w in w5), f"Fatiha v1 word mismatch: {w5}"
    print(f"  anchor OK: qpc p1 l2 words 1..5 == Fatiha 1:1 ({len(w5)} words)")

    # ── 9. arabic search text (normalized, feeds on-device FTS rebuild) ────
    print("== quran_search ==")
    rows = qc.execute("SELECT ayah_id, text FROM arabic_search ORDER BY ayah_id").fetchall()
    assert len(rows) == 6236
    dump(inv / "quran_search/arabic_text.json",
         {"_meta": meta("quranapp.db arabic_search", 6236,
                        "diacritic-stripped normalized text; build FTS indexes on-device"),
          "ayahs": [[aid, t] for aid, t in rows]})

    # ── 10. similar verses + mutashabihat ───────────────────────────────────
    print("== similar ==")
    sv: dict = {}
    for src, match, wc, cov, score, mw in qc.execute(
            "SELECT source_ayah_id, matched_ayah_id, matched_words_count, coverage, score, match_words FROM similar_verses"):
        sv.setdefault(str(src), []).append([match, wc, cov, score, json.loads(mw)] if mw else [match, wc, cov, score, []])
    dump(inv / "similar/similar_verses.json",
         {"_meta": meta("quranapp.db similar_verses", sum(len(v) for v in sv.values()),
                        "coverage/score are percent; match_words: word-index ranges"),
          "columns": ["matched_ayah_id", "matched_words_count", "coverage", "score", "match_words"],
          "pairs": sv})

    phrases = [list(r) for r in qc.execute(
        "SELECT phrase_id, surahs_count, ayahs_count, occurrence_count, source_ayah_id, "
        "source_word_from, source_word_to FROM mutashabihat_phrases ORDER BY phrase_id")]
    occ: dict = {}
    for pid, aid, wr, order in qc.execute(
            "SELECT phrase_id, ayah_id, word_ranges, in_ayah_order FROM mutashabihat_phrase_ayah"):
        occ.setdefault(str(pid), []).append([aid, json.loads(wr), order])
    dump(inv / "similar/mutashabihat.json",
         {"_meta": meta("quranapp.db mutashabihat_*", len(phrases) + sum(len(v) for v in occ.values()),
                        "repeated-phrase detection (mutashabihat)"),
          "phrase_columns": ["phrase_id", "surahs_count", "ayahs_count", "occurrence_count",
                              "source_ayah_id", "word_from", "word_to"],
          "phrases": phrases,
          "occurrence_columns": ["ayah_id", "word_ranges", "in_ayah_order"],
          "occurrences": occ})

    # ── 11. topics ──────────────────────────────────────────────────────────
    print("== topics ==")
    topics_db = sqlite3.connect(f"file:{db_dir / 'topics.db'}{RO}", uri=True)
    tc = topics_db.cursor()
    topics = [[i, slug, t, img, icon, fl] for i, slug, t, img, icon, fl, *_ in tc.execute(
        "SELECT id, slug, type, image_url, icon, flags FROM topics ORDER BY id")]
    locs: dict = {}
    for tid, lang, title, short, desc in tc.execute(
            "SELECT topic_id, lang_code, title, short_description, description FROM topic_localizations"):
        locs.setdefault(str(tid), {})[lang] = [title, short, desc]
    tayahs: dict = {}
    for tid, aid in tc.execute("SELECT topic_id, ayah_id FROM topic_ayahs ORDER BY topic_id, ayah_id"):
        tayahs.setdefault(str(tid), []).append(aid)
    rels = [[s, t, ty, so] for _, s, t, ty, so, _ in tc.execute(
        "SELECT id, src_topic_id, tgt_topic_id, type, sort_order, metadata_json FROM relationships")]
    dump(inv / "topics/topics.json",
         {"_meta": meta("topics.db", len(topics),
                        "types: concept/category/prophet/place/animal/...; flags bitfield"),
          "topic_columns": ["id", "slug", "type", "image_url", "icon", "flags"],
          "topics": topics,
          "localizations": locs,
          "ayahs": tayahs,
          "relationship_columns": ["src_topic_id", "tgt_topic_id", "type", "sort_order"],
          "relationships": rels})

    # ── 12. curated verse packs + science (as-is copies) ───────────────────
    print("== curated / science ==")
    for name, src in (("verses", assets / "verses"), ("science", assets / "science")):
        dst = inv / "curated" / name
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        n = sum(1 for _ in dst.rglob("*") if _.is_file())
        print(f"  copied {n} files -> inventory/curated/{name}/")

    for db in (quran, pinfo, topics_db):
        db.close()
    print("\nDONE. Word-id spaces per script:", max_word_id)


if __name__ == "__main__":
    main()
