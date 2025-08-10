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
        chunk_duration = 5  # Process 5-second chunks
        sample_rate = 16000
        chunk_samples = chunk_duration * sample_rate
        
        # Import transcription service
        from stt_engine.whisperx_npu_engine_real import WhisperXNPUEngine
        from api.websocket_transcription import broadcast_transcription_update
        
        transcriber = WhisperXNPUEngine()
        
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
                    # Read the chunk
                    try:
                        with sf.SoundFile(self.current_file, 'r') as audio_file:
                            audio_file.seek(self.last_position)
                            chunk_data = audio_file.read(chunk_samples)
                            
                        if len(chunk_data) > 0:
                            # Transcribe the chunk
                            result = transcriber.transcribe(
                                chunk_data,
                                diarize=True
                            )
                            
                            if result and result.get("segments"):
                                # Broadcast each segment
                                for segment in result["segments"]:
                                    # Adjust timestamps based on position in file
                                    segment["start"] += self.last_position / sample_rate
                                    segment["end"] += self.last_position / sample_rate
                                    
                                    # Ensure segment has all required fields
                                    broadcast_segment = {
                                        "text": segment.get("text", ""),
                                        "start": segment.get("start", 0),
                                        "end": segment.get("end", 0),
                                        "speaker": segment.get("speaker", "SPEAKER_00"),
                                        "confidence": segment.get("confidence", 0.95)
                                    }
                                    
                                    await broadcast_transcription_update(
                                        self.session_id,
                                        broadcast_segment
                                    )
                                    
                                logger.info(f"Transcribed chunk: {len(result['segments'])} segments, broadcasting to WebSocket clients")
                            
                            # Update position
                            self.last_position += len(chunk_data)
                            
                    except Exception as e:
                        logger.error(f"Error reading audio chunk: {e}")
                        
                await asyncio.sleep(1)  # Check every second
                
            except Exception as e:
                logger.error(f"Live transcription error: {e}")
                await asyncio.sleep(2)
                
# Global instance
live_recording_transcription = LiveRecordingTranscriptionService()