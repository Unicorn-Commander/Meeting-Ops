#!/usr/bin/env python3
"""Simple test of transcription service"""
import os
os.environ['LD_PRELOAD'] = '/lib/x86_64-linux-gnu/libstdc++.so.6'

import numpy as np
from services.transcription_service import transcription_service

print("🧪 Testing Transcription Service")
print("=" * 50)

# Check service status
print("\n1️⃣ Service Status:")
print(f"   Ready: {transcription_service.is_ready}")
print(f"   Current Model: {transcription_service.current_model_id}")

if transcription_service.current_engine:
    print(f"   Engine Type: {type(transcription_service.current_engine).__name__}")
    print(f"   Engine Module: {type(transcription_service.current_engine).__module__}")
else:
    print("   Engine: None")

# Get model info
info = transcription_service.get_current_model_info()
print(f"\n2️⃣ Model Info:")
for key, value in info.items():
    print(f"   {key}: {value}")

# Create test audio (1 second of silence)
print("\n3️⃣ Testing transcription with silent audio...")
test_audio = np.zeros(16000, dtype=np.float32)  # 1 second at 16kHz

try:
    result = transcription_service.process_audio_chunk(test_audio.tobytes())
    if result:
        print(f"   ✅ Transcription successful!")
        print(f"   Text: '{result.text}'")
        print(f"   Confidence: {result.confidence}")
    else:
        print("   ❌ No transcription result")
except Exception as e:
    print(f"   ❌ Transcription error: {e}")

# Test with sine wave
print("\n4️⃣ Testing with sine wave audio...")
t = np.linspace(0, 1, 16000)
sine_audio = (np.sin(2 * np.pi * 440 * t) * 0.5).astype(np.float32)

try:
    result = transcription_service.process_audio_chunk(sine_audio.tobytes())
    if result:
        print(f"   ✅ Transcription successful!")
        print(f"   Text: '{result.text}'")
    else:
        print("   ❌ No transcription result")
except Exception as e:
    print(f"   ❌ Transcription error: {e}")

print("\n" + "=" * 50)
print("Test complete!")