#!/usr/bin/env python3
"""
Transcription with Speaker Diarization Integration
"""

import asyncio
import logging
import time
from typing import Dict, List, Any, Optional
from pathlib import Path
import numpy as np

from npu_whisper_transcriber import NPUWhisperTranscriber
from stt_engine.speaker_diarization import SpeakerDiarizer

logger = logging.getLogger(__name__)

class TranscriptionWithDiarization:
    """Combines NPU Whisper transcription with speaker diarization"""
    
    def __init__(self):
        self.transcriber = NPUWhisperTranscriber()
        self.diarizer = None
        self.diarizer_ready = False
        
    async def initialize_diarizer(self):
        """Initialize speaker diarization asynchronously"""
        try:
            self.diarizer = SpeakerDiarizer()
            await self.diarizer.initialize()
            self.diarizer_ready = self.diarizer.is_ready
            logger.info("✅ Speaker diarization initialized")
        except Exception as e:
            logger.warning(f"⚠️ Speaker diarization not available: {e}")
            logger.info("ℹ️  Diarization requires HuggingFace token for pyannote models")
            logger.info("ℹ️  Set HF_TOKEN environment variable or use WhisperX for diarization")
            self.diarizer_ready = False
    
    def transcribe_with_speakers(self, audio_path: str) -> Dict[str, Any]:
        """Transcribe audio with speaker identification"""
        result = {
            "text": "",
            "segments": [],
            "speakers": [],
            "npu_accelerated": False,
            "diarization_enabled": False
        }
        
        try:
            # First, get the transcription with word timestamps
            logger.info("🎯 Starting NPU transcription...")
            start_time = time.time()
            
            transcription_result = self.transcriber.transcribe(audio_path)
            transcription_time = time.time() - start_time
            
            result["text"] = transcription_result.get("text", "")
            result["npu_accelerated"] = transcription_result.get("npu_accelerated", False)
            result["transcription_time"] = transcription_time
            
            # If diarization is available and ready
            if self.diarizer_ready and self.diarizer:
                logger.info("🎤 Performing speaker diarization...")
                diarization_start = time.time()
                
                # Run diarization (synchronously for now)
                diarization = asyncio.run(self.diarizer.diarize_audio_file(audio_path))
                diarization_time = time.time() - diarization_start
                
                result["diarization_enabled"] = True
                result["diarization_time"] = diarization_time
                
                # Merge transcription with speaker information
                result["segments"] = self._merge_transcription_with_speakers(
                    transcription_result.get("text", ""),
                    diarization
                )
                
                # Extract unique speakers
                speakers = set()
                for segment in result["segments"]:
                    if "speaker" in segment:
                        speakers.add(segment["speaker"])
                
                result["speakers"] = sorted(list(speakers))
                result["num_speakers"] = len(speakers)
                
                logger.info(f"✅ Identified {len(speakers)} speakers")
            else:
                logger.warning("⚠️ Speaker diarization not available, using simulation")
                # Simulate diarization by splitting text into segments
                result["segments"] = self._simulate_diarization(
                    result["text"], 
                    transcription_result.get("duration", 0.0)
                )
                result["speakers"] = ["SPEAKER_00", "SPEAKER_01"]
                result["num_speakers"] = 2
                result["diarization_enabled"] = False  # It's simulated
            
            # Add performance metrics
            result["performance"] = {
                "audio_duration": transcription_result.get("duration", 0),
                "transcription_time": transcription_time,
                "diarization_time": result.get("diarization_time", 0),
                "total_time": time.time() - start_time,
                "rtf": (time.time() - start_time) / transcription_result.get("duration", 1)
            }
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Transcription with diarization failed: {e}")
            result["error"] = str(e)
            return result
    
    def _merge_transcription_with_speakers(self, text: str, diarization: Dict) -> List[Dict]:
        """Merge transcription text with speaker diarization timeline"""
        segments = []
        
        if not diarization.get("timeline"):
            # No diarization data, return whole text
            return [{
                "text": text,
                "speaker": "SPEAKER_00",
                "start_time": 0.0,
                "end_time": diarization.get("duration", 0.0)
            }]
        
        # Simple word-based splitting (in production, use proper alignment)
        words = text.split()
        if not words:
            return segments
        
        # Distribute words across speaker segments
        timeline = diarization["timeline"]
        words_per_second = len(words) / diarization.get("duration", 1.0)
        
        word_index = 0
        for segment in timeline:
            start_time = segment["start"]
            end_time = segment["end"]
            speaker = segment["speaker"]
            duration = end_time - start_time
            
            # Estimate words in this segment
            num_words = int(duration * words_per_second)
            segment_words = []
            
            for _ in range(num_words):
                if word_index < len(words):
                    segment_words.append(words[word_index])
                    word_index += 1
                else:
                    break
            
            if segment_words:
                segments.append({
                    "speaker": speaker,
                    "text": " ".join(segment_words),
                    "start_time": start_time,
                    "end_time": end_time,
                    "confidence": 0.85  # Placeholder confidence
                })
        
        # Add any remaining words to the last segment
        if word_index < len(words) and segments:
            segments[-1]["text"] += " " + " ".join(words[word_index:])
        
        return segments
    
    def _simulate_diarization(self, text: str, duration: float) -> List[Dict]:
        """Simulate speaker diarization for demonstration"""
        if not text:
            return []
        
        # Split text into sentences
        import re
        sentences = re.split(r'[.!?]+', text)
        sentences = [s.strip() for s in sentences if s.strip()]
        
        if not sentences:
            return [{
                "text": text,
                "speaker": "SPEAKER_00",
                "start_time": 0.0,
                "end_time": duration
            }]
        
        # Simulate speaker alternation
        segments = []
        time_per_sentence = duration / len(sentences) if sentences else 0
        
        for i, sentence in enumerate(sentences):
            segments.append({
                "speaker": f"SPEAKER_{i % 2:02d}",  # Alternate between 2 speakers
                "text": sentence + ".",
                "start_time": i * time_per_sentence,
                "end_time": (i + 1) * time_per_sentence,
                "confidence": 0.85
            })
        
        return segments


# Usage example
async def test_diarization():
    """Test transcription with diarization"""
    service = TranscriptionWithDiarization()
    
    # Initialize diarization
    await service.initialize_diarizer()
    
    # Test with an audio file
    test_audio = "/tmp/recordings/session_1753336650/recording.wav"
    
    print("🎯 Testing transcription with speaker diarization...")
    result = service.transcribe_with_speakers(test_audio)
    
    print(f"\n📝 Results:")
    print(f"Text: {result['text'][:100]}...")
    print(f"Speakers: {result.get('speakers', [])}")
    print(f"NPU Accelerated: {result['npu_accelerated']}")
    print(f"Diarization Enabled: {result['diarization_enabled']}")
    
    if result.get("segments"):
        print(f"\n🎤 Speaker segments ({len(result['segments'])} total):")
        for i, segment in enumerate(result["segments"][:3]):  # Show first 3
            print(f"  [{segment['start_time']:.1f}s - {segment['end_time']:.1f}s] "
                  f"{segment['speaker']}: {segment['text'][:50]}...")


if __name__ == "__main__":
    asyncio.run(test_diarization())