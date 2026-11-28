#!/usr/bin/env python3
"""Curated MPREA ingestion, multi-label topic taxonomy, and unified reading FTS5.

Keeps canonical donor tables (`dua_items` = 491, `dua_fts` = 491, `dua_posts` = 30)
untouched while extending `khushu-content.db` / `content.db` with:
  - Curated non-redundant Dua/Adhkar collections (`dua_extra_collections`,
    `dua_extra_items`, ids >= 10001): Al-Ma'thurat (26), Essential Adhkar (14),
    and deduplicated Hisn al-Muslim chapters (133 unique entries).
  - Hajj & Umrah Journey guide articles (`article_categories` id 892,
    `article_items` ids 50001..50005, cleaned of third-party promo URLs).
  - Self-organizing taxonomy (`category_domains`, `content_tags`, `item_tags`)
    mapping categories, articles, science pages, curated sets, and dua
    collections automatically by rule + keyword scoring.
  - Unified HTML-stripped FTS5 search (`reading_search_docs`, `reading_fts`).
"""
from __future__ import annotations

import html as _html
import json
import os
import re
import sqlite3
import unicodedata
from html.parser import HTMLParser
from typing import Iterable


class _TextExtractor(HTMLParser):
    """Lightweight HTML -> plain text stripper preserving block spaces."""

    _BREAK_TAGS = {"p", "br", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "tr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []
        self._skip = False

    def handle_starttag(self, tag: str, attrs) -> None:
        t = tag.lower()
        if t in ("script", "style"):
            self._skip = True
        elif t in self._BREAK_TAGS:
            self._chunks.append(" ")

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t in ("script", "style"):
            self._skip = False
        elif t in self._BREAK_TAGS:
            self._chunks.append(" ")

    def handle_data(self, data: str) -> None:
        if not self._skip and data:
            self._chunks.append(data)

    def text(self) -> str:
        raw = "".join(self._chunks).replace("\u00a0", " ")
        return " ".join(raw.split())


def strip_html(raw: str | None) -> str:
    if not raw:
        return ""
    # Replace inline custom corpus tags like <qref>...</qref>, <hon/> etc. nicely.
    cleaned = re.sub(r"\{\{[^}]+\}\}", " ", raw)
    parser = _TextExtractor()
    try:
        parser.feed(cleaned)
        parser.close()
        out = parser.text()
    except Exception:
        out = " ".join(re.sub(r"<[^>]+>", " ", cleaned).split())
    return _html.unescape(out)


def norm_ar(s: str | None) -> str:
    if not s:
        return ""
    s = "".join(
        ch for ch in unicodedata.normalize("NFD", s)
        if unicodedata.category(ch) != "Mn" and ch not in "\u0640\u0670"
    )
    s = re.sub(r"[^\w\s]", "", s)
    return " ".join(s.split())


def _slugify(value: str) -> str:
    s = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii").lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "other"


# ---- Category domain seed rules + automatic keyword fallback ----------------

_CATEGORY_DOMAIN_SEEDS: dict[str, tuple[str, list[str], int]] = {
    "tafsir-tadabbur": ("quran", ["sunnah", "dua"], 10),
    "knowing-allah": ("quran", ["dua"], 20),
    "loving-the-prophet": ("sunnah", ["quran", "dua"], 10),
    "taste-the-sweetness-of-salah": ("sunnah", ["dua", "quran"], 20),
    "other": ("sunnah", ["dua"], 30),
    "the-pure-heart": ("dua", ["sunnah", "quran"], 10),
    "istighfar": ("dua", ["quran"], 20),
    "related": ("dua", ["sunnah", "quran"], 25),
    "ruqyah": ("dua", ["quran", "sunnah"], 30),
    "ramadan": ("dua", ["quran", "sunnah"], 40),
    "dhul-hijjah": ("dua", ["sunnah"], 50),
    "hajj-and-umrah": ("dua", ["sunnah", "quran"], 55),
    "muharram": ("dua", ["sunnah"], 60),
    "seasons-of-worship": ("dua", ["sunnah"], 70),
}

_DOMAIN_CLASSIFY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "quran": ("quran", "tafsir", "tadabbur", "surah", "ayah", "verse", "revelation", "science"),
    "sunnah": ("sunnah", "prophet", "salah", "prayer", "hadith", "seerah", "companion", "masjid"),
    "dua": ("dua", "dhikr", "adhkar", "istighfar", "ruqyah", "hajj", "umrah", "heart", "fast", "ramadan"),
}

