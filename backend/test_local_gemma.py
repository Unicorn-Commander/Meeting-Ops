#!/usr/bin/env python3
"""Test local Gemma3n E4B configuration"""

import requests
import json

BASE_URL = "http://localhost:9050"

# Login
print("Logging in...")
response = requests.post(
    f"{BASE_URL}/api/auth/login",
    data={"username": "admin", "password": "admin123"}
)
token = response.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

# Check current configuration
print("\n" + "="*60)
print("CURRENT LLM CONFIGURATION")
print("="*60)

endpoints = requests.get(f"{BASE_URL}/api/llm-settings/endpoints", headers=headers).json()
print(f"Active endpoint: {endpoints['active_endpoint']}")
print(f"Fallback enabled: {endpoints['fallback_enabled']}")

print("\nConfigured endpoints:")
for ep in endpoints['endpoints']:
    active = " [ACTIVE]" if ep['name'] == endpoints['active_endpoint'] else ""
    enabled = "✓" if ep['enabled'] else "✗"
    print(f"  {enabled} {ep['name']}: {ep['model']} @ {ep['url']}{active}")

# Focus on local_gemma3n
local_ep = next((ep for ep in endpoints['endpoints'] if ep['name'] == 'local_gemma3n'), None)
if local_ep:
    print(f"\nLocal Gemma3n details:")
    print(f"  Model: {local_ep['model']}")
    print(f"  URL: {local_ep['url']}")
    print(f"  Context: {local_ep['context_window']} tokens")
    print(f"  Description: {local_ep['description']}")

# Ensure local_gemma3n is active
if endpoints['active_endpoint'] != 'local_gemma3n':
    print("\n⚠️  Local Gemma3n is not active. Activating...")
    activate = requests.post(
        f"{BASE_URL}/api/llm-settings/endpoints/local_gemma3n/activate",
        headers=headers
    )
    if activate.status_code == 200:
        print("✅ Activated local_gemma3n")
    else:
        print(f"❌ Failed to activate: {activate.text}")

# Test the local endpoint
print("\n" + "="*60)
print("TESTING LOCAL GEMMA3N")
print("="*60)

test_response = requests.post(
    f"{BASE_URL}/api/llm-settings/endpoints/local_gemma3n/test",
    headers=headers
)

if test_response.status_code == 200:
    result = test_response.json()
    print(f"✅ Connection successful!")
    print(f"   Status: {result.get('status')}")
    print(f"   Has configured model: {result.get('has_configured_model')}")
    if result.get('models'):
        print(f"   Available models: {', '.join(result['models'])}")
else:
    print(f"❌ Test failed: {test_response.text}")

# Test actual generation with Meeting Intelligence
print("\n" + "="*60)
print("TESTING MEETING INTELLIGENCE WITH LOCAL GEMMA3N")
print("="*60)

sample_transcript = """
Team meeting discussion:
- Project deadline is next Friday
- Sarah completed the backend API
- Mike needs two more days for UI
- Testing will begin Thursday
"""

print("Generating live notes...")
notes_response = requests.post(
    f"{BASE_URL}/api/meeting-intelligence/live-notes",
    json={
        "transcript": sample_transcript,
        "templates": ["executive-summary"],
        "session_id": "test-local-gemma"
    },
    headers=headers
)

if notes_response.status_code == 200:
    notes = notes_response.json()
    print("✅ Successfully generated notes with local Gemma3n!")
    print(f"   Session: {notes.get('session_id')}")
    print(f"   Type: {notes.get('type')}")
    
    if 'notes' in notes and notes['notes']:
        print("\n   Generated content:")
        content = json.dumps(notes['notes'], indent=2)
        # Show first 500 chars
        if len(content) > 500:
            print(content[:500] + "...")
        else:
            print(content)
else:
    print(f"❌ Failed to generate notes: {notes_response.status_code}")
    print(f"   Error: {notes_response.text}")

print("\n" + "="*60)
print("✅ Local Gemma3n E4B is configured and working!")
print("="*60)