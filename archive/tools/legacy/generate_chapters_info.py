import os
import json
import time
import requests

# AlfaazPlus API — correctly supports both resource IDs:
#   id=1030 → Ibn Ashur (Tafsir al-Tahrir wa al-Tanwir) — "Themes and Purpose" headings
#   id=58   → A. Maududi (Tafhim al-Qur'an)              — "Name/Period/Theme" headings
ALFAAZPLUS_API = "https://api.alfaazplus.com/quran/chapters/{chapter}/info?language=en&id={resource_id}"

RESOURCES = [
    {"id": 1030, "slug": "",   "display": "Ibn Ashur"},   # default file: {N}.json
    {"id": 58,   "slug": "_58","display": "A. Maududi"},  # alt file:     {N}_58.json
]

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json"
}

STATIC_RESOURCES = [
    {"id": 1030, "display_name": "Ibn Ashur",  "author_name": "Muhammad al-Tahir ibn Ashur"},
    {"id": 58,   "display_name": "A. Maududi", "author_name": "Sayyid Abul Ala Maududi"}
]

def download_chapters_info():
    out_dir = "inventory/chapters/info/en"
    os.makedirs(out_dir, exist_ok=True)

    for resource in RESOURCES:
        rid    = resource["id"]
        slug   = resource["slug"]
        label  = resource["display"]
        print(f"\n=== Scraping {label} (id={rid}) ===")

        for chapter in range(1, 115):
            url = ALFAAZPLUS_API.format(chapter=chapter, resource_id=rid)
            try:
                resp = requests.get(url, headers=HEADERS, timeout=20)
                if resp.status_code == 200:
                    data = resp.json()
                    ci   = data.get("chapter_info", {})

                    cleaned = {
                        "chapter_id":    chapter,
                        "language_code": ci.get("lang_code", "en"),
                        "source":        ci.get("source", ""),
                        "short_text":    ci.get("short_text", ""),
                        "text":          ci.get("text", ""),
                        "resources":     STATIC_RESOURCES
                    }

                    filename = f"{chapter}{slug}.json"
                    file_path = os.path.join(out_dir, filename)
                    with open(file_path, "w", encoding="utf-8") as f:
                        json.dump(cleaned, f, ensure_ascii=False, indent=2)

                    src = ci.get("source", "?")[:60]
                    txt = ci.get("text", "")[:80]
                    print(f"  ✓ Ch{chapter} [{label}] | src: {src} | text: {txt}")
                else:
                    print(f"  ✗ Ch{chapter} [{label}]: HTTP {resp.status_code}")
            except Exception as e:
                print(f"  ✗ Ch{chapter} [{label}]: {e}")

            time.sleep(0.3)

    print("\n\nDone. All files written to inventory/chapters/info/en/")
    print("  {1..114}.json      → Ibn Ashur  (Themes and Purpose / Contexts)")
    print("  {1..114}_58.json   → A. Maududi (Name / Period / Theme)")

if __name__ == "__main__":
    download_chapters_info()
