#!/usr/bin/env python3
"""
Test Whisper large-v3 model with diarization
Records 30 seconds for better speaker detection
"""

import asyncio
import aiohttp
import json
import time
import sys

API_BASE = "http://localhost:9050"

async def test_large_whisper_diarization():
    """Test large Whisper model with speaker diarization"""
    
    print("🎙️ Whisper Large-v3 + Diarization Test")
    print("=" * 60)
    print("This will:")
    print("1. Record 30 seconds from USB mic")
    print("2. Transcribe with Whisper large-v3 model")
    print("3. Apply speaker diarization")
    print("4. Show detailed segments with speakers")
    print("=" * 60)
    print("\n▶️ Make sure your podcast has multiple speakers talking!\n")
    
    async with aiohttp.ClientSession() as session:
        # 1. Create recording session
        print("📝 Creating recording session...")
        async with session.post(
            f"{API_BASE}/api/simple/recording-sessions",
            json={
                "name": "Whisper Large-v3 Diarization Test",
                "description": "Testing advanced transcription with speaker detection"
            }
        ) as resp:
            if resp.status != 200:
                print(f"❌ Failed to create session: {resp.status}")
                return
            
            session_data = await resp.json()
            session_id = session_data["id"]
            print(f"✅ Session created: {session_id}")
        
        # 2. Start recording
        print("\n🔴 Starting 30-second recording...")
        async with session.post(
            f"{API_BASE}/api/simple/recording-sessions/{session_id}/start"
        ) as resp:
            if resp.status != 200:
                print(f"❌ Failed to start recording: {resp.status}")
                return
            
            result = await resp.json()
            print(f"✅ Recording started")
        
        # 3. Wait for recording
        print("\n⏳ Recording in progress (30 seconds)...")
        for i in range(30):
            remaining = 30 - i
            if remaining % 5 == 0:
                print(f"   {remaining} seconds remaining...")
            await asyncio.sleep(1)
        print("")
        
        # 4. Stop recording
        print("⏹️ Stopping recording...")
        async with session.post(
            f"{API_BASE}/api/simple/recording-sessions/{session_id}/stop"
        ) as resp:
            if resp.status != 200:
                print(f"❌ Failed to stop recording: {resp.status}")
                return
            
            result = await resp.json()
            print(f"✅ Recording stopped")
            if "audio_file" in result:
                print(f"📁 Audio file: {result['audio_file']}")
        
        # 5. Wait for transcription
        print("\n🔄 Processing with Whisper large-v3 (this may take a moment)...")
        max_wait = 60
        for i in range(max_wait):
            async with session.get(
                f"{API_BASE}/api/simple/recording-sessions/{session_id}"
            ) as resp:
                if resp.status == 200:
                    session_data = await resp.json()
                    
                    if session_data.get("transcription"):
                        print("\n✅ Transcription complete!")
                        print("\n" + "=" * 60)
                        print("📝 TRANSCRIPTION RESULTS WITH DIARIZATION:")
                        print("=" * 60)
                        
                        trans = session_data["transcription"]
                        
                        # Display segments with speakers
                        if "segments" in trans and trans["segments"]:
                            segments = trans["segments"]
                            print(f"\n📊 Found {len(segments)} segments")
                            
                            # Count speakers
                            speakers = set(seg.get("speaker", "Unknown") for seg in segments)
                            print(f"👥 Detected {len(speakers)} speaker(s): {', '.join(sorted(speakers))}\n")
                            
                            # Display each segment
                            for seg in segments:
                                start = seg.get("start", 0)
                                end = seg.get("end", 0)
                                text = seg.get("text", "")
                                speaker = seg.get("speaker", "Unknown")
                                conf = seg.get("confidence", 0) * 100
                                
                                print(f"[{start:6.2f}s - {end:6.2f}s] {speaker} (conf: {conf:.0f}%):")
                                print(f"  \"{text}\"")
                                
                                # Show word-level timestamps if available
                                if seg.get("words"):
                                    print(f"  Words: {len(seg['words'])} with timestamps")
                                print()
                        else:
                            print("No segments found")
                        
                        # Display performance metrics
                        if "npu_accelerated" in trans:
                            print("\n⚡ Performance Metrics:")
                            print(f"  - Model: Whisper large-v3 with INT8 quantization")
                            print(f"  - NPU Accelerated: {trans.get('npu_accelerated', False)}")
                            print(f"  - Processing Time: {trans.get('processing_time', 0):.2f}s")
                            print(f"  - Audio Duration: {trans.get('duration', 0):.1f}s")
                            print(f"  - Speedup: {trans.get('speedup', 0):.1f}x faster than real-time")
                            print(f"  - RTF: {trans.get('rtf', 0):.3f}")
                            print(f"  - Device: {trans.get('device', 'Unknown')}")
                        
                        return
                    
                    status = session_data.get("status", "unknown")
                    print(f"   Status: {status} ({i+1}/{max_wait}s)...", end='\r')
            
            await asyncio.sleep(1)
        
        print("\n⚠️ Transcription timeout - check backend logs")

if __name__ == "__main__":
    print("🚀 Whisper Large-v3 with Speaker Diarization Test")
    print("Make sure your podcast has multiple people speaking!")
    print("-" * 60)
    
    try:
        asyncio.run(test_large_whisper_diarization())
        print("\n✅ Test complete!")
    except KeyboardInterrupt:
        print("\n⚠️ Test interrupted")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()