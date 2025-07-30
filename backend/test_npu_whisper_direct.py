#!/usr/bin/env python3
"""
Test NPU Whisper transcriber directly
"""

from npu_whisper_transcriber import NPUWhisperTranscriber
import time

def test_npu_whisper():
    """Test NPU Whisper transcription"""
    print("Testing NPU Whisper Transcriber")
    print("=" * 50)
    
    # Initialize transcriber
    transcriber = NPUWhisperTranscriber()
    
    print(f"Model loaded: {transcriber.model_loaded}")
    print(f"NPU available: {transcriber.npu_available}")
    print(f"Using NPU: {transcriber.using_npu}")
    
    if not transcriber.model_loaded:
        print("❌ Failed to load model")
        return
    
    # Test with real audio file
    audio_files = [
        "/tmp/recordings/session_1753336650/recording.wav",
        "/tmp/recordings/session_1753333393/recording.wav"
    ]
    
    for audio_file in audio_files:
        print(f"\n📝 Transcribing: {audio_file}")
        
        start_time = time.time()
        result = transcriber.transcribe(audio_file)
        elapsed = time.time() - start_time
        
        if "error" not in result:
            print(f"✅ Success!")
            print(f"   Text: {result.get('text', 'N/A')}")
            print(f"   Processing time: {elapsed:.2f}s")
            print(f"   Audio duration: {result.get('duration', 0):.1f}s")
            print(f"   RTF: {result.get('rtf', 0):.2f}")
            print(f"   Speedup: {result.get('speedup', 0):.1f}x")
            print(f"   NPU accelerated: {result.get('npu_accelerated', False)}")
            
            # Performance breakdown
            if 'performance' in result:
                perf = result['performance']
                print(f"   Encoder time: {perf.get('encoder_time', 0):.3f}s")
                print(f"   Decoder time: {perf.get('decoder_time', 0):.3f}s")
                print(f"   Tokens generated: {perf.get('tokens_generated', 0)}")
        else:
            print(f"❌ Error: {result.get('error', 'Unknown error')}")

if __name__ == "__main__":
    test_npu_whisper()