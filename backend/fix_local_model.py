#!/usr/bin/env python3
"""Fix local model configuration to use correct model name"""

import requests

BASE_URL = "http://localhost:9050"

# Login
print("Logging in...")
response = requests.post(
    f"{BASE_URL}/api/auth/login",
    data={"username": "admin", "password": "admin123"}
)
token = response.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

# Update local_gemma3n to use the correct model name
print("Updating local_gemma3n to use correct model name...")
update_response = requests.put(
    f"{BASE_URL}/api/llm-settings/endpoints/local_gemma3n",
    json={
        "model": "gemma3n:e4b",  # Use the actual model name
        "context_window": 8192,
        "description": "Local Gemma3n E4B optimized for AMD 8945HS with NPU"
    },
    headers=headers
)

if update_response.status_code == 200:
    print("✅ Updated local_gemma3n to use gemma3n:e4b")
    
    # Test the endpoint
    print("\nTesting local endpoint...")
    test_response = requests.post(
        f"{BASE_URL}/api/llm-settings/endpoints/local_gemma3n/test",
        headers=headers
    )
    
    if test_response.status_code == 200:
        result = test_response.json()
        print(f"✅ Test successful!")
        print(f"   Status: {result.get('status')}")
        print(f"   Has model: {result.get('has_configured_model')}")
    else:
        print(f"❌ Test failed: {test_response.text}")
    
    # Test generation
    print("\nTesting generation with correct model...")
    notes_response = requests.post(
        f"{BASE_URL}/api/meeting-intelligence/live-notes",
        json={
            "transcript": "Quick test: Meeting about improving system performance.",
            "templates": ["executive-summary"],
            "session_id": "test-fixed-model"
        },
        headers=headers
    )
    
    if notes_response.status_code == 200:
        notes = notes_response.json()
        print("✅ Successfully generated notes with gemma3n:e4b!")
        if 'notes' in notes:
            print(f"   Notes type: {type(notes['notes'])}")
            if isinstance(notes['notes'], dict) and 'executive_summary' in notes['notes']:
                print(f"   Summary: {notes['notes']['executive_summary'][:100]}...")
            elif isinstance(notes['notes'], str):
                print(f"   Response: {notes['notes'][:100]}...")
    else:
        print(f"❌ Failed to generate: {notes_response.text}")
else:
    print(f"❌ Update failed: {update_response.text}")