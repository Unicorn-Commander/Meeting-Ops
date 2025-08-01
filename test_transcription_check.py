#!/usr/bin/env python3
"""Check transcriptions for recent sessions"""

import requests
from datetime import datetime

BASE_URL = "http://localhost:9050"

# Get token
response = requests.post(
    f"{BASE_URL}/api/auth/login",
    data={"username": "admin", "password": "admin123"}
)
token = response.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

# Get recent sessions
response = requests.get(
    f"{BASE_URL}/api/recording-sessions",
    headers=headers
)

data = response.json()
# Handle both list and dict responses
if isinstance(data, dict) and "sessions" in data:
    sessions = data["sessions"]
elif isinstance(data, list):
    sessions = data
else:
    sessions = []
    
print(f"Found {len(sessions)} sessions\n")

# Check last 3 sessions
for session in sessions[:3]:
    session_id = session.get("session_id") or session.get("id")
    name = session.get("name", "Unknown")
    status = session.get("state") or session.get("status", "unknown")
    
    print(f"Session: {name}")
    print(f"  ID: {session_id}")
    print(f"  Status: {status}")
    
    # Get transcript
    response = requests.get(
        f"{BASE_URL}/api/sessions/{session_id}/transcript",
        headers=headers
    )
    
    if response.status_code == 200:
        data = response.json()
        
        # Handle different response formats
        if isinstance(data, dict):
            print(f"  Transcript response: {data}")
            transcriptions = data.get("transcriptions", [])
            if "text" in data:
                print(f"  Full text: {data['text'][:200]}...")
        elif isinstance(data, list):
            transcriptions = data
            print(f"  Transcriptions: {len(transcriptions)}")
            for i, trans in enumerate(transcriptions[:2]):  # Show first 2
                text = trans.get("text", "").strip()
                if text:
                    print(f"    [{i+1}] {text[:100]}...")
        else:
            print(f"  Unexpected format: {type(data)}")
    else:
        print(f"  Error getting transcriptions: {response.status_code}")
    
    print()