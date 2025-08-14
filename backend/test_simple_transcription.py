#!/usr/bin/env python3
"""
Simple test to verify transcription is working
"""
import sys
import os
sys.path.append('/home/ucadmin/Meeting-Ops/backend')

import asyncio
from services.whisperx_py313 import WhisperXTranscriber

async def test_transcription():
    """Test basic transcription"""
    
    # Find a recording file
    recordings_dir = "/home/ucadmin/Meeting-Ops/backend/recordings"
    wav_files = [f for f in os.listdir(recordings_dir) if f.endswith('.wav')]
    
    if not wav_files:
        print("No WAV files found to test")
        return
        
    # Use the most recent one
    wav_files.sort()
    test_file = os.path.join(recordings_dir, wav_files[-1])
    
    print(f"Testing transcription on: {test_file}")
    print(f"File size: {os.path.getsize(test_file) / 1024:.1f} KB")
    
    # Initialize transcriber
    print("Initializing WhisperX with base model...")
    transcriber = WhisperXTranscriber(
        model_size="base",
        device="cpu",
        compute_type="int8",
        diarize=False
    )
    
    print("Transcribing...")
    result = transcriber.transcribe(test_file, word_timestamps=False)
    
    if result and result.get("segments"):
        print(f"\nFound {len(result['segments'])} segments:")
        for i, seg in enumerate(result["segments"][:5]):  # First 5 segments
            text = seg.get("text", "").strip()
            print(f"  [{i+1}] {text}")
    else:
        print("No transcription results")
    
    return result

if __name__ == "__main__":
    result = asyncio.run(test_transcription())
    if result:
        print(f"\nTranscription successful!")
    else:
        print("\nTranscription failed")