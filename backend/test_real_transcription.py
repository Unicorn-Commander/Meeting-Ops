#!/usr/bin/env python3
"""
REAL Transcription Test - No Mocking!
=====================================
Let's see what our engine can ACTUALLY do!
"""

import os
import sys
import time
import numpy as np
import logging
from pathlib import Path

# Add backend to path
sys.path.append('.')

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_with_real_audio():
    """Test with the actual audio file"""
    audio_file = "/home/ucadmin/Development/Call with Shafen Khan.m4a"
    
    logger.info("🎯 REAL TRANSCRIPTION TEST")
    logger.info("="*60)
    logger.info(f"Audio file: {audio_file}")
    logger.info(f"File size: {os.path.getsize(audio_file)/1024/1024:.1f} MB")
    
    # First, let's use our existing ONNX Whisper transcriber
    logger.info("\n1️⃣ Testing with current ONNX Whisper Base model...")
    
    try:
        from stt_engine.whisper_npu_transcriber import ONNXWhisperNPUTranscriber
        
        transcriber = ONNXWhisperNPUTranscriber()
        if transcriber.initialize(model_size="base"):
            logger.info("✅ Transcriber initialized")
            
            # Convert M4A to WAV first
            logger.info("🔄 Converting M4A to WAV...")
            import subprocess
            wav_file = "/tmp/test_audio.wav"
            
            # Use ffmpeg to convert
            cmd = [
                "ffmpeg", "-y", "-i", audio_file,
                "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
                wav_file
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                logger.info("✅ Converted to WAV")
                
                # Get audio duration
                probe_cmd = ["ffprobe", "-v", "quiet", "-show_entries", 
                           "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", 
                           wav_file]
                duration_result = subprocess.run(probe_cmd, capture_output=True, text=True)
                duration = float(duration_result.stdout.strip())
                logger.info(f"📏 Audio duration: {duration:.1f} seconds")
                
                # Transcribe!
                logger.info("\n🎤 Starting transcription...")
                start_time = time.time()
                
                result = transcriber.transcribe_audio(wav_file)
                
                elapsed = time.time() - start_time
                rtf = elapsed / duration
                
                logger.info(f"\n✅ TRANSCRIPTION COMPLETE!")
                logger.info(f"⏱️ Processing time: {elapsed:.2f} seconds")
                logger.info(f"📊 RTF: {rtf:.3f} ({1/rtf:.1f}x real-time)")
                logger.info(f"🚀 NPU accelerated: {result.get('npu_accelerated', False)}")
                
                logger.info(f"\n📝 TRANSCRIBED TEXT:")
                logger.info("-"*60)
                print(result.get('text', 'No transcription available'))
                logger.info("-"*60)
                
                # Clean up
                os.remove(wav_file)
                
            else:
                logger.error(f"❌ FFmpeg conversion failed: {result.stderr}")
                
        else:
            logger.error("❌ Failed to initialize transcriber")
            
    except Exception as e:
        logger.error(f"❌ Error with ONNX transcriber: {e}")
        import traceback
        traceback.print_exc()
    
    # Now let's try with a better model if available
    logger.info("\n\n2️⃣ Testing with optimized Whisper Medium (if available)...")
    
    try:
        # Check if we have whisper installed
        import whisper
        
        logger.info("🎯 Using OpenAI Whisper directly for comparison...")
        model = whisper.load_model("base")
        
        logger.info("🎤 Transcribing with Whisper base model...")
        start_time = time.time()
        
        result = model.transcribe(audio_file)
        
        elapsed = time.time() - start_time
        
        logger.info(f"\n✅ WHISPER TRANSCRIPTION COMPLETE!")
        logger.info(f"⏱️ Processing time: {elapsed:.2f} seconds")
        logger.info(f"🌐 Detected language: {result['language']}")
        
        logger.info(f"\n📝 TRANSCRIBED TEXT:")
        logger.info("-"*60)
        print(result['text'])
        logger.info("-"*60)
        
        # Show segments with timestamps
        logger.info(f"\n📋 SEGMENTS:")
        for i, segment in enumerate(result['segments'][:5]):  # First 5 segments
            logger.info(f"[{segment['start']:.1f}s - {segment['end']:.1f}s] {segment['text']}")
        if len(result['segments']) > 5:
            logger.info(f"... and {len(result['segments']) - 5} more segments")
            
    except ImportError:
        logger.info("⚠️ OpenAI Whisper not installed, skipping comparison")
        logger.info("   Install with: pip install openai-whisper")
    except Exception as e:
        logger.error(f"❌ Error with Whisper: {e}")
    
    # Test speaker diarization
    logger.info("\n\n3️⃣ Testing Speaker Diarization...")
    
    try:
        from stt_engine.speaker_diarization import SpeakerDiarizer
        
        diarizer = SpeakerDiarizer()
        if diarizer.initialize():
            logger.info("✅ Diarizer initialized")
            
            # Would diarize here but needs HuggingFace token
            logger.info("⚠️ Diarization requires HuggingFace token")
        else:
            logger.info("❌ Diarizer not available")
            
    except Exception as e:
        logger.error(f"❌ Error with diarization: {e}")


def install_whisper_if_needed():
    """Install whisper for testing"""
    try:
        import whisper
    except ImportError:
        logger.info("📦 Installing OpenAI Whisper for comparison...")
        os.system("pip install openai-whisper")


if __name__ == "__main__":
    # Make sure we have ffmpeg
    if os.system("which ffmpeg > /dev/null 2>&1") != 0:
        logger.error("❌ FFmpeg not found! Please install: sudo apt install ffmpeg")
        sys.exit(1)
    
    # Run the test
    test_with_real_audio()