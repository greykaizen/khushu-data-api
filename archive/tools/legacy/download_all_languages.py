import requests
import json
import os

API_KEY = "bsxUVNjgbGLFfZPz2axhGNNRTSVOaTV0UpKtT9bjVk8XihFo"
languages = ['en', 'ar', 'ur', 'es', 'fr', 'id', 'fa', 'bn', 'ru', 'de', 'tr']

os.makedirs("assets/asma_ul_husna", exist_ok=True)

for lang in languages:
    url = f"https://islamicapi.com/api/v1/asma-ul-husna/?language={lang}&api_key={API_KEY}"
    print(f"Downloading Asma-ul-Husna in '{lang}'...")
    r = requests.get(url)
    if r.status_code == 200:
        try:
            data = r.json()
            if data.get("status") == "success":
                output_path = f"assets/asma_ul_husna/asma_data_{lang}.json"
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=4)
                print(f"Successfully saved to {output_path}")
            else:
                print(f"Failed response for '{lang}': {data.get('message')}")
        except Exception as e:
            print(f"Error parsing JSON for '{lang}': {e}")
    else:
        print(f"Http error {r.status_code} for '{lang}'")