# Multi-label taxonomy topics: (tag_slug, display_label, domain_hint, keywords)
_TAXONOMY_RULES: list[tuple[str, str, str, tuple[str, ...]]] = [
    ("quran-reflection", "Qur'an & Tadabbur", "quran", ("quran", "qur'an", "qur’an", "surah", "ayah", "verse", "tafsir", "tadabbur", "recite", "recitation")),
    ("knowing-allah", "Knowing Allah & His Names", "quran", ("allah", "names of allah", "asma", "lord", "creator", "mercy", "majesty", "sovereignty", "tawhid")),
    ("prophetic-love", "The Prophet & Sunnah", "sunnah", ("prophet", "messenger", "muhammad", "sunnah", "seerah", "companions", "salawat", "blessings upon")),
    ("prayer-salah", "Salah & Standing in Worship", "sunnah", ("salah", "prayer", "wudu", "ablution", "adhan", "masjid", "sujood", "ruku", "tahajjud", "khushu", "fajr", "asr", "maghrib", "isha")),
    ("dua-dhikr", "Supplication & Dhikr", "dua", ("dua", "du'a", "supplicate", "supplication", "dhikr", "adhkar", "remembrance", "takbir", "tasbih", "tahmid", "morning", "evening")),
    ("forgiveness", "Istighfar & Repentance", "dua", ("istighfar", "forgive", "forgiveness", "repent", "repentance", "tawbah", "sin", "mercy", "pardon")),
    ("heart-purification", "Purifying the Heart", "dua", ("heart", "ikhlas", "sincerity", "soul", "nafs", "purification", "humility", "love of allah", "muhasabah")),
    ("patience-trust", "Patience, Ease & Tawakkul", "dua", ("patience", "sabr", "tawakkul", "trust", "anxiety", "distress", "grief", "relief", "calm", "difficulty", "hardship")),
    ("protection-ruqyah", "Protection & Ruqyah", "dua", ("protection", "refuge", "ruqyah", "illness", "healing", "cure", "shirk", "harm", "evil", "sleep", "nightmare")),
    ("gratitude-praise", "Gratitude & Praise", "quran", ("gratitude", "thankful", "shukr", "praise", "hamd", "blessing", "blessings", "bounty")),
    ("fasting-seasons", "Ramadan & Sacred Seasons", "dua", ("ramadan", "fast", "fasting", "siyam", "arafah", "ashura", "muharram", "dhul hijjah", "laylat", "eid")),
    ("hajj-pilgrimage", "Hajj & Umrah", "dua", ("hajj", "umrah", "ihram", "meeqat", "tawaf", "tawaaf", "safa", "marwah", "mina", "arafat", "muzdalifah", "jamarat", "kaabah", "talbiyah")),
    ("daily-life", "Everyday Etiquette & Travel", "sunnah", ("etiquette", "character", "manners", "travel", "journey", "home", "family", "marriage", "parents", "food", "drink", "charity", "sadaqah")),
    ("science-signs", "Signs in Creation", "quran", ("science", "creation", "universe", "embryo", "ocean", "mountains", "heavens", "earth", "astronomy", "rain", "water")),
]


def classify_category_domain(slug: str, name: str, sample_text: str = "") -> tuple[str, list[str], int]:
    if slug in _CATEGORY_DOMAIN_SEEDS:
        return _CATEGORY_DOMAIN_SEEDS[slug]
    hay = f"{slug.replace('-', ' ')} {name} {sample_text}".lower()
    scores = {
        dom: sum(1 for kw in kws if kw in hay)
        for dom, kws in _DOMAIN_CLASSIFY_KEYWORDS.items()
    }
    ordered = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    primary = ordered[0][0] if ordered[0][1] > 0 else "dua"
    secondary = [d for d, sc in ordered[1:] if sc > 0]
    if not secondary:
        secondary = [d for d in ("quran", "sunnah", "dua") if d != primary][:1]
    return primary, secondary, 80


def score_tags(title: str, body_text: str, domain_hint: str) -> list[tuple[str, float]]:
    title_l = title.lower()
    body_l = body_text[:4000].lower()
    scored: list[tuple[str, float]] = []
    for tag, _label, tag_domain, keywords in _TAXONOMY_RULES:
        score = 0.0
        for kw in keywords:
            if kw in title_l:
                score += 0.55
            elif kw in body_l:
                score += 0.22
        if tag_domain == domain_hint and score > 0:
            score += 0.15
        if score >= 0.35:
            scored.append((tag, round(min(1.0, score), 2)))
    if not scored:
        fallback = {
            "quran": "quran-reflection",
            "sunnah": "prayer-salah",
            "dua": "dua-dhikr",
        }.get(domain_hint, "dua-dhikr")
        scored.append((fallback, 0.5))
    scored.sort(key=lambda pair: -pair[1])
    return scored[:5]


