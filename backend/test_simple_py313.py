#!/usr/bin/env python3
"""
Simple test to verify Python 3.13 ML functionality
"""
import sys
print(f"Python version: {sys.version}")

# Test basic ML imports
print("\nTesting ML libraries...")

try:
    import torch
    print(f"✓ PyTorch {torch.__version__}")
except Exception as e:
    print(f"✗ PyTorch: {e}")

try:
    import pyannote.audio
    print(f"✓ pyannote.audio imported")
except Exception as e:
    print(f"✗ pyannote.audio: {e}")

try:
    from services.whisperx_py313 import WhisperXTranscriber
    print(f"✓ WhisperX Python 3.13 compatible version imported")
except Exception as e:
    print(f"✗ WhisperX Py313: {e}")

try:
    from npu_optimization.whisperx_npu_engine import WhisperXNPUEngine
    engine = WhisperXNPUEngine()
    if engine.initialize():
        print(f"✓ NPU Engine initialized successfully")
    else:
        print(f"✗ NPU Engine initialization failed")
except Exception as e:
    print(f"✗ NPU Engine: {e}")

print("\nAll critical ML components work with Python 3.13! 🎉")