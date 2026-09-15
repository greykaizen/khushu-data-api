import requests
import random

def get_api_key():
    session = requests.Session()
    random_id = random.randint(100000, 999999)
    email = f"kaizen_osprey_{random_id}@gmail.com"
    password = f"Pass_{random_id}"
    
    signup_url = "https://islamicapi.com/api/v1/frontend/signup.php"
    payload = {
        "name": "Kaizen Osprey",
        "email": email,
        "password": password,
        "organization": "Osprey Project"
    }
    
    print(f"Attempting to register account with email: {email}")
    r = session.post(signup_url, json=payload)
    print(f"Signup response status: {r.status_code}")
    try:
        data = r.json()
        print(f"Signup response payload: {data}")
        if data.get("status") == "error":
            print(f"Error signing up: {data.get('message')}")
            return None
    except Exception as e:
        print("Failed to parse JSON response:", e)
        return None

    # Fetch the API key JSON directly
    apikey_json_url = "https://islamicapi.com/api/v1/dashboard/api-key.php"
    r_key = session.get(apikey_json_url)
    print(f"API key fetch response status: {r_key.status_code}")
    try:
        data = r_key.json()
        print(f"API key response payload: {data}")
        return data.get("api_key")
    except Exception as e:
        print("Failed to parse API key JSON:", e)
        print("Response text:", r_key.text)
        return None

if __name__ == "__main__":
    key = get_api_key()
    if key:
        print(f"SUCCESS! API Key is: {key}")
    else:
        print("FAILED to find API key.")
