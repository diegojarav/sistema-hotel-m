
import requests
import json
import sys
import os

# Configuration
API_URL = "http://localhost:8000/api/v1"
USERNAME = "testuser"
PASSWORD = "password123"

def get_token():
    try:
        response = requests.post(f"{API_URL}/auth/login", data={"username": USERNAME, "password": PASSWORD})
        if response.status_code == 200:
            return response.json()["access_token"]
        print(f"❌ Login failed: {response.text}")
        return None
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return None

def verify_client_types(token):
    print("\n🔍 Verifying /pricing/client-types...")
    headers = {"Authorization": f"Bearer {token}"}
    try:
        response = requests.get(f"{API_URL}/pricing/client-types", headers=headers)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Success! Found {len(data)} client types.")
            print(f"   Sample: {[ct['name'] for ct in data[:3]]}")
        else:
            print(f"❌ Failed: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"❌ Exception: {e}")

def verify_agent_query(token):
    print("\n🔍 Verifying /agent/query...")
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {"prompt": "Hola, ¿cuáles son los precios?"}
    try:
        response = requests.post(f"{API_URL}/agent/query", headers=headers, json=payload)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Success! Response: {data.get('response', 'No response field')[:50]}...")
        else:
            print(f"❌ Failed: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"❌ Exception: {e}")

def verify_settings():
    print("\n🔍 Verifying /settings/hotel-name...")
    try:
        response = requests.get(f"{API_URL}/settings/hotel-name")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Success! Hotel Name: {data.get('hotel_name', 'Unknown')}")
        else:
            print(f"❌ Failed: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"❌ Exception: {e}")

if __name__ == "__main__":
    print("🚀 Starting Mobile Backend Verification")
    verify_settings()
    token = get_token()
    if token:
        verify_client_types(token)
        verify_agent_query(token)
    else:
        print("❌ Cannot proceed without token for authenticated endpoints.")