def _clean_mprea_prose(raw: str) -> str:
    if not raw:
        return ""
    lines = []
    for line in raw.replace("\u00a0", " ").splitlines():
        s = line.strip()
        lower = s.lower()
        if "muslimpro.com" in lower or lower.startswith("watch our makkah live"):
            continue
        lines.append(s)
    text = "\n".join(lines).strip()
    # Fix duplicated preposition and typo in upstream MPREA Hajj Meeqat prose.
    text = re.sub(r"\bpeople of from\b", "people from", text, flags=re.IGNORECASE)
    text = re.sub(r"\bSyriya\b", "Syria", text)
    return re.sub(r"\n{3,}", "\n\n", text)


def _escape_html(text: str) -> str:
    return _html.escape(text, quote=False)


def _ingest_hajj_guides(conn: sqlite3.Connection, mprea_root: str) -> int:
    """Populate `reading_extra_categories` & `reading_extra_articles` without mutating canonical 13/185 counts."""
    conn.execute("DROP TABLE IF EXISTS reading_extra_articles")
    conn.execute("DROP TABLE IF EXISTS reading_extra_categories")
    conn.execute(
        """CREATE TABLE reading_extra_categories(
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            count INTEGER NOT NULL
        )"""
    )
    conn.execute(
        """CREATE TABLE reading_extra_articles(
            id INTEGER PRIMARY KEY,
            category_slug TEXT NOT NULL,
            title TEXT NOT NULL,
            slug TEXT NOT NULL,
            body_path TEXT NOT NULL,
            content_html TEXT NOT NULL
        )"""
    )
    path = os.path.join(mprea_root, "data", "hajj_recovered", "hajj_journey_days.json")
    if not os.path.isfile(path):
        return 0
    data = json.load(open(path, encoding="utf-8"))
    days = data.get("days") or []
    if not days:
        return 0

    cat_id = 892
    cat_slug = "hajj-and-umrah"
    cat_name = "Hajj & Umrah Guide"
    conn.execute(
        "INSERT OR REPLACE INTO reading_extra_categories(id, name, slug, count) VALUES(?,?,?,?)",
        (cat_id, cat_name, cat_slug, len(days)),
    )

    inserted = 0
    for idx, day in enumerate(days):
        art_id = 50001 + idx
        day_num = day.get("dayNumber", idx)
        raw_title = (day.get("dayTitle") or f"Day {day_num}").strip()
        if day_num == 0:
            title = "Pre-Hajj: The Five Meeqats & Entering Ihram"
        else:
            places_preview = ", ".join(
                (p.get("placeName") or "").strip()
                for p in (day.get("placeList") or [])[:3]
                if p.get("placeName")
            )
            title = f"Hajj {raw_title}: {places_preview}" if places_preview else f"Hajj {raw_title}"

        slug = f"hajj-guide-day-{day_num}"
        body_path = f"mprea/{slug}.html"
        parts = ["<article>"]
        for p in day.get("placeList") or []:
            pname = (p.get("placeName") or "").strip()
            desc = _clean_mprea_prose(p.get("description") or "")
            summary = _clean_mprea_prose(p.get("summary") or "")
            prose = desc if len(desc) >= len(summary) else summary
            if pname:
                parts.append(f"<h3>{_escape_html(pname)}</h3>")
            for para in prose.split("\n\n"):
                clean_p = " ".join(para.split())
                if clean_p:
                    parts.append(f"<p>{_escape_html(clean_p)}</p>")
        parts.append("</article>")
        content_html = "\n".join(parts)

        conn.execute(
            "INSERT OR REPLACE INTO reading_extra_articles(id, category_slug, title, slug, body_path, content_html) "
            "VALUES(?,?,?,?,?,?)",
            (art_id, cat_slug, title, slug, body_path, content_html),
        )
        inserted += 1
    return inserted


