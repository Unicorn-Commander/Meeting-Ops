#!/usr/bin/env python3
"""
REAL Whisper Transcription - Let's see what's in that call!
"""

import whisper
import time
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

def transcribe_shafen_call():
    """Transcribe the actual call with Shafen Khan"""
    audio_file = "/home/ucadmin/Development/Call with Shafen Khan.m4a"
    
    logger.info("🎯 REAL WHISPER TRANSCRIPTION TEST")
    logger.info("="*60)
    logger.info(f"Audio: {audio_file}")
    
    # Load Whisper model
    logger.info("\n📥 Loading Whisper base model...")
    model = whisper.load_model("base")
    logger.info("✅ Model loaded")
    
    # Transcribe!
    logger.info("\n🎤 Starting transcription...")
    start_time = time.time()
    
    result = model.transcribe(
        audio_file,
        fp16=False,  # Use FP32 for CPU
        language=None,  # Auto-detect language
        verbose=True  # Show progress
    )
    
    elapsed = time.time() - start_time
    
    # Get audio duration from the result
    audio_duration = result.get("segments", [{}])[-1].get("end", 0) if result.get("segments") else 0
    rtf = elapsed / audio_duration if audio_duration > 0 else 0
    
    logger.info(f"\n✅ TRANSCRIPTION COMPLETE!")
    logger.info(f"⏱️ Processing time: {elapsed:.2f} seconds")
    logger.info(f"📏 Audio duration: {audio_duration:.1f} seconds")
    logger.info(f"📊 RTF: {rtf:.3f} ({1/rtf:.1f}x real-time)" if rtf > 0 else "📊 RTF: N/A")
    logger.info(f"🌐 Detected language: {result.get('language', 'unknown')}")
    
    logger.info(f"\n📝 FULL TRANSCRIPTION:")
    logger.info("="*60)
    print(result['text'])
    logger.info("="*60)
    
    # Show first few segments with timestamps and speaker hints
    logger.info(f"\n📋 SEGMENTS WITH TIMESTAMPS:")
    for i, segment in enumerate(result['segments'][:10]):  # First 10 segments
        logger.info(f"[{segment['start']:6.1f}s - {segment['end']:6.1f}s] {segment['text']}")
    
    if len(result['segments']) > 10:
        logger.info(f"\n... and {len(result['segments']) - 10} more segments")
        logger.info(f"\n📋 LAST FEW SEGMENTS:")
        for segment in result['segments'][-5:]:
            logger.info(f"[{segment['start']:6.1f}s - {segment['end']:6.1f}s] {segment['text']}")
    
    # Try to identify speakers by analyzing speech patterns
    logger.info(f"\n👥 SPEAKER ANALYSIS (Basic):")
    logger.info("Note: This is just basic analysis - we'd need WhisperX for real speaker diarization")
    
    # Simple heuristic: different speakers might have pauses between them
    potential_speaker_changes = []
    for i in range(1, len(result['segments'])):
        prev_end = result['segments'][i-1]['end']
        curr_start = result['segments'][i]['start']
        gap = curr_start - prev_end
        
        if gap > 1.0:  # More than 1 second gap might indicate speaker change
            potential_speaker_changes.append(i)
    
    logger.info(f"Potential speaker changes at segments: {potential_speaker_changes[:10]}")
    
    # Save to file
    output_file = "shafen_call_transcript.txt"
    with open(output_file, "w") as f:
        f.write(f"Transcription of: {audio_file}\n")
        f.write(f"Duration: {audio_duration:.1f} seconds\n")
        f.write(f"Language: {result.get('language', 'unknown')}\n")
        f.write(f"Processing time: {elapsed:.2f} seconds\n")
        f.write("="*60 + "\n\n")
        f.write(result['text'])
        f.write("\n\n" + "="*60 + "\nSegments with timestamps:\n\n")
        
        for segment in result['segments']:
            f.write(f"[{segment['start']:6.1f}s - {segment['end']:6.1f}s] {segment['text']}\n")
    
    logger.info(f"\n💾 Transcript saved to: {output_file}")
    
    return result


if __name__ == "__main__":
    try:
        transcribe_shafen_call()
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()