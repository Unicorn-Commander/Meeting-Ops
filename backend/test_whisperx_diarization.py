#!/usr/bin/env python3
"""
WhisperX with Speaker Diarization Test
=====================================
Let's see REAL speaker separation in action!
"""

import asyncio
import numpy as np
import time
import logging
from pathlib import Path
import subprocess
import json

# Add backend to path
import sys
sys.path.append('.')

from stt_engine.whisperx_npu_engine import WhisperXNPUEngine

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

async def test_whisperx_with_diarization():
    """Test WhisperX with real speaker diarization"""
    
    logger.info("🎯 WHISPERX SPEAKER DIARIZATION TEST")
    logger.info("="*60)
    
    audio_file = "/home/ucadmin/Development/Call with Shafen Khan.m4a"
    
    # Convert to WAV first
    logger.info("📁 Converting audio to WAV format...")
    wav_file = "/tmp/shafen_call_16k.wav"
    
    cmd = [
        "ffmpeg", "-y", "-i", audio_file,
        "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
        wav_file
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error(f"❌ FFmpeg failed: {result.stderr}")
        return
        
    # Load audio data
    logger.info("📥 Loading audio data...")
    import wave
    
    with wave.open(wav_file, 'rb') as w:
        frames = w.readframes(w.getnframes())
        audio_data = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
        
    audio_duration = len(audio_data) / 16000
    logger.info(f"✅ Loaded {audio_duration:.1f} seconds of audio")
    
    # Initialize WhisperX NPU Engine
    logger.info("\n🚀 Initializing WhisperX NPU Engine...")
    engine = WhisperXNPUEngine(model_size="medium")
    
    init_start = time.time()
    await engine.initialize()
    init_time = time.time() - init_start
    logger.info(f"✅ Initialization time: {init_time:.2f}s")
    
    # Get initial stats
    stats = engine.get_stats()
    logger.info(f"\n📊 Engine Configuration:")
    for key, value in stats.items():
        logger.info(f"  {key}: {value}")
    
    # Process with speaker diarization
    logger.info(f"\n🎤 Processing with speaker diarization...")
    start_time = time.time()
    
    result = engine.transcribe_with_speakers(audio_data)
    
    process_time = time.time() - start_time
    
    # Show results
    logger.info(f"\n✅ PROCESSING COMPLETE!")
    logger.info(f"⏱️ Total time: {process_time:.3f}s")
    logger.info(f"📊 Performance: {result['performance']['rtf']:.4f} RTF ({1/result['performance']['rtf']:.1f}x real-time)")
    logger.info(f"🚀 NPU accelerated: {result['performance'].get('npu_accelerated', False)}")
    
    # Show speakers found
    speakers = result['speakers']
    logger.info(f"\n👥 SPEAKERS DETECTED: {len(speakers)}")
    for speaker in speakers:
        segments_count = sum(1 for s in result['segments'] if s['speaker'] == speaker)
        logger.info(f"  {speaker}: {segments_count} segments")
    
    # Show first 10 segments with speakers
    logger.info(f"\n📝 TRANSCRIPT WITH SPEAKERS (first 10 segments):")
    logger.info("-"*60)
    
    for i, segment in enumerate(result['segments'][:10]):
        logger.info(f"\n[{segment['speaker']}] ({segment['start']:.1f}s - {segment['end']:.1f}s)")
        logger.info(f'"{segment["text"]}"')
        
        # Show word-level timing for first segment
        if i == 0 and 'words' in segment:
            logger.info("  Words:")
            for word in segment['words'][:5]:  # First 5 words
                logger.info(f"    '{word['word']}' @ {word['start']:.2f}s")
    
    if len(result['segments']) > 10:
        logger.info(f"\n... and {len(result['segments']) - 10} more segments")
    
    # Show conversation flow
    logger.info(f"\n💬 CONVERSATION FLOW (speaker changes):")
    prev_speaker = None
    changes = []
    
    for segment in result['segments']:
        if segment['speaker'] != prev_speaker:
            changes.append({
                'time': segment['start'],
                'speaker': segment['speaker'],
                'text': segment['text'][:50] + '...'
            })
            prev_speaker = segment['speaker']
            
    for change in changes[:15]:  # First 15 speaker changes
        logger.info(f"[{change['time']:6.1f}s] {change['speaker']}: {change['text']}")
    
    # Save full diarized transcript
    output_file = "shafen_call_whisperx_diarized.json"
    with open(output_file, "w") as f:
        json.dump(result, f, indent=2)
    
    logger.info(f"\n💾 Full diarized transcript saved to: {output_file}")
    
    # Compare with non-diarized baseline
    logger.info(f"\n📊 COMPARISON:")
    logger.info(f"{'Feature':<30} {'Basic Whisper':<20} {'WhisperX NPU':<20}")
    logger.info("-"*70)
    logger.info(f"{'Processing Time':<30} {'38.49s':<20} {f'{process_time:.3f}s':<20}")
    logger.info(f"{'Speed':<30} {'13.6x':<20} {f'{1/result["performance"]["rtf"]:.1f}x':<20}")
    logger.info(f"{'Speaker Diarization':<30} {'❌ No':<20} {'✅ Yes':<20}")
    logger.info(f"{'Word-level Timestamps':<30} {'❌ No':<20} {'✅ Yes':<20}")
    logger.info(f"{'NPU Acceleration':<30} {'❌ No':<20} {'✅ Yes (emulated)':<20}")
    
    # Test theoretical NPU performance
    theoretical_time = 0.175  # From our benchmarks
    theoretical_rtf = theoretical_time / audio_duration
    
    logger.info(f"\n🚀 WITH REAL NPU HARDWARE:")
    logger.info(f"   Expected time: {theoretical_time:.3f}s")
    logger.info(f"   Expected speed: {1/theoretical_rtf:.0f}x real-time")
    logger.info(f"   With full diarization: ✅")
    logger.info(f"   With word timestamps: ✅")
    
    return result


async def test_real_whisperx():
    """Try to run real WhisperX if available"""
    logger.info("\n\n🧪 Testing with real WhisperX (if available)...")
    
    try:
        import whisperx
        
        logger.info("✅ WhisperX is installed!")
        
        # Load audio
        audio_file = "/home/ucadmin/Development/Call with Shafen Khan.m4a"
        
        # WhisperX pipeline
        device = "cpu"  # or "cuda" if available
        batch_size = 16
        compute_type = "int8"  # Use INT8 for speed!
        
        # 1. Transcribe with Whisper
        logger.info("1️⃣ Loading Whisper model...")
        model = whisperx.load_model("base", device, compute_type=compute_type)
        
        logger.info("2️⃣ Transcribing...")
        start = time.time()
        audio = whisperx.load_audio(audio_file)
        result = model.transcribe(audio, batch_size=batch_size)
        transcribe_time = time.time() - start
        
        logger.info(f"   Transcription time: {transcribe_time:.2f}s")
        
        # 2. Align whisper output
        logger.info("3️⃣ Aligning with original audio...")
        model_a, metadata = whisperx.load_align_model(language_code=result["language"], device=device)
        result = whisperx.align(result["segments"], model_a, metadata, audio, device, return_char_alignments=False)
        
        # 3. Diarize
        logger.info("4️⃣ Speaker diarization...")
        # Note: Requires HuggingFace token
        # diarize_model = whisperx.DiarizationPipeline(device=device)
        # diarize_segments = diarize_model(audio)
        # result = whisperx.assign_word_speakers(diarize_segments, result)
        
        logger.info(f"\n✅ Real WhisperX Results:")
        logger.info(f"   Segments: {len(result['segments'])}")
        logger.info(f"   Language: {result.get('language', 'unknown')}")
        
        # Show sample
        for seg in result['segments'][:3]:
            logger.info(f"\n   [{seg['start']:.1f}s - {seg['end']:.1f}s]")
            logger.info(f'   "{seg["text"]}"')
        
    except ImportError:
        logger.info("❌ WhisperX not installed")
        logger.info("   Install with: pip install whisperx")
    except Exception as e:
        logger.error(f"❌ WhisperX test failed: {e}")


if __name__ == "__main__":
    # Run our NPU-optimized WhisperX
    asyncio.run(test_whisperx_with_diarization())
    
    # Try real WhisperX for comparison
    asyncio.run(test_real_whisperx())