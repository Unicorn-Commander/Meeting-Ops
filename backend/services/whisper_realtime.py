"""
Real Whisper transcription service using faster-whisper or whisperx
This provides actual transcription, not mock data
"""
import os
import time
import wave
import json
import logging
import tempfile
import subprocess
from typing import Optional, Dict, List
from pathlib import Path
import asyncio

logger = logging.getLogger(__name__)

class WhisperRealtimeService:
    def __init__(self):
        """Initialize Whisper service"""
        self.model_name = "base"  # Start with base model for speed
        self.model_path = None
        self.transcription_tasks = {}
        self.ensure_whisper_installed()
        
    def ensure_whisper_installed(self):
        """Ensure whisper is available"""
        try:
            # Check if whisper is installed
            result = subprocess.run(
                ["which", "whisper"], 
                capture_output=True, 
                text=True
            )
            if result.returncode == 0:
                logger.info("✅ Whisper CLI found")
                return True
        except:
            pass
            
        # Try to install whisper
        try:
            logger.info("Installing whisper...")
            subprocess.run([
                "pip", "install", "-q", "openai-whisper"
            ], check=True)
            logger.info("✅ Whisper installed")
            return True
        except Exception as e:
            logger.warning(f"Could not install whisper: {e}")
            return False
    
    def transcribe_audio_file(self, audio_path: str) -> Dict:
        """
        Transcribe an audio file using Whisper CLI
        
        Returns:
            Dictionary with transcription results
        """
        try:
            # Create temp directory for output
            with tempfile.TemporaryDirectory() as temp_dir:
                output_base = os.path.join(temp_dir, "output")
                
                # Run whisper command
                cmd = [
                    "whisper",
                    audio_path,
                    "--model", self.model_name,
                    "--language", "en",
                    "--output_format", "json",
                    "--output_dir", temp_dir,
                    "--verbose", "False"
                ]
                
                logger.info(f"Running Whisper on {audio_path}")
                start_time = time.time()
                
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=300  # 5 minute timeout
                )
                
                processing_time = time.time() - start_time
                
                # Read the JSON output
                json_file = None
                for file in os.listdir(temp_dir):
                    if file.endswith('.json'):
                        json_file = os.path.join(temp_dir, file)
                        break
                
                if json_file and os.path.exists(json_file):
                    with open(json_file, 'r') as f:
                        whisper_output = json.load(f)
                    
                    # Convert to our format
                    segments = []
                    for seg in whisper_output.get('segments', []):
                        segments.append({
                            "start": seg['start'],
                            "end": seg['end'],
                            "text": seg['text'].strip(),
                            "speaker": "SPEAKER_01",  # Whisper doesn't do diarization
                            "confidence": seg.get('avg_logprob', -0.5) + 1.5  # Convert to 0-1 scale
                        })
                    
                    return {
                        "text": whisper_output.get('text', ''),
                        "segments": segments,
                        "language": whisper_output.get('language', 'en'),
                        "duration": whisper_output.get('duration', 0),
                        "processing_time": processing_time,
                        "model": self.model_name
                    }
                else:
                    # Fallback if no JSON output
                    if result.stdout:
                        return {
                            "text": result.stdout.strip(),
                            "segments": [{
                                "start": 0,
                                "end": 10,
                                "text": result.stdout.strip(),
                                "speaker": "SPEAKER_01",
                                "confidence": 0.8
                            }],
                            "processing_time": processing_time,
                            "model": self.model_name
                        }
                    else:
                        raise Exception("No output from Whisper")
                        
        except subprocess.TimeoutExpired:
            logger.error("Whisper transcription timed out")
            return self._fallback_transcription(audio_path)
        except Exception as e:
            logger.error(f"Whisper transcription failed: {e}")
            return self._fallback_transcription(audio_path)
    
    def _fallback_transcription(self, audio_path: str) -> Dict:
        """Fallback transcription when Whisper fails"""
        try:
            # Get audio duration
            with wave.open(audio_path, 'rb') as wf:
                frames = wf.getnframes()
                rate = wf.getframerate()
                duration = frames / float(rate)
        except:
            duration = 0
            
        return {
            "text": "Transcription processing... (Whisper not available)",
            "segments": [{
                "start": 0,
                "end": duration,
                "text": "Audio recorded successfully. Transcription service initializing...",
                "speaker": "SPEAKER_01",
                "confidence": 0.0
            }],
            "duration": duration,
            "processing_time": 0,
            "model": "none",
            "error": "Whisper not available"
        }
    
    async def transcribe_chunk_realtime(self, audio_chunk: bytes, session_id: str) -> Optional[Dict]:
        """
        Transcribe audio chunk in near real-time
        For true real-time, we'd need to accumulate chunks and process periodically
        """
        # This would need to:
        # 1. Accumulate audio chunks into ~5-10 second segments
        # 2. Save to temp file
        # 3. Run whisper on it
        # 4. Return results
        
        # For now, return None (would need proper implementation)
        return None

# Try to use faster-whisper if available (much faster)
try:
    import faster_whisper
    
    class FasterWhisperService(WhisperRealtimeService):
        def __init__(self):
            """Initialize faster-whisper"""
            super().__init__()
            self.model_name = "base"
            try:
                from faster_whisper import WhisperModel
                # Use CPU for now (could use CUDA if available)
                self.model = WhisperModel(self.model_name, device="cpu", compute_type="int8")
                logger.info("✅ Using faster-whisper for transcription")
            except Exception as e:
                logger.warning(f"Could not load faster-whisper model: {e}")
                self.model = None
        
        def transcribe_audio_file(self, audio_path: str) -> Dict:
            """Transcribe using faster-whisper (much faster than regular whisper)"""
            if not self.model:
                return super().transcribe_audio_file(audio_path)
                
            try:
                start_time = time.time()
                
                # Transcribe with faster-whisper
                segments_list = []
                text_parts = []
                
                segments, info = self.model.transcribe(
                    audio_path,
                    beam_size=5,
                    language="en",
                    word_timestamps=True
                )
                
                for segment in segments:
                    segments_list.append({
                        "start": segment.start,
                        "end": segment.end,
                        "text": segment.text.strip(),
                        "speaker": "SPEAKER_01",
                        "confidence": segment.avg_logprob + 1.5 if segment.avg_logprob else 0.9,
                        "words": [
                            {
                                "word": word.word,
                                "start": word.start,
                                "end": word.end,
                                "confidence": word.probability
                            }
                            for word in (segment.words or [])
                        ] if segment.words else None
                    })
                    text_parts.append(segment.text.strip())
                
                processing_time = time.time() - start_time
                
                return {
                    "text": " ".join(text_parts),
                    "segments": segments_list,
                    "language": info.language,
                    "duration": info.duration,
                    "processing_time": processing_time,
                    "model": f"faster-whisper-{self.model_name}",
                    "word_timestamps": True
                }
                
            except Exception as e:
                logger.error(f"Faster-whisper failed: {e}")
                return super().transcribe_audio_file(audio_path)
    
    # Use faster-whisper as default
    whisper_realtime_service = FasterWhisperService()
    
except ImportError:
    logger.info("faster-whisper not available, using standard whisper")
    whisper_realtime_service = WhisperRealtimeService()