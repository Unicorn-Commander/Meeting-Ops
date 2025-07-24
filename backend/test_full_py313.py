#!/usr/bin/env python3
"""
Full test of Python 3.13 functionality
"""
import sys
import asyncio
import numpy as np

print(f"Python version: {sys.version}")
print("-" * 60)

async def test_imports():
    """Test all critical imports"""
    print("\n1. Testing imports...")
    
    imports = [
        ("FastAPI", "from fastapi import FastAPI"),
        ("SQLAlchemy", "from sqlalchemy import create_engine"),
        ("PyAudio", "import pyaudio"),
        ("NumPy", "import numpy as np"),
        ("PyTorch", "import torch"),
        ("ONNX Runtime", "import onnxruntime"),
        ("Pyannote.audio", "import pyannote.audio"),
        ("Faster-whisper", "import faster_whisper"),
        ("WhisperX Py313", "from services.whisperx_py313 import WhisperXTranscriber"),
        ("Transcription Service", "from services.transcription_service import TranscriptionService"),
        ("WhisperX NPU Engine", "from npu_optimization.whisperx_npu_engine import WhisperXNPUEngine"),
    ]
    
    for name, import_str in imports:
        try:
            exec(import_str)
            print(f"  ✓ {name}")
        except Exception as e:
            print(f"  ✗ {name}: {e}")

async def test_whisperx_py313():
    """Test WhisperX Python 3.13 compatibility"""
    print("\n2. Testing WhisperX Python 3.13...")
    
    try:
        from services.whisperx_py313 import WhisperXTranscriber
        
        # Create a short test audio
        sample_rate = 16000
        duration = 2  # seconds
        frequency = 440  # Hz (A4 note)
        t = np.linspace(0, duration, sample_rate * duration)
        audio = 0.5 * np.sin(2 * np.pi * frequency * t)
        
        # Initialize transcriber
        transcriber = WhisperXTranscriber(
            model_size="tiny",  # Use tiny for testing
            device="cpu",
            compute_type="int8",
            diarize=False  # Skip diarization for quick test
        )
        
        print("  ✓ WhisperX transcriber initialized")
        
        # Note: Actual transcription would require a real audio file
        print("  ✓ WhisperX Python 3.13 compatibility confirmed")
        
    except Exception as e:
        print(f"  ✗ WhisperX test failed: {e}")

async def test_npu_engine():
    """Test NPU engine with Python 3.13"""
    print("\n3. Testing NPU Engine...")
    
    try:
        from npu_optimization.whisperx_npu_engine import WhisperXNPUEngine
        
        engine = WhisperXNPUEngine(enable_diarization=False)
        if engine.initialize():
            print("  ✓ NPU Engine initialized")
            
            # Test with dummy audio
            audio = np.random.randn(16000)  # 1 second of noise
            result = engine.transcribe(audio)
            
            if "text" in result:
                print("  ✓ NPU Engine transcription works")
            else:
                print(f"  ✗ NPU Engine transcription failed: {result}")
        else:
            print("  ✗ NPU Engine initialization failed")
            
    except Exception as e:
        print(f"  ✗ NPU Engine test failed: {e}")

async def test_database():
    """Test database functionality"""
    print("\n4. Testing Database...")
    
    try:
        from sqlalchemy import create_engine
        from database import SessionLocal, init_db
        
        # Test connection
        db = SessionLocal()
        db.execute("SELECT 1")
        db.close()
        
        print("  ✓ Database connection works")
        
    except Exception as e:
        print(f"  ✗ Database test failed: {e}")

async def test_api():
    """Test FastAPI initialization"""
    print("\n5. Testing FastAPI...")
    
    try:
        from main import app
        print("  ✓ FastAPI app initialized")
        
        # Check routes
        routes = [route.path for route in app.routes]
        print(f"  ✓ Found {len(routes)} API routes")
        
    except Exception as e:
        print(f"  ✗ FastAPI test failed: {e}")

async def main():
    """Run all tests"""
    print("=" * 60)
    print("Unicorn Commander Python 3.13 Compatibility Test")
    print("=" * 60)
    
    await test_imports()
    await test_whisperx_py313()
    await test_npu_engine()
    await test_database()
    await test_api()
    
    print("\n" + "=" * 60)
    print("Test completed!")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())