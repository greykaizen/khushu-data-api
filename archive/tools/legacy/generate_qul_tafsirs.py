import os
import json
import gzip
import urllib.request
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_DIR = "/home/kaizen/AndroidStudioProjects/khushu-quran-data/inventory/tafsirs"
MANIFEST_PATH = os.path.join(BASE_DIR, "available_tafsirs_info.json")

QUL_BOOKS = [
    {
        "slug": "french-mokhtasar",
        "lang": "fr",
        "lang_name": "Français",
        "name": "French Mokhtasar",
        "author": "Mokhtasar"
    },
    {
        "slug": "spanish-mokhtasar",
        "lang": "es",
        "lang_name": "Español",
        "name": "Spanish Mokhtasar",
        "author": "Mokhtasar"
    },
    {
        "slug": "indonesian-mokhtasar",
        "lang": "id",
        "lang_name": "Bahasa Indonesia",
        "name": "Indonesian Mokhtasar",
        "author": "Mokhtasar"
    },
    {
        "slug": "turkish-mokhtasar",
        "lang": "tr",
        "lang_name": "Türkçe",
        "name": "Turkish Mokhtasar",
        "author": "Mokhtasar"
    },
    {
        "slug": "tamil-mokhtasar",
        "lang": "ta",
        "lang_name": "தமிழ்",
        "name": "Tamil Mokhtasar",
        "author": "Mokhtasar"
    },
    {
        "slug": "hindi-mokhtasar",
        "lang": "hi",
        "lang_name": "हिंदी",
        "name": "Hindi Mokhtasar",
        "author": "Mokhtasar"
    }
]

def download_surah_json(slug, ch_num):
    url = f"https://raw.githubusercontent.com/spa5k/tafsir_api/main/tafsir/{slug}/{ch_num}.json"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=20) as response:
                data = json.load(response)
                return ch_num, data
        except Exception as e:
            if attempt == 3:
                print(f"    Failed to fetch {slug} ch {ch_num} after 4 attempts: {e}")
                return ch_num, []
            time.sleep(1.5 * (attempt + 1))
    return ch_num, []

def process_qul_book(book):
    slug = book["slug"]
    lang_code = book["lang"]
    
    print(f"\n>>> Processing QUL Tafsir {slug} ({lang_code}) ...")
    
    chapters_data = {}
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(download_surah_json, slug, ch): ch for ch in range(1, 115)}
        for future in as_completed(futures):
            ch_num, data = future.result()
            chapters_data[ch_num] = data

    book_records = []
    split_records = {ch: [] for ch in range(1, 115)}
    
    for ch in range(1, 115):
        items = chapters_data.get(ch, [])
        for item in items:
            ayah_no = item.get("ayah")
            text = item.get("text", "")
            if ayah_no is None:
                continue
                
            record = {
                "chapter": ch,
                "fromVerse": ayah_no,
                "toVerse": ayah_no,
                "text": text
            }
            book_records.append(record)
            split_records[ch].append({
                "fromVerse": ayah_no,
                "toVerse": ayah_no,
                "text": text
            })
            
    if not book_records:
        print(f"!!! No records found for {slug}. Skipping.")
        return False
        
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
        
    print(f"  Successfully processed {slug} ({lang_code}). Gzipped size: {os.path.getsize(complete_gz_path)/1024:.2f} KB")
    return True

def main():
    # Load current available_tafsirs_info.json manifest
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest_data = json.load(f)
        
    for book in QUL_BOOKS:
        success = process_qul_book(book)
        if success:
            # Add to manifest
            lang_code = book["lang"]
            manifest_item = {
                "key": book["slug"],
                "name": book["name"],
                "author": book["author"],
                "langCode": lang_code,
                "langName": book["lang_name"],
                "slug": book["slug"]
            }
            
            if lang_code not in manifest_data["tafsirs"]:
                manifest_data["tafsirs"][lang_code] = []
                
            # Avoid duplication
            existing_slugs = [x["slug"] for x in manifest_data["tafsirs"][lang_code]]
            if book["slug"] not in existing_slugs:
                manifest_data["tafsirs"][lang_code].append(manifest_item)
                
    # Save updated available_tafsirs_info.json
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, ensure_ascii=False, indent=2)
        
    print(f"\n>>> Updated manifest generated successfully at {MANIFEST_PATH}.")

if __name__ == "__main__":
    main()
