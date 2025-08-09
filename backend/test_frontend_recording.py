#!/usr/bin/env python3
"""
Test script to verify frontend recording functionality
"""

import asyncio
import json
from aiohttp import web
import aiohttp
from aiohttp import ClientSession

async def test_recording_flow():
    """Test the complete recording flow as the frontend would"""
    
    API_BASE = "http://localhost:9050"
    
    async with ClientSession() as session:
        print("🎙️ Testing Frontend Recording Flow")
        print("=" * 50)
        
        # 1. Check audio devices
        print("1️⃣ Checking audio devices...")
        async with session.get(f"{API_BASE}/api/audio-devices") as resp:
            if resp.status == 200:
                devices = await resp.json()
                print(f"✅ Found {len(devices.get('devices', []))} audio devices")
                for dev in devices.get('devices', []):
                    print(f"   - {dev.get('name', 'Unknown')}")
            else:
                print(f"❌ Failed to get audio devices: {resp.status}")
                return
        
        # 2. Create recording session
        print("\n2️⃣ Creating recording session...")
        async with session.post(
            f"{API_BASE}/api/simple/recording-sessions",
            json={
                "name": "Frontend Test Recording",
                "description": "Testing frontend recording flow"
            }
        ) as resp:
            if resp.status != 200:
                print(f"❌ Failed to create session: {resp.status}")
                text = await resp.text()
                print(f"Response: {text}")
                return
            
            session_data = await resp.json()
            session_id = session_data["id"]
            print(f"✅ Session created: {session_id}")
        
        # 3. Start recording
        print("\n3️⃣ Starting recording...")
        async with session.post(
            f"{API_BASE}/api/simple/recording-sessions/{session_id}/start"
        ) as resp:
            if resp.status != 200:
                print(f"❌ Failed to start recording: {resp.status}")
                return
            
            result = await resp.json()
            print(f"✅ Recording started: {result.get('message', 'OK')}")
        
        # 4. Connect WebSocket for transcription
        print("\n4️⃣ Connecting WebSocket for live transcription...")
        ws_url = f"ws://localhost:9050/ws/transcription/{session_id}"
        
        try:
            async with session.ws_connect(ws_url) as ws:
                print("✅ WebSocket connected")
                
                # Listen for transcriptions for 10 seconds
                print("\n⏳ Recording for 10 seconds...")
                print("   (Make some noise or play audio!)")
                
                start_time = asyncio.get_event_loop().time()
                transcription_count = 0
                
                while asyncio.get_event_loop().time() - start_time < 10:
                    try:
                        msg = await asyncio.wait_for(ws.receive(), timeout=1.0)
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            data = json.loads(msg.data)
                            if data.get('type') == 'transcription':
                                transcription_count += 1
                                text = data.get('data', {}).get('text', '')
                                if text:
                                    print(f"   📝 Transcription #{transcription_count}: {text[:50]}...")
                    except asyncio.TimeoutError:
                        # No message received, continue
                        pass
                
                print(f"\n   Received {transcription_count} transcriptions")
                
        except Exception as e:
            print(f"⚠️ WebSocket error: {e}")
        
        # 5. Stop recording
        print("\n5️⃣ Stopping recording...")
        async with session.post(
            f"{API_BASE}/api/simple/recording-sessions/{session_id}/stop"
        ) as resp:
            if resp.status != 200:
                print(f"❌ Failed to stop recording: {resp.status}")
                return
            
            result = await resp.json()
            print(f"✅ Recording stopped")
            if "audio_file" in result:
                print(f"   📁 Audio file: {result['audio_file']}")
        
        # 6. Get session with transcription
        print("\n6️⃣ Getting session with transcription...")
        await asyncio.sleep(2)  # Wait for processing
        
        async with session.get(
            f"{API_BASE}/api/simple/recording-sessions/{session_id}"
        ) as resp:
            if resp.status == 200:
                session_data = await resp.json()
                
                if session_data.get("transcription"):
                    trans = session_data["transcription"]
                    segments = trans.get("segments", [])
                    print(f"✅ Transcription complete: {len(segments)} segments")
                    
                    if segments:
                        print("\n📝 First few segments:")
                        for seg in segments[:3]:
                            print(f"   [{seg.get('start', 0):.1f}s] {seg.get('speaker', 'Unknown')}: {seg.get('text', '')}")
                else:
                    print("⚠️ No transcription found")
            else:
                print(f"❌ Failed to get session: {resp.status}")
        
        print("\n" + "=" * 50)
        print("✅ Frontend recording flow test complete!")

if __name__ == "__main__":
    print("🚀 Testing Frontend Recording Flow")
    print("This simulates what the frontend does when recording")
    print("-" * 50)
    
    try:
        asyncio.run(test_recording_flow())
    except KeyboardInterrupt:
        print("\n⚠️ Test interrupted")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()