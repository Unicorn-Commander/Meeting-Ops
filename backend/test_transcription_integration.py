#!/usr/bin/env python3
"""
Test transcription integration with 10-second chunks
"""
import requests
import json
import time
import sys
import os

# API base URL
API_BASE = "http://localhost:9050"

def test_transcription_integration():
    """Test the complete transcription pipeline"""
    
    print("🧪 Testing transcription integration...")
    
    # 1. Create a test session
    print("📝 Creating test session...")
    response = requests.post(f"{API_BASE}/api/recording-sessions", 
                           json={"name": "Transcription Integration Test", 
                                "description": "Testing 10-second chunk transcription"})
    
    if response.status_code != 200:
        print(f"❌ Failed to create session: {response.status_code}")
        return False
    
    session_data = response.json()
    session_id = session_data["session"]["session_id"]
    print(f"✅ Created session: {session_id}")
    
    # 2. Start recording
    print("🎙️ Starting recording...")
    response = requests.post(f"{API_BASE}/api/recording-sessions/{session_id}/start")
    
    if response.status_code != 200:
        print(f"❌ Failed to start recording: {response.status_code}")
        return False
    
    print("✅ Recording started")
    
    # 3. Wait for some chunks to be processed (if audio was working)
    print("⏰ Waiting 5 seconds for potential audio processing...")
    time.sleep(5)
    
    # 4. Check session status
    print("📊 Checking session status...")
    response = requests.get(f"{API_BASE}/api/recording-sessions/{session_id}")
    
    if response.status_code != 200:
        print(f"❌ Failed to get session status: {response.status_code}")
        return False
    
    session_info = response.json()
    print(f"📋 Session status: {session_info.get('status', 'unknown')}")
    print(f"📋 Transcriptions: {session_info.get('total_transcriptions', 0)}")
    
    # 5. Stop recording
    print("⏹️ Stopping recording...")
    response = requests.post(f"{API_BASE}/api/recording-sessions/{session_id}/stop")
    
    if response.status_code != 200:
        print(f"❌ Failed to stop recording: {response.status_code}")
        return False
    
    final_session = response.json()["session"]
    print(f"✅ Recording stopped")
    print(f"📊 Final status: {final_session.get('status')}")
    print(f"⏱️ Duration: {final_session.get('duration_seconds', 0)} seconds")
    
    # 6. Check if any files were created
    print("📁 Checking for audio files...")
    response = requests.get(f"{API_BASE}/api/files/session/{session_id}")
    
    if response.status_code == 200:
        files = response.json()
        print(f"📁 Found {len(files)} audio files")
        for file_info in files:
            print(f"   - {file_info.get('filename', 'Unknown')}: {file_info.get('size_bytes', 0)} bytes")
    else:
        print("❌ Could not retrieve file information (authentication required)")
    
    return True

if __name__ == "__main__":
    success = test_transcription_integration()
    if success:
        print("🎉 Integration test completed successfully!")
    else:
        print("❌ Integration test failed!")