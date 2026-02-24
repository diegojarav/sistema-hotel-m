
import requests
import json
import sys

# Constants
API_URL = "http://localhost:8000/api/v1"
LOGIN_URL = f"{API_URL}/auth/login"
RESERVATIONS_URL = f"{API_URL}/reservations"

# Credentials (assuming default admin or receptionist exists from seed)
USERNAME = "admin"  # Adjust if needed
PASSWORD = "admin"  # Adjust if needed, or use a known user

def verify_mobile_fetch():
    print(f"Testing Mobile API Fetch: {RESERVATIONS_URL}")
    
    # 1. Login to get token
    try:
        login_payload = {
            "username": USERNAME,
            "password": PASSWORD
        }
        # Login is usually form-data in OAuth2, let's try standard form-data
        response = requests.post(LOGIN_URL, data=login_payload)
        
        if response.status_code != 200:
            print(f"❌ Login Failed: {response.status_code} - {response.text}")
            return False
            
        token_data = response.json()
        access_token = token_data.get("access_token")
        print(f"✅ Login Success. Token obtained.")
        
    except Exception as e:
        print(f"❌ Login Exception: {e}")
        return False

    # 2. Fetch Reservations (Mimic Mobile App)
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.get(RESERVATIONS_URL, headers=headers)
        
        if response.status_code != 200:
            print(f"❌ Fetch Failed: {response.status_code} - {response.text}")
            return False
            
        data = response.json()
        print(f"✅ Fetch Success. Count: {len(data)}")
        
        if len(data) > 0:
            print("Sampling first item:")
            print(json.dumps(data[0], indent=2))
            
            # 3. Validate Schema matches Mobile Expectations
            # interface Reservation { id, room_id, guest_name, status, check_in, check_out }
            required_keys = ["id", "room_id", "guest_name", "status", "check_in", "check_out"]
            item = data[0]
            missing = [k for k in required_keys if k not in item]
            
            if missing:
                print(f"❌ Schema Mismatch! Missing keys: {missing}")
                return False
            else:
                print("✅ Schema matches Mobile Interface.")
                
        else:
            print("⚠️ No reservations to validate schema against.")
            
    except Exception as e:
        print(f"❌ Fetch Exception: {e}")
        return False

    return True

if __name__ == "__main__":
    if verify_mobile_fetch():
        sys.exit(0)
    else:
        sys.exit(1)
