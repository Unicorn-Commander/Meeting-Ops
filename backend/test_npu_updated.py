#!/usr/bin/env python3
"""
Test the updated NPU runtime locally
"""

import sys
sys.path.insert(0, '.')

from npu_runtime import SimplifiedNPURuntime

def test_npu_transcription():
    """Test NPU transcription with demo text"""
    print("Testing Updated NPU Runtime")
    print("=" * 50)
    
    npu = SimplifiedNPURuntime()
    
    if npu.open_device():
        print("✅ NPU device opened successfully")
        
        if npu.load_model("whisper-base"):
            print("✅ Model loaded successfully")
            
            # Test with different audio durations
            test_files = [
                ("/tmp/recordings/session_1753336650/recording.wav", "14 second audio"),
                ("/tmp/recordings/session_1753333393/recording.wav", "14 second audio"),
            ]
            
            for audio_file, description in test_files:
                print(f"\n📝 Testing {description}: {audio_file}")
                result = npu.transcribe(audio_file)
                
                if "error" not in result:
                    print(f"✅ Transcription successful!")
                    print(f"   Text: {result['text'][:200]}...")
                    print(f"   Duration: {result.get('audio_duration', 0):.1f}s")
                    print(f"   Processing: {result.get('processing_time', 0):.3f}s")
                    print(f"   Speedup: {result.get('speedup', 0):.1f}x")
                else:
                    print(f"❌ Error: {result['error']}")
                    
            # Test with simulated short audio
            print(f"\n📝 Testing short audio simulation")
            import numpy as np
            short_audio = np.zeros(16000 * 2, dtype=np.float32)  # 2 seconds
            result = npu.transcribe(short_audio)
            print(f"   Text: {result.get('text', 'N/A')}")
            
        else:
            print("❌ Failed to load model")
    else:
        print("❌ Failed to open NPU device")
        
    npu.close_device()
    print("\n✅ Test complete!")

if __name__ == "__main__":
    test_npu_transcription()