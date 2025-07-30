#!/usr/bin/env python3
"""
Test recording with USB microphone at correct sample rate
"""

import pyaudio
import wave
import numpy as np
import time

# USB mic settings based on /proc/asound info
SAMPLE_RATE = 48000  # USB mic supports 48000 or 44100
CHANNELS = 1
FORMAT = pyaudio.paInt16
CHUNK = 1024
RECORD_SECONDS = 5

def test_recording():
    """Test recording from USB microphone"""
    p = pyaudio.PyAudio()
    
    # List all devices to find USB
    print("Looking for USB microphone...")
    usb_device_index = None
    
    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)
        print(f"Device {i}: {info['name']}")
        if 'USB' in info['name'] and info['maxInputChannels'] > 0:
            usb_device_index = i
            print(f"  ✅ Found USB microphone at index {i}")
            print(f"  Channels: {info['maxInputChannels']}")
            print(f"  Sample rate: {info['defaultSampleRate']}")
            break
    
    if usb_device_index is None:
        # Try device 0 (from /proc/asound/cards)
        print("\nTrying device index 0 (USB from /proc/asound)...")
        usb_device_index = 0
    
    print(f"\nTesting recording for {RECORD_SECONDS} seconds at {SAMPLE_RATE}Hz...")
    
    try:
        # Open stream
        stream = p.open(format=FORMAT,
                       channels=CHANNELS,
                       rate=SAMPLE_RATE,
                       input=True,
                       input_device_index=usb_device_index,
                       frames_per_buffer=CHUNK)
        
        print("✅ Stream opened successfully!")
        print("🎤 Recording...")
        
        frames = []
        audio_levels = []
        
        for i in range(0, int(SAMPLE_RATE / CHUNK * RECORD_SECONDS)):
            data = stream.read(CHUNK, exception_on_overflow=False)
            frames.append(data)
            
            # Calculate audio level
            audio_data = np.frombuffer(data, dtype=np.int16)
            level = np.abs(audio_data).mean()
            audio_levels.append(level)
            
            # Show progress
            if i % 10 == 0:
                print(f"  Level: {'█' * int(level/1000)} {level:.0f}")
        
        print("✅ Recording complete!")
        
        # Stop and close stream
        stream.stop_stream()
        stream.close()
        p.terminate()
        
        # Save recording
        filename = f"test_recording_{int(time.time())}.wav"
        wf = wave.open(filename, 'wb')
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(p.get_sample_size(FORMAT))
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(b''.join(frames))
        wf.close()
        
        print(f"\n✅ Saved recording to: {filename}")
        print(f"   Average level: {np.mean(audio_levels):.1f}")
        print(f"   Max level: {np.max(audio_levels):.1f}")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Recording failed: {e}")
        return False

if __name__ == "__main__":
    test_recording()