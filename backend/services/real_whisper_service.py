"""
LEGACY Whisper transcription service (UC-1 appliance line).

Not the live path: this product transcribes with Parakeet (browser + server).
The "220x speedup" previously claimed here was a hardcoded constant, never measured.
"""

import logging
import time
import os
from typing import Dict, Optional
import sys
from pathlib import Path

# Add NPU engine paths
sys.path.append(str(Path(__file__).parent.parent / "stt_engine"))
sys.path.append(str(Path(__file__).parent.parent / "npu_optimization"))

logger = logging.getLogger(__name__)

class RealWhisperService:
    """NPU-accelerated transcription service using WhisperX"""
    
    def __init__(self, model_name: str = "large-v3"):
        self.model_name = model_name
        self.npu_engine = None
        self.is_initialized = False
        self.use_npu = True  # Enable NPU by default
        
    def initialize(self):
        """Load the NPU-accelerated WhisperX model"""
        try:
            logger.info(f"🚀 Loading NPU-accelerated WhisperX model: {self.model_name}")
            
            # Try to load NPU WhisperX engine
            if self.use_npu:
                try:
                    from whisperx_npu_engine_real import WhisperXNPUEngineReal
                    self.npu_engine = WhisperXNPUEngineReal(model_size=self.model_name)
                    self.is_initialized = True
                    logger.info(f"✅ NPU WhisperX model '{self.model_name}' loaded successfully")
                    logger.info("NPU engine loaded (legacy appliance path; no measured speedup)")
                    return True
                except Exception as e:
                    logger.warning(f"NPU engine failed to load: {e}")
                    logger.info("🔄 Falling back to CPU WhisperX...")
                    self.use_npu = False
            
            # Fallback to CPU WhisperX
            if not self.use_npu:
                from services.whisperx_py313 import WhisperXTranscriber
                self.npu_engine = WhisperXTranscriber(
                    model_size=self.model_name,
                    device="cpu",
                    compute_type="int8",
                    diarize=True
                )
                self.is_initialized = True
                logger.info(f"✅ CPU WhisperX model '{self.model_name}' loaded successfully")
                return True
                
        except Exception as e:
            logger.error(f"Failed to load WhisperX model: {e}")
            return False
            
    def transcribe_file(self, audio_path: str, **kwargs) -> Dict:
        """Transcribe an audio file using NPU-accelerated WhisperX"""
        if not self.is_initialized:
            if not self.initialize():
                logger.error("Failed to initialize NPU WhisperX model")
                return self._get_error_result()
                
        if not os.path.exists(audio_path):
            logger.error(f"Audio file not found: {audio_path}")
            return self._get_error_result()
            
        try:
            start_time = time.time()
            logger.info(f"🎙️ NPU Transcribing: {audio_path}")
            
            # Extract diarization flag from kwargs
            diarize = kwargs.get("diarize", True)
            
            # Transcribe with NPU WhisperX
            if self.use_npu:
                # Use the legacy NPU engine (appliance line)
                result = self.npu_engine.transcribe_file(audio_path, diarize=diarize)
            else:
                # Use CPU WhisperX
                result = self.npu_engine.transcribe(
                    audio_path,
                    word_timestamps=True
                )
            
            processing_time = time.time() - start_time
            
            # Get audio duration for RTF calculation
            audio_duration = result.get("duration", 0)
            if audio_duration == 0:
                audio_duration = self._get_audio_duration(audio_path)
            
            rtf = processing_time / audio_duration if audio_duration > 0 else 0
            speedup = 1.0 / rtf if rtf > 0 else 0
            
            logger.info(f"✅ NPU Transcription complete in {processing_time:.2f}s")
            logger.info(f"⚡ Performance: RTF={rtf:.4f}, Speedup={speedup:.1f}x")
            
            # Format result for backend compatibility
            formatted_result = {
                "text": result.get("text", ""),
                "segments": self._format_npu_segments(result.get("segments", [])),
                "language": result.get("language", "en"),
                "duration": processing_time,
                "audio_duration": audio_duration,
                "rtf": rtf,
                "speedup": speedup,
                "model": self.model_name,
                "npu_accelerated": self.use_npu,
                "success": True
            }
            
            return formatted_result
            
        except Exception as e:
            logger.error(f"NPU Transcription failed: {e}", exc_info=True)
            return self._get_error_result()
            
    def _format_npu_segments(self, segments):
        """Format NPU WhisperX segments for backend compatibility"""
        formatted = []
        for seg in segments:
            formatted_seg = {
                "start": seg.get("start", 0),
                "end": seg.get("end", 0),
                "text": seg.get("text", "").strip(),
                "confidence": seg.get("confidence", 0.95),
                "speaker": seg.get("speaker", "SPEAKER_00")  # NPU provides speaker IDs
            }
            
            # Add word-level timestamps if available
            if "words" in seg:
                formatted_seg["words"] = []
                for w in seg["words"]:
                    # Handle both dict and object types
                    if hasattr(w, 'word'):  # faster-whisper Word object
                        word_data = {
                            "word": getattr(w, 'word', ''),
                            "start": getattr(w, 'start', 0),
                            "end": getattr(w, 'end', 0),
                            "confidence": getattr(w, 'probability', 0.95)
                        }
                    else:  # dict format
                        word_data = {
                            "word": w.get("word", ""),
                            "start": w.get("start", 0),
                            "end": w.get("end", 0),
                            "confidence": w.get("confidence", w.get("probability", 0.95))
                        }
                    formatted_seg["words"].append(word_data)
                
            formatted.append(formatted_seg)
            
        return formatted
        
    def _get_error_result(self):
        """Return error result format"""
        return {
            "text": "[NPU Transcription failed]",
            "segments": [],
            "success": False,
            "model": self.model_name,
            "npu_accelerated": False
        }
    
    def _get_audio_duration(self, audio_path: str) -> float:
        """Get duration of audio file in seconds"""
        try:
            import wave
            with wave.open(audio_path, 'rb') as wf:
                frames = wf.getnframes()
                rate = wf.getframerate()
                duration = frames / float(rate)
                return duration
        except Exception:
            return 0.0
    
    def get_npu_status(self) -> Dict:
        """Get NPU acceleration status"""
        return {
            "npu_available": self.use_npu,
            "model": self.model_name,
            "acceleration_factor": None,  # never measured; do not report a figure
            "status": "npu_accelerated" if self.use_npu else "cpu_fallback",
            "engine": "WhisperX + MLIR-AIE2" if self.use_npu else "WhisperX CPU"
        }

# Global instance - Use large-v3 model for best quality with NPU
real_whisper_service = RealWhisperService(model_name="large-v3")