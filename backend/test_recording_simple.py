#!/usr/bin/env python3
"""
Test recording with the simple API bypassing audio monitor conflicts
"""
import requests
import time
import json
import subprocess

API_BASE = "http://localhost:9050/api/simple"

def test_recording():
    # Kill any existing arecord processes
    print("Killing any existing arecord processes...")
    subprocess.run(["pkill", "-f", "arecord"], capture_output=True)
    time.sleep(1)
    
    # Create a new session
    print("\n1. Creating recording session...")
    resp = requests.post(f"{API_BASE}/recording-sessions", 
                        json={"name": "Direct Test Recording", 
                              "description": "Testing without audio monitor"})
    session = resp.json()
    session_id = session["id"]
    print(f"   Session created: {session_id}")
    
    # Start recording
    print("\n2. Starting recording...")
    resp = requests.post(f"{API_BASE}/recording-sessions/{session_id}/start")
    print(f"   Response: {resp.status_code}")
    if resp.status_code == 200:
        result = resp.json()
        print(f"   Status: {result['status']}")
        print(f"   File: {result['audio_file']}")
    else:
        print(f"   Error: {resp.text}")
        return
    
    # Record for 5 seconds
    print("\n3. Recording for 5 seconds...")
    for i in range(5):
        time.sleep(1)
        print(f"   {i+1}...")
    
    # Stop recording
    print("\n4. Stopping recording...")
    resp = requests.post(f"{API_BASE}/recording-sessions/{session_id}/stop")
    result = resp.json()
    print(f"   Status: {result['status']}")
    print(f"   Duration: {result['duration']:.2f} seconds")
    print(f"   File size: {result['file_size']} bytes")
    print(f"   File path: {result['file_path']}")
    
    # Check if file exists
    import os
    if os.path.exists(result['file_path']):
        print(f"\n✅ SUCCESS: Recording file created!")
        print(f"   Size: {os.path.getsize(result['file_path'])} bytes")
    else:
        print(f"\n❌ FAILED: Recording file not found!")

if __name__ == "__main__":
    test_recording()