#!/usr/bin/env python3
"""
Test USB microphone using ALSA hw: syntax
"""

import sounddevice as sd
import numpy as np
import time

# List all devices first
print("=== Available Audio Devices ===")
print(sd.query_devices())

print("\n=== Testing USB Microphone ===")

# Try different device specifications
device_specs = [
    'hw:0,0',  # USB device from /proc/asound/cards
    'USB',
    'default',
    0,  # Device index
]

for device in device_specs:
    print(f"\nTrying device: {device}")
    try:
        # Query device info
        if isinstance(device, int):
            info = sd.query_devices(device)
        else:
            try:
                info = sd.query_devices(device)
            except:
                info = None
        
        if info:
            print(f"  Found: {info['name']}")
            print(f"  Sample rate: {info['default_samplerate']}")
            print(f"  Input channels: {info['max_input_channels']}")
        
        # Try recording at different sample rates
        for sample_rate in [48000, 44100, 16000]:
            print(f"\n  Testing at {sample_rate} Hz...")
            try:
                duration = 2  # seconds
                recording = sd.rec(
                    int(duration * sample_rate),
                    samplerate=sample_rate,
                    channels=1,
                    device=device,
                    dtype='int16'
                )
                
                print("    Recording for 2 seconds...")
                sd.wait()
                
                # Check if we got data
                max_val = np.abs(recording).max()
                mean_val = np.abs(recording).mean()
                
                print(f"    ✅ Success! Max level: {max_val}, Mean level: {mean_val:.1f}")
                
                if max_val > 100:  # If we got actual audio
                    print(f"    🎤 Audio detected!")
                    
                # Save the working configuration
                print(f"\n✅ WORKING CONFIGURATION:")
                print(f"   Device: {device}")
                print(f"   Sample rate: {sample_rate} Hz")
                print(f"   Channels: 1")
                break
                
            except Exception as e:
                print(f"    ❌ Failed: {e}")
                
    except Exception as e:
        print(f"  Error with device {device}: {e}")

print("\n❌ No working configuration found")

# Also try direct ALSA access
print("\n=== Trying direct ALSA device names ===")
import subprocess

try:
    # List ALSA devices
    result = subprocess.run(['arecord', '-L'], capture_output=True, text=True)
    print("Available ALSA capture devices:")
    print(result.stdout)
except:
    print("arecord command not available")