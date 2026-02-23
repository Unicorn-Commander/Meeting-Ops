# Meeting-Ops Recording Appliance
Part of the Unicorn Commander Suite

## Project Overview
Hardware appliance for AI-powered meeting recording and transcription. NPU acceleration, real-time transcription, speaker diarization, and meeting insights. Designed for headless deployment on AMD Ryzen AI hardware for SMBs.

**Status**: Backend ~95% | Frontend ~95% | Auth working | LLM integrated | Mobile responsive

## Quick Start

```bash
# Start Docker services (PostgreSQL on 5434, llama.cpp GPT-OSS-20B on 11437)
docker compose -f docker-compose-full-stack.yml up -d

# Start backend (port 9050)
cd backend && ./start-backend.sh

# Start frontend (port 7777)
cd frontend && npm run dev -- --host 0.0.0.0

# Run tests
cd backend && python3 -m pytest tests/ -v    # 40 pass, 3 skip
cd frontend && npm run build                  # 0 TS errors
cd frontend && npx vitest run                 # 23 pass
```

**Login**: admin / admin123 (superuser)

**Access**:
- Frontend: http://your-server-ip:7777
- Backend API docs: http://your-server-ip:9050/docs

## Architecture

### LLM: GPT-OSS 20B on llama.cpp Vulkan (default)
- Default model: `gpt-oss-20b-mxfp4.gguf` in `./models/` (~28 tok/s, ~12GB VRAM)
- Fallback model: `granite-3.3-2b-instruct-Q4_K_M.gguf` (~43 tok/s, ~1.5GB VRAM)
- Model registry: `backend/config/model_registry.py` — centralized model configs
- Active model setting: `ai.llm_model` in settings_manager (persisted to DB)
- Token multiplier: GPT-OSS uses Harmony prompt format with hidden reasoning tokens (3x multiplier applied automatically)
- API: OpenAI-compatible `/v1/chat/completions` at port 11437
- GPU: AMD 780M iGPU via Vulkan (RADV)
- Used for: summaries, titles, AI chat, insights, sentiment analysis
- Switch models: `POST /api/settings/models/active` or Settings UI dropdown

### Frontend (React 19 + TypeScript + Vite + TailwindCSS)
Active router: `AppRouterSimplified.tsx` (mobile-responsive with hamburger menu)

| Route | Page | Purpose |
|-------|------|---------|
| /login | Login.tsx | Authentication |
| /record | LiveRecording.tsx | Recording + live transcription |
| /sessions | Sessions.tsx | Session list + search + pagination |
| /sessions/:id | SessionDetails.tsx | Playback + transcript + export + AI chat |
| /settings | SettingsEnhanced.tsx | System settings + vocabulary |
| /admin/agents | AgentDashboard.tsx | AI agent management |
| /admin/agents-old | AgentConfiguration.tsx | Legacy agent config |

Contexts: AuthContext, ThemeContext, RecordingContext
Shared components: Login, ErrorMessage, LoadingSpinner, RecordingIndicator, SessionCreator, Toast, MeetingIntelligenceDashboard

### Backend (FastAPI + Python 3.13)

**main.py** loads 22 routers with status tracking:
- 3 required (auth, recording, sessions) - fail fast
- 19 optional (agent, AI, analytics, satellite, etc.) - log warning on failure
- `/health` reports router status and real timestamps

**Key API routers** (in `backend/api/`):
- `simple_recording_db.py` - Recording CRUD + audio capture + full-text search
- `sessions.py` - Session management
- `ai_chat.py` - Per-meeting AI chat (real LLM)
- `ai_insights.py` - AI-powered insights (keywords, sentiment, action items via _call_llm)
- `ai_settings.py` - Model list/switch endpoints, AI settings
- `analytics_simple.py` - Speaker analytics + duration trends
- `batch_export.py` - PDF/DOCX/TXT/JSON/SRT export
- `vocabulary.py` - Custom vocabulary CRUD
- `websocket_transcription.py` - Live transcription via WebSocket
- `websocket_auto_summary.py` - Progressive AI summaries
- `satellite_api.py` - Satellite device CRUD, heartbeat, audio/transcript upload
- `websocket_satellite.py` - Real-time audio streaming from satellite devices
- `websocket_remote_audio.py` - Companion app remote audio WebSocket

**Key services** (in `backend/services/`):
- `unified_llm_service.py` - LLM via llama.cpp OpenAI API (reads model from model_registry, applies token multiplier)
- `unified_agent_service.py` - Progressive summarization (reads model from model_registry)
- `working_audio_service.py` - USB mic audio capture
- `real_whisper_service.py` - NPU-accelerated Whisper
- `transcription_service.py` - Transcription orchestration

### Infrastructure
- PostgreSQL on port 5434 (session/transcript storage)
- Redis (real-time pub/sub)
- llama.cpp Vulkan on port 11437 (GPT-OSS 20B default, Granite 3.3 2B fallback)
- Qdrant on port 6335 (hybrid vector search — dense + BM25 sparse)

