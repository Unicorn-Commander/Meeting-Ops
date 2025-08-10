#!/usr/bin/env python3
"""
Test script to verify VAD fix and transcription
"""

import requests
import time
import json

API_URL = "http://localhost:9050"

def test_recording_with_transcription():
    print("1. Creating session...")
    response = requests.post(
        f"{API_URL}/api/simple/recording-sessions",
        json={"name": "VAD Fix Test", "description": "Testing with VAD disabled"}
    )
    session = response.json()
    session_id = session['id']
    print(f"   Session created: {session_id}")
    
    print("\n2. Starting recording...")
    response = requests.post(f"{API_URL}/api/simple/recording-sessions/{session_id}/start")
    print(f"   Recording started: {response.json()}")
    
    print("\n3. Recording for 10 seconds (please speak)...")
    for i in range(10, 0, -1):
        print(f"   {i}...", end="", flush=True)
        time.sleep(1)
    print()
    
    print("\n4. Stopping recording...")
    response = requests.post(f"{API_URL}/api/simple/recording-sessions/{session_id}/stop")
    print(f"   Recording stopped: {response.json()}")
    
    print("\n5. Getting transcription...")
    response = requests.get(f"{API_URL}/api/simple/recording-sessions/{session_id}")
    session_data = response.json()
    
    if session_data.get('transcript'):
        transcript_data = json.loads(session_data['transcript'])
        print(f"\n   ✅ TRANSCRIPTION SUCCESSFUL!")
        print(f"   Segments: {len(transcript_data.get('segments', []))}")
        print(f"   Full text: {transcript_data.get('full_text', 'No text')[:200]}...")
        
        if transcript_data.get('segments'):
            print(f"\n   First few segments:")
            for seg in transcript_data['segments'][:3]:
                print(f"   - [{seg['start']:.1f}s-{seg['end']:.1f}s]: {seg['text']}")
    else:
        print(f"\n   ❌ No transcription found")
        print(f"   Session data: {session_data}")

if __name__ == "__main__":
    test_recording_with_transcription()