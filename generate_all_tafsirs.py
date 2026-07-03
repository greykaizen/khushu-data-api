import os
import json
import gzip
import urllib.request
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

RESOURCES_URL = "https://api.quran.com/api/v4/resources/tafsirs?language=en"
BASE_DIR = "/home/kaizen/AndroidStudioProjects/khushu-quran-data/inventory/tafsirs"
MANIFEST_PATH = os.path.join(BASE_DIR, "available_tafsirs_info.json")

# Map Quran.com language_name to ISO 639-1 language codes
LANG_MAP = {
    "arabic": "ar",
    "english": "en",
    "urdu": "ur",
    "bengali": "bn",
    "kurdish": "ku",
    "russian": "ru"
}

def get_tafsirs_list():
    req = urllib.request.Request(RESOURCES_URL, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            data = json.load(response)
            return data.get("tafsirs", [])
    except Exception as e:
        print(f"Error fetching resources list: {e}")
        return []

def download_chapter_tafsir(slug, ch_num):
    url = f"https://api.qurancdn.com/api/v4/tafsirs/{slug}/by_chapter/{ch_num}"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=20) as response:
                data = json.load(response)
                return ch_num, data.get("tafsirs", [])
        except Exception as e:
            if attempt == 3:
                print(f"    Failed to fetch {slug} ch {ch_num} after 4 attempts: {e}")
                return ch_num, []
            time.sleep(1.5 * (attempt + 1))
    return ch_num, []

def process_tafsir_book(tafsir_info):
    slug = tafsir_info["slug"]
    lang_name = tafsir_info["language_name"].lower()
    lang_code = LANG_MAP.get(lang_name)
    
    if not lang_code:
        print(f"Skipping {slug} due to unmapped language: {lang_name}")
        return False
        
    print(f"\n>>> Starting {slug} ({lang_code}) ...")
    
    # We download 114 chapters using a ThreadPoolExecutor
    chapters_data = {}
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(download_chapter_tafsir, slug, ch): ch for ch in range(1, 115)}
        for future in as_completed(futures):
            ch_num, segments = future.result()
            chapters_data[ch_num] = segments

    # Format into DB TafsirRecord structures
    # val slug: String, val chapter: Int, val fromVerse: Int, val toVerse: Int, val text: String
    book_records = []
    split_records = {ch: [] for ch in range(1, 115)}
    
    for ch in range(1, 115):
        segments = chapters_data.get(ch, [])
        for seg in segments:
            verse_key = seg.get("verse_key", "")
            if not verse_key or ":" not in verse_key:
                continue
            
            try:
                parts = verse_key.split(":")
                chapter_no = int(parts[0])
                verse_no = int(parts[1])
            except:
                continue
                
            text = seg.get("text", "")
            
            record = {
                "chapter": chapter_no,
                "fromVerse": verse_no,
                "toVerse": verse_no,
                "text": text
            }
            book_records.append(record)
            split_records[chapter_no].append({
                "fromVerse": verse_no,
                "toVerse": verse_no,
                "text": text
            })
            
    if not book_records:
        print(f"!!! No segments downloaded for {slug}. Skipping write.")
        return False

    # Directories structured by language code
    target_dir = os.path.join(BASE_DIR, lang_code, slug)
    split_dir = os.path.join(target_dir, "split")
    os.makedirs(split_dir, exist_ok=True)
    
    # Save split surah files
    for ch, records in split_records.items():
        split_file = os.path.join(split_dir, f"{ch}.json")
        with open(split_file, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False)
            
    # Save gzipped complete book
    complete_gz_path = os.path.join(target_dir, "tafsir.json.gz")
    with gzip.open(complete_gz_path, "wt", encoding="utf-8") as f:
        json.dump(book_records, f, ensure_ascii=False)
        
    print(f"  Saved {len(book_records)} segments for {slug} in '{lang_code}/{slug}/'.")
    print(f"  Gzipped complete size: {os.path.getsize(complete_gz_path)/1024:.2f} KB")
    return True

def main():
    tafsirs = get_tafsirs_list()
    print(f"Found {len(tafsirs)} total Tafsir books on Quran.com.")
    
    # Process all books
    successful_slugs = set()
    for item in tafsirs:
        success = process_tafsir_book(item)
        if success:
            successful_slugs.add(item["slug"])
            
    # Rebuild available_tafsirs_info.json with successfully processed books
    manifest_data = {"tafsirs": {}}
    for item in tafsirs:
        slug = item["slug"]
        if slug not in successful_slugs:
            continue
            
        lang_name = item["language_name"].lower()
        lang_code = LANG_MAP.get(lang_name)
        lang_name_display = item["language_name"].capitalize()
        
        # Build TafsirMetadata manifest item
        manifest_item = {
            "key": slug,
            "name": item["name"],
            "author": item["author_name"],
            "langCode": lang_code,
            "langName": lang_name_display,
            "slug": slug
        }
        
        if lang_code not in manifest_data["tafsirs"]:
            manifest_data["tafsirs"][lang_code] = []
        manifest_data["tafsirs"][lang_code].append(manifest_item)
        
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, ensure_ascii=False, indent=2)
        
    print(f"\n>>> Manifest generated successfully at {MANIFEST_PATH}.")
    print("Successfully processed books summary:")
    for lang, items in manifest_data["tafsirs"].items():
        print(f"  {lang}: {len(items)} books")

if __name__ == "__main__":
    main()
