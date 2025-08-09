#!/usr/bin/env python3
"""
Test the fixed recording system
"""

import asyncio
import time
from services.working_audio_service import audio_service

async def test_recording():
    print("🧪 Testing Fixed Recording System")
    print("-" * 50)
    
    # Test 1: Start recording
    print("\n📍 Test 1: Start Recording")
    session_id = "test-session-001"
    success, result = audio_service.start_recording(session_id)
    
    if success:
        print(f"✅ Recording started successfully")
        print(f"   File: {result}")
    else:
        print(f"❌ Failed to start: {result}")
        return
    
    # Record for 5 seconds
    print("\n🎤 Recording for 5 seconds...")
    for i in range(5):
        print(f"   {i+1}...")
        await asyncio.sleep(1)
    
    # Test 2: Stop recording
    print("\n📍 Test 2: Stop Recording")
    success, result = audio_service.stop_recording(session_id)
    
    if success:
        print(f"✅ Recording stopped successfully")
        print(f"   File: {result}")
        
        import os
        if os.path.exists(result):
            size = os.path.getsize(result)
            print(f"   Size: {size:,} bytes")
            print(f"   Duration: ~{size / (44100 * 2):.1f} seconds")
    else:
        print(f"❌ Failed to stop: {result}")
    
    print("\n🎉 Test complete!")

if __name__ == "__main__":
    asyncio.run(test_recording())