#!/usr/bin/env python3
"""Test recording and transcription functionality"""

import requests
import time
import json
import asyncio
import websockets

BASE_URL = "http://localhost:9050"

def get_token():
    """Get auth token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        data={"username": "admin", "password": "admin123"}
    )
    return response.json()["access_token"]

async def test_transcription_websocket(session_id):
    """Connect to transcription WebSocket"""
    print(f"\nConnecting to transcription WebSocket for session {session_id}...")
    
    try:
        # Try the /ws/transcription endpoint instead
        ws_url = f"ws://localhost:9050/ws/transcription"
        print(f"Trying: {ws_url}")
        
        async with websockets.connect(ws_url) as websocket:
            print("✅ Connected to transcription WebSocket")
            
            # Listen for a few messages
            for i in range(10):
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                    data = json.loads(message)
                    print(f"Transcription: {data}")
                except asyncio.TimeoutError:
                    print(".", end="", flush=True)
                except Exception as e:
                    print(f"Message error: {e}")
                    
    except Exception as e:
        print(f"❌ WebSocket error: {e}")

def test_recording():
    """Test recording workflow"""
    print("Testing Recording & Transcription...")
    print("=" * 50)
    
    # Get token
    token = get_token()
    headers = {"Authorization": f"Bearer {token}"}
    
    # 1. Create session
    print("\n1. Creating recording session...")
    response = requests.post(
        f"{BASE_URL}/api/recording-sessions",
        headers=headers,
        json={"name": "Test Recording", "description": "Testing transcription"}
    )
    
    if response.status_code not in [200, 201]:
        print(f"❌ Failed to create session: {response.status_code}")
        print(response.text)
        return
        
    data = response.json()
    print(f"Session response: {data}")
    
    # Handle nested response
    if "session" in data:
        session = data["session"]
        session_id = session.get("id") or session.get("session_id")
    else:
        session = data
        session_id = session.get("id") or session.get("session_id")
        
    print(f"✅ Session created: ID={session_id}")
    
    # 2. Start recording
    print("\n2. Starting recording...")
    response = requests.post(
        f"{BASE_URL}/api/recording-sessions/{session_id}/start",
        headers=headers
    )
    
    if response.status_code not in [200, 201]:
        print(f"❌ Failed to start recording: {response.status_code}")
        print(response.text)
        return
        
    print("✅ Recording started")
    
    # 3. Test transcription WebSocket
    print("\n3. Testing live transcription...")
    asyncio.run(test_transcription_websocket(session_id))
    
    # 4. Let it record for 10 seconds
    print("\n4. Recording for 10 seconds...")
    for i in range(10):
        print(f"  {10-i} seconds remaining...", end="\r")
        time.sleep(1)
    
    # 5. Stop recording
    print("\n\n5. Stopping recording...")
    response = requests.post(
        f"{BASE_URL}/api/recording-sessions/{session_id}/stop",
        headers=headers
    )
    
    if response.status_code not in [200, 201]:
        print(f"❌ Failed to stop recording: {response.status_code}")
        print(response.text)
        return
        
    print("✅ Recording stopped")
    
    # 6. Get transcriptions
    print("\n6. Getting transcriptions...")
    response = requests.get(
        f"{BASE_URL}/api/recording-sessions/{session_id}/transcriptions",
        headers=headers
    )
    
    if response.status_code == 200:
        transcriptions = response.json()
        print(f"✅ Found {len(transcriptions)} transcriptions")
        for t in transcriptions[:3]:  # Show first 3
            print(f"   - {t.get('text', 'No text')}")
    else:
        print(f"❌ Failed to get transcriptions: {response.status_code}")
    
    # 7. Test summarization
    print("\n7. Testing summarization...")
    response = requests.post(
        f"{BASE_URL}/api/recording-sessions/{session_id}/summarize",
        headers=headers
    )
    
    if response.status_code in [200, 201]:
        print("✅ Summary requested")
        
        # Wait a bit for processing
        time.sleep(3)
        
        # Get summary
        response = requests.get(
            f"{BASE_URL}/api/recording-sessions/{session_id}/summary",
            headers=headers
        )
        
        if response.status_code == 200:
            summary = response.json()
            print(f"✅ Summary: {summary.get('summary', 'No summary')[:100]}...")
        else:
            print(f"❌ Failed to get summary: {response.status_code}")
    else:
        print(f"❌ Failed to request summary: {response.status_code}")
        print(response.text)

if __name__ == "__main__":
    test_recording()