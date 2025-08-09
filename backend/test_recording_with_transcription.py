#!/usr/bin/env python3
"""
Test recording from USB mic and transcribe with NPU
Perfect for testing with podcast audio playing
"""

import asyncio
import aiohttp
import json
import time
import sys
from pathlib import Path

API_BASE = "http://localhost:9050"

async def test_recording_and_transcription():
    """Test recording and transcription workflow"""
    
    print("🎙️ Meeting-Ops Recording Test")
    print("=" * 50)
    print("This will:")
    print("1. Create a recording session")
    print("2. Start recording from USB mic (10 seconds)")
    print("3. Stop and process with NPU transcription")
    print("4. Display results")
    print("=" * 50)
    print("\n▶️ Please ensure your podcast is playing!\n")
    
    async with aiohttp.ClientSession() as session:
        # 1. Create recording session
        print("📝 Creating recording session...")
        async with session.post(
            f"{API_BASE}/api/simple/recording-sessions",
            json={
                "name": "Podcast Test Recording",
                "description": "Testing with live podcast audio"
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
        
        # 2. Start recording
        print("\n🔴 Starting recording (10 seconds)...")
        async with session.post(
            f"{API_BASE}/api/simple/recording-sessions/{session_id}/start"
        ) as resp:
            if resp.status != 200:
                print(f"❌ Failed to start recording: {resp.status}")
                text = await resp.text()
                print(f"Response: {text}")
                return
            
            result = await resp.json()
            print(f"✅ Recording started: {result['message']}")
        
        # 3. Wait for recording
        print("\n⏳ Recording in progress...")
        for i in range(10):
            print(f"   {10-i} seconds remaining...", end='\r')
            await asyncio.sleep(1)
        print("\n")
        
        # 4. Stop recording
        print("⏹️ Stopping recording...")
        async with session.post(
            f"{API_BASE}/api/simple/recording-sessions/{session_id}/stop"
        ) as resp:
            if resp.status != 200:
                print(f"❌ Failed to stop recording: {resp.status}")
                text = await resp.text()
                print(f"Response: {text}")
                return
            
            result = await resp.json()
            print(f"✅ Recording stopped")
            if "audio_file" in result:
                print(f"📁 Audio file: {result['audio_file']}")
        
        # 5. Check transcription status
        print("\n🔄 Waiting for NPU transcription...")
        max_wait = 30
        for i in range(max_wait):
            async with session.get(
                f"{API_BASE}/api/simple/recording-sessions/{session_id}"
            ) as resp:
                if resp.status == 200:
                    session_data = await resp.json()
                    
                    # Check for transcription
                    if session_data.get("transcription"):
                        print("\n✅ Transcription complete!")
                        print("\n" + "=" * 50)
                        print("📝 TRANSCRIPTION RESULTS:")
                        print("=" * 50)
                        
                        trans = session_data["transcription"]
                        
                        # Display segments
                        if "segments" in trans:
                            print(f"\n📊 Found {len(trans['segments'])} segments:\n")
                            for seg in trans["segments"]:
                                start = seg.get("start", 0)
                                end = seg.get("end", 0)
                                text = seg.get("text", "")
                                speaker = seg.get("speaker", "Unknown")
                                
                                print(f"[{start:.1f}s - {end:.1f}s] {speaker}:")
                                print(f"  \"{text}\"\n")
                        
                        # Display performance metrics
                        if "npu_accelerated" in trans:
                            print("\n⚡ NPU Performance:")
                            print(f"  - NPU Accelerated: {trans.get('npu_accelerated', False)}")
                            print(f"  - Processing Time: {trans.get('processing_time', 0):.3f}s")
                            print(f"  - Speedup: {trans.get('speedup', 0):.1f}x")
                            print(f"  - RTF: {trans.get('rtf', 0):.4f}")
                            print(f"  - Device: {trans.get('device', 'Unknown')}")
                        
                        return
                    
                    # Show status
                    status = session_data.get("status", "unknown")
                    print(f"   Status: {status} ({i+1}/{max_wait}s)...", end='\r')
            
            await asyncio.sleep(1)
        
        print("\n⚠️ Transcription timeout - check backend logs")

if __name__ == "__main__":
    print("🚀 Meeting-Ops Recording & Transcription Test")
    print("Make sure your podcast is playing on the speakers!")
    print("-" * 50)
    
    try:
        asyncio.run(test_recording_and_transcription())
        print("\n✅ Test complete!")
    except KeyboardInterrupt:
        print("\n⚠️ Test interrupted")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()