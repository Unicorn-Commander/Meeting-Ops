import numpy as np
from typing import Dict

class WhisperXNPUEngine:
    def __init__(self):
        # Initialize with mock NPU acceleration
        self.npu_metrics = {
            "enabled": True,
            "speedup_factor": 220,  # Matches real NPU performance
            "rtf": 0.004,  # Real-time factor
            "device": "AMD NPU Phoenix"
        }
        print(f"WhisperX NPU Engine initialized with metrics: {self.npu_metrics}")
    
    def _generate_mock_transcription(self) -> Dict:
        """Generates a mock transcription in the expected format."""
        return {
            "segments": [
                {
                    "start": 0.0,
                    "end": 2.5,
                    "text": "Hello, this is a test.",
                    "speaker": "SPEAKER_00",
                    "confidence": 0.95,
                    "words": [
                        {"word": "Hello", "start": 0.0, "end": 0.3, "confidence": 0.98},
                        {"word": "this", "start": 0.4, "end": 0.6, "confidence": 0.97}
                    ]
                },
                {
                    "start": 3.0,
                    "end": 5.0,
                    "text": "This is a second sentence.",
                    "speaker": "SPEAKER_01",
                    "confidence": 0.92,
                    "words": [
                        {"word": "This", "start": 3.0, "end": 3.2, "confidence": 0.95},
                        {"word": "is", "start": 3.3, "end": 3.4, "confidence": 0.94}
                    ]
                }
            ],
            "language": "en"
        }

    def transcribe_chunk(self, audio_data: np.ndarray) -> Dict:
        # Return mock transcription with speaker diarization
        print(f"Mock transcribe_chunk called with audio data of shape: {audio_data.shape}")
        return self._generate_mock_transcription()
    
    def transcribe(self, audio_path: str) -> Dict:
        # Full file transcription with diarization
        print(f"Mock transcribe called for file: {audio_path}")
        return self._generate_mock_transcription()
    
    def transcribe_file(self, audio_path: str, diarize: bool = True) -> Dict:
        # Wrapper method supporting diarization flag
        print(f"Mock transcribe_file called for file: {audio_path} with diarize={diarize}")
        return self._generate_mock_transcription()
