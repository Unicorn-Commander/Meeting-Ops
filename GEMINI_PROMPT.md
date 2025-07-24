# Gemini Development Prompt - Unicorn Commander Meeting Ops

## Project Overview
You are working on **Unicorn Commander Meeting Ops**, a local-first, AI-powered meeting room recording appliance with NPU acceleration. The project features real-time transcription, speaker diarization, and meeting insights, designed for headless deployment on hardware appliances for SMBs.

## Current System Status

### ✅ Recently Completed by Claude
1. **Fixed WebSocket authentication** in `/home/ucadmin/Development/Unicorn-Commander-Meeting-Ops/backend/api/recording_v2.py` (lines 269-293)
2. **Implemented complete search & memory system**:
   - NPU-accelerated embedding service
   - Knowledge graph extraction from meetings
   - Unified search with semantic, keyword, and graph strategies
   - Full API layer and React UI

### 🚧 Your Current Task: WhisperX NPU Engine Stub (Task #208)

**Objective**: Create a WhisperX NPU engine stub to resolve import issues and enable the unified transcription service.

**Background**: The project uses WhisperX for unified STT + speaker diarization. There are import errors when trying to use the real WhisperX implementation, so we need a stub that provides the same interface.

## Implementation Requirements

### 1. Create WhisperX NPU Engine Stub

**File**: `/home/ucadmin/Development/Unicorn-Commander-Meeting-Ops/backend/stt_engine/whisperx_npu_engine.py`

This file should implement:
```python
class WhisperXNPUEngine:
    def __init__(self):
        # Initialize with mock NPU acceleration
        pass
    
    def transcribe_chunk(self, audio_data: np.ndarray) -> Dict:
        # Return mock transcription with speaker diarization
        # Format: {"segments": [...], "language": "en"}
        pass
    
    def transcribe(self, audio_path: str) -> Dict:
        # Full file transcription with diarization
        pass
    
    def transcribe_file(self, audio_path: str, diarize: bool = True) -> Dict:
        # Wrapper method supporting diarization flag
        pass
```

### 2. Expected Output Format

The stub should return data in this format:
```json
{
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
        }
    ],
    "language": "en"
}
```

### 3. Integration Points

The stub needs to work with:
- **Unified Transcription Service**: `/home/ucadmin/Development/Unicorn-Commander-Meeting-Ops/backend/services/transcription_service.py`
- **Audio Session Manager**: `/home/ucadmin/Development/Unicorn-Commander-Meeting-Ops/backend/services/audio_session_manager.py`
- **Recording API v2**: `/home/ucadmin/Development/Unicorn-Commander-Meeting-Ops/backend/api/recording_v2.py`

### 4. Mock NPU Acceleration

Include mock NPU performance metrics:
```python
self.npu_metrics = {
    "enabled": True,
    "speedup_factor": 220,  # Matches real NPU performance
    "rtf": 0.004,  # Real-time factor
    "device": "AMD NPU Phoenix"
}
```

## Testing Your Implementation

### 1. Test Import
```bash
cd /home/ucadmin/Development/Unicorn-Commander-Meeting-Ops/backend
python -c "from stt_engine.whisperx_npu_engine import WhisperXNPUEngine"
```

### 2. Test Transcription
Create a test script at `/home/ucadmin/Development/Unicorn-Commander-Meeting-Ops/backend/test_whisperx_stub.py`:
```python
from stt_engine.whisperx_npu_engine import WhisperXNPUEngine
import numpy as np

engine = WhisperXNPUEngine()

# Test chunk transcription
audio_chunk = np.random.randn(16000)  # 1 second of audio
result = engine.transcribe_chunk(audio_chunk)
print("Chunk result:", result)

# Test file transcription
result = engine.transcribe_file("test_audio.wav")
print("File result:", result)
```

### 3. Test WebSocket Integration
After implementing the stub, test the WebSocket recording:
```bash
# Start backend
cd /home/ucadmin/Development/Unicorn-Commander-Meeting-Ops/backend
python main.py

# In another terminal, test WebSocket
# You'll need a valid JWT token from login
```

## Additional Files You May Need to Check

1. **NPU Optimization Directory**: `/home/ucadmin/Development/Unicorn-Commander-Meeting-Ops/backend/npu_optimization/`
   - Contains existing NPU acceleration implementations
   - Look at `whisperx_npu_engine.py` for reference

2. **Settings Manager**: `/home/ucadmin/Development/Unicorn-Commander-Meeting-Ops/backend/services/settings_manager.py`
   - Check how STT models are configured

3. **Database Models**: `/home/ucadmin/Development/Unicorn-Commander-Meeting-Ops/backend/database/models.py`
   - Understand transcription data storage

## Success Criteria

✅ The WhisperX NPU engine stub can be imported without errors  
✅ It returns properly formatted transcription data with speaker diarization  
✅ The unified transcription service can use it successfully  
✅ WebSocket recording sessions work with the stub  
✅ Mock performance metrics indicate NPU acceleration  

## Important Notes

1. **Keep it Simple**: This is a stub/mock implementation. Focus on making imports work and returning realistic data.

2. **Maintain Compatibility**: The interface must match what the real WhisperX would provide.

3. **Use Existing Patterns**: Look at the existing code structure in the `stt_engine` directory for consistency.

4. **Test Incrementally**: Test imports first, then basic functionality, then integration.

## Next Steps After Completion

Once Task #208 is complete, the next priorities are:
- Task #209: Test WebSocket real-time transcription with the new service
- Task #214: Set up AMD Phoenix NPU drivers (requires hardware access)

Good luck! Let me know if you need any clarification or run into issues.