def _ingest_extra_duas(conn: sqlite3.Connection, mprea_root: str) -> tuple[int, int]:
    """Populate `dua_extra_collections` and `dua_extra_items` (ids >= 10001)."""
    conn.execute("DROP TABLE IF EXISTS dua_extra_items")
    conn.execute("DROP TABLE IF EXISTS dua_extra_collections")
    conn.execute(
        """CREATE TABLE dua_extra_collections(
            slug TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            category TEXT NOT NULL,
            source TEXT NOT NULL,
            item_count INTEGER NOT NULL,
            primary_domain TEXT NOT NULL
        )"""
    )
    conn.execute(
        """CREATE TABLE dua_extra_items(
            id INTEGER PRIMARY KEY,
            collection_slug TEXT NOT NULL,
            post_title TEXT NOT NULL,
            category TEXT NOT NULL,
            title TEXT NOT NULL,
            arabic TEXT NOT NULL,
            repetition TEXT NOT NULL,
            translation TEXT NOT NULL,
            transliteration TEXT NOT NULL,
            virtue TEXT NOT NULL,
            explanation TEXT NOT NULL,
            reference TEXT,
            audio_url TEXT
        )"""
    )

    existing_ar = {
        norm_ar(r[0])
        for r in conn.execute("SELECT arabic FROM dua_items")
        if r[0]
    }
    next_id = 10001
    coll_count = 0
    item_count = 0

    # 1) Al-Ma'thurat (complete 26-step litany)
    am_path = os.path.join(mprea_root, "data", "dua_almathurat_collection.json")
    if os.path.isfile(am_path):
        am = json.load(open(am_path, encoding="utf-8"))
        entries = am.get("contents") or []
        if entries:
            cslug = "al-mathurat"
            ctitle = (am.get("title") or "Al-Ma'thurat").strip()
            conn.execute(
                "INSERT INTO dua_extra_collections VALUES(?,?,?,?,?,?)",
                (cslug, ctitle, "main-adhkar", "al-mathurat", len(entries), "dua"),
            )
            coll_count += 1
            for entry in entries:
                rep_n = entry.get("targetReadCount") or 1
                rep = f"({rep_n}x)" if isinstance(rep_n, int) and rep_n > 1 else ""
                ar = (entry.get("arabic") or "").strip()
                tr = (entry.get("translation") or "").strip()
                tl = (entry.get("transliteration") or "").strip()
                ref = (entry.get("reference") or "").strip() or None
                conn.execute(
                    "INSERT INTO dua_extra_items VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        next_id,
                        cslug,
                        ctitle,
                        "main-adhkar",
                        (entry.get("title") or ctitle).strip(),
                        ar,
                        rep,
                        tr,
                        tl,
                        "",
                        "",
                        ref,
                        None,
                    ),
                )
                next_id += 1
                item_count += 1

    # 2) Essential Adhkar (14 daily phrases from dhikrs_multilingual.json)
    dk_path = os.path.join(mprea_root, "data", "dua_recovered", "dhikrs_multilingual.json")
    if os.path.isfile(dk_path):
        dhikrs = json.load(open(dk_path, encoding="utf-8"))
        if isinstance(dhikrs, list) and dhikrs:
            cslug = "essential-dhikr"
            ctitle = "Essential Daily Adhkar"
            conn.execute(
                "INSERT INTO dua_extra_collections VALUES(?,?,?,?,?,?)",
                (cslug, ctitle, "main-adhkar", "dhikrs", len(dhikrs), "dua"),
            )
            coll_count += 1
            for item in dhikrs:
                ar = (item.get("arabic") or "").strip()
                tl = " ".join((item.get("transliteration") or "").split())
                tr_raw = ((item.get("translations") or {}).get("en_default") or "").strip()
                tr = tr_raw.strip('"').strip()
                title = tl if len(tl) <= 72 else tr[:72]
                conn.execute(
                    "INSERT INTO dua_extra_items VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (next_id, cslug, ctitle, "main-adhkar", title, ar, "", tr, tl, "", "", None, None),
                )
                next_id += 1
                item_count += 1

    # 3) Deduplicated Hisn al-Muslim supplications from hisnul_v12.sqlite
    hc_path = os.path.join(mprea_root, "data", "emulator_live", "databases", "hisnul_v12.sqlite")
    if os.path.isfile(hc_path):
        hc = sqlite3.connect(hc_path)
        cats = dict(hc.execute("SELECT _id, en FROM hisnul_categories"))
        chaps = {r[0]: (r[1], r[2]) for r in hc.execute("SELECT _id, category_id, en FROM hisnul_chapters")}
        seen_hisn: set[str] = set()
        by_cat: dict[str, list[tuple[str, str, str, str, str | None]]] = {}
        for _id, chap_id, ar, trans, en, ref in hc.execute(
            "SELECT _id, chapterid, ar, trans, en, ref FROM hisnul_items ORDER BY _id"
        ):
            ar_s = (ar or "").strip()
            na = norm_ar(ar_s)
            if not na or na in existing_ar or na in seen_hisn:
                continue
            seen_hisn.add(na)
            cat_id, chap_title = chaps.get(chap_id, (0, "Hisn al-Muslim"))
            cat_name = (cats.get(cat_id) or "Other").strip()
            title = (chap_title or cat_name).strip()
            by_cat.setdefault(cat_name, []).append(
                (
                    title,
                    ar_s,
                    (en or "").strip(),
                    (trans or "").strip(),
                    (ref or "").strip() or None,
                )
            )
        hc.close()

        for cat_name in sorted(by_cat):
            items = by_cat[cat_name]
            cslug = f"hisn-{_slugify(cat_name)}"
            ctitle = f"Hisn al-Muslim: {cat_name}"
            dom = "sunnah" if cat_name in ("Prayer", "Good Etiquette") else "dua"
            conn.execute(
                "INSERT INTO dua_extra_collections VALUES(?,?,?,?,?,?)",
                (cslug, ctitle, "other-adhkar", "hisnul", len(items), dom),
            )
            coll_count += 1
            for title, ar_s, en_s, trans_s, ref_s in items:
                conn.execute(
                    "INSERT INTO dua_extra_items VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (next_id, cslug, ctitle, "other-adhkar", title, ar_s, "", en_s, trans_s, "", "", ref_s, None),
                )
                next_id += 1
                item_count += 1

    return coll_count, item_count


