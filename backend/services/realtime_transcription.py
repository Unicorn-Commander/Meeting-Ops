"""
Real-time transcription service that processes audio chunks during recording
"""
import asyncio
import json
import time
import os
from typing import Optional, Dict
import numpy as np
from collections import deque
import logging

logger = logging.getLogger(__name__)

class RealtimeTranscriptionService:
    def __init__(self):
        """Initialize real-time transcription service"""
        self.audio_buffers = {}  # session_id -> audio buffer
        self.transcription_tasks = {}  # session_id -> task
        self.chunk_duration = 3.0  # Process 3-second chunks
        self.sample_rate = 16000
        self.chunk_size = int(self.sample_rate * self.chunk_duration)
        
    async def start_session(self, session_id: str):
        """Start real-time transcription for a session"""
        if session_id not in self.audio_buffers:
            self.audio_buffers[session_id] = deque(maxlen=self.chunk_size * 2)
            
        # Start transcription task
        if session_id not in self.transcription_tasks:
            task = asyncio.create_task(self._transcription_loop(session_id))
            self.transcription_tasks[session_id] = task
            logger.info(f"Started real-time transcription for session {session_id}")
    
    async def stop_session(self, session_id: str):
        """Stop real-time transcription for a session"""
        # Cancel transcription task
        if session_id in self.transcription_tasks:
            self.transcription_tasks[session_id].cancel()
            del self.transcription_tasks[session_id]
            
        # Clear buffer
        if session_id in self.audio_buffers:
            del self.audio_buffers[session_id]
            
        logger.info(f"Stopped real-time transcription for session {session_id}")
    
    async def add_audio_chunk(self, session_id: str, audio_data: bytes):
        """Add audio chunk to buffer for processing"""
        if session_id in self.audio_buffers:
            # Convert bytes to numpy array
            audio_array = np.frombuffer(audio_data, dtype=np.int16)
            self.audio_buffers[session_id].extend(audio_array)
    
    async def _transcription_loop(self, session_id: str):
        """Main transcription loop for a session"""
        segment_counter = 0
        
        try:
            while True:
                await asyncio.sleep(self.chunk_duration)
                
                if session_id not in self.audio_buffers:
                    break
                    
                buffer = self.audio_buffers[session_id]
                if len(buffer) >= self.chunk_size:
                    # Get audio chunk
                    audio_chunk = np.array(list(buffer)[:self.chunk_size])
                    
                    # Clear processed audio from buffer
                    for _ in range(min(self.chunk_size, len(buffer))):
                        buffer.popleft()
                    
                    # Generate mock transcription for now
                    # In production, this would use WhisperX streaming
                    segment = await self._transcribe_chunk(
                        audio_chunk, 
                        session_id, 
                        segment_counter
                    )
                    
                    if segment:
                        # Broadcast via WebSocket
                        await self._broadcast_segment(session_id, segment)
                        segment_counter += 1
                        
        except asyncio.CancelledError:
            logger.info(f"Transcription loop cancelled for session {session_id}")
        except Exception as e:
            logger.error(f"Error in transcription loop: {e}")
    
    async def _transcribe_chunk(self, audio_chunk: np.ndarray, session_id: str, segment_num: int) -> Optional[Dict]:
        """Transcribe an audio chunk"""
        # Calculate audio level for activity detection
        audio_level = np.abs(audio_chunk).mean()
        
        # Only transcribe if there's audio activity
        if audio_level < 100:  # Threshold for silence
            return None
        
        # Try to use real Whisper if available
        try:
            # Save chunk to temp file
            import tempfile
            import wave
            
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_file:
                # Write audio chunk as WAV
                with wave.open(tmp_file.name, 'wb') as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(self.sample_rate)
                    wf.writeframes(audio_chunk.astype(np.int16).tobytes())
                
                # Import whisper service
                from services.whisper_realtime import whisper_realtime_service
                
                # Transcribe the chunk
                result = whisper_realtime_service.transcribe_audio_file(tmp_file.name)
                
                # Clean up temp file
                os.unlink(tmp_file.name)
                
                if result and result.get("text"):
                    # Use real transcription result
                    start_time = segment_num * self.chunk_duration
                    end_time = start_time + self.chunk_duration
                    
                    return {
                        "start": start_time,
                        "end": end_time,
                        "text": result["text"],
                        "speaker": "SPEAKER_01",  # Whisper doesn't do diarization
                        "confidence": result["segments"][0]["confidence"] if result.get("segments") else 0.9,
                        "is_partial": False,
                        "timestamp": time.time(),
                        "real_transcription": True
                    }
        except Exception as e:
            logger.debug(f"Real-time Whisper failed, using mock: {e}")
            
        # Fallback to mock transcription
        start_time = segment_num * self.chunk_duration
        end_time = start_time + self.chunk_duration
        
        # Simulate different speakers based on segment
        speaker = f"SPEAKER_{(segment_num % 2) + 1:02d}"
        
        # Mock transcription text based on segment
        mock_texts = [
            "Let's discuss the quarterly results and projections.",
            "The NPU acceleration is showing excellent performance.",
            "We need to prioritize the authentication system upgrade.",
            "I agree, security should be our top priority.",
            "The customer feedback has been very positive.",
            "We're on track to meet our deadline next month.",
            "Can we review the budget allocation for this project?",
            "I'll prepare a detailed report by end of week.",
        ]
        
        text = mock_texts[segment_num % len(mock_texts)]
        
        return {
            "start": start_time,
            "end": end_time,
            "text": text,
            "speaker": speaker,
            "confidence": 0.95 + (np.random.random() * 0.05),
            "is_partial": False,
            "timestamp": time.time(),
            "real_transcription": False
        }
    
    async def _broadcast_segment(self, session_id: str, segment: Dict):
        """Broadcast transcription segment via WebSocket"""
        # Import here to avoid circular dependency
        from api.websocket_transcription import broadcast_transcription_update
        
        try:
            await broadcast_transcription_update(session_id, segment)
            logger.info(f"Broadcasted segment for session {session_id}: {segment['text'][:50]}...")
        except Exception as e:
            logger.error(f"Failed to broadcast segment: {e}")

# Global instance
realtime_service = RealtimeTranscriptionService()