#!/usr/bin/env python3
import os
os.environ['LD_PRELOAD'] = '/lib/x86_64-linux-gnu/libstdc++.so.6'

import sounddevice as sd
import numpy as np
import time

print("🎤 Testing sounddevice directly...")
print(f"✅ Sounddevice version: {sd.__version__}")

# List devices
devices = sd.query_devices()
print(f"\n📋 Found {len(devices) if hasattr(devices, '__len__') else 1} audio devices:")

if hasattr(devices, '__len__'):
    for i, dev in enumerate(devices):
        if dev['max_input_channels'] > 0:
            print(f"  [{i}] {dev['name']} - {dev['max_input_channels']} input channels")
else:
    if devices['max_input_channels'] > 0:
        print(f"  [0] {devices['name']} - {devices['max_input_channels']} input channels")

# Test recording
print("\n🎙️ Testing 3-second recording...")
duration = 3
sample_rate = 16000
recording = sd.rec(int(duration * sample_rate), samplerate=sample_rate, channels=1)
sd.wait()
print(f"✅ Recorded {len(recording)} samples")
print(f"📊 Audio level: min={recording.min():.3f}, max={recording.max():.3f}, mean={np.abs(recording).mean():.3f}")

# Test audio callback
print("\n🔄 Testing audio callback for 3 seconds...")
callback_count = 0

def audio_callback(indata, frames, time, status):
    global callback_count
    callback_count += 1
    if callback_count % 10 == 0:
        print(f"  📝 Callback #{callback_count}: {frames} frames, level={np.abs(indata).mean():.4f}")

stream = sd.InputStream(callback=audio_callback, channels=1, samplerate=sample_rate)
stream.start()
time.sleep(3)
stream.stop()
stream.close()

print(f"\n✅ Total callbacks: {callback_count}")
print("🎉 Sounddevice is working properly!")