#!/usr/bin/env python3
"""
Direct test of transcription service to see if it processes audio chunks
"""
import sys
import os
sys.path.append('/home/ucadmin/Development/Unicorn-Commander-Meeting-Ops/backend')

import numpy as np
from services.transcription_service import transcription_service

# Create fake audio data (1 second of 16kHz audio)
sample_rate = 16000
duration = 1.0
t = np.linspace(0, duration, int(sample_rate * duration))
# Generate a 440Hz sine wave (A note)
audio_data = (np.sin(2 * np.pi * 440 * t) * 0.3 * 32767).astype(np.int16)
audio_bytes = audio_data.tobytes()

print(f"Testing transcription service...")
print(f"Service ready: {transcription_service.is_ready}")
print(f"Current model: {transcription_service.current_model_id}")
print(f"Audio data size: {len(audio_bytes)} bytes")

# Test transcription
try:
    result = transcription_service.process_audio_chunk(audio_bytes, "test_session")
    if result:
        print(f"✅ Transcription result: {result.to_dict()}")
    else:
        print("❌ No transcription result returned")
except Exception as e:
    print(f"❌ Error during transcription: {e}")
    import traceback
    traceback.print_exc()