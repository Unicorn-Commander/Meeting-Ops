#!/usr/bin/env python3
"""Test ONNX Whisper directly"""
import os
os.environ['LD_PRELOAD'] = '/lib/x86_64-linux-gnu/libstdc++.so.6'

import numpy as np
from stt_engine.whisper_npu_transcriber import ONNXWhisperNPUTranscriber

# Initialize
transcriber = ONNXWhisperNPUTranscriber()
if transcriber.initialize():
    print("✅ ONNX Whisper initialized")
    
    # Create test audio (10 seconds of sine wave)
    sample_rate = 16000
    duration = 10.0
    t = np.linspace(0, duration, int(sample_rate * duration))
    audio = np.sin(2 * np.pi * 440 * t).astype(np.float32) * 0.5  # 440Hz tone
    
    print(f"🎵 Test audio: {len(audio)} samples ({duration}s)")
    
    # Transcribe
    result = transcriber.transcribe_chunk(audio)
    print(f"📝 Result: {result}")
else:
    print("❌ Failed to initialize")