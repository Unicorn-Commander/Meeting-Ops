"""
Audio Consumer Base Class
Base class for services that consume audio from the unified capture service
"""

import redis
import threading
import queue
import json
import logging
from typing import Callable, Optional
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

class AudioConsumer(ABC):
    """
    Base class for audio consumers
    Subscribes to Redis channels and processes audio
    """
    
    def __init__(self, redis_url: str = "redis://localhost:6379", consumer_id: str = "consumer"):
        self.redis_client = redis.from_url(redis_url)
        self.pubsub = self.redis_client.pubsub()
        self.consumer_id = consumer_id
        
        # Local queue for audio chunks
        self.audio_queue = queue.Queue(maxsize=100)
        
        # State
        self.is_running = False
        self.subscribe_thread = None
        self.process_thread = None
        
    def start(self):
        """Start consuming audio"""
        if self.is_running:
            return
            
        self.is_running = True
        
        # Subscribe to appropriate channels
        self._setup_subscriptions()
        
        # Start subscription thread
        self.subscribe_thread = threading.Thread(
            target=self._subscription_worker, 
            daemon=True
        )
        self.subscribe_thread.start()
        
        # Start processing thread
        self.process_thread = threading.Thread(
            target=self._processing_worker,
            daemon=True
        )
        self.process_thread.start()
        
        logger.info(f"✅ {self.consumer_id} started consuming audio")
        
    def _setup_subscriptions(self):
        """Setup Redis subscriptions based on consumer needs"""
        # Subscribe to channels based on what this consumer needs
        pass
        
    def _subscription_worker(self):
        """Worker thread for Redis subscriptions"""
        for message in self.pubsub.listen():
            if not self.is_running:
                break
                
            if message['type'] == 'message':
                self._handle_message(message)
                
    def _handle_message(self, message):
        """Handle incoming Redis message"""
        channel = message['channel'].decode('utf-8')
        data = message['data']
        
        # Route to appropriate handler
        if channel == 'audio:raw':
            self.audio_queue.put(data)
        elif channel == 'audio:levels':
            self._handle_audio_levels(json.loads(data))
            
    def _processing_worker(self):
        """Worker thread for processing audio"""
        while self.is_running:
            try:
                audio_chunk = self.audio_queue.get(timeout=1)
                self.process_audio(audio_chunk)
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Processing error in {self.consumer_id}: {e}")
                
    @abstractmethod
    def process_audio(self, audio_chunk: bytes):
        """Process audio chunk - implement in subclass"""
        pass
        
    def _handle_audio_levels(self, levels: dict):
        """Handle audio level updates"""
        # Override in subclass if needed
        pass
        
    def stop(self):
        """Stop consuming audio"""
        self.is_running = False
        self.pubsub.close()
        logger.info(f"⏹️ {self.consumer_id} stopped")


class RecordingConsumer(AudioConsumer):
    """Consumer for recording audio to files"""
    
    def __init__(self, session_id: str, redis_url: str = "redis://localhost:6379"):
        super().__init__(redis_url, f"recorder-{session_id}")
        self.session_id = session_id
        self.audio_file = None
        self.bytes_written = 0
        
    def _setup_subscriptions(self):
        """Subscribe to raw audio channel"""
        self.pubsub.subscribe('audio:raw')
        
    def process_audio(self, audio_chunk: bytes):
        """Write audio to file"""
        if self.audio_file:
            self.audio_file.write(audio_chunk)
            self.bytes_written += len(audio_chunk)
            
            # Update recording status in Redis
            self.redis_client.hset(f'recording:{self.session_id}', 'bytes_written', self.bytes_written)
            
    def start_recording(self, filepath: str):
        """Start recording to file"""
        import wave
        self.audio_file = wave.open(filepath, 'wb')
        self.audio_file.setnchannels(1)
        self.audio_file.setsampwidth(2)  # 16-bit
        self.audio_file.setframerate(44100)
        self.start()
        
    def stop_recording(self):
        """Stop recording and close file"""
        self.stop()
        if self.audio_file:
            self.audio_file.close()
            self.audio_file = None


class TranscriptionConsumer(AudioConsumer):
    """Consumer for transcription service"""
    
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        super().__init__(redis_url, "transcriber")
        self.audio_buffer = bytearray()
        self.buffer_seconds = 2  # Process every 2 seconds
        self.bytes_per_second = 44100 * 2  # 44.1kHz * 16-bit
        
    def _setup_subscriptions(self):
        """Subscribe to raw audio for transcription"""
        self.pubsub.subscribe('audio:raw')
        
    def process_audio(self, audio_chunk: bytes):
        """Buffer audio and transcribe when ready"""
        self.audio_buffer.extend(audio_chunk)
        
        # Process when we have enough audio
        if len(self.audio_buffer) >= self.bytes_per_second * self.buffer_seconds:
            # Get the audio to process
            audio_to_process = bytes(self.audio_buffer[:self.bytes_per_second * self.buffer_seconds])
            
            # Keep remaining audio
            self.audio_buffer = self.audio_buffer[self.bytes_per_second * self.buffer_seconds:]
            
            # Transcribe (this would call your NPU transcription)
            self._transcribe_audio(audio_to_process)
            
    def _transcribe_audio(self, audio_data: bytes):
        """Transcribe audio using NPU service"""
        # This would call your actual transcription service
        # For now, just publish that we have audio to transcribe
        self.redis_client.publish('audio:transcribe:request', audio_data)
        logger.info(f"📝 Sent {len(audio_data)} bytes for transcription")


class AudioLevelConsumer(AudioConsumer):
    """Consumer for audio level monitoring"""
    
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        super().__init__(redis_url, "level-monitor")
        
    def _setup_subscriptions(self):
        """Subscribe to audio levels channel"""
        self.pubsub.subscribe('audio:levels')
        
    def process_audio(self, audio_chunk: bytes):
        """Not used for level monitoring"""
        pass
        
    def _handle_audio_levels(self, levels: dict):
        """Handle audio level updates"""
        # Broadcast to WebSocket clients or update UI
        logger.debug(f"📊 Audio level: {levels['audio_level']:.2%}, peak: {levels['peak_level']:.2%}")