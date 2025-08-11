#!/usr/bin/env python3
"""
Test improved transcription with better chunk handling and VAD settings
"""

import asyncio
import os
import time
import numpy as np
import soundfile as sf
from pathlib import Path

# Add backend to path
import sys
sys.path.append(str(Path(__file__).parent))

from stt_engine.whisperx_npu_engine_real import WhisperXNPUEngine

async def test_transcription_improvements():
    """Test the improved transcription settings"""
    
    print("=" * 60)
    print("🎯 Testing Improved Transcription Settings")
    print("=" * 60)
    
    # Find a recent recording to test with
    recordings_dir = Path("/home/ucadmin/Meeting-Ops/backend/recordings")
    
    # Get the most recent WAV file
    wav_files = list(recordings_dir.glob("*.wav"))
    if not wav_files:
        print("❌ No recordings found to test with")
        print("Please record something first using the GUI")
        return
    
    # Sort by modification time and get the most recent
    latest_recording = max(wav_files, key=lambda p: p.stat().st_mtime)
    print(f"📁 Testing with: {latest_recording.name}")
    print(f"   Size: {latest_recording.stat().st_size:,} bytes")
    
    # Load the audio
    audio_data, sr = sf.read(str(latest_recording))
    duration = len(audio_data) / sr
    print(f"   Duration: {duration:.1f} seconds")
    print(f"   Sample rate: {sr} Hz")
    
    # Test with different chunk sizes
    print("\n🔧 Testing with improved settings:")
    print("   - Chunk size: 30 seconds (was 10)")
    print("   - VAD threshold: 0.3 (was 0.5)")
    print("   - Min silence: 1000ms (was 500ms)")
    print("   - Speech padding: 800ms (was 400ms)")
    
    # Initialize transcriber
    transcriber = WhisperXNPUEngine(model_size="large-v3")
    
    # Process the whole file first to get baseline
    print("\n📝 Full file transcription:")
    print("-" * 40)
    
    start_time = time.time()
    result = transcriber.transcribe(str(latest_recording), diarize=True)
    processing_time = time.time() - start_time
    
    if result and result.get("segments"):
        total_words = 0
        speakers = set()
        
        for i, segment in enumerate(result["segments"]):
            text = segment.get("text", "").strip()
            speaker = segment.get("speaker", "SPEAKER_00")
            start = segment.get("start", 0)
            end = segment.get("end", 0)
            
            if text:
                words = len(text.split())
                total_words += words
                speakers.add(speaker)
                print(f"[{start:.1f}s - {end:.1f}s] {speaker}: {text}")
        
        print("-" * 40)
        print(f"\n📊 Statistics:")
        print(f"   Total segments: {len(result['segments'])}")
        print(f"   Total words: {total_words}")
        print(f"   Speakers detected: {len(speakers)} ({', '.join(sorted(speakers))})")
        print(f"   Processing time: {processing_time:.2f}s")
        print(f"   Speed: {duration/processing_time:.1f}x real-time")
    else:
        print("❌ No transcription returned")
    
    # Now test chunk processing to simulate live transcription
    print("\n\n🔄 Testing chunk-based processing (simulating live):")
    print("-" * 40)
    
    # Resample to 16kHz if needed
    if sr != 16000:
        import librosa
        print(f"   Resampling from {sr}Hz to 16000Hz...")
        audio_16k = librosa.resample(audio_data, orig_sr=sr, target_sr=16000)
    else:
        audio_16k = audio_data
    
    # Process in 30-second chunks with 5-second overlap
    chunk_duration = 30
    chunk_overlap = 5
    chunk_samples = chunk_duration * 16000
    overlap_samples = chunk_overlap * 16000
    
    all_segments = []
    position = 0
    chunk_num = 0
    
    while position < len(audio_16k):
        chunk_num += 1
        
        # Get chunk with overlap
        start_pos = max(0, position - overlap_samples) if position > 0 else position
        end_pos = min(position + chunk_samples, len(audio_16k))
        chunk = audio_16k[start_pos:end_pos]
        
        if len(chunk) < 16000 * 2:  # Skip chunks shorter than 2 seconds
            break
        
        print(f"\n   Chunk {chunk_num}: {len(chunk)/16000:.1f}s")
        
        # Transcribe chunk
        chunk_result = transcriber.transcribe(chunk, diarize=True)
        
        if chunk_result and chunk_result.get("segments"):
            for segment in chunk_result["segments"]:
                # Adjust timestamps based on position
                segment["start"] += position / 16000
                segment["end"] += position / 16000
                all_segments.append(segment)
                
                text = segment.get("text", "").strip()
                if text:
                    print(f"      {segment['speaker']}: {text[:80]}...")
        
        # Move forward (not including overlap)
        position += (chunk_samples - overlap_samples)
    
    print("-" * 40)
    print(f"\n📊 Chunk processing statistics:")
    print(f"   Total chunks: {chunk_num}")
    print(f"   Total segments: {len(all_segments)}")
    print(f"   Unique speakers: {len(set(s['speaker'] for s in all_segments))}")
    
    print("\n✅ Test complete!")
    print("\n💡 Recommendations:")
    print("   - If still missing dialogue, try increasing chunk_overlap to 10 seconds")
    print("   - If getting repeated text, check that overlap handling is working")
    print("   - Monitor CPU usage during recording - resampling should be < 1%")

if __name__ == "__main__":
    asyncio.run(test_transcription_improvements())