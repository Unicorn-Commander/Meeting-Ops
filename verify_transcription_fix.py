#!/usr/bin/env python3
"""Verify live transcription fix with 5-second recording and API check"""

import requests
import time
import websocket
import os

BASE_URL = "http://localhost:9050"
AUDIO_PATH = "/home/ucadmin/Development/Unicorn-Commander-Meeting-Ops/backend/storage/audio_files/recordings/session_1753039257_b20b3f67/recording_20250720_192103.wav"

# Get token
response = requests.post(f"{BASE_URL}/api/auth/login", data={"username": "admin", "password": "admin123"})
if response.status_code != 200:
    print(f"Login failed: {response.text}")
    exit(1)
token = response.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

# Create session
response = requests.post(f"{BASE_URL}/api/recording-sessions", headers=headers, json={"name": "Verification Test", "description": "Fix confirmation"})
if response.status_code != 200:
    print(f"Create session failed: {response.text}")
    exit(1)
session_id = response.json()["session"]["session_id"]
print(f"Created session: {session_id}")

# Start recording
response = requests.post(f"{BASE_URL}/api/recording-sessions/{session_id}/start", headers=headers)
if response.status_code != 200:
    print(f"Start failed: {response.text}")
    exit(1)
print("✅ Recording started!")

# Send audio chunk via WS
ws_url = f"ws://localhost:9050/ws/stream/{session_id}?token={token}"
ws = websocket.create_connection(ws_url)
with open(AUDIO_PATH, 'rb') as f:
    audio_data = f.read()
ws.send_binary(audio_data)
print("Sent audio chunk")
time.sleep(5)
ws.close()

# Stop recording
response = requests.post(f"{BASE_URL}/api/recording-sessions/{session_id}/stop", headers=headers)
print(f"Stop response: {response.status_code}")

# Get transcript from API (try GET first, fallback to POST if Method Not Allowed)
response = requests.get(f"{BASE_URL}/api/sessions/{session_id}/transcript", headers=headers)
if response.status_code == 405:
    response = requests.post(f"{BASE_URL}/api/sessions/{session_id}/transcript", headers=headers)
if response.status_code == 200:
    transcript = response.json()
    print("\nAPI Transcript Response:")
    print(transcript)
else:
    print(f"API failed: {response.status_code} - {response.text}")
