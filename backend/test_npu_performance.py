#!/usr/bin/env python3
"""
Test NPU Performance with Sample Audio
"""

import time
import numpy as np
from pathlib import Path
from stt_engine.npu_accelerator import NPUAccelerator

def test_npu_with_sample_audio():
    """Test NPU performance with generated audio"""
    print("🧪 NPU Performance Test")
    print("=" * 50)
    
    try:
        # Initialize NPU
        print("🚀 Initializing NPU...")
        npu = NPUAccelerator()
        
        if not npu.is_available():
            print("❌ NPU not available")
            return
        
        print("✅ NPU initialized successfully")
        
        # Generate test audio (30 seconds at 16kHz)
        duration = 30  # seconds
        sample_rate = 16000
        print(f"\n📊 Generating {duration} seconds of test audio...")
        
        # Create realistic speech-like audio (not just noise)
        t = np.linspace(0, duration, duration * sample_rate)
        # Mix of frequencies common in speech
        audio = (
            0.3 * np.sin(2 * np.pi * 200 * t) +  # Low frequency
            0.2 * np.sin(2 * np.pi * 800 * t) +  # Mid frequency
            0.1 * np.sin(2 * np.pi * 2000 * t) + # High frequency
            0.1 * np.random.randn(len(t))        # Some noise
        )
        audio = audio.astype(np.float32)
        
        print(f"📏 Audio shape: {audio.shape}")
        print(f"📏 Audio duration: {len(audio) / sample_rate:.2f} seconds")
        
        # Warm up NPU
        print("\n🔥 Warming up NPU...")
        _ = npu.execute_kernel("whisper_transcribe", {"audio": audio[:16000]})  # 1 second
        
        # Test different audio lengths
        test_durations = [1, 5, 10, 30]  # seconds
        
        print("\n📊 Performance Results:")
        print("-" * 60)
        print(f"{'Duration':<10} {'NPU Time':<12} {'Real-time Factor':<20} {'Throughput'}")
        print("-" * 60)
        
        for test_duration in test_durations:
            # Extract test audio chunk
            test_samples = test_duration * sample_rate
            test_audio = audio[:test_samples]
            
            # Measure NPU processing time
            start_time = time.time()
            result = npu.execute_kernel("whisper_transcribe", {"audio": test_audio})
            npu_time = time.time() - start_time
            
            # Calculate metrics
            rtf = test_duration / npu_time if npu_time > 0 else 0
            throughput = test_duration / npu_time if npu_time > 0 else 0
            
            print(f"{test_duration:>6}s    {npu_time:>8.3f}s    {rtf:>15.1f}x    {throughput:>8.1f} sec/sec")
            
            # Show transcription preview (if available)
            if 'transcription' in result and result['transcription']:
                preview = result['transcription'][:50] + "..." if len(result['transcription']) > 50 else result['transcription']
                print(f"   └─ Text: {preview}")
        
        print("-" * 60)
        
        # Benchmark specific operations
        print("\n🔬 Detailed NPU Benchmark:")
        benchmark_results = npu.benchmark()
        for operation, time_ms in benchmark_results.items():
            print(f"   {operation}: {time_ms:.2f}ms")
        
        # Show hardware info
        if hasattr(npu, 'npu_runtime') and npu.npu_runtime:
            device_info = npu.npu_runtime.get_device_info()
            print("\n🖥️ NPU Hardware Info:")
            for key, value in device_info.items():
                print(f"   {key}: {value}")
        
    except Exception as e:
        print(f"\n❌ Error during test: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_npu_with_sample_audio()