#!/usr/bin/env python3
"""
Test the complete recording pipeline programmatically
"""

import asyncio
import aiohttp
import json
import numpy as np
import time
from datetime import datetime

API_BASE_URL = "http://localhost:9050"

# Test credentials
USERNAME = "admin"
PASSWORD = "changeme123!"

async def login():
    """Login and get access token"""
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{API_BASE_URL}/api/auth/login",
            data={"username": USERNAME, "password": PASSWORD}
        ) as response:
            if response.status == 200:
                data = await response.json()
                print(f"✅ Login successful! Token: {data['access_token'][:20]}...")
                return data['access_token']
            else:
                print(f"❌ Login failed: {response.status}")
                text = await response.text()
                print(f"   Response: {text}")
                return None

async def create_recording_session(token):
    """Create a new recording session"""
    headers = {"Authorization": f"Bearer {token}"}
    
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{API_BASE_URL}/api/recording-sessions",
            headers=headers,
            json={
                "name": f"Test Recording - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                "description": "Automated test recording"
            }
        ) as response:
            if response.status == 200:
                data = await response.json()
                # Handle nested response structure
                if 'session' in data:
                    session = data['session']
                    session_id = session.get('session_id') or session.get('id')
                else:
                    session_id = data.get('session_id') or data.get('id')
                print(f"✅ Recording session created! ID: {session_id}")
                return session_id
            else:
                print(f"❌ Failed to create session: {response.status}")
                text = await response.text()
                print(f"   Response: {text}")
                return None

async def start_recording(token, session_id):
    """Start recording for a session"""
    headers = {"Authorization": f"Bearer {token}"}
    
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{API_BASE_URL}/api/recording-sessions/{session_id}/start",
            headers=headers
        ) as response:
            if response.status == 200:
                print(f"✅ Recording started!")
                return True
            else:
                print(f"❌ Failed to start recording: {response.status}")
                text = await response.text()
                print(f"   Response: {text}")
                return False

async def send_audio_chunk(token, session_id, audio_data):
    """Send audio chunk via WebSocket"""
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        session = aiohttp.ClientSession()
        ws = await session.ws_connect(
            f"ws://localhost:9050/ws/stream/{session_id}",
            headers=headers
        )
        
        # Send audio data
        await ws.send_bytes(audio_data)
        print(f"✅ Sent {len(audio_data)} bytes of audio")
        
        # Wait for response
        msg = await asyncio.wait_for(ws.receive(), timeout=5.0)
        if msg.type == aiohttp.WSMsgType.TEXT:
            data = json.loads(msg.data)
            print(f"📝 Transcription: {data}")
        
        await ws.close()
        await session.close()
        return True
        
    except Exception as e:
        print(f"❌ WebSocket error: {e}")
        return False

async def test_audio_levels_websocket(token):
    """Test audio levels WebSocket with authentication"""
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        session = aiohttp.ClientSession()
        ws = await session.ws_connect(
            f"ws://localhost:9050/ws/audio-levels",
            headers=headers
        )
        
        print("✅ Connected to audio levels WebSocket")
        
        # Listen for a few messages
        for i in range(5):
            msg = await asyncio.wait_for(ws.receive(), timeout=2.0)
            if msg.type == aiohttp.WSMsgType.TEXT:
                data = json.loads(msg.data)
                print(f"🎤 Audio level: {data}")
        
        await ws.close()
        await session.close()
        return True
        
    except Exception as e:
        print(f"❌ Audio levels WebSocket error: {e}")
        return False

async def stop_recording(token, session_id):
    """Stop recording for a session"""
    headers = {"Authorization": f"Bearer {token}"}
    
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{API_BASE_URL}/api/recording-sessions/{session_id}/stop",
            headers=headers
        ) as response:
            if response.status == 200:
                print(f"✅ Recording stopped!")
                return True
            else:
                print(f"❌ Failed to stop recording: {response.status}")
                return False

async def get_session_details(token, session_id):
    """Get session details including transcriptions"""
    headers = {"Authorization": f"Bearer {token}"}
    
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{API_BASE_URL}/api/recording-sessions/{session_id}",
            headers=headers
        ) as response:
            if response.status == 200:
                data = await response.json()
                # Handle different response structures
                if 'session' in data:
                    session = data['session']
                else:
                    session = data
                    
                print(f"\n📊 Session Details:")
                print(f"   Name: {session.get('name', 'N/A')}")
                print(f"   Status: {session.get('status', 'N/A')}")
                print(f"   Duration: {session.get('duration_seconds', 0)} seconds")
                print(f"   Transcriptions: {session.get('total_transcriptions', 0)}")
                
                transcriptions = session.get('transcriptions', [])
                if transcriptions:
                    print("\n📝 Transcriptions:")
                    for t in transcriptions[:5]:  # Show first 5
                        print(f"   - {t.get('text', t)}")
                
                return data
            else:
                print(f"❌ Failed to get session details: {response.status}")
                return None

def generate_test_audio(duration_seconds=5, sample_rate=16000):
    """Generate synthetic audio data for testing"""
    # Generate a simple sine wave
    frequency = 440  # A4 note
    t = np.linspace(0, duration_seconds, int(sample_rate * duration_seconds))
    audio = np.sin(2 * np.pi * frequency * t)
    
    # Add some variation
    audio += 0.1 * np.sin(2 * np.pi * 880 * t)  # Add octave
    
    # Convert to int16
    audio = (audio * 32767).astype(np.int16)
    
    return audio.tobytes()

async def main():
    print("🚀 Starting Recording Pipeline Test\n")
    
    # Step 1: Login
    print("1️⃣ Testing login...")
    token = await login()
    if not token:
        print("❌ Cannot proceed without authentication")
        return
    
    # Step 2: Test audio levels WebSocket
    print("\n2️⃣ Testing audio levels WebSocket...")
    await test_audio_levels_websocket(token)
    
    # Step 3: Create recording session
    print("\n3️⃣ Creating recording session...")
    session_id = await create_recording_session(token)
    if not session_id:
        print("❌ Cannot proceed without session")
        return
    
    # Step 4: Start recording
    print("\n4️⃣ Starting recording...")
    if not await start_recording(token, session_id):
        print("❌ Failed to start recording")
        return
    
    # Step 5: Send audio chunks
    print("\n5️⃣ Sending audio data...")
    audio_data = generate_test_audio(duration_seconds=3)
    
    # Split into chunks
    chunk_size = 16000 * 2  # 2 seconds of audio
    chunks = [audio_data[i:i+chunk_size] for i in range(0, len(audio_data), chunk_size)]
    
    for i, chunk in enumerate(chunks):
        print(f"\n   Sending chunk {i+1}/{len(chunks)}...")
        await send_audio_chunk(token, session_id, chunk)
        await asyncio.sleep(0.5)  # Small delay between chunks
    
    # Step 6: Stop recording
    print("\n6️⃣ Stopping recording...")
    await stop_recording(token, session_id)
    
    # Step 7: Get session details
    print("\n7️⃣ Getting session details...")
    await asyncio.sleep(2)  # Give backend time to process
    await get_session_details(token, session_id)
    
    print("\n✅ Test completed!")

if __name__ == "__main__":
    asyncio.run(main())