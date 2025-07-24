#!/usr/bin/env python3
"""Test NPU recording and transcription"""
import os
os.environ['LD_PRELOAD'] = '/lib/x86_64-linux-gnu/libstdc++.so.6'

import requests
import json
import time

API_URL = "http://localhost:9050"

print("🧪 Testing NPU Recording and Transcription")
print("=" * 50)

# 1. Login
print("\n1️⃣ Logging in...")
response = requests.post(
    f"{API_URL}/api/auth/login",
    data={"username": "admin", "password": "changeme123!"}
)
if response.status_code == 200:
    token = response.json()["access_token"]
    print("✅ Logged in successfully")
else:
    print(f"❌ Login failed: {response.text}")
    exit(1)

headers = {"Authorization": f"Bearer {token}"}

# 2. Check current transcription model
print("\n2️⃣ Checking current transcription model...")
response = requests.get(f"{API_URL}/api/status", headers=headers)
if response.status_code == 200:
    status = response.json()
    print(f"   Transcriber ready: {status.get('transcriber_ready', False)}")
    print(f"   NPU available: {status.get('npu_available', False)}")
    if 'system_info' in status:
        print(f"   Model: {status['system_info'].get('model_path', 'Unknown')}")

# 3. Create a recording session
print("\n3️⃣ Creating recording session...")
response = requests.post(
    f"{API_URL}/api/recording-sessions",
    headers=headers,
    json={
        "meeting_name": "NPU Test Recording",
        "meeting_type": "test",
        "recording_mode": "automatic"
    }
)
if response.status_code == 200:
    session = response.json()
    session_id = session["session_id"]
    print(f"✅ Session created: {session_id}")
else:
    print(f"❌ Failed to create session: {response.text}")
    exit(1)

# 4. Start recording
print("\n4️⃣ Starting recording...")
response = requests.post(
    f"{API_URL}/api/recording-sessions/{session_id}/start",
    headers=headers
)
if response.status_code == 200:
    print("✅ Recording started")
    print("🎙️ Please speak for 15 seconds...")
else:
    print(f"❌ Failed to start recording: {response.text}")
    exit(1)

# 5. Wait and check for transcriptions
print("\n5️⃣ Monitoring for transcriptions...")
for i in range(15):
    time.sleep(1)
    # Get session details
    response = requests.get(
        f"{API_URL}/api/recording-sessions/{session_id}",
        headers=headers
    )
    if response.status_code == 200:
        session_data = response.json()
        total = session_data.get("total_transcriptions", 0)
        npu = session_data.get("npu_accelerated", False)
        print(f"   {i+1}/15s - Transcriptions: {total}, NPU: {npu}")

# 6. Stop recording
print("\n6️⃣ Stopping recording...")
response = requests.post(
    f"{API_URL}/api/recording-sessions/{session_id}/stop",
    headers=headers
)
if response.status_code == 200:
    print("✅ Recording stopped")

# 7. Get transcriptions
print("\n7️⃣ Getting transcriptions...")
response = requests.get(
    f"{API_URL}/api/recording-sessions/{session_id}/transcriptions",
    headers=headers
)
if response.status_code == 200:
    transcriptions = response.json()
    print(f"   Total transcriptions: {len(transcriptions)}")
    if transcriptions:
        for t in transcriptions[:3]:  # Show first 3
            print(f"   - {t.get('text', 'N/A')}")
            if 'metadata' in t and t['metadata']:
                meta = json.loads(t['metadata']) if isinstance(t['metadata'], str) else t['metadata']
                if 'npu_accelerated' in meta:
                    print(f"     NPU: {meta['npu_accelerated']}")
else:
    print(f"   Failed to get transcriptions: {response.text}")

print("\n" + "=" * 50)
print("✅ Test complete!")