def _build_taxonomy_and_search(conn: sqlite3.Connection) -> tuple[int, int]:
    """Populate category_domains, content_tags, item_tags, reading_search_docs & reading_fts."""
    for tbl in ("item_tags", "content_tags", "category_domains", "reading_search_docs", "reading_fts"):
        conn.execute(f"DROP TABLE IF EXISTS {tbl}")

    conn.execute(
        """CREATE TABLE category_domains(
            category_slug TEXT PRIMARY KEY,
            primary_domain TEXT NOT NULL,
            secondary_domains TEXT NOT NULL,
            sort_weight INTEGER NOT NULL
        )"""
    )
    conn.execute(
        """CREATE TABLE content_tags(
            tag TEXT PRIMARY KEY,
            label TEXT NOT NULL,
            domain_hint TEXT NOT NULL
        )"""
    )
    conn.execute(
        """CREATE TABLE item_tags(
            item_type TEXT NOT NULL,
            item_id TEXT NOT NULL,
            tag TEXT NOT NULL,
            weight REAL NOT NULL,
            PRIMARY KEY(item_type, item_id, tag)
        )"""
    )
    conn.execute(
        """CREATE TABLE reading_search_docs(
            doc_id INTEGER PRIMARY KEY,
            item_type TEXT NOT NULL,
            item_key TEXT NOT NULL,
            title TEXT NOT NULL,
            subtitle TEXT NOT NULL,
            category_slug TEXT NOT NULL,
            domain TEXT NOT NULL,
            excerpt TEXT NOT NULL
        )"""
    )
    conn.execute(
        "CREATE VIRTUAL TABLE reading_fts USING fts5(title, subtitle, plain_text, content='', tokenize='unicode61')"
    )

    for tag, label, dom_hint, _ in _TAXONOMY_RULES:
        conn.execute("INSERT INTO content_tags VALUES(?,?,?)", (tag, label, dom_hint))

    # Map category slugs to domains
    cat_samples: dict[str, str] = {}
    for slug, title in conn.execute(
        "SELECT c.slug, GROUP_CONCAT(a.title, ' ') "
        "FROM article_categories c "
        "LEFT JOIN article_members m ON m.category_id=c.id "
        "LEFT JOIN article_items a ON a.id=m.article_id "
        "GROUP BY c.id"
    ):
        cat_samples[slug] = title or ""
    for slug, title in conn.execute(
        "SELECT c.slug, GROUP_CONCAT(a.title, ' ') "
        "FROM reading_extra_categories c "
        "LEFT JOIN reading_extra_articles a ON a.category_slug=c.slug "
        "GROUP BY c.id"
    ):
        cat_samples[slug] = title or ""

    cat_domain_map: dict[str, str] = {}
    extra_cat_names: dict[str, str] = {}
    for _cid, cname, cslug, _cnt in (
        conn.execute("SELECT id, name, slug, count FROM article_categories").fetchall() +
        conn.execute("SELECT id, name, slug, count FROM reading_extra_categories").fetchall()
    ):
        primary, secondary, weight = classify_category_domain(cslug, cname or "", cat_samples.get(cslug, ""))
        cat_domain_map[cslug] = primary
        extra_cat_names[cslug] = cname or ""
        conn.execute(
            "INSERT OR REPLACE INTO category_domains VALUES(?,?,?,?)",
            (cslug, primary, ",".join(secondary), weight),
        )

    cat_domain_map_by_article: dict[int, tuple[str, str]] = {}
    for aid, cname, cslug in conn.execute(
        "SELECT a.id, c.name, c.slug FROM article_items a "
        "JOIN article_members m ON m.article_id=a.id "
        "JOIN article_categories c ON c.id=m.category_id "
        "ORDER BY c.id, a.id"
    ):
        cat_domain_map_by_article.setdefault(aid, (cslug, cname or ""))

    doc_id = 1
    tag_rows: list[tuple[str, str, str, float]] = []

    def add_doc(
        item_type: str,
        item_key: str,
        title: str,
        subtitle: str,
        category_slug: str,
        domain: str,
        plain_text: str,
        extra_tag_text: str = "",
    ) -> None:
        nonlocal doc_id
        clean_title = strip_html(title)
        clean_sub = strip_html(subtitle)
        clean_plain = " ".join(plain_text.split())
        excerpt = clean_plain[:200].rstrip()
        if len(clean_plain) > 200:
            excerpt = excerpt.rsplit(" ", 1)[0] + "…"
        conn.execute(
            "INSERT INTO reading_search_docs VALUES(?,?,?,?,?,?,?,?)",
            (doc_id, item_type, item_key, clean_title, clean_sub, category_slug, domain, excerpt),
        )
        conn.execute(
            "INSERT INTO reading_fts(rowid, title, subtitle, plain_text) VALUES(?,?,?,?)",
            (doc_id, clean_title, clean_sub, clean_plain),
        )
        for tag, weight in score_tags(clean_title, f"{clean_plain} {extra_tag_text}", domain):
            tag_rows.append((item_type, item_key, tag, weight))
        doc_id += 1

    # 1) Canonical articles
    for aid, title, slug, html in conn.execute(
        "SELECT id, title, slug, content_html FROM article_items WHERE has_body=1 ORDER BY id"
    ):
        cslug, cname = cat_domain_map_by_article.get(aid, ("other", "Reading"))
        domain = cat_domain_map.get(cslug, "dua")
        plain = strip_html(html)
        add_doc("article", str(aid), title, cname, cslug, domain, plain, extra_tag_text=cname)

    # 1b) MPREA / extra reading articles (Hajj & Umrah guides)
    for aid, cslug, title, slug, html in conn.execute(
        "SELECT id, category_slug, title, slug, content_html FROM reading_extra_articles ORDER BY id"
    ):
        cname = extra_cat_names.get(cslug, "Reading")
        domain = cat_domain_map.get(cslug, "dua")
        plain = strip_html(html)
        add_doc("article", str(aid), title, cname, cslug, domain, plain, extra_tag_text=cname)

    # 2) Quran & Science pages
    for tid, title in conn.execute("SELECT id, title FROM curated_science_topics ORDER BY id"):
        row = conn.execute(
            "SELECT html FROM curated_science_pages WHERE topic_id=? AND lang='en' LIMIT 1",
            (tid,),
        ).fetchone()
        if row is None:
            row = conn.execute(
                "SELECT html FROM curated_science_pages WHERE topic_id=? LIMIT 1",
                (tid,),
            ).fetchone()
        plain = strip_html(row[0] if row else "")
        add_doc("science", str(tid), title or str(tid), "Quran & Science", "quran-science", "quran", plain)

    # 3) Curated Quran verse collections (type0/type1/type2/major_sins)
    set_labels = {
        "type0": "Solutions from Quran",
        "type1": "Duas in Quran",
        "type2": "Quranic Etiquette",
        "major_sins": "Major Sins",
    }
    for kind, entry_id, refs in conn.execute("SELECT kind, entry_id, refs FROM curated_sets"):
        trow = conn.execute(
            "SELECT title FROM curated_titles WHERE kind=? AND entry_id=? AND lang='en' LIMIT 1",
            (kind, entry_id),
        ).fetchone()
        title = trow[0] if trow and trow[0] else f"Entry {entry_id}"
        label = set_labels.get(kind, "Quran Collection")
        add_doc(
            "curated_set",
            f"{kind}:{entry_id}",
            title,
            label,
            kind,
            "quran",
            f"{title} {label} {refs}",
        )

    # 4) Canonical dua collections (30)
    for pslug, ptitle, pcat in conn.execute(
        "SELECT subcategory, post_title, category FROM dua_posts ORDER BY category, post_id"
    ):
        duas_text = " ".join(
            f"{r[0] or ''} {r[1] or ''} {r[2] or ''}"
            for r in conn.execute(
                "SELECT title, translation, reference FROM dua_items WHERE subcategory=?",
                (pslug,),
            )
        )
        add_doc("dua_collection", pslug, ptitle, "Duas & Adhkar", pslug, "dua", duas_text)

    # 5) Supplementary dua collections (Al-Ma'thurat, Essential Adhkar, Hisn al-Muslim)
    for cslug, ctitle, _cat, source, dom in conn.execute(
        "SELECT slug, title, category, source, primary_domain FROM dua_extra_collections ORDER BY slug"
    ):
        duas_text = " ".join(
            f"{r[0] or ''} {r[1] or ''} {r[2] or ''}"
            for r in conn.execute(
                "SELECT title, translation, reference FROM dua_extra_items WHERE collection_slug=?",
                (cslug,),
            )
        )
        add_doc("dua_extra_collection", cslug, ctitle, f"Duas & Adhkar · {source}", cslug, dom, duas_text)

    # Tag article categories themselves from constituent article tags so domain/tag queries stay O(categories)
    conn.executemany(
        "INSERT OR REPLACE INTO item_tags(item_type, item_id, tag, weight) VALUES(?,?,?,?)",
        tag_rows,
    )
    return doc_id - 1, len(tag_rows)


