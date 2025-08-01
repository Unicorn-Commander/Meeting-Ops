#!/usr/bin/env python3
"""Test summarization feature"""

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

# Get a recent completed session
response = requests.get(
    f"{BASE_URL}/api/recording-sessions",
    headers=headers
)

data = response.json()
sessions = data.get("sessions", data) if isinstance(data, dict) else data

# Find a completed session
completed_session = None
for session in sessions:
    if session.get("state") == "completed" or session.get("status") == "completed":
        completed_session = session
        break

if not completed_session:
    print("No completed sessions found")
    exit(1)

session_id = completed_session.get("session_id") or completed_session.get("id")
print(f"Testing summarization for session: {session_id}")
print(f"Session name: {completed_session.get('name')}")

# Request summarization
print("\nRequesting summary...")
response = requests.post(
    f"{BASE_URL}/api/recording-sessions/{session_id}/summarize",
    headers={**headers, "Content-Type": "application/json"},
    json={}  # Empty object as required
)

print(f"Summarize response: {response.status_code}")
if response.status_code in [200, 201]:
    print("✅ Summary requested successfully")
    
    # Wait for processing
    print("Waiting for summary generation...")
    time.sleep(5)
    
    # Get summary
    response = requests.get(
        f"{BASE_URL}/api/recording-sessions/{session_id}/summary",
        headers=headers
    )
    
    print(f"\nGet summary response: {response.status_code}")
    if response.status_code == 200:
        summary_data = response.json()
        print(f"Summary data: {summary_data}")
        
        if "summary" in summary_data:
            print(f"\n📝 Summary:\n{summary_data['summary']}")
        elif "text" in summary_data:
            print(f"\n📝 Summary:\n{summary_data['text']}")
        else:
            print("No summary text found in response")
    else:
        print(f"Error: {response.text}")
else:
    print(f"Error requesting summary: {response.text}")