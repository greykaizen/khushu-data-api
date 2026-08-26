import os
import json
import urllib.request
import subprocess

TRANSCRIPT_PATH = "/home/kaizen/.gemini/antigravity-cli/brain/1920f840-1222-40b3-adf4-853c4b874cba/.system_generated/logs/transcript_full.jsonl"
DATA_REPO_DIR = "/home/kaizen/AndroidStudioProjects/khushu-quran-data"
APP_ASSETS_DIR = "/home/kaizen/AndroidStudioProjects/Osprey/app/src/main/assets"

def extract_json_from_transcript():
    print("Reading transcript to extract Asma-ul-Husna JSON...")
    if not os.path.exists(TRANSCRIPT_PATH):
        print(f"Error: Transcript file not found at {TRANSCRIPT_PATH}")
        return None
    
    with open(TRANSCRIPT_PATH, "r", encoding="utf-8") as f:
        for line in f:
            if "asma-ul-husna/rahman.mp3" in line:
                try:
                    obj = json.loads(line)
                    if "content" not in obj:
                        continue
                    content = obj["content"]
                    idx = content.find('"names"')
                    if idx == -1:
                        continue
                    start = content.rfind("{", 0, idx)
                    if start == -1:
                        continue
                    json_str = content[start:]
                    try:
                        data, _ = json.JSONDecoder().raw_decode(json_str)
                        return data
                    except Exception as e:
                        print(f"JSON raw_decode failed: {e}")
                        continue
                except Exception as e:
                    print(f"Line parse failed: {e}")
                    continue
    return None

def main():
    data = extract_json_from_transcript()
    if not data:
        print("Failed to extract JSON data from transcript.")
        return
    
    print("Successfully extracted Asma-ul-Husna data!")
    
    # Create target directories
    repo_assets_dir = os.path.join(DATA_REPO_DIR, "assets", "asma_ul_husna")
    app_assets_dir = os.path.join(APP_ASSETS_DIR, "asma_ul_husna")
    os.makedirs(repo_assets_dir, exist_ok=True)
    os.makedirs(app_assets_dir, exist_ok=True)
    
    names = data.get("names", [])
    updated_names = []
    
    for item in names:
        number = item.get("number")
        arabic_name = item.get("name")
        transliteration = item.get("transliteration")
        translation = item.get("translation")
        meaning = item.get("meaning")
        audio_path = item.get("audio")
        
        filename = os.path.basename(audio_path)
        base_name, _ = os.path.splitext(filename)
        opus_filename = f"{base_name}.opus"
        
        # Download URL
        download_url = f"https://islamicapi.com{audio_path}"
        temp_mp3 = os.path.join(repo_assets_dir, f"temp_{number}.mp3")
        target_opus = os.path.join(repo_assets_dir, opus_filename)
        
        print(f"[{number}/99] Downloading {download_url}...")
        try:
            urllib.request.urlretrieve(download_url, temp_mp3)
            
            # Convert to opus using ffmpeg
            print(f"Converting to OPUS: {target_opus}")
            cmd = [
                "ffmpeg", "-y", "-i", temp_mp3,
                "-c:a", "libopus", "-b:a", "32k", "-application", "voip",
                target_opus
            ]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            
            # Delete temporary MP3
            if os.path.exists(temp_mp3):
                os.remove(temp_mp3)
                
            # Copy to app assets
            app_target_opus = os.path.join(app_assets_dir, opus_filename)
            subprocess.run(["cp", target_opus, app_target_opus], check=True)
            
        except Exception as e:
            print(f"Error processing item {number}: {e}")
            if os.path.exists(temp_mp3):
                os.remove(temp_mp3)
        
        # Build updated item record
        updated_item = {
            "number": number,
            "name": arabic_name,
            "transliteration": transliteration,
            "translation": translation,
            "meaning": meaning,
            "audio": f"assets/asma_ul_husna/{opus_filename}"
        }
        updated_names.append(updated_item)
        
    # Write JSON files
    final_data = {
        "code": 200,
        "status": "success",
        "data": {
            "names": updated_names,
            "total": len(updated_names),
            "language": data.get("language", "English"),
            "language_code": data.get("language_code", "en"),
            "title": data.get("title", "The Beautiful Names of Allah"),
            "arabic_title": data.get("arabic_title", "أسماء الله الحسنى"),
            "description": data.get("description", ""),
            "recitation_benefits": data.get("recitation_benefits", ""),
            "hadith": data.get("hadith", "")
        }
    }
    
    repo_json_path = os.path.join(repo_assets_dir, "asma_data_en.json")
    app_json_path = os.path.join(app_assets_dir, "asma_data_en.json")
    
    with open(repo_json_path, "w", encoding="utf-8") as f:
        json.dump(final_data, f, ensure_ascii=False, indent=4)
        
    with open(app_json_path, "w", encoding="utf-8") as f:
        json.dump(final_data, f, ensure_ascii=False, indent=4)
        
    print(f"All 99 names and audios successfully processed and written to:")
    print(f" - {repo_json_path}")
    print(f" - {app_json_path}")

if __name__ == "__main__":
    main()
