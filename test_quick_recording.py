#!/usr/bin/env python3
"""Quick test of recording with session_id"""

import requests
import time

BASE_URL = "http://localhost:9050"

# Get token
response = requests.post(
    f"{BASE_URL}/api/auth/login",
    data={"username": "admin", "password": "admin123"}
)
token = response.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

# Create session
response = requests.post(
    f"{BASE_URL}/api/recording-sessions",
    headers=headers,
    json={"name": "Quick Test", "description": "Testing"}
)

data = response.json()
session = data["session"]
session_id = session["session_id"]  # Use session_id, not id
print(f"Created session: {session_id}")

# Start recording
response = requests.post(
    f"{BASE_URL}/api/recording-sessions/{session_id}/start",
    headers=headers
)

print(f"Start recording response: {response.status_code}")
if response.status_code == 200:
    print("✅ Recording started!")
    
    # Record for 5 seconds
    print("Recording for 5 seconds...")
    time.sleep(5)
    
    # Stop recording
    response = requests.post(
        f"{BASE_URL}/api/recording-sessions/{session_id}/stop",
        headers=headers
    )
    print(f"Stop recording response: {response.status_code}")
    
    # Get transcriptions
    response = requests.get(
        f"{BASE_URL}/api/recording-sessions/{session_id}/transcriptions",
        headers=headers
    )
    
    if response.status_code == 200:
        transcriptions = response.json()
        print(f"\nTranscriptions: {len(transcriptions)} chunks")
        for t in transcriptions:
            print(f"- {t.get('text', '')}")
else:
    print(f"Error: {response.text}")