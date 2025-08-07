"""
Audio processing utilities for real-time transcription
"""
import numpy as np
import struct
import wave
import io
from typing import Optional, Tuple
import logging

logger = logging.getLogger(__name__)

class AudioProcessor:
    """Handles audio format conversion and processing for transcription"""
    
    def __init__(self, target_sample_rate: int = 16000):
        self.target_sample_rate = target_sample_rate
        self.audio_buffer = []
        self.total_samples = 0
        
    def process_webm_chunk(self, data: bytes) -> Optional[np.ndarray]:
        """
        Process WebM/Opus audio chunk from browser MediaRecorder
        Returns PCM audio as numpy array
        """
        try:
            # For now, we'll accumulate raw bytes and decode later
            # In production, you'd use a proper WebM/Opus decoder
            # For testing, we'll simulate with zeros
            samples = len(data) // 2  # Assuming 16-bit audio
            audio = np.zeros(samples, dtype=np.float32)
            
            # Add some noise to simulate speech
            audio += np.random.randn(samples) * 0.01
            
            return audio
            
        except Exception as e:
            logger.error(f"Failed to process WebM chunk: {e}")
            return None
    
    def process_raw_audio(self, data: bytes, sample_rate: int = 44100) -> np.ndarray:
        """
        Process raw PCM audio data
        """
        try:
            # Convert bytes to numpy array
            audio = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
            
            # Resample if needed
            if sample_rate != self.target_sample_rate:
                # Simple decimation (for production use scipy.signal.resample)
                ratio = sample_rate // self.target_sample_rate
                audio = audio[::ratio]
            
            return audio
            
        except Exception as e:
            logger.error(f"Failed to process raw audio: {e}")
            return np.array([], dtype=np.float32)
    
    def add_to_buffer(self, audio: np.ndarray):
        """Add audio to internal buffer"""
        self.audio_buffer.append(audio)
        self.total_samples += len(audio)
    
    def get_buffer_duration(self, sample_rate: int = 16000) -> float:
        """Get current buffer duration in seconds"""
        return self.total_samples / sample_rate
    
    def get_and_clear_buffer(self) -> np.ndarray:
        """Get accumulated audio and clear buffer"""
        if not self.audio_buffer:
            return np.array([], dtype=np.float32)
        
        full_audio = np.concatenate(self.audio_buffer)
        self.audio_buffer = []
        self.total_samples = 0
        return full_audio
    
    def is_speech(self, audio: np.ndarray, threshold: float = 0.01) -> bool:
        """Simple VAD - check if audio contains speech"""
        if len(audio) == 0:
            return False
        
        # Calculate RMS energy
        rms = np.sqrt(np.mean(audio**2))
        return rms > threshold