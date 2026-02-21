# Meeting-Ops Backend Development Guide

## Quick Start
```bash
cd backend
./start-backend.sh  # Starts on port 9050

# Or manually:
uvicorn main:app --host 0.0.0.0 --port 9050 --reload

# Database (PostgreSQL via Docker on port 5434)
docker compose -f docker-compose-full-stack.yml up -d
# Connection: postgresql://meetingops:REMOVED@localhost:5434/meeting_sessions

# LLM (Granite 3.3 2B via llama.cpp Vulkan on port 11437)
# Started by docker-compose, OpenAI-compatible API
```

## Architecture

### LLM Integration
- Model: Granite 3.3 2B (Q4_K_M GGUF) on llama.cpp Vulkan
- API: OpenAI-compatible `/v1/chat/completions` at `http://localhost:11437`
- Service: `services/unified_llm_service.py` (singleton, `llm_service` global)
- Used by: ai_chat, ai_insights, unified_agent_service, meeting_notes_service

### main.py
Loads 19 routers via `_load_router()` with status tracking:
- **Required** (3): auth, recording (simple_recording_db), sessions - fail fast on error
- **Optional** (16): all others - log warning, report in /health

`/health` returns `{"status": "healthy"|"degraded", "routers_loaded": N, "routers_failed": [...]}` with real timestamps.

### API Routers (backend/api/)
| Router | Purpose |
|--------|---------|
| simple_recording_db.py | Recording CRUD, audio capture, search, vocabulary integration |
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
| analytics_simple.py | Speaker analytics + duration trends |
| ai_insights.py | AI insights (keywords, sentiment, action items via LLM) |
| ai_chat.py | Per-meeting AI chat (real LLM with transcript context) |
| vocabulary.py | Custom vocabulary CRUD |
| batch_export.py | PDF/DOCX/TXT/JSON/SRT export |
| audio_upload.py | Audio file upload |
| simple_settings.py | Settings management |

### Services (backend/services/)
| Service | Purpose | Status |
|---------|---------|--------|
| unified_llm_service.py | Granite 3.3 2B via llama.cpp OpenAI API | Working |
| unified_agent_service.py | Progressive summarization (single model) | Working |
| working_audio_service.py | USB mic recording via FFmpeg | Working |
| real_whisper_service.py | NPU-accelerated Whisper | Working |
| transcription_service.py | Transcription orchestration | Working |
| llm_service.py | LLM service (llama.cpp backend) | Working |
| meeting_notes_service.py | Meeting notes generation | Working |
| auto_summarization_service.py | Auto-summarization | Working |
| live_transcription_service.py | Live transcription service | Working |
| agent_manager_service.py | Agent management | Working |
| websocket_registry.py | WebSocket connection tracking | Working |
| model_providers.py | Model provider config (OpenAI-compatible) | Working |
| settings_manager.py | Settings persistence | Working |

### Database
```
PostgreSQL (port 5434):
- recording_sessions (id, session_id, name, title, status, created_at, started_at, ended_at, audio_file, transcript, transcript_simple, transcript_diarized, summary, final_summary, duration, ...)
- transcriptions (id, session_id, text, speaker, start_time, end_time, confidence, created_at)
- unified_agents (id, name, system_prompt, model_name, config)
- custom_vocabulary (id, term, expansion, category, priority, is_active, case_sensitive, regex_pattern)
- vocabulary_sets (id, name, description, terms)
```

### Config (backend/config/)
- `ai_backends.py` - Single backend: llama.cpp at localhost:11437
- `dual_ai_backends.py` - Backward-compat wrapper (same single backend)

## Known Issues
1. **Audio file path** - Occasional double-nesting of path components
2. **Qdrant vector search** - Not yet integrated (full-text SQL search available)

## Testing
```bash
# Run all tests (39 pass, 3 skip)
python3 -m pytest tests/ -v

# Test files:
# test_auth.py (6 tests) - login, token, protected routes
# test_health.py (3 tests) - health, status endpoints
# test_recording.py (8 tests) - CRUD lifecycle
# test_export.py (3 tests) - transcript download
# test_analytics.py (4 tests) - summary, sessions, performance
# test_search_analytics.py (15 tests) - search, analytics, AI insights
# test_vocabulary.py (3 tests, skipped on SQLite) - vocab CRUD
```

## NPU Performance
- Whisper Large-v3: 220x speedup, 0.0045 RTF
- 1 hour audio processed in 16.2 seconds
- 4,789 tokens/sec, INT8 via MLIR-AIE2
