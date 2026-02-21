# Meeting-Ops Recording Appliance
Part of the Unicorn Commander Suite

## Project Overview
Hardware appliance for AI-powered meeting recording and transcription. NPU acceleration, real-time transcription, speaker diarization, and meeting insights. Designed for headless deployment on AMD Ryzen AI hardware for SMBs.

**Status**: Backend ~90% | Frontend ~70% | Auth working | Unified Agent working

## Quick Start

```bash
# Start Docker services
docker compose -f docker-compose-full-stack.yml up -d

# Start backend (port 9050)
cd backend && ./start-backend.sh

# Start frontend (port 7778)
cd frontend && npm run dev -- --host 0.0.0.0
```

**Login**: admin / admin123 (superuser)

**Access**:
- Frontend: http://your-server-ip:7778
- Backend API docs: http://your-server-ip:9050/docs

## Architecture

### Frontend (React 19 + TypeScript + Vite + TailwindCSS)
Active router: `AppRouterSimplified.tsx`

| Route | Page | Purpose |
|-------|------|---------|
| /login | Login.tsx | Authentication |
| /record | LiveRecording.tsx | Live recording + transcription |
| /sessions | Sessions.tsx | Session list + management |
| /sessions/:id | SessionDetails.tsx | Playback + transcript + export |
| /settings | SettingsEnhanced.tsx | System settings |
| /admin/agents | AgentDashboard.tsx | AI agent management |
| /admin/agents-old | AgentConfiguration.tsx | Legacy agent config |

Contexts: AuthContext, ThemeContext, RecordingContext
Shared components: Login, ErrorMessage, LoadingSpinner, RecordingIndicator, SessionCreator, MeetingIntelligenceDashboard

### Backend (FastAPI + Python 3.13)

**main.py** loads 19 routers with status tracking:
- 3 required (auth, recording, sessions) - fail fast
- 16 optional (agent, AI, analytics, etc.) - log warning on failure
- `/health` reports router status and real timestamps

**Key API routers** (in `backend/api/`):
- `simple_recording_db.py` - Recording CRUD + audio capture
- `sessions.py` - Session management
- `websocket_transcription.py` - Live transcription via WebSocket
- `websocket_auto_summary.py` - Progressive AI summaries
- `unified_agent_api.py` - AI agent configuration
- `meeting_intelligence_real.py` - AI-powered meeting analysis

**Key services** (in `backend/services/`):
- `working_audio_service.py` - USB mic audio capture
- `real_whisper_service.py` - NPU-accelerated Whisper
- `transcription_service.py` - Transcription orchestration
- `unified_agent_service.py` - AI agent (granite3.3:8b)
- `unified_llm_service.py` - LLM provider abstraction

### Infrastructure
- PostgreSQL (session/transcript storage)
- Redis (real-time pub/sub)
- Qdrant (vector search - not yet integrated)
- Docker Compose configs: full-stack, prod, dev

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
GET  /api/simple/recording-sessions/{id}/download/audio  # Download WAV
WS   /ws/transcription/{session_id}               # Live transcription
WS   /ws/audio-levels                             # Audio level monitoring
GET  /health                                       # Health + router status
GET  /api/status                                   # System status
```

## Known Issues
1. Transcription segments not saving to DB (column name mismatch)
2. UnifiedAgentService.analyze_meeting method incomplete
3. LiveRecordingTranscription parameter mismatch
4. PDF/DOCX export not implemented
5. Full-text/semantic search not implemented
6. Analytics dashboard visualizations pending
7. TypeScript build has ~42 errors (functionality works despite errors)

## Development Priorities
1. Fix TypeScript build errors for clean production builds
2. Fix database column mismatches (transcription segments)
3. Implement missing analyze_meeting method
4. Custom vocabulary system (industry acronyms)
5. Advanced export (PDF/DOCX)
6. Search & discovery (full-text + semantic)
7. Per-meeting AI chat
8. Meeting analytics dashboard

## File Structure (post-cleanup)
```
UC-Meeting-Ops/
  backend/
    main.py                    # FastAPI app, 19 routers
    api/                       # 19 API routers
    services/                  # 22 service modules
    auth/                      # JWT authentication
    database/                  # SQLAlchemy models + connection
    models/                    # Unified agent model
    npu_optimization/          # NPU kernels + config
    start-backend.sh           # Start script
  frontend/
    src/
      App.tsx                  # Root component
      AppRouterSimplified.tsx  # Router (7 routes)
      pages/                   # 7 page components
      components/              # 6 shared components
      contexts/                # 3 context providers
      hooks/                   # 1 hook (useKeyboardShortcuts)
      config.ts                # API URL configuration
  docker-compose-full-stack.yml
  docker-compose.prod.yml
  docker-compose.dev.yml
  start-meeting-ops.sh
  stop-stack.sh
```
