#!/usr/bin/env python3
"""Test the LLM configuration API"""

import requests
import json

# Base URL
BASE_URL = "http://localhost:9050"

# Login (uses form data, not JSON)
print("Logging in...")
login_response = requests.post(
    f"{BASE_URL}/api/auth/login",
    data={"username": "admin", "password": "admin123"}
)

if login_response.status_code == 200:
    token = login_response.json().get("access_token")
    print(f"✅ Login successful, token: {token[:20]}...")
    
    # Get endpoints
    headers = {"Authorization": f"Bearer {token}"}
    
    print("\nFetching LLM endpoints...")
    endpoints_response = requests.get(
        f"{BASE_URL}/api/llm-settings/endpoints",
        headers=headers
    )
    
    if endpoints_response.status_code == 200:
        data = endpoints_response.json()
        print(f"✅ Fetched {len(data['endpoints'])} endpoints")
        print(f"Active endpoint: {data['active_endpoint']}")
        print(f"Fallback enabled: {data['fallback_enabled']}")
        
        print("\nEndpoints:")
        for ep in data['endpoints']:
            status = "✓" if ep['enabled'] else "✗"
            active = " [ACTIVE]" if ep['name'] == data['active_endpoint'] else ""
            print(f"  {status} {ep['name']}: {ep['provider']} - {ep['model']}{active}")
            print(f"     URL: {ep['url']}")
            print(f"     Context: {ep['context_window']} tokens")
            
        # Test an endpoint
        print("\n" + "="*50)
        print("Testing remote endpoint...")
        test_response = requests.post(
            f"{BASE_URL}/api/llm-settings/endpoints/remote_gemma2_9b/test",
            headers=headers
        )
        
        if test_response.status_code == 200:
            test_data = test_response.json()
            print(f"✅ Test successful: {test_data}")
        else:
            print(f"❌ Test failed: {test_response.status_code}")
            print(test_response.text)
            
    else:
        print(f"❌ Failed to get endpoints: {endpoints_response.status_code}")
        print(endpoints_response.text)
else:
    print(f"❌ Login failed: {login_response.status_code}")
    print(login_response.text)