def _reading_plain_map(conn: sqlite3.Connection) -> dict[tuple[str, str], str]:
    """Reconstruct searchable plain text for every doc in `reading_search_docs`."""
    out: dict[tuple[str, str], str] = {}
    for aid, html in conn.execute("SELECT id, content_html FROM article_items WHERE has_body=1"):
        out[("article", str(aid))] = strip_html(html)
    if conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='reading_extra_articles'"
    ).fetchone():
        for aid, html in conn.execute("SELECT id, content_html FROM reading_extra_articles"):
            out[("article", str(aid))] = strip_html(html)
    for tid in [r[0] for r in conn.execute("SELECT id FROM curated_science_topics")]:
        row = conn.execute(
            "SELECT html FROM curated_science_pages WHERE topic_id=? AND lang='en' LIMIT 1",
            (tid,),
        ).fetchone() or conn.execute(
            "SELECT html FROM curated_science_pages WHERE topic_id=? LIMIT 1",
            (tid,),
        ).fetchone()
        out[("science", str(tid))] = strip_html(row[0] if row else "")
    set_labels = {
        "type0": "Solutions from Quran",
        "type1": "Duas in Quran",
        "type2": "Quranic Etiquette",
        "major_sins": "Major Sins",
    }
    for kind, entry_id, refs in conn.execute("SELECT kind, entry_id, refs FROM curated_sets"):
        out[("curated_set", f"{kind}:{entry_id}")] = f"{set_labels.get(kind, '')} {refs}"
    for pslug, in conn.execute("SELECT subcategory FROM dua_posts"):
        out[("dua_collection", pslug)] = " ".join(
            f"{r[0] or ''} {r[1] or ''} {r[2] or ''}"
            for r in conn.execute("SELECT title, translation, reference FROM dua_items WHERE subcategory=?", (pslug,))
        )
    for cslug, in conn.execute("SELECT slug FROM dua_extra_collections"):
        out[("dua_extra_collection", cslug)] = " ".join(
            f"{r[0] or ''} {r[1] or ''} {r[2] or ''}"
            for r in conn.execute("SELECT title, translation, reference FROM dua_extra_items WHERE collection_slug=?", (cslug,))
        )
    return out


