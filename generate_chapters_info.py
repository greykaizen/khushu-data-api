import os
import json
import time
import requests

def download_chapters_info():
    out_dir = "inventory/chapters/info/en"
    os.makedirs(out_dir, exist_ok=True)
    
    print("Starting download of chapter info for 114 chapters...")
    for chapter in range(1, 115):
        url = f"https://api.quran.com/api/v4/chapters/{chapter}/info?language=en"
        print(f"Fetching Chapter {chapter} info...")
        try:
            response = requests.get(url, timeout=15)
            if response.status_code == 200:
                data = response.json()
                chapter_info = data.get("chapter_info", {})
                
                # Standardize JSON format
                cleaned_data = {
                    "chapter_id": chapter_info.get("chapter_id", chapter),
                    "language_code": "en",
                    "source": chapter_info.get("source", "Seyyed Hossein Nasr"),
                    "short_text": chapter_info.get("short_text", ""),
                    "text": chapter_info.get("text", "")
                }
                
                file_path = os.path.join(out_dir, f"{chapter}.json")
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(cleaned_data, f, ensure_ascii=False, indent=2)
                
                print(f"Successfully saved Chapter {chapter} info.")
            else:
                print(f"Failed to fetch Chapter {chapter} info: HTTP {response.status_code}")
        except Exception as e:
            print(f"Error fetching Chapter {chapter} info: {e}")
        
        # Polite sleep to avoid rate limits
        time.sleep(0.5)

if __name__ == "__main__":
    download_chapters_info()
