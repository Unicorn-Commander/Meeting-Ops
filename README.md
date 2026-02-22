# Meeting-Ops

<div align="center">

**On-Premise AI Meeting Recording & Transcription Appliance**

[![Python 3.13](https://img.shields.io/badge/Python-3.13-3776ab?logo=python&logoColor=white)](https://python.org)
[![React 19](https://img.shields.io/badge/React-19-61dafb?logo=react&logoColor=white)](https://react.dev)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Vulkan](https://img.shields.io/badge/Vulkan-iGPU%20Accelerated-ac162c?logo=vulkan&logoColor=white)](https://vulkan.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green)](LICENSE)

*Part of the [Unicorn Commander](https://git.unicorncommander.ai) Suite*

---

**Record meetings. Transcribe in real-time. Get AI summaries. Export everything.**

**100% on-premise. Zero cloud dependencies. Your data never leaves the building.**

</div>

---

## What It Does

Meeting-Ops is a self-hosted meeting intelligence appliance. Plug in a USB mic, hit record, and it handles everything: real-time transcription with speaker identification, live AI-generated summaries and action items, full-text search across all meetings, and export to PDF/DOCX. It runs entirely on local hardware — no cloud APIs, no subscriptions, no data leaving your network.

### The Stack (All Local, All Vulkan-Accelerated)

| Component | Technology | What It Does |
|-----------|-----------|--------------|
| **Speech-to-Text** | [whisper.cpp](https://github.com/ggerganov/whisper.cpp) + Vulkan | Large-v3-turbo model on AMD 780M iGPU, ~9.6x realtime |
| **LLM** | [llama.cpp](https://github.com/ggerganov/llama.cpp) + Vulkan | Granite 3.3 2B (IBM) for summaries, chat, insights at ~850 tok/s |
| **Speaker ID** | NumPy acoustic clustering | Lightweight diarization without PyTorch, 303x realtime |
| **Frontend** | React 19 + TypeScript + Tailwind | Mobile-responsive SPA with live WebSocket updates |
| **Backend** | FastAPI + Python 3.13 | 19 API routers, WebSocket streaming, JWT auth |
| **Database** | PostgreSQL + Redis | Session storage, real-time pub/sub |

> **Why Vulkan?** On AMD Phoenix (780M iGPU), Vulkan is **2.4x faster** than ROCm for LLM inference (~850 tok/s vs ~350 tok/s). No ROCm install needed — just the RADV Mesa driver that ships with Linux.

---

## Screenshots

<div align="center">
<table>
<tr>
<td align="center"><img src="meeting-ops-live-recording.png" alt="Live Recording" width="400"><br><strong>Live Recording & Transcription</strong></td>
<td align="center"><img src="meeting-ops-sessionmanager.png" alt="Sessions" width="400"><br><strong>Session Management</strong></td>
</tr>
<tr>
<td align="center"><img src="meeting-ops-aichat.png" alt="AI Chat" width="400"><br><strong>Per-Meeting AI Chat</strong></td>
<td align="center"><img src="meeting-ops-login.png" alt="Login" width="400"><br><strong>Secure Authentication</strong></td>
</tr>
</table>
</div>

---

## Features

### Recording & Transcription
- **Real-time transcription** via whisper.cpp Vulkan server (large-v3-turbo)
- **Speaker diarization** — automatic speaker identification using acoustic feature clustering
- **Hallucination filtering** — catches common Whisper artifacts ("Thank you", silence dots, etc.)
- **Audio normalization** — handles quiet USB mics automatically (software gain + OS-level boost)
- **Device selection** — choose between USB mic, built-in mic, or auto-detect
- **Always-on mode** — continuous listening with automatic meeting segmentation (silence-gap detection)
- **Auto-stop** — recordings stop automatically after 5 minutes of silence

### AI Intelligence (Granite 3.3 2B via llama.cpp Vulkan)
- **Progressive summarization** — AI summaries update every 500 words during recording
- **Auto-generated titles** — meetings get descriptive names based on content
- **Per-meeting AI chat** — ask questions about any recorded meeting ("What were the action items?")
- **AI insights** — keywords, sentiment analysis, action items, decisions
- **Custom vocabulary** — define domain-specific terms for better transcription accuracy

### Session Management
- **Full-text search** — find meetings by content, title, or description
- **Export** — PDF, DOCX, TXT, JSON, SRT formats with real content
- **Analytics** — speaker talk time, meeting duration trends, word count distributions
- **Pagination & bulk operations** — manage large session libraries
- **Audio playback** — stream recordings directly in the browser

### Platform
- **JWT authentication** — role-based access (admin/user)
- **Mobile responsive** — hamburger menu, stacked layouts, touch-friendly
- **WebSocket streaming** — live transcription and summary updates
- **CORS hardened** — RFC1918 private network only (configurable)
- **Docker deployment** — one-command setup with persistent volumes

---

## Quick Start

### Prerequisites

- Linux (Ubuntu 22.04+ recommended)
- Docker & Docker Compose
- Node.js 18+ and npm
- Python 3.13+
- USB microphone (or built-in mic)
- AMD GPU with Vulkan support (for accelerated inference) — or CPU fallback

### 1. Start Infrastructure

```bash
cd UC-Meeting-Ops

# Start PostgreSQL, Redis, and llama.cpp (Granite 3.3 2B on Vulkan)
docker compose -f docker-compose-full-stack.yml up -d

# Wait for the LLM to load (~15 seconds)
sleep 15 && curl -s http://localhost:11437/health
```

### 2. Start whisper.cpp STT Server (if AMD iGPU available)

```bash
# If you have the whisper-server systemd service configured:
systemctl --user start whisper-server

# Or run directly:
whisper-server \
  --model models/ggml-large-v3-turbo.bin \
  --host 0.0.0.0 --port 8178 \
  --convert --gpu 0
```

### 3. Start Backend

```bash
cd backend
./start-backend.sh
# Or manually:
DATABASE_URL="postgresql://meetingops:REMOVED@localhost:5434/meeting_sessions" \
  python3 -m uvicorn main:app --host 0.0.0.0 --port 9050
```

### 4. Start Frontend

```bash
cd frontend
npm install
npm run dev -- --host 0.0.0.0
# Runs on http://localhost:7777
```

### 5. Login

Open `http://your-server-ip:7777` and log in:
- **Username**: `admin`
- **Password**: `admin123`

---

## Architecture

```
                    ┌─────────────────────────────────┐
                    │       React 19 Frontend          │
                    │    TypeScript + Tailwind + Vite   │
                    │         Port 7777                 │
                    └──────────┬──────────────────┬────┘
                               │ REST/WS          │ WS
                    ┌──────────▼──────────────────▼────┐
                    │       FastAPI Backend             │
                    │   19 Routers • JWT Auth • WS      │
                    │         Port 9050                 │
                    └──┬─────┬─────┬──────┬───────┬────┘
                       │     │     │      │       │
              ┌────────▼┐ ┌─▼───┐ │  ┌───▼────┐  │
              │PostgreSQL│ │Redis│ │  │llama.cpp│  │
              │  :5434   │ │:6379│ │  │ Vulkan  │  │
              │ Sessions │ │Pub/ │ │  │Granite  │  │
              │Transcripts│ Sub │ │  │3.3 2B   │  │
              └──────────┘ └─────┘ │  │ :11437  │  │
                                   │  └─────────┘  │
                          ┌────────▼─────┐  ┌──────▼──────┐
                          │ whisper.cpp   │  │ PipeWire    │
                          │ Vulkan STT    │  │ + ffmpeg    │
                          │ large-v3-turbo│  │ Audio       │
                          │ :8178         │  │ Capture     │
                          └───────────────┘  └──────┬──────┘
                                                    │
                                              ┌─────▼─────┐
                                              │ USB Mic /  │
                                              │ Built-in   │
                                              └────────────┘
```

### Services & Ports

| Service | Port | Purpose |
|---------|------|---------|
| Frontend (Vite) | 7777 | React SPA |
| Backend (FastAPI) | 9050 | REST API + WebSockets |
| PostgreSQL | 5434 | Session & transcript storage |
| Redis | 6379 | Real-time pub/sub, recording state |
| llama.cpp (Vulkan) | 11437 | Granite 3.3 2B LLM (OpenAI-compatible API) |
| whisper-server (Vulkan) | 8178 | Speech-to-text (large-v3-turbo) |

### Audio Pipeline

```
USB Mic → PipeWire → ffmpeg (44.1kHz mono WAV)
  → 15-second chunks → silence detection (-75dB)
  → audio normalization (quiet mic boost)
  → whisper.cpp Vulkan (large-v3-turbo, ~9.6x RT)
  → hallucination filter
  → speaker diarization (acoustic clustering)
  → WebSocket broadcast → React UI
  → PostgreSQL storage
  → AI progressive summary (Granite 3.3 2B @ 500-word intervals)
```

### Key Backend Modules

| Module | Purpose |
|--------|---------|
| `api/simple_recording_db.py` | Recording CRUD, audio capture, search, always-on mode |
| `services/live_recording_transcription.py` | Real-time chunk transcription with silence/hallucination handling |
| `services/working_audio_service.py` | ffmpeg + PipeWire audio recording |
| `services/always_on_recorder.py` | Continuous recording with automatic meeting segmentation |
| `services/unified_llm_service.py` | Granite 3.3 2B via llama.cpp OpenAI-compatible API |
| `services/unified_agent_service.py` | Progressive AI summarization |
| `services/speaker_diarization_onnx.py` | Lightweight speaker ID (NumPy, no PyTorch) |
| `services/whisper_server_client.py` | HTTP client for whisper.cpp server |
| `api/ai_chat.py` | Per-meeting AI chat with transcript context |
| `api/ai_insights.py` | AI-powered keyword/sentiment/action item extraction |
| `api/batch_export.py` | PDF (reportlab), DOCX (python-docx), TXT, JSON, SRT export |
| `api/analytics_simple.py` | Speaker analytics, duration trends |
| `api/vocabulary.py` | Custom vocabulary management |

---

## API Reference

All endpoints require JWT authentication unless noted. Get a token:

```bash
TOKEN=$(curl -s -X POST http://localhost:9050/api/auth/login \
  -d "username=admin&password=admin123" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
```

### Recording

```bash
# Create a session
curl -X POST http://localhost:9050/api/simple/recording-sessions \
  -H "Content-Type: application/json" \
  -d '{"name": "Team Standup", "description": "Daily sync"}'

# Start recording (with optional device selection)
curl -X POST http://localhost:9050/api/simple/recording-sessions/{id}/start \
  -H "Content-Type: application/json" \
  -d '{"device_id": "alsa_input.usb-..."}'  # or omit body for auto-detect

# Stop recording
curl -X POST http://localhost:9050/api/simple/recording-sessions/{id}/stop

# Always-on mode (continuous listening, auto-segments meetings)
curl -X POST http://localhost:9050/api/simple/always-on/start \
  -H "Authorization: Bearer $TOKEN"
curl -X POST http://localhost:9050/api/simple/always-on/stop \
  -H "Authorization: Bearer $TOKEN"
curl http://localhost:9050/api/simple/always-on/status \
  -H "Authorization: Bearer $TOKEN"
```

### Sessions & Search

```bash
# List sessions (paginated)
curl "http://localhost:9050/api/simple/recording-sessions?limit=10&offset=0"

# Full-text search
curl "http://localhost:9050/api/simple/recording-sessions/search?q=budget+discussion"

# Get session with transcript
curl http://localhost:9050/api/simple/recording-sessions/{id}

# Download audio
curl http://localhost:9050/api/simple/recording-sessions/{id}/download/audio -o meeting.wav
```

### Export

```bash
# PDF export
curl http://localhost:9050/api/simple/recording-sessions/{id}/download/summary/pdf -o meeting.pdf

# DOCX export
curl http://localhost:9050/api/simple/recording-sessions/{id}/download/summary/docx -o meeting.docx

# Also available: TXT, JSON, SRT via /api/meetings/{id}/export?format=txt
```

### AI Features

```bash
# Chat with a meeting
curl -X POST http://localhost:9050/api/ai-chat/sessions/{id}/messages \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "What were the main action items?"}'

# Get AI insights (keywords, sentiment, actions)
curl http://localhost:9050/api/simple/recording-sessions/{id}/insights \
  -H "Authorization: Bearer $TOKEN"

# Analytics
curl http://localhost:9050/api/analytics/summary \
  -H "Authorization: Bearer $TOKEN"
curl http://localhost:9050/api/analytics/speakers \
  -H "Authorization: Bearer $TOKEN"
```

### WebSocket (Live Transcription)

```javascript
const ws = new WebSocket('ws://localhost:9050/ws/transcription/{session_id}');
ws.onmessage = (event) => {
  const segment = JSON.parse(event.data);
  console.log(`[${segment.speaker}] ${segment.text}`);
  // { text, speaker, start, end, confidence }
};
```

### Health

```bash
curl http://localhost:9050/health
# {"status":"healthy","routers_loaded":19,"routers_failed":[],...}
```

---

## Testing

```bash
# Backend (40 pass, 3 skip)
cd backend
DATABASE_URL="postgresql://meetingops:REMOVED@localhost:5434/meeting_sessions" \
  python3 -m pytest tests/ -v

# Frontend build (0 TypeScript errors)
cd frontend
npm run build

# Frontend tests (23 pass)
cd frontend
npx vitest run
```

### Test Coverage

| Test File | Tests | What It Covers |
|-----------|-------|---------------|
| `test_auth.py` | 6 | Login, tokens, protected routes |
| `test_health.py` | 3 | Health, status endpoints |
| `test_recording.py` | 8 | Full CRUD lifecycle |
| `test_export.py` | 3 | Transcript download |
| `test_analytics.py` | 4 | Analytics summary, sessions |
| `test_search_analytics.py` | 16 | Search, analytics, AI insights, auth |
| `test_vocabulary.py` | 3 | Vocabulary CRUD (PostgreSQL only) |

---

## Hardware

Developed and tested on:

- **CPU**: AMD Ryzen 7 8845HS (Phoenix3) — 8 cores, 16 threads
- **iGPU**: AMD Radeon 780M — Vulkan via RADV Mesa driver
- **NPU**: AMD XDNA (16 TOPS) — driver loaded, kernel infrastructure ready
- **RAM**: 32GB DDR5
- **OS**: Ubuntu 24.04+

### Why This Hardware Matters

The 780M iGPU runs **both** whisper.cpp and llama.cpp simultaneously via Vulkan — no discrete GPU needed. The entire AI stack (STT + LLM) runs on the integrated graphics at production-quality speeds. This makes it viable as a small, quiet, affordable appliance that sits in a conference room.

---

## Configuration

### Environment Variables

```bash
# Required
DATABASE_URL=postgresql://meetingops:REMOVED@localhost:5434/meeting_sessions

# Optional
REDIS_URL=redis://localhost:6379          # Default
CORS_ORIGINS=                              # Comma-separated origins (default: RFC1918 regex)
SECRET_KEY=your-jwt-secret                 # For JWT tokens
```

### Docker Compose Services

```bash
docker compose -f docker-compose-full-stack.yml up -d
```

This starts:
- **PostgreSQL** (port 5434) — session and transcript storage
- **Redis** (port 6379) — real-time pub/sub
- **llama.cpp Vulkan** (port 11437) — Granite 3.3 2B Q4_K_M with OpenAI-compatible API

The whisper.cpp STT server runs as a systemd user service (or manually) on port 8178.

### Audio Setup

```bash
# Check available devices
pactl list sources short

# Set USB mic gain (if too quiet)
pactl set-source-volume <source-name> 200%

# The startup script does this automatically:
./scripts/set-mic-gain.sh
```

---

## Project Structure

```
UC-Meeting-Ops/
  backend/
    main.py                              # FastAPI app, loads 19 routers
    api/                                 # 19 API router modules
      simple_recording_db.py             #   Recording CRUD + search + always-on
      ai_chat.py                         #   Per-meeting AI chat
      ai_insights.py                     #   AI keyword/sentiment analysis
      batch_export.py                    #   PDF/DOCX/TXT/JSON/SRT export
      analytics_simple.py               #   Speaker & duration analytics
      vocabulary.py                      #   Custom vocabulary CRUD
      websocket_transcription.py         #   Live transcription WebSocket
      websocket_auto_summary.py          #   Progressive AI summaries
    services/                            # Core service modules
      always_on_recorder.py              #   Continuous recording + auto-segmentation
      live_recording_transcription.py    #   Real-time chunk transcription
      working_audio_service.py           #   ffmpeg + PipeWire audio capture
      unified_llm_service.py             #   llama.cpp Vulkan LLM client
      unified_agent_service.py           #   Progressive summarization
      speaker_diarization_onnx.py        #   Lightweight speaker ID
      whisper_server_client.py           #   whisper.cpp HTTP client
    auth/                                # JWT authentication
    database/                            # SQLAlchemy models + connection
    tests/                               # 8 test files, 40 tests
    start-backend.sh                     # Startup script
  frontend/
    src/
      App.tsx                            # Root component
      AppRouterSimplified.tsx            # Router (7 routes, mobile responsive)
      pages/                             # 7 page components
        LiveRecording.tsx                #   Recording + live transcription + always-on toggle
        Sessions.tsx                     #   Session list + search + pagination
        SessionDetails.tsx               #   Playback + transcript + export + AI chat
        SettingsEnhanced.tsx             #   System settings + vocabulary
        Login.tsx                        #   Authentication
      components/                        # Shared UI components
      contexts/                          # Auth, Theme, Recording contexts
      __tests__/                         # 4 test files, 23 tests
      config.ts                          # API URL configuration
  models/                                # GGUF model files for llama.cpp
  scripts/
    set-mic-gain.sh                      # USB mic gain persistence
  docs/
    always-on-recording-design.md        # Always-on architecture design
  docker-compose-full-stack.yml          # Infrastructure services
```

---

## Roadmap

### Done
- [x] Real-time transcription (whisper.cpp Vulkan)
- [x] Speaker diarization (acoustic clustering)
- [x] LLM summaries & chat (Granite 3.3 2B via llama.cpp Vulkan)
- [x] PDF/DOCX export (reportlab + python-docx)
- [x] Full-text search
- [x] Analytics & speaker insights
- [x] Mobile responsive UI
- [x] JWT authentication
- [x] Audio device selection
- [x] Whisper hallucination filtering
- [x] Auto-stop idle recordings
- [x] Always-on continuous recording mode
- [x] Custom vocabulary

### Planned
- [ ] Qdrant semantic/vector search ("find meetings about budget")
- [ ] Multi-room recording (multiple mic sources)
- [ ] LLM-based meeting segmentation (context-aware splitting)
- [ ] Satellite recording devices (record offline, upload later)
- [ ] Browser extension for client-side recording + upload
- [ ] Storage management (auto-cleanup old recordings)

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

<div align="center">

**Built by [Magic Unicorn Unconventional Technology & Stuff Inc.](https://magicunicorn.tech)**

*On-premise meeting intelligence. No cloud required.*

</div>