def populate_reading_fts(conn: sqlite3.Connection) -> int:
    """Populate contentless `reading_fts` from `reading_search_docs` on an open DB."""
    plain_map = _reading_plain_map(conn)
    rows = conn.execute(
        "SELECT doc_id, item_type, item_key, title, subtitle, excerpt FROM reading_search_docs ORDER BY doc_id"
    ).fetchall()
    conn.executemany(
        "INSERT INTO reading_fts(rowid, title, subtitle, plain_text) VALUES(?,?,?,?)",
        (
            (doc_id, title, sub, plain_map.get((itype, ikey)) or excerpt)
            for doc_id, itype, ikey, title, sub, excerpt in rows
        ),
    )
    return len(rows)


def populate_content_db(conn: sqlite3.Connection, data_api_root: str) -> None:
    """Extend an open consolidated `khushu-content.db` connection in-place."""
    mprea_root = os.path.abspath(os.path.join(data_api_root, "..", "mprea"))
    hajj_n = 0
    coll_n, dua_n = 0, 0
    names_n = 0
    if os.path.isdir(mprea_root):
        hajj_n = _ingest_hajj_guides(conn, mprea_root)
        coll_n, dua_n = _ingest_extra_duas(conn, mprea_root)
        names_n = _ingest_names99_mprea(conn, mprea_root)
    else:
        _ensure_empty_extra_duas(conn)
        _ensure_empty_names99_meta(conn)
    fts_n, tag_n = _build_taxonomy_and_search(conn)
    conn.commit()
    print(
        f"  taxonomy+mprea: hajj_articles={hajj_n} extra_dua_colls={coll_n} "
        f"extra_duas={dua_n} names_glyphs={names_n} reading_fts={fts_n} item_tags={tag_n}"
    )


