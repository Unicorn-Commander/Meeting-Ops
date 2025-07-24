#!/usr/bin/env python3
import os
os.environ['LD_PRELOAD'] = '/lib/x86_64-linux-gnu/libstdc++.so.6'

import sys
sys.path.append('.')

# Check what's happening with imports
print("Testing audio service initialization...")

try:
    import sounddevice as sd
    print(f"✅ sounddevice imported successfully: {sd.__version__}")
except Exception as e:
    print(f"❌ sounddevice import failed: {e}")

from services.audio_input_service import audio_input_service, SOUNDDEVICE_AVAILABLE, PYAUDIO_AVAILABLE

print(f"\nModule-level flags:")
print(f"  SOUNDDEVICE_AVAILABLE: {SOUNDDEVICE_AVAILABLE}")
print(f"  PYAUDIO_AVAILABLE: {PYAUDIO_AVAILABLE}")

print(f"\naudio_input_service instance:")
print(f"  use_sounddevice: {audio_input_service.use_sounddevice}")
print(f"  sample_rate: {audio_input_service.sample_rate}")
print(f"  channels: {audio_input_service.channels}")

# Initialize it
print(f"\nInitializing audio service...")
result = audio_input_service.initialize("default", 16000, 1)
print(f"  Initialize result: {result}")
print(f"  use_sounddevice after init: {audio_input_service.use_sounddevice}")

# Try to start recording
print(f"\nStarting recording...")
result = audio_input_service.start_recording("test_session")
print(f"  Start recording result: {result}")
print(f"  is_recording: {audio_input_service.is_recording}")
print(f"  has stream: {audio_input_service.sd_stream is not None or audio_input_service.stream is not None}")

# Stop
audio_input_service.stop_recording()
print("✅ Test complete")