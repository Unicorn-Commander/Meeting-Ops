#!/usr/bin/env python3
"""Test end-to-end flow: recording, transcription, and WebSocket delivery"""
import os
os.environ['LD_PRELOAD'] = '/lib/x86_64-linux-gnu/libstdc++.so.6'

import asyncio
import websockets
import httpx
import json
import base64
import time
from datetime import datetime

API_URL = "http://localhost:9050"
WS_URL = "ws://localhost:9050"

async def get_auth_token():
    """Login and get auth token"""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{API_URL}/api/auth/login",
            data={"username": "admin", "password": "changeme123!"}
        )
        if response.status_code == 200:
            return response.json()["access_token"]
        else:
            raise Exception(f"Login failed: {response.text}")

async def create_session(token):
    """Create a new recording session"""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{API_URL}/api/recording-sessions",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "meeting_name": "End-to-End Test Session",
                "meeting_type": "test",
                "recording_mode": "automatic"
            }
        )
        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(f"Session creation failed: {response.text}")

async def start_recording(token, session_id):
    """Start recording for a session"""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{API_URL}/api/recording-sessions/{session_id}/start",
            headers={"Authorization": f"Bearer {token}"}
        )
        if response.status_code == 200:
            return True
        else:
            raise Exception(f"Start recording failed: {response.text}")

async def listen_for_transcriptions(session_id, token):
    """Connect to WebSocket and listen for transcriptions"""
    uri = f"{WS_URL}/ws/stream/{session_id}?token={token}"
    
    transcriptions = []
    
    try:
        async with websockets.connect(uri) as websocket:
            print("✅ WebSocket connected")
            
            # Listen for messages for 20 seconds
            start_time = time.time()
            while time.time() - start_time < 20:
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                    data = json.loads(message)
                    
                    if data["type"] == "status":
                        print(f"📊 Status: {data['message']}")
                    elif data["type"] == "transcription":
                        print(f"📝 Transcription: {data['text']}")
                        transcriptions.append(data)
                    else:
                        print(f"📨 Message type: {data['type']}")
                        
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    print(f"❌ Error receiving message: {e}")
                    
    except Exception as e:
        print(f"❌ WebSocket error: {e}")
        
    return transcriptions

async def stop_recording(token, session_id):
    """Stop recording for a session"""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{API_URL}/api/recording-sessions/{session_id}/stop",
            headers={"Authorization": f"Bearer {token}"}
        )
        if response.status_code == 200:
            return True
        else:
            print(f"Stop recording failed: {response.text}")
            return False

async def test_summarization(token, session_id):
    """Test LLM summarization"""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{API_URL}/api/recording-sessions/{session_id}/summarize",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "summary_style": "executive"
            }
        )
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Summarization failed: {response.text}")
            return None

async def main():
    print("🧪 Starting End-to-End Test")
    print("=" * 50)
    
    try:
        # 1. Get auth token
        print("\n1️⃣ Getting auth token...")
        token = await get_auth_token()
        print("✅ Authenticated")
        
        # 2. Create session
        print("\n2️⃣ Creating recording session...")
        session = await create_session(token)
        session_id = session["session_id"]
        print(f"✅ Session created: {session_id}")
        
        # 3. Start recording
        print("\n3️⃣ Starting recording...")
        await start_recording(token, session_id)
        print("✅ Recording started")
        
        # 4. Listen for transcriptions
        print("\n4️⃣ Listening for transcriptions (20 seconds)...")
        print("🎙️ Please speak into your microphone...")
        transcriptions = await listen_for_transcriptions(session_id, token)
        
        # 5. Stop recording
        print("\n5️⃣ Stopping recording...")
        await stop_recording(token, session_id)
        print("✅ Recording stopped")
        
        # 6. Test summarization
        print("\n6️⃣ Testing summarization...")
        summary = await test_summarization(token, session_id)
        if summary:
            print(f"✅ Summary generated:")
            if "summary" in summary and "executive_summary" in summary["summary"]:
                print(f"   {summary['summary']['executive_summary'][:200]}...")
        
        # Results
        print("\n" + "=" * 50)
        print("📊 Test Results:")
        print(f"   Transcriptions received: {len(transcriptions)}")
        if transcriptions:
            print(f"   First transcription: {transcriptions[0]['text']}")
        print(f"   Session ID: {session_id}")
        
        # Check files
        print("\n7️⃣ Checking audio files...")
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{API_URL}/api/files/session/{session_id}",
                headers={"Authorization": f"Bearer {token}"}
            )
            if response.status_code == 200:
                files = response.json()
                print(f"✅ Audio files: {len(files['files'])} files found")
                for file in files['files']:
                    print(f"   - {file['filename']} ({file['size_bytes']} bytes)")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())