def _norm_gloss(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()
    if s.startswith("the "):
        s = s[4:].strip()
    return s


def _ensure_empty_names99_meta(conn: sqlite3.Connection) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS names_mprea_meta(
            number INTEGER PRIMARY KEY,
            translit_diacritic TEXT NOT NULL,
            alt_meanings_en TEXT,
            glyph_vw REAL NOT NULL,
            glyph_vh REAL NOT NULL,
            glyph_paths_json TEXT NOT NULL
        )"""
    )


def _ingest_names99_mprea(conn: sqlite3.Connection, mprea_root: str) -> int:
    src = os.path.join(mprea_root, "data", "names99_recovered", "muslimpro_names99.json")
    conn.execute("DROP TABLE IF EXISTS names_mprea_meta")
    _ensure_empty_names99_meta(conn)
    if not os.path.isfile(src):
        return 0

    payload = json.load(open(src, encoding="utf-8"))
    db_translations = {
        row[0]: (row[1] or "")
        for row in conn.execute("SELECT number, translation FROM names_names WHERE lang_code='en'")
    }
    rows = []
    for entry in payload.get("names", []):
        num = int(entry["index"])
        translit = (entry.get("transliteration") or "").strip()
        glyph = entry.get("glyph") or {}
        vw = float(glyph.get("viewportWidth") or 0.0)
        vh = float(glyph.get("viewportHeight") or 0.0)
        paths = [
            p["pathData"].strip()
            for p in glyph.get("paths", [])
            if p.get("pathData") and p["pathData"].strip()
        ]
        if not paths or vw <= 0 or vh <= 0:
            continue

        db_norm = _norm_gloss(db_translations.get(num, ""))
        seen = {db_norm} if db_norm else set()
        novel: list[str] = []
        raw_meaning = (entry.get("meaning_en") or "").strip()
        for part in re.split(r"\s*(?:,|/)\s*", raw_meaning):
            clean = part.strip()
            norm = _norm_gloss(clean)
            if not clean or not norm or norm in seen:
                continue
            seen.add(norm)
            novel.append(clean)

        alt_json = json.dumps(novel, ensure_ascii=False) if novel else None
        rows.append((num, translit, alt_json, vw, vh, json.dumps(paths, ensure_ascii=False)))

    conn.executemany(
        "INSERT INTO names_mprea_meta VALUES(?,?,?,?,?,?)",
        rows,
    )
    return len(rows)


def _ensure_empty_extra_duas(conn: sqlite3.Connection) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS dua_extra_collections(
            slug TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            category TEXT NOT NULL,
            source TEXT NOT NULL,
            item_count INTEGER NOT NULL,
            primary_domain TEXT NOT NULL
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS dua_extra_items(
            id INTEGER PRIMARY KEY,
            collection_slug TEXT NOT NULL,
            post_title TEXT NOT NULL,
            category TEXT NOT NULL,
            title TEXT NOT NULL,
            arabic TEXT NOT NULL,
            repetition TEXT NOT NULL,
            translation TEXT NOT NULL,
            transliteration TEXT NOT NULL,
            virtue TEXT NOT NULL,
            explanation TEXT NOT NULL,
            reference TEXT,
            audio_url TEXT
        )"""
    )
