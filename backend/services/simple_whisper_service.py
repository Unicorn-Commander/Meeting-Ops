"""
Simple Whisper service using faster-whisper for basic transcription
This is a minimal implementation focused on getting transcription working
"""

import logging
import os
from typing import Dict, Any, Optional, List
import tempfile
import wave
import numpy as np
from faster_whisper import WhisperModel

logger = logging.getLogger(__name__)

class SimpleWhisperService:
    """
    Simple transcription service using faster-whisper
    """
    
    def __init__(self):
        self.model = None
        self.model_size = "base"
        self.device = "cpu"
        self.compute_type = "int8"
        
    def _ensure_model_loaded(self):
        """Load the faster-whisper model if not already loaded"""
        if self.model is not None:
            return
            
        try:
            logger.info(f"Loading Whisper {self.model_size} model...")
            self.model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type
            )
            logger.info("✅ Whisper model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load Whisper model: {e}")
            self.model = None
    
    def get_status(self) -> Dict[str, Any]:
        """Get the status of the transcription service"""
        self._ensure_model_loaded()
        
        return {
            "whisper_available": self.model is not None,
            "model_size": self.model_size,
            "device": self.device,
            "compute_type": self.compute_type,
            "status": "ready" if self.model else "failed"
        }
    
    def transcribe_file(self, audio_path: str, language: str = None) -> Dict[str, Any]:
        """
        Transcribe an audio file
        """
        self._ensure_model_loaded()
        
        if self.model is None:
            return self._mock_transcription(audio_path)
        
        try:
            logger.info(f"Transcribing {audio_path}...")
            
            # Transcribe with faster-whisper
            segments, info = self.model.transcribe(
                audio_path,
                language=language,
                word_timestamps=True,
                vad_filter=True,
                vad_parameters=dict(
                    min_silence_duration_ms=500,
                    speech_pad_ms=400,
                )
            )
            
            # Convert to list and format
            segments_list = list(segments)
            
            formatted_segments = []
            full_text = ""
            
            for segment in segments_list:
                segment_dict = {
                    "start": segment.start,
                    "end": segment.end,
                    "text": segment.text.strip(),
                    "speaker": "SPEAKER_01",  # Default speaker for now
                    "confidence": getattr(segment, 'avg_logprob', 0.9),
                }
                
                # Add word-level timestamps if available
                if hasattr(segment, 'words') and segment.words:
                    segment_dict["words"] = [
                        {
                            "start": word.start,
                            "end": word.end,
                            "word": word.word.strip(),
                            "confidence": getattr(word, 'probability', 0.9)
                        }
                        for word in segment.words
                    ]
                
                formatted_segments.append(segment_dict)
                full_text += segment.text + " "
            
            duration = self._get_audio_duration(audio_path)
            
            return {
                "text": full_text.strip(),
                "segments": formatted_segments,
                "language": info.language,
                "language_probability": info.language_probability,
                "duration": info.duration,
                "model": self.model_size,
                "method": "faster_whisper",
                "word_count": len(full_text.split()) if full_text else 0,
                "segment_count": len(formatted_segments)
            }
            
        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            return self._mock_transcription(audio_path)
    
    def _mock_transcription(self, audio_path: str) -> Dict[str, Any]:
        """Generate a mock transcription when real transcription fails"""
        duration = self._get_audio_duration(audio_path)
        
        mock_segments = [
            {
                "start": 0.0,
                "end": min(5.0, duration),
                "text": "This is a mock transcription because Whisper is not fully available.",
                "speaker": "SPEAKER_01",
                "confidence": 0.9,
                "words": [
                    {"word": "This", "start": 0.0, "end": 0.3, "confidence": 0.9},
                    {"word": "is", "start": 0.3, "end": 0.5, "confidence": 0.9},
                    {"word": "a", "start": 0.5, "end": 0.6, "confidence": 0.9},
                    {"word": "mock", "start": 0.6, "end": 0.9, "confidence": 0.9},
                    {"word": "transcription", "start": 0.9, "end": 1.8, "confidence": 0.9},
                ]
            }
        ]
        
        if duration > 5.0:
            mock_segments.append({
                "start": 5.0,
                "end": duration,
                "text": f"Please install proper Whisper dependencies to get real transcription. Audio duration: {duration:.1f} seconds.",
                "speaker": "SPEAKER_01",
                "confidence": 0.8,
                "words": []
            })
        
        full_text = " ".join([seg["text"] for seg in mock_segments])
        
        return {
            "text": full_text,
            "segments": mock_segments,
            "language": "en",
            "language_probability": 0.9,
            "duration": duration,
            "model": "mock",
            "method": "mock_fallback",
            "word_count": len(full_text.split()),
            "segment_count": len(mock_segments),
            "warning": "This is a mock transcription. Install Whisper dependencies for real transcription."
        }
    
    def _get_audio_duration(self, audio_path: str) -> float:
        """Get duration of audio file in seconds"""
        try:
            with wave.open(audio_path, 'rb') as wf:
                frames = wf.getnframes()
                rate = wf.getframerate()
                duration = frames / float(rate)
                return duration
        except Exception:
            return 10.0  # Default duration for mock

# Global service instance
simple_whisper_service = SimpleWhisperService()

def get_whisper_service():
    """Get the global simple whisper service instance"""
    return simple_whisper_service