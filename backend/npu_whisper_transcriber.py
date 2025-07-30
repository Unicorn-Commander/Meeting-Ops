"""
NPU-aware WhisperX transcriber with automatic fallback
"""
import os
import numpy as np
import logging
import time
from pathlib import Path
from typing import Dict, Optional
import librosa

# Import WhisperX NPU engine
try:
    from stt_engine.whisperx_npu_engine import WhisperXNPUEngine
    WHISPERX_AVAILABLE = True
except ImportError:
    WHISPERX_AVAILABLE = False
    print("Warning: WhisperX NPU engine not available, using fallback")

logger = logging.getLogger(__name__)

class NPUWhisperTranscriber:
    """WhisperX transcriber with NPU acceleration support"""
    
    def __init__(self):
        self.sample_rate = 16000
        self.model_loaded = False
        self.whisperx_engine = None
        self.npu_available = False
        self.using_npu = False
        self._try_load_model()
        
    def _check_npu_availability(self):
        """Check if NPU is available and accessible"""
        try:
            # Check if NPU device exists
            if os.path.exists("/dev/accel/accel0"):
                # Try to open it
                fd = os.open("/dev/accel/accel0", os.O_RDWR)
                os.close(fd)
                self.npu_available = True
                logger.info("✅ NPU device detected and accessible")
                return True
            else:
                logger.info("ℹ️  No NPU device found at /dev/accel/accel0")
                return False
        except Exception as e:
            logger.warning(f"NPU check failed: {e}")
            return False
        
    def _try_load_model(self):
        """Load WhisperX NPU engine"""
        try:
            if WHISPERX_AVAILABLE:
                logger.info("Initializing WhisperX NPU engine...")
                self.whisperx_engine = WhisperXNPUEngine()
                
                # Check NPU availability
                self._check_npu_availability()
                
                self.model_loaded = True
                self.using_npu = True
                logger.info("✅ WhisperX NPU engine loaded successfully")
            else:
                logger.warning("WhisperX NPU engine not available, using fallback")
                self.model_loaded = False
                self.using_npu = False
                
        except Exception as e:
            logger.error(f"Failed to load WhisperX NPU engine: {e}")
            # Fallback to CPU-only mock transcription
            self.model_loaded = False
            self.using_npu = False
            
    def transcribe(self, audio_path: str) -> Dict:
        """Transcribe audio with WhisperX NPU acceleration if available"""
        try:
            start_time = time.time()
            
            # Load audio
            audio, sr = librosa.load(audio_path, sr=self.sample_rate, mono=True)
            duration = len(audio) / sr
            
            if not self.model_loaded or not self.whisperx_engine:
                # Fallback to basic detection
                rms = np.sqrt(np.mean(audio**2))
                is_speech = rms > 0.01
                
                return {
                    "text": f"{'Speech' if is_speech else 'Silence'} detected ({duration:.1f}s)",
                    "duration": duration,
                    "processing_time": time.time() - start_time,
                    "npu_accelerated": False,
                    "model": "fallback"
                }
            
            # Use WhisperX NPU engine for transcription
            result = self.whisperx_engine.transcribe(audio_path)
            
            # Extract text from segments
            full_text = " ".join([segment["text"] for segment in result.get("segments", [])])
            
            return {
                "text": full_text,
                "segments": result.get("segments", []),
                "language": result.get("language", "en"),
                "duration": duration,
                "processing_time": time.time() - start_time,
                "npu_accelerated": self.using_npu,
                "model": "whisperx-npu"
            }
            
        except Exception as e:
            logger.error(f"Transcription error: {e}")
            return {
                "text": f"Error: {str(e)}",
                "segments": [],
                "error": str(e),
                "npu_accelerated": False
            }
            
    def transcribe_with_diarization(self, audio_path: str) -> Dict:
        """Transcribe with speaker diarization using WhisperX"""
        try:
            start_time = time.time()
            
            if not self.model_loaded or not self.whisperx_engine:
                return self.transcribe(audio_path)
            
            # WhisperX includes speaker diarization by default
            result = self.whisperx_engine.transcribe(audio_path)
            
            # Extract text from segments
            full_text = " ".join([segment["text"] for segment in result.get("segments", [])])
            
            return {
                "text": full_text,
                "segments": result.get("segments", []),
                "language": result.get("language", "en"),
                "processing_time": time.time() - start_time,
                "npu_accelerated": self.using_npu,
                "speaker_diarization": True,
                "model": "whisperx-npu-diarized"
            }
            
        except Exception as e:
            logger.error(f"Diarization error: {e}")
            return self.transcribe(audio_path)
    
    def transcribe_chunk(self, audio_data: np.ndarray) -> Dict:
        """Transcribe audio chunk for real-time processing"""
        try:
            start_time = time.time()
            
            if not self.model_loaded or not self.whisperx_engine:
                # Fallback: basic silence detection
                rms = np.sqrt(np.mean(audio_data**2))
                is_speech = rms > 0.01
                
                return {
                    "text": "Speech detected" if is_speech else "",
                    "confidence": 0.5 if is_speech else 0.1,
                    "processing_time": time.time() - start_time,
                    "npu_accelerated": False
                }
            
            # Use WhisperX for chunk transcription
            result = self.whisperx_engine.transcribe_chunk(audio_data)
            
            # Extract text from segments
            full_text = " ".join([segment["text"] for segment in result.get("segments", [])])
            
            return {
                "text": full_text,
                "segments": result.get("segments", []),
                "processing_time": time.time() - start_time,
                "npu_accelerated": self.using_npu,
                "model": "whisperx-npu-chunk"
            }
            
        except Exception as e:
            logger.error(f"Chunk transcription error: {e}")
            return {
                "text": "",
                "error": str(e),
                "processing_time": time.time() - start_time,
                "npu_accelerated": False
            }
    
    def get_performance_metrics(self) -> Dict:
        """Get current performance metrics"""
        if self.whisperx_engine and hasattr(self.whisperx_engine, 'npu_metrics'):
            return self.whisperx_engine.npu_metrics
        
        return {
            "enabled": self.using_npu,
            "npu_available": self.npu_available,
            "model_loaded": self.model_loaded,
            "device": "AMD NPU Phoenix" if self.npu_available else "CPU"
        }