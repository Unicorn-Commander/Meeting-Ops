#!/usr/bin/env python3
"""
Check available audio devices and their capabilities
"""

try:
    import sounddevice as sd
    print("=== Sounddevice Audio Devices ===\n")
    devices = sd.query_devices()
    for i, device in enumerate(devices):
        print(f"Device {i}: {device['name']}")
        print(f"  Channels: {device['max_input_channels']} input, {device['max_output_channels']} output")
        print(f"  Default sample rate: {device['default_samplerate']} Hz")
        print(f"  Host API: {sd.query_hostapis(device['hostapi'])['name']}")
        
        # Check if this is a USB device by looking for specific patterns
        if 'USB' in device['name'] or device['max_input_channels'] > 0:
            print(f"  [Potential recording device]")
        print()
        
    # Try to find the USB device specifically
    print("\n=== Looking for USB Audio Device ===")
    sd._terminate()
    sd._initialize()
    devices = sd.query_devices()
    print(f"Total devices found: {len(devices)}")
    
except Exception as e:
    print(f"Sounddevice error: {e}")
    print()

try:
    import pyaudio
    print("\n=== PyAudio Devices ===\n")
    p = pyaudio.PyAudio()
    
    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)
        if info['maxInputChannels'] > 0:
            print(f"Device {i}: {info['name']}")
            print(f"  Input channels: {info['maxInputChannels']}")
            print(f"  Default sample rate: {info['defaultSampleRate']} Hz")
            print(f"  Host API: {p.get_host_api_info_by_index(info['hostApi'])['name']}")
            
            # Check supported sample rates
            standard_rates = [8000, 16000, 22050, 44100, 48000]
            supported = []
            for rate in standard_rates:
                try:
                    if p.is_format_supported(rate,
                                           input_device=i,
                                           input_channels=1,
                                           input_format=pyaudio.paInt16):
                        supported.append(rate)
                except:
                    pass
            print(f"  Supported sample rates: {supported}")
            print()
    
    p.terminate()
except Exception as e:
    print(f"PyAudio error: {e}")

# Also check with system commands
print("\n=== System Audio Info ===")
import subprocess

try:
    result = subprocess.run(['cat', '/proc/asound/cards'], capture_output=True, text=True)
    print("Sound cards:")
    print(result.stdout)
except:
    pass

try:
    result = subprocess.run(['cat', '/proc/asound/pcm'], capture_output=True, text=True)
    print("\nPCM devices:")
    print(result.stdout)
except:
    pass