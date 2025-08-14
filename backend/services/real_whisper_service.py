"""
Real Whisper Transcription Service
Actual transcription using OpenAI Whisper or Faster-Whisper
"""

import logging
import time
import whisper
from typing import Dict, Optional
import os

logger = logging.getLogger(__name__)

class RealWhisperService:
    """Real transcription service using Whisper"""
    
    def __init__(self, model_name: str = "base"):
        self.model_name = model_name
        self.model = None
        self.is_initialized = False
        
    def initialize(self):
        """Load the Whisper model"""
        try:
            logger.info(f"Loading Whisper model: {self.model_name}")
            self.model = whisper.load_model(self.model_name)
            self.is_initialized = True
            logger.info(f"✅ Whisper model '{self.model_name}' loaded successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to load Whisper model: {e}")
            return False
            
    def transcribe_file(self, audio_path: str, **kwargs) -> Dict:
        """Transcribe an audio file"""
        if not self.is_initialized:
            if not self.initialize():
                logger.error("Failed to initialize Whisper model")
                return self._get_error_result()
                
        if not os.path.exists(audio_path):
            logger.error(f"Audio file not found: {audio_path}")
            return self._get_error_result()
            
        try:
            start_time = time.time()
            logger.info(f"Transcribing: {audio_path}")
            
            # Transcribe with Whisper
            result = self.model.transcribe(
                audio_path,
                language="en",  # Force English for speed
                task="transcribe",
                verbose=False,
                word_timestamps=True  # Get word-level timestamps
            )
            
            processing_time = time.time() - start_time
            logger.info(f"Transcription complete in {processing_time:.2f}s")
            
            # Format result
            return {
                "text": result.get("text", ""),
                "segments": self._format_segments(result.get("segments", [])),
                "language": result.get("language", "en"),
                "duration": processing_time,
                "model": self.model_name,
                "success": True
            }
            
        except Exception as e:
            logger.error(f"Transcription failed: {e}", exc_info=True)
            return self._get_error_result()
            
    def _format_segments(self, segments):
        """Format Whisper segments for our system"""
        formatted = []
        for seg in segments:
            formatted_seg = {
                "start": seg.get("start", 0),
                "end": seg.get("end", 0),
                "text": seg.get("text", "").strip(),
                "confidence": seg.get("confidence", 0.95),
                "speaker": "SPEAKER_01"  # Default speaker (no diarization yet)
            }
            
            # Add word-level timestamps if available
            if "words" in seg:
                formatted_seg["words"] = [
                    {
                        "word": w.get("word", ""),
                        "start": w.get("start", 0),
                        "end": w.get("end", 0),
                        "confidence": w.get("probability", 0.95)
                    }
                    for w in seg["words"]
                ]
                
            formatted.append(formatted_seg)
            
        return formatted
        
    def _get_error_result(self):
        """Return error result format"""
        return {
            "text": "[Transcription failed]",
            "segments": [],
            "success": False,
            "model": self.model_name
        }

# Global instance
real_whisper_service = RealWhisperService(model_name="base")