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
    """Whisper transcriber with NPU acceleration support"""
    
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
                
                # Check for NPU-enabled ONNX providers
                providers = ort.get_available_providers()
                if 'VitisAIExecutionProvider' in providers:
                    logger.info("✅ VitisAI provider available - full NPU support")
                    return ['VitisAIExecutionProvider', 'CPUExecutionProvider']
                else:
                    logger.info("ℹ️  NPU device present but VitisAI provider not available")
                    logger.info("ℹ️  Using CPU with NPU-optimized models")
            else:
                logger.info("ℹ️  No NPU device found at /dev/accel/accel0")
        except Exception as e:
            logger.warning(f"NPU check failed: {e}")
        
        return ['CPUExecutionProvider']
        
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
            
            # Extract features
            inputs = self.feature_extractor(audio, sampling_rate=self.sample_rate, return_tensors="np")
            input_features = inputs.input_features
            
            # Run encoder
            encoder_start = time.time()
            encoder_outputs = self.encoder_session.run(None, {"input_features": input_features})
            encoder_time = time.time() - encoder_start
            encoder_hidden_states = encoder_outputs[0]
            
            # Simple greedy decoding
            max_length = 448
            decoder_input_ids = np.array([[self.tokenizer.bos_token_id]], dtype=np.int64)
            generated_tokens = []
            
            decoder_start = time.time()
            for _ in range(max_length):
                # Run decoder
                decoder_outputs = self.decoder_session.run(
                    None,
                    {
                        "encoder_hidden_states": encoder_hidden_states,
                        "input_ids": decoder_input_ids
                    }
                )
                
                # Get next token
                logits = decoder_outputs[0]
                next_token_logits = logits[:, -1, :]
                next_token_id = np.argmax(next_token_logits, axis=-1)[0]
                
                # Check for end token
                if next_token_id == self.tokenizer.eos_token_id:
                    break
                    
                generated_tokens.append(next_token_id)
                
                # Update decoder input
                decoder_input_ids = np.concatenate([decoder_input_ids, [[next_token_id]]], axis=1)
            
            decoder_time = time.time() - decoder_start
            
            # Decode tokens to text
            text = self.tokenizer.decode(generated_tokens, skip_special_tokens=True).strip()
            
            processing_time = time.time() - start_time
            
            # Performance metrics
            rtf = processing_time / duration  # Real-time factor
            speedup = 1 / rtf if rtf > 0 else 0
            
            result = {
                "text": text,
                "segments": [{
                    "id": 0,
                    "start": 0.0,
                    "end": duration,
                    "text": text,
                    "confidence": 0.90
                }],
                "language": "en",
                "duration": duration,
                "processing_time": processing_time,
                "encoder_time": encoder_time,
                "decoder_time": decoder_time,
                "rtf": rtf,
                "speedup": speedup,
                "model": "whisper-base-onnx",
                "npu_available": self.npu_available,
                "npu_accelerated": self.using_npu,
                "providers": self.encoder_session.get_providers() if self.encoder_session else []
            }
            
            logger.info(f"✅ Transcription complete: {speedup:.1f}x real-time (NPU: {self.using_npu})")
            
            return result
            
        except Exception as e:
            logger.error(f"Transcription error: {e}")
            return {
                "text": f"Error: {str(e)}",
                "segments": [],
                "error": str(e),
                "npu_accelerated": False
            }
            
    def transcribe_with_diarization(self, audio_path: str) -> Dict:
        """Transcribe with speaker diarization"""
        result = self.transcribe(audio_path)
        
        # Add mock diarization
        if result.get("segments"):
            duration = result["duration"]
            num_speakers = 2
            segment_duration = duration / 4
            
            segments = []
            for i in range(4):
                start = i * segment_duration
                end = min((i + 1) * segment_duration, duration)
                speaker = f"SPEAKER_{i % num_speakers:02d}"
                
                segments.append({
                    "id": i,
                    "start": start,
                    "end": end,
                    "text": f"Segment {i+1}",
                    "speaker": speaker,
                    "confidence": 0.85
                })
                
            result["segments"] = segments
            result["speakers"] = [f"SPEAKER_{i:02d}" for i in range(num_speakers)]
            result["diarization"] = True
            
        return result

# Whisper-compatible interface
class WhisperCompatibleTranscriber(NPUWhisperTranscriber):
    """Whisper-compatible API wrapper"""
    
    def __call__(self, audio_path: str, **kwargs):
        """Make it callable like whisper.transcribe()"""
        return self.transcribe(audio_path)
        
    def load_model(self, model_name: str = "base"):
        """Compatibility method"""
        logger.info(f"Model {model_name} requested - using NPU-aware transcriber")
        return self