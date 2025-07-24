#!/usr/bin/env python3
"""
Test Python 3.13 compatibility with ML libraries
"""
import sys
import os

print(f"Python version: {sys.version}")

# Test imports
print("\nTesting imports...")

try:
    import numpy as np
    print("✓ NumPy imported successfully")
except Exception as e:
    print(f"✗ NumPy import failed: {e}")

try:
    import torch
    print(f"✓ PyTorch imported successfully (version: {torch.__version__})")
except Exception as e:
    print(f"✗ PyTorch import failed: {e}")

try:
    import torchaudio
    print(f"✓ Torchaudio imported successfully (version: {torchaudio.__version__})")
except Exception as e:
    print(f"✗ Torchaudio import failed: {e}")

try:
    import onnxruntime as ort
    print(f"✓ ONNX Runtime imported successfully (version: {ort.__version__})")
    print(f"  Available providers: {ort.get_available_providers()}")
except Exception as e:
    print(f"✗ ONNX Runtime import failed: {e}")

try:
    import pyannote.audio
    print("✓ pyannote.audio imported successfully")
except Exception as e:
    print(f"✗ pyannote.audio import failed: {e}")

try:
    import faster_whisper
    print("✓ faster-whisper imported successfully")
except Exception as e:
    print(f"✗ faster-whisper import failed: {e}")

try:
    from services.whisperx_py313 import load_model
    print("✓ whisperx_py313 imported successfully")
except Exception as e:
    print(f"✗ whisperx_py313 import failed: {e}")

# Test NPU detection
print("\nChecking NPU support...")
try:
    providers = ort.get_available_providers()
    if 'DmlExecutionProvider' in providers:
        print("✓ DirectML (NPU) provider available!")
    else:
        print("✗ DirectML (NPU) provider not available")
        print(f"  Available providers: {providers}")
except Exception as e:
    print(f"✗ Error checking providers: {e}")

print("\nAll tests completed!")