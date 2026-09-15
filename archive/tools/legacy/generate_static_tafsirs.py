import os
import json
import gzip
import urllib.request
import time

MANIFEST_PATH = "/home/kaizen/AndroidStudioProjects/khushu-quran-data/inventory/tafsirs/available_tafsirs_info.json"
BASE_DIR = "/home/kaizen/AndroidStudioProjects/khushu-quran-data/inventory/tafsirs"

def get_tafsirs_list():
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    tafsir_entries = []
    tafsirs_obj = data.get("tafsirs", {})
    for lang, items in tafsirs_obj.items():
        for item in items:
            tafsir_entries.append({
                "key": item.get("key"),
                "slug": item.get("slug")
            })
    return tafsir_entries

def download_tafsir_book(key, slug):
    total_surahs = 114
    batch_size = 10
    all_segments = []
    
    print(f"\n>>> Downloading {key} (slug: {slug}) surah-by-surah...")
    
    for start in range(1, total_surahs + 1, batch_size):
        end = min(start + batch_size - 1, total_surahs)
        url = f"https://api.alfaazplus.com/quran/tafsirs/by_surah?key={key}&surahs={start}-{end}"
        
        # Retry logic
        for attempt in range(3):
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=30) as response:
                    parsed = json.loads(response.read().decode('utf-8'))
                    all_segments.extend(parsed.get("tafsirs", []))
                print(f"  Chapters {start}-{end} fetched successfully.")
                break
            except Exception as e:
                print(f"  Attempt {attempt + 1} failed for {start}-{end}: {e}")
                if attempt == 2:
                    raise Exception(f"Failed to fetch {start}-{end} after 3 attempts")
                time.sleep(2)
                
    return all_segments

def save_and_split(slug, segments):
    target_dir = os.path.join(BASE_DIR, slug)
    split_dir = os.path.join(target_dir, "split")
    os.makedirs(split_dir, exist_ok=True)
    
    # Organize segments by surah number
    surah_map = {i: [] for i in range(1, 115)}
    for seg in segments:
        # Segment structures contain 'verse_key' like "2:285" or 'verses' list like ["2:285", "2:286"]
        verse_key = seg.get("verse_key", "")
        chapter_no = -1
        if ":" in verse_key:
            chapter_no = int(verse_key.split(":")[0])
        else:
            verses = seg.get("verses", [])
            if verses and ":" in verses[0]:
                chapter_no = int(verses[0].split(":")[0])
                
        if 1 <= chapter_no <= 114:
            # Build record structure matching TafsirRecord DB model
            # val slug: String, val chapter: Int, val fromVerse: Int, val toVerse: Int, val text: String
            verses_list = []
            for v in seg.get("verses", []):
                if ":" in v:
                    try:
                        verses_list.append(int(v.split(":")[1]))
                    except:
                        pass
            verses_list.sort()
            from_verse = verses_list[0] if verses_list else -1
            to_verse = verses_list[-1] if verses_list else -1
            
            surah_map[chapter_no].append({
                "fromVerse": from_verse,
                "toVerse": to_verse,
                "text": seg.get("text", "")
            })
            
    # Save split files
    for ch_no, records in surah_map.items():
        split_file = os.path.join(split_dir, f"{ch_no}.json")
        with open(split_file, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False)
            
    # Format and save complete book (list of TafsirRecord structures)
    book_records = []
    for seg in segments:
        verse_key = seg.get("verse_key", "")
        chapter_no = -1
        if ":" in verse_key:
            chapter_no = int(verse_key.split(":")[0])
        else:
            verses = seg.get("verses", [])
            if verses and ":" in verses[0]:
                chapter_no = int(verses[0].split(":")[0])
                
        verses_list = []
        for v in seg.get("verses", []):
            if ":" in v:
                try:
                    verses_list.append(int(v.split(":")[1]))
                except:
                    pass
        verses_list.sort()
        from_verse = verses_list[0] if verses_list else -1
        to_verse = verses_list[-1] if verses_list else -1
        
        book_records.append({
            "chapter": chapter_no,
            "fromVerse": from_verse,
            "toVerse": to_verse,
            "text": seg.get("text", "")
        })
        
    complete_json_path = os.path.join(target_dir, "tafsir.json")
    with open(complete_json_path, "w", encoding="utf-8") as f:
        json.dump(book_records, f, ensure_ascii=False)
        
    # Compress complete book
    complete_gz_path = complete_json_path + ".gz"
    with gzip.open(complete_gz_path, "wt", encoding="utf-8") as f:
        json.dump(book_records, f, ensure_ascii=False)
        
    # Remove uncompressed large complete json to keep repo size minimal
    if os.path.exists(complete_json_path):
        os.remove(complete_json_path)
        
    print(f"  Successfully saved {len(segments)} segments for {slug}.")
    print(f"  Gzipped complete book size: {os.path.getsize(complete_gz_path)/1024:.2f} KB")

def main():
    tafsir_entries = get_tafsirs_list()
    print(f"Found {len(tafsir_entries)} Tafsir books to process.")
    
    for entry in tafsir_entries:
        try:
            segments = download_tafsir_book(entry["key"], entry["slug"])
            save_and_split(entry["slug"], segments)
            # Short sleep to prevent server rate limiting
            time.sleep(1)
        except Exception as e:
            print(f"Error processing {entry['key']}: {e}")

if __name__ == "__main__":
    main()
