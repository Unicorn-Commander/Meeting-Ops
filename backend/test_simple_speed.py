#!/usr/bin/env python3
"""
Simple transcription speed test with current model
"""

import time
import requests
import os

# Test with the audio we recorded
TEST_AUDIO = "/home/ucadmin/Meeting-Ops/backend/recordings/recording_a80dd669-eb13-45d0-b3a7-b3b70bd3f0e0_20250809_211910.wav"

# Get file size
file_size = os.path.getsize(TEST_AUDIO)
# Estimate duration (44100 Hz, 16-bit mono)
AUDIO_DURATION = file_size / (44100 * 2)

print(f"🎵 Testing transcription speed")
print(f"📁 File: {TEST_AUDIO}")
print(f"📊 Size: {file_size:,} bytes")
print(f"⏱️  Duration: ~{AUDIO_DURATION:.1f} seconds")
print("-" * 50)

# Test 3 times for consistency
for test_num in range(1, 4):
    print(f"\n🧪 Test #{test_num}:")
    
    start_time = time.time()
    
    try:
        with open(TEST_AUDIO, 'rb') as f:
            response = requests.post(
                "http://localhost:9050/api/transcribe",
                files={'file': f},
                timeout=120
            )
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        if response.status_code == 200:
            result = response.json()
            text = result.get('text', '')
            
            # Performance metrics
            speedup = AUDIO_DURATION / processing_time if processing_time > 0 else 0
            rtf = processing_time / AUDIO_DURATION
            
            print(f"   ✅ Success!")
            print(f"   ⏱️  Processing time: {processing_time:.2f} seconds")
            print(f"   🚀 Speedup: {speedup:.1f}x faster than real-time")
            print(f"   📊 RTF: {rtf:.4f} (lower is better)")
            print(f"   📝 Transcribed: {len(text)} characters")
            if text:
                print(f"   💬 Preview: \"{text[:150]}...\"")
        else:
            print(f"   ❌ Failed: HTTP {response.status_code}")
            print(f"   Response: {response.text[:200]}")
    
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    time.sleep(2)

print("\n" + "="*60)
print("📊 SUMMARY")
print("="*60)
print(f"Audio: {AUDIO_DURATION:.1f} seconds")
print("Current model: whisper-base with NPU acceleration (if available)")
print("\nNOTE: The system is configured to use NPU acceleration")
print("when available. The actual model being used depends on")
print("what's loaded in the transcription service.")