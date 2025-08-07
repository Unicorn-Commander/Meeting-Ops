#!/usr/bin/env python3
"""
Test real audio recording and NPU transcription
"""

import subprocess
import numpy as np
import tempfile
import os
from services.fast_npu_transcriber import get_fast_npu_transcriber

def record_and_transcribe(duration=5):
    """Record from microphone and transcribe with NPU"""
    
    print(f"🎤 Recording {duration} seconds from USB microphone...")
    print("📣 Please speak clearly into the microphone!")
    
    # Create temporary file
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
        temp_path = temp_file.name
    
    try:
        # Record audio from USB mic
        cmd = [
            'arecord',
            '-D', 'hw:0,0',  # USB PnP Sound Device
            '-f', 'S16_LE',  # 16-bit signed little endian
            '-r', '44100',   # 44.1kHz sample rate
            '-c', '1',       # Mono
            '-d', str(duration),  # Duration in seconds
            temp_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"❌ Recording failed: {result.stderr}")
            return None
            
        print("✅ Recording completed!")
        
        # Load audio data using scipy or librosa (simpler than sox)
        try:
            import scipy.io.wavfile
            sample_rate, audio_data = scipy.io.wavfile.read(temp_path)
            # Convert to float32 and normalize
            if audio_data.dtype == np.int16:
                audio_data = audio_data.astype(np.float32) / 32768.0
            print(f"🔊 Audio loaded with scipy: {len(audio_data)} samples")
        except ImportError:
            print("⚠️ Scipy not available, trying basic numpy load...")
            # Read raw wav data (skip header)
            with open(temp_path, 'rb') as f:
                f.seek(44)  # Skip WAV header
                raw_data = f.read()
            audio_data = np.frombuffer(raw_data, dtype=np.int16).astype(np.float32) / 32768.0
            print(f"🔊 Audio loaded with numpy: {len(audio_data)} samples")
        
        print(f"📊 Duration: {len(audio_data)/44100:.2f}s, Max amplitude: {np.max(np.abs(audio_data)):.3f}")
        
        # Initialize NPU transcriber
        print("🧠 Initializing NPU transcriber...")
        transcriber = get_fast_npu_transcriber()
        
        if not transcriber.is_ready:
            print("❌ NPU transcriber not ready")
            return None
            
        print("✅ NPU transcriber ready!")
        print(f"📊 NPU Status: {transcriber.get_status()}")
        
        # Transcribe with NPU
        print("⚡ Transcribing with NPU (large-v3 + INT8)...")
        result = transcriber.transcribe(audio_data, sample_rate=44100)
        
        # Display results
        print("\n" + "="*50)
        print("🎯 NPU TRANSCRIPTION RESULTS")
        print("="*50)
        print(f"Text: {result.get('text', 'No speech detected')}")
        print(f"Processing time: {result.get('processing_time', 0):.3f}s")
        print(f"Real-time factor: {result.get('rtf', 0):.3f}x")
        print(f"NPU optimized: {result.get('npu_optimized', False)}")
        print(f"Model: {result.get('model', 'Unknown')}")
        
        if result.get('segments'):
            print(f"Segments: {len(result['segments'])}")
            for i, seg in enumerate(result['segments'][:3]):  # Show first 3 segments
                print(f"  {i+1}. [{seg.get('start', 0):.1f}s-{seg.get('end', 0):.1f}s]: {seg.get('text', '')}")
        
        return result
        
    finally:
        # Clean up
        if os.path.exists(temp_path):
            os.unlink(temp_path)

if __name__ == "__main__":
    print("🚀 Meeting-Ops NPU Real Audio Test")
    print("📻 Make sure your radio/podcast is playing for testing!")
    
    result = record_and_transcribe(duration=10)
    
    if result and result.get('text'):
        print("\n✅ SUCCESS: NPU transcription is working with real audio!")
        rtf = result.get('rtf', 1.0)
        if rtf < 0.1:
            print(f"⚡ EXCELLENT: {rtf:.3f}x real-time (very fast)")
        elif rtf < 0.5:
            print(f"✅ GOOD: {rtf:.3f}x real-time")
        else:
            print(f"⚠️ SLOW: {rtf:.3f}x real-time")
    else:
        print("\n❌ No transcription result - check microphone and audio input")