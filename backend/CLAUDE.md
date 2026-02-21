# Meeting-Ops Backend Development Guide

## Quick Start
```bash
cd backend
./start-backend.sh  # Starts on port 9050

# Or manually:
source venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 9050 --reload

# Database (PostgreSQL via Docker)
docker compose -f docker-compose-full-stack.yml up -d
# Connection: postgresql://meetingops:REMOVED@localhost:5432/meeting_sessions
```

## Architecture

### main.py
Loads 19 routers via `_load_router()` with status tracking:
- **Required** (3): auth, recording (simple_recording_db), sessions - fail fast on error
- **Optional** (16): all others - log warning, report in /health

`/health` returns `{"status": "healthy"|"degraded", "routers_loaded": N, "routers_failed": [...]}` with real timestamps.

### API Routers (backend/api/)
| Router | Purpose |
|--------|---------|
| simple_recording_db.py | Recording CRUD, audio capture, file management |
| sessions.py | Session listing and management |
| meeting_management.py | Meeting operations |
| meeting_intelligence_real.py | AI-powered meeting analysis |
| ai_settings.py | AI model configuration |
| agent_management_api.py | Agent CRUD |
| meeting_notes_unified.py | Meeting notes (multi-model) |
| websocket_transcription.py | Live transcription WebSocket |
| websocket_auto_summary.py | Progressive AI summaries |
| unified_agent_api.py | Unified agent config |
| live_transcription.py | Live transcription control |
| analytics_simple.py | Basic analytics |
| ai_insights.py | AI insights endpoint |
| ai_chat.py | AI chat interface |
| vocabulary.py | Custom vocabulary management |
| batch_export.py | Batch export |
| audio_upload.py | Audio file upload |
| simple_settings.py | Settings management |

### Services (backend/services/)
| Service | Purpose | Status |
|---------|---------|--------|
| working_audio_service.py | USB mic recording via FFmpeg | Working |
| real_whisper_service.py | NPU-accelerated Whisper | Working |
| transcription_service.py | Transcription orchestration | Working |
| unified_agent_service.py | AI agent (granite3.3:8b) | Missing analyze_meeting |
| unified_llm_service.py | LLM provider abstraction | Working |
| auto_summarization_service.py | Auto-summarization | Working |
| live_recording_transcription.py | Live transcription during recording | Parameter issue |
| live_transcription_service.py | Live transcription service | Working |
| llm_service.py | Gemma/LLM service | Working |
| meeting_notes_service.py | Meeting notes generation | Working |
| agent_manager_service.py | Agent management | Working |
| websocket_registry.py | WebSocket connection tracking | Working |
| whisperx_npu_service.py | WhisperX NPU integration | Working |
| system_service.py | System info | Working |
| progressive_interval_manager.py | Summary interval logic | Working |
| settings_manager.py | Settings persistence | Working |
| performance_metrics_service.py | Performance tracking | Working |
| stt_model_manager.py | STT model management | Working |
| model_providers.py | Model provider config | Working |

### Database
```
PostgreSQL tables:
- recording_sessions (id, session_id, title, status, created_at, started_at, ended_at, audio_file, transcript, summary, duration, ...)
- transcriptions (id, session_id, text, speaker, start_time, end_time, confidence, created_at)
- unified_agents (id, name, system_prompt, model_name, config)
```

## Known Issues

1. **Transcription segments not saving** - Column name mismatch (timestamp vs created_at)
2. **analyze_meeting missing** - UnifiedAgentService needs this method implemented
3. **live_recording_transcription** - start_monitoring parameter mismatch
4. **Audio file path** - Occasional double-nesting of path components

## Testing
```bash
# Health check
curl http://localhost:9050/health

# Create + record session
SESSION=$(curl -s -X POST http://localhost:9050/api/simple/recording-sessions \
  -H "Content-Type: application/json" -d '{"name":"Test"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
curl -X POST http://localhost:9050/api/simple/recording-sessions/$SESSION/start
sleep 10
curl -X POST http://localhost:9050/api/simple/recording-sessions/$SESSION/stop
curl http://localhost:9050/api/simple/recording-sessions/$SESSION
```

## NPU Performance
- Whisper Large-v3: 220x speedup, 0.0045 RTF
- 1 hour audio processed in 16.2 seconds
- 4,789 tokens/sec, INT8 via MLIR-AIE2
