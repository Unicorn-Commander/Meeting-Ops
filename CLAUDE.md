# Meeting-Ops Recording Appliance
Part of the Unicorn Commander Suite

## Project Overview
Hardware appliance for AI-powered meeting recording and transcription. NPU acceleration, real-time transcription, speaker diarization, and meeting insights. Designed for headless deployment on AMD Ryzen AI hardware for SMBs. Cloud build (v0.7.x) and on-prem appliance build ship from the same codebase via compose targets.

**Status**: Backend ~95% | Frontend ~95% | Auth working | LLM integrated | Mobile responsive | Phase B server-live streaming with Sortformer speakers + EOU detection LIVE | Brigade graph writes LIVE

**Latest release**: v2.3.0 tagged 2026-05-27; PWA service worker switched to prompt/parked (skipWaiting false) so a deploy never swaps cached chunks mid-recording — update banner defers while recording (live or always-on) and surfaces on stop. On top of v2.2.0 (opt-in Sortformer canonical-hybrid diarization for `/finalize-audio`, PARKED — default stays pyannote; Sortformer v1 one-shot diarize OOMs on real-length meetings, see CHANGELOG), on top of v2.1.0 (2026-05-26) utterance-grouped per-word streaming UI, on top of v2.0.0 (v2 endpoint wire-up with per-word `tokens_finalized` + EOU detection) + v1.5.0 (parakeet checkpoint swap to streaming-trained `parakeet_realtime_eou_120m-v1`) + v1.4.0 (`<ServerLiveTranscript>` wired into Record page) + v1.3.0 (cursor + VAD silence-gate) + v1.2.0 (Sortformer parallel dispatch + speaker badges) + v1.1.0 (catch-up of post-v1.0.0 commits). Operational runbook at `docs/runbook-streaming-v2.md`. Backend pytest: 338 passed / 0 failed / 3 skipped.

## Architecture is browser-first by design

Live STT and live summarization run in the user's browser (Parakeet 0.6B INT8 + Qwen 3 0.6B / Gemma 4 E2B via onnxruntime-web + transformers.js, cached in IndexedDB). The server only runs at meeting completion (Parakeet 1.1B fp16 + pyannote 3.1 + wespeaker embeddings + Qwen 3.6 35B-A3B-Vision), in a single 30-90 second pass per finished meeting. Privacy mode skips the server pass entirely; nothing leaves the device.