### NPU (AMD Phoenix, 16 TOPS)
- 220x speedup over CPU, 0.0045 RTF
- 4,789 tokens/sec, INT8 via MLIR-AIE2
- Whisper Large-v3 default model

## API Endpoints

```
POST /api/auth/login                              # Login (admin/admin123)
POST /api/simple/recording-sessions               # Create session
POST /api/simple/recording-sessions/{id}/start    # Start recording
POST /api/simple/recording-sessions/{id}/stop     # Stop recording
GET  /api/simple/recording-sessions               # List sessions
GET  /api/simple/recording-sessions/{id}          # Get session + transcript
GET  /api/simple/recording-sessions/search?q=...  # Full-text search
GET  /api/simple/recording-sessions/{id}/download/audio   # Download WAV
GET  /api/simple/recording-sessions/{id}/download/summary/pdf   # PDF export
GET  /api/simple/recording-sessions/{id}/download/summary/docx  # DOCX export
POST /api/ai-chat/sessions/{id}/messages          # AI chat with meeting context
POST /api/ai-chat/rag/query                       # Cross-meeting RAG query (multi-turn)
GET  /api/ai-chat/rag/history                     # RAG chat history
GET  /api/simple/recording-sessions/semantic-search?q=...  # Hybrid semantic search (Qdrant)
GET  /api/analytics/summary                       # Analytics with speaker data
GET  /api/analytics/speakers                      # Speaker analytics
GET  /api/analytics/duration-trends               # Duration trends
GET  /api/simple/recording-sessions/{id}/insights  # AI insights (keywords, sentiment)
WS   /ws/transcription/{session_id}               # Live transcription
WS   /ws/audio-levels                             # Audio level monitoring
GET  /api/settings/models                          # Model info + status
GET  /api/settings/models/available                # List all models with active indicator
POST /api/settings/models/active                   # Switch active LLM model
GET  /health                                       # Health + router status
# Satellite Devices
POST /api/satellites/register                      # Register satellite device
GET  /api/satellites                               # List all satellites
GET  /api/satellites/{device_id}                   # Get satellite details
PUT  /api/satellites/{device_id}                   # Update satellite config
DELETE /api/satellites/{device_id}                  # Remove satellite
POST /api/satellites/{device_id}/heartbeat         # Device heartbeat
POST /api/satellites/{device_id}/upload-audio       # Upload WAV (store-and-forward)
POST /api/satellites/{device_id}/transcript         # Upload transcript (local STT)
POST /api/satellites/{device_id}/start-recording    # Trigger recording
POST /api/satellites/{device_id}/stop-recording     # Stop recording
GET  /api/satellites/rooms                          # List rooms with satellites
WS   /ws/satellite/{device_id}/audio               # Real-time satellite audio stream
# Companion App
WS   /ws/remote-audio/{session_id}                  # Remote audio stream from companion app
```

### MCP Server (Model Context Protocol)
Standalone MCP server for external AI agent access to Meeting-Ops data.
- Location: `mcp/meeting_ops_mcp.py`
- Transport: stdio (for Claude Desktop, Open WebUI, etc.)
- 8 tools: search_meetings, ask_about_meetings, list_meetings, get_meeting_details, get_meeting_transcript, chat_with_meeting, get_analytics, get_meeting_insights
- 2 resources: meetings://list, meetings://{session_id}
- 2 prompts: meeting_analysis, cross_meeting_research
- Config: `MEETING_OPS_URL`, `MEETING_OPS_USER`, `MEETING_OPS_PASS` env vars

```bash
# Run standalone
python3 mcp/meeting_ops_mcp.py

# Claude Desktop config (~/.claude/claude_desktop_config.json)
# { "mcpServers": { "meeting-ops": { "command": "python3", "args": ["/path/to/mcp/meeting_ops_mcp.py"] } } }
```

## Known Issues
1. Audio file path occasional double-nesting of path components

## File Structure
```
UC-Meeting-Ops/
  backend/
    main.py                    # FastAPI app, 22 routers
    api/                       # 22 API routers (incl. satellite, remote audio)
    services/                  # 22 service modules
    auth/                      # JWT authentication
    database/                  # SQLAlchemy models + connection
    models/                    # Unified agent + vocabulary models
    config/                    # AI backend config + model registry
    tests/                     # 8 test files (39 tests)
    start-backend.sh           # Start script
  frontend/
    src/
      App.tsx                  # Root component (+ ToastContainer)
      AppRouterSimplified.tsx  # Router (7 routes, mobile responsive)
      pages/                   # 7 page components
      components/              # 7 shared components (+ Toast.tsx)
      contexts/                # 3 context providers
      hooks/                   # 1 hook (useKeyboardShortcuts)
      __tests__/               # 4 test files (23 tests)
      config.ts                # API URL configuration
  mcp/
    meeting_ops_mcp.py         # MCP server for external AI agents (8 tools)
  docs/                        # Design documents
    companion-app-design.md    # Mac/PC companion app architecture
    satellite-devices-design.md # ESP32/RPi satellite device specs
  models/                      # GGUF model files for llama.cpp
  docker-compose-full-stack.yml
```
