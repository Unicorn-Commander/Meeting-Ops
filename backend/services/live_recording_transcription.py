"""
Live Recording Transcription Service
Processes chunks of audio during recording for real-time transcription
Now with AI-powered meeting notes generation
"""

import asyncio
import logging
import time
import os
import json
from pathlib import Path
from typing import Optional, Dict, List
import numpy as np
import soundfile as sf
import redis.asyncio as redis

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
        self.redis_client = None
        self.transcript_buffer = []  # Buffer for meeting notes generation
        
    async def start_monitoring(self, audio_file: str, session_id: str):
        """Start monitoring a recording file for live transcription"""
        self.current_file = audio_file
        self.session_id = session_id
        self.last_position = 0
        self.is_active = True
        
        logger.info(f"🎙️ Starting live transcription monitoring")
        logger.info(f"   File: {audio_file}")
        logger.info(f"   Session: {session_id}")
        logger.info(f"   File exists: {os.path.exists(audio_file)}")
        
        # Start the monitoring task
        self.transcription_task = asyncio.create_task(
            self._monitor_and_transcribe()
        )
        logger.info(f"✅ Live transcription task started")
        
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
        # Longer chunks for more reliable transcription
        # 15 seconds gives enough context for accurate transcription
        chunk_duration = 15  # Process 15-second chunks for better accuracy
        chunk_overlap = 2  # 2-second overlap for continuity
        recording_sample_rate = 44100  # Recording at 44.1kHz
        target_sample_rate = 16000  # Whisper needs 16kHz
        chunk_samples = chunk_duration * recording_sample_rate
        overlap_samples = chunk_overlap * recording_sample_rate
        min_chunk_duration = 3  # Minimum chunk size to avoid bad transcriptions
        
        # Import transcription service
        from services.whisperx_py313 import WhisperXTranscriber
        from api.websocket_transcription import broadcast_transcription_update
        
        # Use whisper-base for live transcription (faster, good enough for monitoring)
        # Save large-v3 for final accurate transcription
        logger.info("Initializing WhisperX for live transcription...")
        transcriber = WhisperXTranscriber(
            model_size="base",  # Use base for speed in live mode
            device="cpu",
            compute_type="int8",
            diarize=False  # Skip diarization for speed
        )
        
        while self.is_active:
            try:
                # Check if file exists and has grown
                if not os.path.exists(self.current_file):
                    logger.warning(f"Recording file not found: {self.current_file}")
                    await asyncio.sleep(1)
                    continue
                
                file_size = os.path.getsize(self.current_file)
                logger.debug(f"File size: {file_size} bytes, last position: {self.last_position}")
                
                # WAV header is 44 bytes, each sample is 2 bytes (16-bit)
                available_samples = (file_size - 44) // 2
                
                # Check if we have enough new data for a chunk
                if available_samples - self.last_position >= chunk_samples:
                    logger.info(f"Processing chunk: {available_samples} samples available, need {chunk_samples}")
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
                            
                            # Save chunk to temporary file for WhisperX
                            import tempfile
                            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_file:
                                sf.write(tmp_file.name, chunk_resampled, target_sample_rate)
                                tmp_path = tmp_file.name
                            
                            # Transcribe the chunk using WhisperX
                            try:
                                result = transcriber.transcribe(
                                    tmp_path,
                                    word_timestamps=False  # Skip word timestamps for speed
                                )
                            finally:
                                # Clean up temp file
                                os.unlink(tmp_path)
                            
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
                                    
                                    # Add to transcript buffer for notes generation
                                    self.transcript_buffer.append(broadcast_segment)
                                    
                                    # Publish to Redis for notes generation service
                                    await self._publish_to_redis(broadcast_segment)
                                    
                                logger.info(f"Transcribed chunk: {len(result['segments'])} segments")
                            else:
                                logger.warning("No segments returned from transcription")
                            
                            # Update position (move forward by chunk_duration, not full read length)
                            self.last_position += chunk_samples  # Move by chunk size, not including overlap
                            
                    except Exception as e:
                        logger.error(f"Error reading audio chunk: {e}")
                else:
                    # Not enough data yet
                    needed_samples = chunk_samples - (available_samples - self.last_position)
                    needed_seconds = needed_samples / recording_sample_rate
                    logger.debug(f"Waiting for more audio: need {needed_seconds:.1f} more seconds")
                        
                await asyncio.sleep(1)  # Check every second
                
            except Exception as e:
                logger.error(f"Live transcription error: {e}")
                await asyncio.sleep(2)
    
    async def _publish_to_redis(self, segment: Dict):
        """Publish transcript segment to Redis for notes generation"""
        try:
            if not self.redis_client:
                self.redis_client = await redis.from_url("redis://localhost:6379", decode_responses=True)
            
            # Publish to channel for meeting notes service
            channel = f"transcription:{self.session_id}"
            message = json.dumps({
                'text': segment['text'],
                'speaker': segment.get('speaker'),
                'timestamp': time.time(),
                'start': segment.get('start'),
                'end': segment.get('end')
            })
            
            await self.redis_client.publish(channel, message)
            logger.debug(f"Published segment to Redis channel: {channel}")
            
        except Exception as e:
            logger.error(f"Error publishing to Redis: {e}")
                
# Global instance
live_recording_transcription = LiveRecordingTranscriptionService()