This isn't an aesthetic choice — it's the moat. Our marginal cost per concurrent user-hour is $0 in compute (the user's CPU/GPU does it). Competitors pay AssemblyAI / Deepgram per audio-minute and OpenAI / Anthropic per token, per user, continuously. At scale we're 10-100x cheaper to run.

**Default new features to browser-side compute.** Only fold a feature into the server completion pass if quality genuinely requires it. Only reach for a third-party API as a last resort, behind a feature flag, with the cost owner explicit. See `docs/compute-economics.md` for the full strategy doc + the decision tree for future architecture choices.

## Design docs

Canonical index: `docs/README.md`. It groups every document in `docs/` by topic, includes line counts, and records shipped vs designed status.

- `docs/compute-economics.md`: Browser-first compute model, pricing tiers, cost moat, and deployment topology.
- `docs/POSTGRESQL_QDRANT_SETUP.md`: PostgreSQL plus Qdrant setup, SQLite migration, and semantic search operations.
- `docs/WYOMING_PROTOCOL.md`: Wyoming Protocol reference for Home Assistant satellites, wake words, gestures, and remote activation.
- `docs/always-on-recording-design.md`: Earlier continuous recording and silence-gap segmentation design.
- `docs/companion-app-design.md`: Desktop companion app design for mic plus system-audio capture.
- `docs/satellite-devices-design.md`: ESP32-S3 and Raspberry Pi satellite-device architecture.
- `docs/phase-b-server-live-streaming.md`: Paid-tier server-live streaming design with Parakeet streaming and Qwen rolling summaries.
- `docs/phase-c1-native-ios-design.md`: Native iOS, Core ML, SwiftUI, watchOS, FluidAudio, and Apple Foundation Models plan.
- `docs/bulk-audio-import-design.md`: Bulk import pipeline for the 526-file backlog and `/import` workflow.
- `docs/conference-room-design.md`: Conference Room mode, room entities, USB mic path, and satellite convergence.
- `docs/brigade-integration-design.md`: Meeting-Ops to Brigade graph writer and 3D viewer integration.
- `docs/appliance-extraction-design.md`: Appliance extraction into a separate enterprise on-prem repo via submodule.
- `docs/screen-recording-design.md`: Personal screen plus audio recording MVP design.
- `docs/image-registry-decision.md`: Forgejo container registry decision for canonical image distribution.

## Active roadmap

Mobile and native roadmap is locked as A → B → C-1 → C-2 → C-3:

1. Phase A, mobile PWA capture-only: SHIPPED v0.8.0 + v0.8.1. Mobile captures + uploads with completion processing after stop.
2. Phase B, server-live streaming: SHIPPED through v2.1.0. Sortformer 4-speaker live diarization, Parakeet realtime-EOU 120M streaming, per-word `tokens_finalized` + EOU detection, utterance-grouped UI in the Record page. Gated on `hasFeature('server_live')` (enterprise/pro/superuser). See `docs/runbook-streaming-v2.md` for operational details. Remaining: Opus uplink (utility shipped v1.2.0 but capture path not wired), full deprecation of v1.3.0 cursor+VAD workarounds (cheap insurance for now).
3. Phase C-1, native iOS: C-1.2 SHIPPED on local branch `/Users/aaronstransky/UC-Meeting-Ops-iOS/phase-c1-2-fluidaudio @ 0ed9982`. TranscriptionService + GRDB schema + BackgroundAudioUploader + SessionViewModel. Swift build clean, 14 tests pass. Xcode target wiring still pending. No Forgejo remote yet.
4. Phase C-2, watchOS extension on top of C-1: future.
5. Phase C-3, native Android plus NNAPI: future.

Queued behind product/design decisions:
- Sortformer canonical /finalize-audio: opt-in hybrid SHIPPED v2.2.0 but PARKED — Sortformer v1 one-shot diarize OOMs on real-length meetings (38-min needs ~25 GiB on the 12 GB 3060). pyannote stays canonical. Promotion needs chunk+embedding-stitch, the streaming-state API, or NeMo 2.5. See CHANGELOG 2.2.0 + runbook.
- Free-tier reframe (Privacy Mode → Free Tier UX relabel)
- PWA deploy coordination: SHIPPED v2.3.0 — SW switched to prompt/parked (skipWaiting false); update banner deferred while recording (live or always-on), surfaces on stop.
- Pricing decision + Stripe checkout build

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
1. MeetingIntelligenceDashboard live notes/final report generation endpoints not yet implemented (buttons disabled)

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

## Cloud deployment (bigboy)

The cloud Meeting-Ops instance lives at `/home/muut/Production/UC-Meeting-Ops/` on bigboy (magicunicorn on Tailscale, 100.121.80.175). Source tree is at `/home/muut/Production/UC-Meeting-Ops/src/` (where .git lives).

### Compose invocation quirk

`deploy/` is symlinked from the project root: `/home/muut/Production/UC-Meeting-Ops/deploy → src/deploy`. The compose file uses a build context of `../../src/backend` which only resolves via the symlinked path. Therefore:

```bash
# CORRECT — run from project root (where the symlink is)
cd /home/muut/Production/UC-Meeting-Ops/
docker compose --env-file deploy/bigboy/.env.bigboy -f deploy/bigboy/docker-compose.bigboy.yml up -d --force-recreate --build

# WRONG — runs from src/, build context resolves to a non-existent path
cd /home/muut/Production/UC-Meeting-Ops/src/
docker compose -f deploy/bigboy/docker-compose.bigboy.yml ...
```

Always invoke compose from `/home/muut/Production/UC-Meeting-Ops/`, not from `/src/`.

### Always pass --env-file

Compose without `--env-file deploy/bigboy/.env.bigboy` will silently fall back to a partial environment and may boot containers with wrong config. The env file is required — make it part of every `docker compose` invocation.

## Versioning + CHANGELOG

This project uses [Semantic Versioning](https://semver.org/). Current series: v0.8.x.

`CHANGELOG.md` at repo root tracks every release in [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format. Update CHANGELOG.md alongside `frontend/package.json` version bump on every release.

Workflow:
1. Make changes, commit normally.
2. When tagging a release: bump `frontend/package.json` version, update CHANGELOG.md (move `[Unreleased]` content to the new version section with date).
3. Annotated tag with the same release notes as the CHANGELOG entry: `git tag -a vX.Y.Z -m '<release notes>'`.
4. Push branch + tag: `git push origin main && git push origin vX.Y.Z`.

Tags ship to canonical Forgejo: `git.unicorncommander.ai/UnicornCommander/UC-Meeting-Ops`.
