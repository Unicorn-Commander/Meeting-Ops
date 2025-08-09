"""
Unified Audio Capture Service
Single point of audio capture that distributes to multiple consumers via Redis
"""

import asyncio
import subprocess
import threading
import queue
import time
import logging
import redis
import json
import numpy as np
from typing import Optional, List, Callable
from datetime import datetime

logger = logging.getLogger(__name__)

class UnifiedAudioCapture:
    """
    Single audio capture service that:
    1. Captures from USB mic ONCE
    2. Distributes via Redis pub/sub
    3. Maintains circular buffer for time-shift
    4. Provides audio to all consumers
    """
    
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis_client = redis.from_url(redis_url)
        self.pubsub = self.redis_client.pubsub()
        
        # Audio settings
        self.device = "hw:0,0"  # USB mic
        self.sample_rate = 44100
        self.channels = 1
        self.chunk_size = 4096  # ~93ms at 44.1kHz
        
        # State
        self.is_running = False
        self.capture_process = None
        self.audio_buffer = queue.Queue(maxsize=1000)  # Local buffer
        
        # Circular buffer for time-shift (in memory)
        self.circular_buffer = []
        self.max_buffer_seconds = 3600  # 1 hour max
        
        # Subscribers tracking
        self.active_streams = set()
        
    async def start(self):
        """Start the unified audio capture"""
        if self.is_running:
            logger.warning("Audio capture already running")
            return
            
        self.is_running = True
        
        # Start capture thread
        capture_thread = threading.Thread(target=self._capture_audio, daemon=True)
        capture_thread.start()
        
        # Start distribution thread
        distribution_thread = threading.Thread(target=self._distribute_audio, daemon=True)
        distribution_thread.start()
        
        logger.info("✅ Unified Audio Capture started")
        logger.info(f"  📍 Device: {self.device}")
        logger.info(f"  🎵 Sample rate: {self.sample_rate} Hz")
        logger.info(f"  📡 Distributing via Redis pub/sub")
        
    def _capture_audio(self):
        """Capture audio from USB mic in a separate thread"""
        cmd = [
            'arecord',
            '-D', self.device,
            '-f', 'S16_LE',
            '-r', str(self.sample_rate),
            '-c', str(self.channels),
            '-t', 'raw',
            '-q'  # Quiet mode
        ]
        
        try:
            self.capture_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            logger.info("🎤 Audio capture process started")
            
            while self.is_running:
                # Read audio chunk
                audio_chunk = self.capture_process.stdout.read(self.chunk_size * 2)  # 16-bit = 2 bytes
                
                if not audio_chunk:
                    logger.warning("No audio data received")
                    time.sleep(0.01)
                    continue
                
                # Put in local queue
                try:
                    self.audio_buffer.put(audio_chunk, block=False)
                except queue.Full:
                    # Drop oldest if buffer full
                    try:
                        self.audio_buffer.get_nowait()
                        self.audio_buffer.put(audio_chunk, block=False)
                    except:
                        pass
                        
        except Exception as e:
            logger.error(f"Audio capture error: {e}")
        finally:
            if self.capture_process:
                self.capture_process.terminate()
                
    def _distribute_audio(self):
        """Distribute audio to all consumers via Redis"""
        while self.is_running:
            try:
                # Get audio from buffer
                audio_chunk = self.audio_buffer.get(timeout=1)
                
                # Convert to numpy for processing
                audio_array = np.frombuffer(audio_chunk, dtype=np.int16)
                
                # Calculate audio level
                audio_level = float(np.abs(audio_array).mean()) / 32768.0
                peak_level = float(np.abs(audio_array).max()) / 32768.0
                
                # Create message with multiple data streams
                message = {
                    'timestamp': datetime.now().isoformat(),
                    'audio_level': audio_level,
                    'peak_level': peak_level,
                    'chunk_size': len(audio_chunk),
                    'sample_rate': self.sample_rate
                }
                
                # Publish to different Redis channels for different consumers
                
                # 1. Audio levels channel (for monitoring)
                self.redis_client.publish('audio:levels', json.dumps(message))
                
                # 2. Raw audio channel (for recording)
                self.redis_client.publish('audio:raw', audio_chunk)
                
                # 3. Transcription channel (batched for efficiency)
                # Only send every 2 seconds worth of audio for transcription
                self._buffer_for_transcription(audio_chunk)
                
                # 4. Add to circular buffer for time-shift
                self._add_to_circular_buffer(audio_chunk)
                
                # Update Redis with current status
                self.redis_client.set('audio:capture:status', json.dumps({
                    'running': True,
                    'device': self.device,
                    'sample_rate': self.sample_rate,
                    'buffer_size': len(self.circular_buffer),
                    'active_streams': len(self.active_streams)
                }))
                
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Distribution error: {e}")
                
    def _buffer_for_transcription(self, audio_chunk):
        """Buffer audio and send to transcription when we have enough"""
        # This is managed by the buffer - transcription service will pull when ready
        pass
        
    def _add_to_circular_buffer(self, audio_chunk):
        """Add audio to circular buffer for time-shift recording"""
        timestamp = datetime.now()
        
        # Add to buffer
        self.circular_buffer.append({
            'timestamp': timestamp,
            'audio': audio_chunk
        })
        
        # Remove old data (keep last hour)
        cutoff_time = datetime.now().timestamp() - self.max_buffer_seconds
        self.circular_buffer = [
            chunk for chunk in self.circular_buffer 
            if chunk['timestamp'].timestamp() > cutoff_time
        ]
        
    async def stop(self):
        """Stop audio capture"""
        self.is_running = False
        
        if self.capture_process:
            self.capture_process.terminate()
            
        logger.info("⏹️ Unified Audio Capture stopped")
        
    def get_buffer_for_timeshift(self, seconds: int) -> bytes:
        """Get audio from circular buffer for time-shift recording"""
        cutoff_time = datetime.now().timestamp() - seconds
        
        # Collect all audio chunks from the last N seconds
        audio_chunks = []
        for chunk in self.circular_buffer:
            if chunk['timestamp'].timestamp() > cutoff_time:
                audio_chunks.append(chunk['audio'])
                
        # Concatenate all chunks
        if audio_chunks:
            return b''.join(audio_chunks)
        return b''
        
    def register_stream(self, stream_id: str):
        """Register a new consumer stream"""
        self.active_streams.add(stream_id)
        logger.info(f"📝 Registered stream: {stream_id}")
        
    def unregister_stream(self, stream_id: str):
        """Unregister a consumer stream"""
        self.active_streams.discard(stream_id)
        logger.info(f"🗑️ Unregistered stream: {stream_id}")

# Global instance
unified_audio_capture = UnifiedAudioCapture()