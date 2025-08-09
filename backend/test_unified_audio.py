#!/usr/bin/env python3
"""
Test the unified audio capture system
"""

import asyncio
import time
import redis
import json
from services.audio_consumer import RecordingConsumer, TranscriptionConsumer, AudioLevelConsumer

async def test_unified_system():
    """Test the unified audio system"""
    
    print("🧪 Testing Unified Audio System")
    print("-" * 50)
    
    # Connect to Redis
    r = redis.from_url("redis://localhost:6379")
    
    # Check if unified capture is running
    status = r.get('audio:capture:status')
    if status:
        status_data = json.loads(status)
        print(f"✅ Audio capture is running")
        print(f"   Device: {status_data['device']}")
        print(f"   Sample rate: {status_data['sample_rate']}")
    else:
        print("❌ Audio capture not running. Start it with:")
        print("   python start_unified_audio.py")
        return
    
    print("\n📊 Monitoring audio levels for 5 seconds...")
    
    # Subscribe to audio levels
    pubsub = r.pubsub()
    pubsub.subscribe('audio:levels')
    
    start_time = time.time()
    message_count = 0
    
    while time.time() - start_time < 5:
        message = pubsub.get_message(timeout=1)
        if message and message['type'] == 'message':
            data = json.loads(message['data'])
            message_count += 1
            level_bar = '█' * int(data['audio_level'] * 50)
            print(f"\rLevel: {level_bar:<50} {data['audio_level']:.2%}", end='')
    
    print(f"\n\n✅ Received {message_count} audio level updates")
    
    # Test recording consumer
    print("\n🎤 Testing recording consumer...")
    recorder = RecordingConsumer("test-session-001")
    recorder.start_recording("/tmp/test_unified_recording.wav")
    print("   Recording for 3 seconds...")
    await asyncio.sleep(3)
    recorder.stop_recording()
    
    import os
    if os.path.exists("/tmp/test_unified_recording.wav"):
        size = os.path.getsize("/tmp/test_unified_recording.wav")
        print(f"✅ Recording saved: {size:,} bytes")
    else:
        print("❌ Recording failed")
    
    print("\n🎉 Test complete!")

if __name__ == "__main__":
    asyncio.run(test_unified_system())