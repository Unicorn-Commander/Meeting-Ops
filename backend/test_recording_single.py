#!/usr/bin/env python3
import requests
import time

API_BASE = "http://localhost:9050"

# Create and start recording
resp = requests.post(f"{API_BASE}/api/recording-sessions", 
                    json={"name": "Direct Test", "description": "Testing"})
session_id = resp.json()["session"]["session_id"]
print(f"Session: {session_id}")

resp = requests.post(f"{API_BASE}/api/recording-sessions/{session_id}/start")
print(f"Start response: {resp.text}")

# Let it record
time.sleep(5)

# Stop
resp = requests.post(f"{API_BASE}/api/recording-sessions/{session_id}/stop")
print(f"Stop response: {resp.json()['session']['duration_seconds']}s recorded")