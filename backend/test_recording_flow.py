#!/usr/bin/env python3
import requests
import time
import os

API_BASE = "http://localhost:9050"

print("🧪 Testing complete recording flow...")

# 1. Create session
print("\n1️⃣ Creating session...")
resp = requests.post(f"{API_BASE}/api/recording-sessions", 
                    json={"name": "Flow Test", "description": "Testing complete flow"})
session_data = resp.json()
session_id = session_data["session"]["session_id"]
print(f"✅ Session created: {session_id}")

# 2. Start recording
print("\n2️⃣ Starting recording...")
resp = requests.post(f"{API_BASE}/api/recording-sessions/{session_id}/start")
print(f"✅ Recording started: {resp.json()['success']}")

# 3. Wait 15 seconds for audio chunks
print("\n3️⃣ Recording for 15 seconds (should generate 1-2 chunks)...")
for i in range(15):
    print(f"   {i+1}/15 seconds...", end='\r')
    time.sleep(1)
print("\n✅ Recording complete")

# 4. Stop recording
print("\n4️⃣ Stopping recording...")
resp = requests.post(f"{API_BASE}/api/recording-sessions/{session_id}/stop")
final_session = resp.json()["session"]
print(f"✅ Recording stopped")
print(f"   Status: {final_session['status']}")
print(f"   Duration: {final_session['duration_seconds']}s")

# 5. Check audio file
print("\n5️⃣ Checking audio file...")
audio_dir = f"storage/audio_files/recordings/{session_id}"
if os.path.exists(audio_dir):
    files = os.listdir(audio_dir)
    for f in files:
        if f.endswith('.wav'):
            file_path = os.path.join(audio_dir, f)
            file_size = os.path.getsize(file_path)
            print(f"   File: {f}")
            print(f"   Size: {file_size} bytes")
            if file_size > 0:
                print("   ✅ Audio file has data!")
            else:
                print("   ❌ Audio file is empty!")
else:
    print("   ❌ Audio directory not found!")

print("\n🏁 Test complete!")