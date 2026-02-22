"""
Live Recording Transcription Service
Processes chunks of audio during recording for real-time transcription
Uses NPU-accelerated transcription_service (WhisperX NPU)
"""

import asyncio
import logging
import time
import os
import json
import tempfile
from pathlib import Path
from typing import Optional, Dict, List
import numpy as np
import soundfile as sf
import redis.asyncio as redis

logger = logging.getLogger(__name__)

# Redis URL from environment (default matches docker-compose port 6381)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6381")

class LiveRecordingTranscriptionService:
    """
    Service that monitors an active recording and transcribes chunks
    in real-time for live transcription display.
    Uses the NPU-accelerated transcription_service for fast inference.
    """

    def __init__(self):
        self.is_active = False
        self.current_file = None
        self.last_position = 0
        self.transcription_task = None
        self.redis_client = None
        self.transcript_buffer = []  # Buffer for meeting notes generation
        self.session_word_counts = {}  # Track word counts per session
        self.triggered_intervals = {}  # Track triggered summary intervals

    async def start_monitoring(self, audio_file: str, session_id: str):
        """Start monitoring a recording file for live transcription"""
        self.current_file = audio_file
        self.session_id = session_id
        self.last_position = 0
        self.is_active = True
        self.transcript_buffer = []

        logger.info(f"Starting live transcription monitoring")
        logger.info(f"   File: {audio_file}")
        logger.info(f"   Session: {session_id}")
        logger.info(f"   File exists: {os.path.exists(audio_file)}")

        # Start the monitoring task
        self.transcription_task = asyncio.create_task(
            self._monitor_and_transcribe()
        )
        logger.info(f"Live transcription task started")

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
        """Monitor recording file and transcribe new chunks using NPU service"""
        chunk_duration = 15  # 15-second chunks for good accuracy
        chunk_overlap = 2   # 2-second overlap for continuity
        recording_sample_rate = 44100  # Recording at 44.1kHz
        target_sample_rate = 16000     # Whisper needs 16kHz
        chunk_samples = chunk_duration * recording_sample_rate
        overlap_samples = chunk_overlap * recording_sample_rate
        min_chunk_duration = 3  # Minimum chunk size to avoid bad transcriptions

        # Import NPU transcription service (works on AMD, no CUDA needed)
        from services.transcription_service import transcription_service
        from api.websocket_transcription import broadcast_transcription_update

        if not transcription_service.is_ready:
            logger.error("Transcription service not ready - live transcription disabled")
            return

        logger.info(f"Using NPU transcription service: model={transcription_service.current_model_id}, ready={transcription_service.is_ready}")

        # Wait for file to be created (up to 10 seconds)
        file_wait_count = 0
        while not os.path.exists(self.current_file) and file_wait_count < 10:
            logger.info(f"Waiting for recording file to be created... ({file_wait_count+1}/10)")
            await asyncio.sleep(1)
            file_wait_count += 1

        if not os.path.exists(self.current_file):
            logger.error(f"Recording file never created: {self.current_file}")
            return

        logger.info(f"Recording file found, starting live transcription monitoring")

        while self.is_active:
            try:
                if not os.path.exists(self.current_file):
                    logger.error(f"Recording file disappeared: {self.current_file}")
                    break

                file_size = os.path.getsize(self.current_file)
                logger.debug(f"File size: {file_size} bytes, last position: {self.last_position}")

                # WAV header is 44 bytes, each sample is 2 bytes (16-bit)
                available_samples = (file_size - 44) // 2

                if available_samples - self.last_position >= chunk_samples:
                    logger.info(f"Processing chunk: {available_samples} samples available, need {chunk_samples}")
                    try:
                        with sf.SoundFile(self.current_file, 'r') as audio_file:
                            start_position = max(0, self.last_position - overlap_samples)
                            audio_file.seek(start_position)
                            read_samples = chunk_samples + (self.last_position - start_position)
                            chunk_data = audio_file.read(read_samples)

                        if len(chunk_data) > 0:
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

                            # Save chunk to temporary WAV file
                            tmp_fd, tmp_path = tempfile.mkstemp(suffix='.wav')
                            os.close(tmp_fd)
                            sf.write(tmp_path, chunk_resampled, target_sample_rate)

                            # Transcribe using NPU transcription service
                            try:
                                result = await asyncio.get_event_loop().run_in_executor(
                                    None,
                                    transcription_service.transcribe_file,
                                    tmp_path
                                )
                            finally:
                                os.unlink(tmp_path)

                            if result and result.get("segments"):
                                for segment in result["segments"]:
                                    text = segment.get("text", "").strip()
                                    if not text or len(text) < 3:
                                        continue

                                    # Adjust timestamps to absolute position in recording
                                    seg_start = segment.get("start", 0)
                                    seg_end = segment.get("end", 0)

                                    # Convert NumPy types to Python float
                                    seg_start = float(seg_start.item()) if hasattr(seg_start, 'item') else float(seg_start)
                                    seg_end = float(seg_end.item()) if hasattr(seg_end, 'item') else float(seg_end)

                                    seg_start += self.last_position / recording_sample_rate
                                    seg_end += self.last_position / recording_sample_rate

                                    conf_val = segment.get("confidence", 0.95)
                                    conf_val = float(conf_val.item()) if hasattr(conf_val, 'item') else float(conf_val)

                                    broadcast_segment = {
                                        "text": text,
                                        "start": seg_start,
                                        "end": seg_end,
                                        "speaker": segment.get("speaker"),
                                        "confidence": conf_val
                                    }

                                    logger.info(f"Broadcasting segment: '{text[:50]}...'")

                                    from api.websocket_auto_summary import broadcast_transcription_segment
                                    await broadcast_transcription_segment(
                                        self.session_id,
                                        broadcast_segment
                                    )

                                    self.transcript_buffer.append(broadcast_segment)

                                    from api.websocket_auto_summary import session_word_counts
                                    current_word_count = session_word_counts.get(self.session_id, 0)

                                    await self._check_and_trigger_summary(
                                        self.session_id,
                                        current_word_count
                                    )

                                    await self._publish_to_redis(broadcast_segment)

                                logger.info(f"Transcribed chunk: {len(result['segments'])} segments")
                            elif result and result.get("text"):
                                # Result has text but no segments - broadcast as single segment
                                text = result["text"].strip()
                                if text and len(text) >= 3:
                                    broadcast_segment = {
                                        "text": text,
                                        "start": float(self.last_position / recording_sample_rate),
                                        "end": float((self.last_position + chunk_samples) / recording_sample_rate),
                                        "speaker": None,
                                        "confidence": result.get("confidence", 0.95)
                                    }

                                    logger.info(f"Broadcasting text: '{text[:50]}...'")

                                    from api.websocket_auto_summary import broadcast_transcription_segment
                                    await broadcast_transcription_segment(
                                        self.session_id,
                                        broadcast_segment
                                    )

                                    self.transcript_buffer.append(broadcast_segment)

                                    from api.websocket_auto_summary import session_word_counts
                                    current_word_count = session_word_counts.get(self.session_id, 0)
                                    await self._check_and_trigger_summary(
                                        self.session_id, current_word_count
                                    )
                                    await self._publish_to_redis(broadcast_segment)

                                logger.info("Transcribed chunk: 1 segment (from text)")
                            else:
                                logger.warning("No segments returned from transcription")

                            self.last_position += chunk_samples

                    except Exception as e:
                        logger.error(f"Error reading/transcribing audio chunk: {e}", exc_info=True)
                else:
                    needed_samples = chunk_samples - (available_samples - self.last_position)
                    needed_seconds = needed_samples / recording_sample_rate
                    logger.debug(f"Waiting for more audio: need {needed_seconds:.1f} more seconds")

                await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"Live transcription error: {e}")
                await asyncio.sleep(2)
    
    async def _check_and_trigger_summary(self, session_id: str, total_words: int):
        """Check if we should trigger a progressive summary"""
        # Fixed 500-word intervals for progressive summaries
        interval = 500
        
        if session_id not in self.triggered_intervals:
            self.triggered_intervals[session_id] = 0  # Track last trigger point
        
        # Check if we've passed the next 500-word threshold
        next_threshold = ((self.triggered_intervals[session_id] // interval) + 1) * interval
        
        if total_words >= next_threshold:
            logger.info(f"🎯 Progressive summary triggered at {total_words} words for session {session_id}")
            
            # Update last trigger point
            self.triggered_intervals[session_id] = total_words
            
            # Trigger progressive summary via progressive_interval_manager
            try:
                from services.progressive_interval_manager import progressive_interval_manager
                await progressive_interval_manager.trigger_progressive_summary(
                    session_id=session_id,
                    current_word_count=total_words,
                    force=True
                )
                logger.info(f"✅ Progressive summary requested for {session_id} at {total_words} words (next at {total_words + interval})")
            except Exception as e:
                logger.error(f"Failed to trigger progressive summary: {e}")
    
    async def _publish_to_redis(self, segment: Dict):
        """Publish transcript segment to Redis for notes generation"""
        try:
            if not self.redis_client:
                self.redis_client = await redis.from_url(REDIS_URL, decode_responses=True)
            
            # Publish to channel for meeting notes service
            channel = f"transcription:{self.session_id}"
            message = json.dumps({
                'text': segment['text'],
                'speaker': segment.get('speaker'),
                'timestamp': time.time(),
                'start': segment.get('start'),
                'end': segment.get('end'),
                'word_count': len(segment['text'].split()),
                'total_words': self.session_word_counts.get(self.session_id, 0)
            })
            
            await self.redis_client.publish(channel, message)
            logger.debug(f"Published segment to Redis channel: {channel}")
            
        except Exception as e:
            logger.error(f"Error publishing to Redis: {e}")
                
# Global instance
live_recording_transcription = LiveRecordingTranscriptionService()