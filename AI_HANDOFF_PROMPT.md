# AI Assistant Handoff Prompt - Unicorn Commander Meeting Ops

## Project Overview
You are taking over development of Unicorn Commander, a meeting recording and transcription system running in Docker. The system has a React frontend and FastAPI backend with authentication working. Your task is to implement the core audio recording and transcription functionality.

## Current Status
- ✅ Docker deployment working (Frontend port 7776, Backend port 9050)
- ✅ Authentication functional (username: admin, password: admin123)
- ✅ Basic UI structure in place
- ❌ Audio recording not capturing actual audio
- ❌ Transcription not processing audio
- ❌ Ollama integration not connected

## Project Structure
```
/home/ucadmin/Development/Unicorn-Commander-Meeting-Ops/
├── frontend/                 # React TypeScript frontend
│   ├── src/
│   │   ├── components/      # UI components
│   │   ├── contexts/        # Auth context
│   │   └── App.tsx         # Main app
│   ├── Dockerfile
│   └── nginx.conf
├── backend/                 # FastAPI Python backend
│   ├── services/
│   │   ├── audio_service.py          # Audio capture (needs work)
│   │   ├── transcription_service.py  # Transcription (needs work)
│   │   └── settings_manager.py       # Settings management
│   ├── routers/
│   │   ├── recording.py     # Recording endpoints
│   │   ├── sessions.py      # Session management
│   │   └── streaming.py     # WebSocket endpoints
│   ├── main_docker.py       # Docker entry point
│   ├── auth_docker.py       # Simplified auth for Docker
│   ├── requirements-docker.txt
│   └── Dockerfile
├── docker-compose.yml       # Docker orchestration
└── MASTER_PRIORITY_CHECKLIST.md  # Detailed task list
```

## Critical Files to Modify

### Backend Audio Capture
**File**: `/home/ucadmin/Development/Unicorn-Commander-Meeting-Ops/backend/services/audio_service.py`
- Currently uses dummy audio generation
- Need to implement real PyAudio capture
- Must handle device selection from settings

### Backend Transcription
**File**: `/home/ucadmin/Development/Unicorn-Commander-Meeting-Ops/backend/services/transcription_service.py`
- Currently returns dummy transcriptions
- Need to load ONNX Whisper model
- Process audio chunks and return real text

### WebSocket Streaming
**File**: `/home/ucadmin/Development/Unicorn-Commander-Meeting-Ops/backend/routers/streaming.py`
- WebSocket endpoint exists at `/ws/stream/{session_id}`
- Need to ensure audio chunks are processed and transcriptions broadcast

### Frontend Display
**File**: `/home/ucadmin/Development/Unicorn-Commander-Meeting-Ops/frontend/src/components/RecordingDashboard.tsx`
- Need to display live transcriptions from WebSocket
- Show speaker indicators when implemented

## Docker Considerations
- Audio device access: May need `--device /dev/snd` in docker-compose.yml
- Model storage: Create volume for ONNX models
- Ollama access: Network connectivity to host port 11434

## Phase 1 Tasks (Priority Order)

### 1. Enable Audio Capture (2-3 hours)
```python
# In backend/services/audio_service.py
# Replace generate_dummy_audio() with real PyAudio capture
# Use settings for device selection
# Test with: curl http://localhost:7776/api/audio-devices
```

### 2. Load Whisper Model (1-2 hours)
```python
# In backend/services/transcription_service.py
# Download whisper-base ONNX model
# Initialize in __init__ or on first use
# Cache in /app/whisper_models/
```

### 3. Process Audio Chunks (2-3 hours)
```python
# Implement process_audio_chunk() method
# Convert audio to mel spectrogram
# Run through Whisper model
# Return transcription with timestamp
```

### 4. WebSocket Broadcasting (1-2 hours)
```python
# In streaming.py websocket_endpoint()
# Ensure transcriptions are sent to connected clients
# Format: {"text": "...", "timestamp": ..., "speaker": "..."}
```

### 5. Frontend Display (1-2 hours)
```typescript
// In RecordingDashboard.tsx
// Subscribe to WebSocket
// Display incoming transcriptions
// Auto-scroll transcript
```

## Testing Commands
```bash
# Check if backend is healthy
curl http://localhost:7776/api/status

# List audio devices
curl http://localhost:7776/api/audio-devices -H "Authorization: Bearer YOUR_TOKEN"

# Start recording session
curl -X POST http://localhost:7776/api/recording-sessions \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title": "Test Recording"}'

# Check Ollama connection (from inside container)
docker exec unicorn-backend curl http://host.docker.internal:11434/api/tags
```

## Success Criteria
1. Can select microphone and see audio levels
2. Live transcription appears as you speak
3. Audio files are saved and playable
4. Can generate summary via Ollama
5. WebSocket doesn't drop connection

## Gotchas & Tips
- Docker audio: May need `--privileged` flag or PulseAudio socket
- CORS is already configured for all origins
- Auth token required for most endpoints
- Models should be cached to avoid re-downloading
- Use `docker logs unicorn-backend -f` to debug

## Recommended Approach
1. Start with hardcoded audio device (index 0)
2. Get basic transcription working with whisper-tiny
3. Add device selection after basics work
4. Optimize with larger models later

## Available Models & Services
- Whisper ONNX models: Use `whisper-base` for balance of speed/quality
- Ollama: Running on host at `localhost:11434` with `gemma3n` model
- NPU acceleration: Available but implement CPU version first

## Question for You
Would you prefer to:
A) Implement everything in one go
B) Start with just audio capture and verify it works
C) Mock audio but get transcription pipeline working first

The codebase is ready for development. All authentication and infrastructure is working. Focus on making audio → transcription → display pipeline functional.