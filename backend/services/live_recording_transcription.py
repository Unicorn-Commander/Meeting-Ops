"""
Live Recording Transcription Service
Processes chunks of audio during recording for real-time transcription
"""

import asyncio
import logging
import time
import os
from pathlib import Path
from typing import Optional, Dict, List
import numpy as np
import soundfile as sf

logger = logging.getLogger(__name__)

class LiveRecordingTranscriptionService:
    """
    Service that monitors an active recording and transcribes chunks
    in real-time for live transcription display
    """
    
    def __init__(self):
        self.is_active = False
        self.current_file = None
        self.last_position = 0
        self.transcription_task = None
        
    async def start_monitoring(self, audio_file: str, session_id: str):
        """Start monitoring a recording file for live transcription"""
        self.current_file = audio_file
        self.session_id = session_id
        self.last_position = 0
        self.is_active = True
        
        # Start the monitoring task
        self.transcription_task = asyncio.create_task(
            self._monitor_and_transcribe()
        )
        logger.info(f"Started live transcription monitoring for {audio_file}")
        
    async def stop_monitoring(self):
        """Stop monitoring"""
        self.is_active = False
        if self.transcription_task:
            self.transcription_task.cancel()
            try:
                await self.transcription_task
            except asyncio.CancelledError:
                pass
        logger.info("Stopped live transcription monitoring")
        
    async def _monitor_and_transcribe(self):
        """Monitor recording file and transcribe new chunks"""
        # Faster updates for more responsive feel (like iPhone)
        # Smaller chunks = faster processing = more frequent updates
        chunk_duration = 5  # Process 5-second chunks for quick updates
        chunk_overlap = 1  # 1-second overlap for continuity
        recording_sample_rate = 44100  # Recording at 44.1kHz
        target_sample_rate = 16000  # Whisper needs 16kHz
        chunk_samples = chunk_duration * recording_sample_rate
        overlap_samples = chunk_overlap * recording_sample_rate
        min_chunk_duration = 3  # Minimum chunk size to avoid bad transcriptions
        
        # Import transcription service
        from stt_engine.whisperx_npu_engine_real import WhisperXNPUEngine
        from api.websocket_transcription import broadcast_transcription_update
        
        # Use whisper-base for live transcription (faster, good enough for monitoring)
        # Save large-v3 for final accurate transcription
        transcriber = WhisperXNPUEngine(model_size="base")
        
        while self.is_active:
            try:
                # Check if file exists and has grown
                if not os.path.exists(self.current_file):
                    await asyncio.sleep(1)
                    continue
                
                file_size = os.path.getsize(self.current_file)
                
                # WAV header is 44 bytes, each sample is 2 bytes (16-bit)
                available_samples = (file_size - 44) // 2
                
                # Check if we have enough new data for a chunk
                if available_samples - self.last_position >= chunk_samples:
                    # Read the chunk with overlap from previous chunk
                    try:
                        with sf.SoundFile(self.current_file, 'r') as audio_file:
                            # Include overlap from previous chunk if not at start
                            start_position = max(0, self.last_position - overlap_samples)
                            audio_file.seek(start_position)
                            
                            # Read chunk plus overlap
                            read_samples = chunk_samples + (self.last_position - start_position)
                            chunk_data = audio_file.read(read_samples)
                            
                        if len(chunk_data) > 0:
                            # Only transcribe if we have enough audio (avoid tiny chunks)
                            chunk_duration_actual = len(chunk_data) / recording_sample_rate
                            if chunk_duration_actual < min_chunk_duration:
                                logger.debug(f"Skipping short chunk: {chunk_duration_actual:.1f}s")
                                self.last_position += len(chunk_data)
                                continue
                            
                            logger.info(f"Processing chunk: {chunk_duration_actual:.1f}s of audio from position {self.last_position}")
                            
                            # Resample from 44.1kHz to 16kHz for Whisper
                            import librosa
                            chunk_resampled = librosa.resample(
                                chunk_data, 
                                orig_sr=recording_sample_rate, 
                                target_sr=target_sample_rate
                            )
                            
                            # Transcribe the resampled chunk
                            # No diarization for live - faster and simpler
                            result = transcriber.transcribe(
                                chunk_resampled,
                                diarize=False  # Skip diarization for speed
                            )
                            
                            if result and result.get("segments"):
                                # Broadcast each segment
                                for segment in result["segments"]:
                                    # Skip empty or very short segments
                                    text = segment.get("text", "").strip()
                                    if not text or len(text) < 3:
                                        continue
                                    
                                    # Adjust timestamps based on position in file (using recording sample rate)
                                    segment["start"] += self.last_position / recording_sample_rate
                                    segment["end"] += self.last_position / recording_sample_rate
                                    
                                    # Ensure segment has all required fields
                                    # No speaker for live transcription (no diarization)
                                    broadcast_segment = {
                                        "text": text,
                                        "start": segment.get("start", 0),
                                        "end": segment.get("end", 0),
                                        "speaker": None,  # No diarization for live
                                        "confidence": segment.get("confidence", 0.95)
                                    }
                                    
                                    logger.info(f"Broadcasting segment: '{text[:50]}...' speaker={broadcast_segment['speaker']}")
                                    
                                    await broadcast_transcription_update(
                                        self.session_id,
                                        broadcast_segment
                                    )
                                    
                                logger.info(f"Transcribed chunk: {len(result['segments'])} segments")
                            else:
                                logger.warning("No segments returned from transcription")
                            
                            # Update position (move forward by chunk_duration, not full read length)
                            self.last_position += chunk_samples  # Move by chunk size, not including overlap
                            
                    except Exception as e:
                        logger.error(f"Error reading audio chunk: {e}")
                        
                await asyncio.sleep(1)  # Check every second
                
            except Exception as e:
                logger.error(f"Live transcription error: {e}")
                await asyncio.sleep(2)
                
# Global instance
live_recording_transcription = LiveRecordingTranscriptionService()