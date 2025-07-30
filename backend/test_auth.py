#!/usr/bin/env python
import requests

# Login
login_response = requests.post(
    "http://localhost:1950/api/auth/login",
    data={"username": "admin", "password": "changeme123!"}
)

if login_response.status_code == 200:
    data = login_response.json()
    token = data["access_token"]
    print(f"✅ Login successful")
    print(f"   User: {data['user']['username']}")
    print(f"   Role: {data['user']['role']}")
    print(f"   Is Superuser: {data['user']['is_superuser']}")
    
    # Get /me endpoint
    me_response = requests.get(
        "http://localhost:1950/api/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    if me_response.status_code == 200:
        me_data = me_response.json()
        print(f"\n✅ /me endpoint:")
        print(f"   Role: {me_data['role']}")
        print(f"   Is Superuser: {me_data['is_superuser']}")
    else:
        print(f"❌ /me failed: {me_response.status_code}")
else:
    print(f"❌ Login failed: {login_response.status_code}")
    print(login_response.text)