import os
import json
import time
import requests

# AlfaazPlus API — the same backend quran.com uses.
# Default (no id param) returns Ibn Ashur content.
# ?id=58 = Maududi, ?id=1030 = Ibn Ashur.
# The `resources` list in the response gives all available authors.
ALFAAZ_BASE = "https://api.alfaazplus.com/quran/chapters/{chapter}/info"

def download_chapters_info():
    out_dir = "inventory/chapters/info/en"
    os.makedirs(out_dir, exist_ok=True)

    print("Starting download of chapter info for 114 chapters from api.alfaazplus.com ...")
    for chapter in range(1, 115):
        url = ALFAAZ_BASE.format(chapter=chapter) + "?language=en"
        print(f"Fetching Chapter {chapter} info from AlfaazPlus ...")
        try:
            response = requests.get(url, timeout=20)
            if response.status_code == 200:
                data = response.json()
                chapter_info = data.get("chapter_info", {})
                resources = data.get("resources", [])

                # Standardize JSON format — store resources list for future author-switching
                cleaned_data = {
                    "chapter_id": chapter,
                    "language_code": chapter_info.get("lang_code", "en"),
                    "source": chapter_info.get("source", ""),
                    "short_text": chapter_info.get("short_text", ""),
                    "text": chapter_info.get("text", ""),
                    "resources": [
                        {
                            "id": r.get("id"),
                            "display_name": r.get("display_name", ""),
                            "author_name": r.get("author_name", ""),
                            "language_name": r.get("language_name", "")
                        }
                        for r in resources
                    ]
                }

                file_path = os.path.join(out_dir, f"{chapter}.json")
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(cleaned_data, f, ensure_ascii=False, indent=2)

                author = chapter_info.get("source", "unknown")
                print(f"  ✓ Chapter {chapter} saved. Author/source: {author}")
            else:
                print(f"  ✗ Failed Chapter {chapter}: HTTP {response.status_code}")
        except Exception as e:
            print(f"  ✗ Error fetching Chapter {chapter}: {e}")

        # Polite sleep to avoid rate limits
        time.sleep(0.5)

    print("\nDone. All 114 chapter info files written to inventory/chapters/info/en/")

if __name__ == "__main__":
    download_chapters_info()
