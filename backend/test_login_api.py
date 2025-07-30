#!/usr/bin/env python3
import requests
import json

# Test login endpoint
url = "http://localhost:9050/api/auth/login"
data = {
    "username": "admin",
    "password": "Changeme123!"
}

print(f"Testing login with: {json.dumps(data, indent=2)}")
print(f"URL: {url}")

try:
    response = requests.post(url, json=data)
    print(f"\nStatus Code: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    
    if response.status_code == 200:
        print("\n✅ Login successful!")
        token = response.json().get('access_token')
        print(f"Access token: {token[:20]}..." if token else "No token received")
    else:
        print("\n❌ Login failed")
        
except Exception as e:
    print(f"\n❌ Error: {e}")