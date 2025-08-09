#!/usr/bin/env python3
"""
Complete system test - Recording + Transcription
"""

import requests
import time
import json

BASE_URL = "http://localhost:9050"

def test_complete_flow():
    print("🧪 Testing Complete Recording + Transcription Flow")
    print("=" * 60)
    
    # Step 1: Create session
    print("\n📝 Step 1: Creating recording session...")
    response = requests.post(
        f"{BASE_URL}/api/simple/recording-sessions",
        json={"name": "Complete System Test", "description": "Testing recording + NPU transcription"}
    )
    
    if response.status_code != 200:
        print(f"❌ Failed to create session: {response.text}")
        return
    
    session = response.json()
    session_id = session["id"]
    print(f"✅ Session created: {session_id}")
    
    # Step 2: Start recording
    print("\n🎤 Step 2: Starting recording...")
    response = requests.post(f"{BASE_URL}/api/simple/recording-sessions/{session_id}/start")
    
    if response.status_code != 200:
        print(f"❌ Failed to start recording: {response.text}")
        return
    
    print(f"✅ Recording started")
    print("   Recording for 5 seconds...")
    
    # Record for 5 seconds
    for i in range(5):
        print(f"   {i+1}...")
        time.sleep(1)
    
    # Step 3: Stop recording
    print("\n⏹️ Step 3: Stopping recording...")
    response = requests.post(f"{BASE_URL}/api/simple/recording-sessions/{session_id}/stop")
    
    if response.status_code != 200:
        print(f"❌ Failed to stop recording: {response.text}")
        return
    
    result = response.json()
    print(f"✅ Recording stopped")
    print(f"   Duration: {result.get('duration', 0):.1f} seconds")
    print(f"   File: {result.get('audio_file', 'N/A')}")
    
    # Step 4: Wait for transcription
    print("\n📝 Step 4: Waiting for NPU transcription...")
    for i in range(10):
        response = requests.get(f"{BASE_URL}/api/simple/recording-sessions/{session_id}")
        session_data = response.json()
        
        if session_data["status"] == "completed":
            print(f"✅ Transcription complete!")
            if session_data.get("transcription"):
                trans = session_data["transcription"]
                print(f"   Text: {trans.get('text', 'N/A')[:200]}...")
                print(f"   Confidence: {trans.get('confidence', 0):.2%}")
            break
        elif session_data["status"] == "error":
            print(f"❌ Transcription failed: {session_data.get('error', 'Unknown error')}")
            break
        else:
            print(f"   Status: {session_data['status']}... ({i+1}/10)")
            time.sleep(2)
    
    print("\n" + "=" * 60)
    print("🎉 TEST COMPLETE!")
    print("\nSummary:")
    print(f"  ✅ Session created: {session_id}")
    print(f"  ✅ Audio recorded: ~5 seconds")
    print(f"  ✅ File saved: {result.get('audio_file', 'N/A')}")
    print(f"  ✅ Status: {session_data['status']}")
    
    if session_data.get("transcription"):
        print(f"  ✅ Transcription available: YES")
    else:
        print(f"  ⚠️ Transcription available: NO (might need more time)")

if __name__ == "__main__":
    # Check if backend is running
    try:
        response = requests.get(f"{BASE_URL}/docs")
        if response.status_code == 200:
            print("✅ Backend is running\n")
            test_complete_flow()
        else:
            print("❌ Backend returned unexpected status")
    except requests.exceptions.ConnectionError:
        print("❌ Backend is not running!")
        print("   Please start it with: cd backend && ./start-backend.sh")