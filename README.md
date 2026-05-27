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

## Release Notes

See [CHANGELOG.md](./CHANGELOG.md) for the full per-version release history. Latest tag: **v3.9.0** (2026-05-27) — canonical meeting audio now lives in Garage object storage (durable, self-hosted), on top of the per-room multi-mic picker, tags-as-folders sessions grouping, free-tier enforcement + consumer signup, and the Phase B server-live streaming line.

## What It Does

Meeting-Ops is meeting intelligence. Hit record and it handles everything: real-time transcription, speaker identification, live AI-generated summaries and action items, full-text search across all meetings, and export to PDF/DOCX. It runs in two flavors: a cloud-hosted multi-tenant build (the v0.7.x line on `meetingops.magicunicorn.dev`) and an on-prem appliance build (Ryzen AI 780M + Vulkan), shipped from the same codebase via compose targets.

---

## Architecture: browser-first by design

The thing that makes Meeting-Ops different from every other meeting-AI product on the market isn't the model selection or the UI. It's that we don't run the per-minute compute. The user's browser does.

### Two stacks, two jobs

```
┌──────────────────────── BROWSER (live work, free to us) ──────────────────────┐
│                                                                                 │
│   Mic   →  VAD  →  Parakeet 0.6B INT8       ──► live transcript                 │
│           (Silero)   (onnxruntime-web, WebGPU/WASM)                            │
│                                                                                 │
│                   →  Qwen 3 0.6B / Gemma 4 E2B  ──► live rolling summary       │
│                      (transformers.js / web-llm)                                │
│                                                                                 │
│                   MediaRecorder ──► 30s WebM/Opus chunks ─┐                    │
│                                                            │                    │
└────────────────────────────────────────────────────────────┼────────────────────┘
                                                             │
                              POST /audio-chunks (every 30s) │  bandwidth: ~28 MB/hr
                                                             ▼
┌──────────── SERVER (runs ONCE at meeting completion, ~30-90 sec) ─────────────┐
│                                                                                │
│   ffmpeg reassemble  →  Parakeet 1.1B fp16   ──► word-timestamped transcript  │
│                          (midboy2 3060)                                        │
│                                                                                │
│                      →  pyannote 3.1 + wespeaker  ──► diarized + matched      │
│                          (bigboy 3090 / RTX 6000)                              │
│                                                                                │
│                      →  Qwen 3.6 35B-A3B-Vision  ──► polished final summary   │
│                          (midboy1 P40, np 4)         action items, attendees  │
│                                                                                │
└────────────────────────────────────────────────────────────────────────────────┘
```

The browser stack runs in the user's tab for the entire meeting. The server stack runs exactly once when the meeting ends, in 30-90 seconds, on idle ecosystem GPU.

### Why this matters

Every other meeting-AI product (Otter, Granola, Fathom, Fireflies, Read.ai) pays AssemblyAI/Deepgram per audio-minute and OpenAI/Anthropic per token, per user, continuously, for the whole meeting. That cost scales linearly with concurrent users.

Our marginal cost per concurrent user-hour is zero. The user's CPU/GPU does it. Our marginal cost per completed meeting is ~30-90 GPU-seconds on hardware we already own. At 1000 concurrent users in hour-long meetings, competitors pay $500-1500/hr in live compute; we pay roughly $20 across when those meetings actually finish, on bare-metal GPU we already own.

This is a real moat. Replicating it requires (a) shipping browser inference at all, (b) picking and validating browser-runnable models that don't embarrass you, and (c) accepting that live quality is "good enough for live" instead of "best possible for live." Most competitors won't make all three decisions; their existing positioning makes (c) particularly hard.

### The free side benefit: privacy mode

Because the browser stack is self-contained, turning the server step off is a feature flag. Audio bytes never leave the device. Privacy mode is a per-session toggle (orthogonal to pricing tier; anyone can enable it). Enterprise + HIPAA deployments default it on.

### Tier model

- **Free**: browser live + browser final, on-device only — audio never leaves the browser. Enforced server-side (server-processing endpoints 403 free users). Live since v3.0.0/v3.1.0.
- **Pro**: + server reprocess on completion (Parakeet 1.1B + pyannote + Qwen 3.6), live server transcript, durable cross-device storage, bulk import.
- **Enterprise**: + speaker library + retention + BYOK Brigade + HIPAA + dedicated/on-prem.

Consumer self-serve signup (email/password + verification) is built (v3.2.0 backend + v3.5.0 frontend) and inert until activated; SSO users are unaffected. Pricing/Stripe checkout is the remaining gate.

### Audio storage & data durability (v3.7.0+)

Canonical meeting audio is stored in **Garage** (S3-compatible object storage) on our own hardware — not a third-party cloud — mirroring how session attachments already work. Local disk is a transient working cache; a session row records the durable location (`audio_storage_backend` / `audio_object_key`). Reads resolve local-first and fall back to Garage; deleting a session purges its Garage objects too ("delete my data" actually deletes). As of the **v3.9.0 cutover**, Garage is authoritative and local copies of completed sessions are size-verified then evicted to reclaim disk. Free-tier audio is exempt — it stays in the browser. See [`docs/audio-storage-garage.md`](./docs/audio-storage-garage.md).

### Deployment topology

- `meetingops.magicunicorn.dev` (canonical) / `meeting-ops.magicunicorn.dev` (hyphenated alias) — dev + beta tier, where v0.x lives today.
- `unicorncommander.ai` — production target. Stable releases only. Free + Pro launch here.
- Enterprise — dedicated server or on-prem appliance per customer. HIPAA deployments (Legacy1, etc.) get their own instance.

### Implementation status (2026-05-27)

- Browser STT + LLM: live since v0.6.0
- Server reprocess pipeline: live
- Privacy mode: live since v0.6.0
- Phase B server-live streaming (Sortformer diarization + Parakeet realtime-EOU): live (v2.x)
- Tier gating / free-tier enforcement: live (v3.0.0–v3.1.0)
- Consumer signup (backend + frontend): built, inert until activation (v3.2.0 / v3.5.0)
- Sessions folders + per-room multi-mic picker: live (v3.8.0)
- Garage audio object storage + cutover: live (v3.7.0–v3.9.0)
- `unicorncommander.ai` production cutover + Stripe checkout: pending
- Enterprise on-prem packaging: depends on `docs/appliance-extraction-design.md`

**Full design + strategy doc**: [`docs/compute-economics.md`](./docs/compute-economics.md). Read this before adding any new server-side per-minute service; the architecture is the moat and we don't want to give it back by reaching for an external API when we could push the work to the browser or fold it into the completion pass.

---

### Appliance build stack (on-prem)

The on-prem appliance build (`docs/appliance-extraction-design.md`) targets AMD Ryzen AI Phoenix hardware and runs the entire AI stack locally on the 780M iGPU via Vulkan. Same codebase, different compose target.

| Component | Technology | What It Does |
|-----------|-----------|--------------|
| **Speech-to-Text** | [whisper.cpp](https://github.com/ggerganov/whisper.cpp) + Vulkan | Large-v3-turbo model on AMD 780M iGPU, ~9.6x realtime |
| **LLM** | [llama.cpp](https://github.com/ggerganov/llama.cpp) + Vulkan | Granite 3.3 2B (IBM) for summaries, chat, insights at ~850 tok/s |
| **Speaker ID** | NumPy acoustic clustering | Lightweight diarization without PyTorch, 303x realtime |
| **Frontend** | React 19 + TypeScript + Tailwind | Mobile-responsive SPA with live WebSocket updates |
| **Backend** | FastAPI + Python 3.13 | 21 API routers, WebSocket streaming, JWT auth |
| **Database** | PostgreSQL + Redis + Qdrant | Session storage, real-time pub/sub, vector search |

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

### Cross-Meeting Intelligence (RAG)
- **Cross-meeting AI chat** — ask questions across all recorded meetings, not just one
- **Hybrid search** (semantic + BM25 keyword) for precise retrieval across your entire meeting library
- **Speaker-aware transcript chunking** for better context in AI answers
- **Source citations** — AI answers link back to the specific meetings where information was found

### Multi-Room & Remote Recording
- **Satellite device support** — ESP32-S3 (~$15/node) and Raspberry Pi for multi-room recording
- **Companion app support** — Mac/PC menu bar app for remote meeting capture
- **Store-and-forward mode** — devices record offline and upload when WiFi is available
- **WebSocket real-time streaming** — binary PCM audio from any device to the server
- **Room management** — assign devices to rooms, track status via heartbeat

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
┌─────────────────────────────────────────────────────────────────┐
│                     Remote Devices                               │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐                  │
│  │ ESP32-S3 │  │  RPi 5   │  │ Mac/PC       │                  │
│  │ Satellite│  │ Satellite│  │ Companion App│                  │
│  │   $15    │  │  $130    │  │ (Swift/etc)  │                  │
│  └────┬─────┘  └────┬─────┘  └──────┬───────┘                  │
│       │ WS/HTTP      │ WS/HTTP       │ WS                       │
└───────┼──────────────┼───────────────┼──────────────────────────┘
        │              │               │
┌───────▼──────────────▼───────────────▼──────────────────────────┐
│                  Meeting-Ops Server                               │
│  ┌──────────────────────────────────────────────────────┐       │
│  │              FastAPI Backend (21 Routers)              │       │
│  │   REST API • WebSockets • JWT Auth • Port 9050        │       │
│  └───┬────────┬──────────┬──────────┬──────────┬────────┘       │
│      │        │          │          │          │                 │
│  ┌───▼──┐ ┌──▼──┐ ┌─────▼────┐ ┌───▼───┐ ┌───▼───┐           │
│  │Postgre│ │Redis│ │llama.cpp │ │whisper│ │Qdrant │           │
│  │SQL    │ │     │ │Vulkan    │ │.cpp   │ │Vector │           │
│  │:5434  │ │:6381│ │Granite2B │ │Vulkan │ │Search │           │
│  │       │ │     │ │:11437    │ │:8178  │ │:6335  │           │
│  └───────┘ └─────┘ └──────────┘ └───────┘ └───────┘           │
│                                                                  │
│  ┌──────────────────────────┐  ┌────────────┐                   │
│  │   React 19 Frontend      │  │ USB Mic /  │                   │
│  │   Port 7777              │  │ Built-in   │                   │
│  └──────────────────────────┘  └────────────┘                   │
└──────────────────────────────────────────────────────────────────┘
```

### Services & Ports

| Service | Port | Purpose |
|---------|------|---------|
| Frontend (Vite) | 7777 | React SPA |
| Backend (FastAPI) | 9050 | REST API + WebSockets (21 routers) |
| PostgreSQL | 5434 | Session & transcript storage |
| Redis | 6381 | Real-time pub/sub, recording state |
| Qdrant | 6335 | Vector search (semantic meeting search) |
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
| `api/satellite_api.py` | Satellite device CRUD, heartbeat, audio/transcript upload |
| `api/websocket_satellite.py` | Real-time audio streaming from satellite devices |

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

# Semantic search (natural language, vector similarity)
curl "http://localhost:9050/api/simple/recording-sessions/semantic-search?q=budget+planning+discussion&limit=5"

# Reindex all sessions into vector store
curl -X POST http://localhost:9050/api/simple/semantic-search/reindex \
  -H "Authorization: Bearer $TOKEN"

# Storage management
curl http://localhost:9050/api/simple/storage/stats \
  -H "Authorization: Bearer $TOKEN"
curl -X POST "http://localhost:9050/api/simple/storage/cleanup?days=90&dry_run=true" \
  -H "Authorization: Bearer $TOKEN"
```

### Cross-Meeting RAG

```bash
# Ask questions across ALL meetings (not just one)
curl -X POST http://localhost:9050/api/ai-chat/rag/query \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "What did we discuss about the budget across all meetings?"}'
```

### Satellite Devices

```bash
# Register a satellite device
curl -X POST http://localhost:9050/api/satellites/register \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"device_id":"esp32-office-01","name":"Office ESP32","room_name":"Main Office","device_type":"esp32-s3"}'

# List all satellites
curl http://localhost:9050/api/satellites \
  -H "Authorization: Bearer $TOKEN"

# Device heartbeat
curl -X POST http://localhost:9050/api/satellites/{device_id}/heartbeat \
  -H "Authorization: Bearer $TOKEN"

# Upload recorded audio (store-and-forward)
curl -X POST http://localhost:9050/api/satellites/{device_id}/upload-audio \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@recording.wav"

# Upload transcript (RPi local STT)
curl -X POST http://localhost:9050/api/satellites/{device_id}/transcript \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"transcript_text": "...", "segments": [...]}'

# Satellite audio streaming (real-time)
# WebSocket: ws://localhost:9050/ws/satellite/{device_id}/audio
# Sends binary PCM frames (16kHz, 16-bit, mono)

# Remote audio streaming (companion app)
# WebSocket: ws://localhost:9050/ws/remote-audio/{session_id}?token=JWT_TOKEN
# Sends binary PCM frames (16kHz, 16-bit, mono)
# Receives JSON transcription results
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
# {"status":"healthy","routers_loaded":21,"routers_failed":[],...}
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
REDIS_URL=redis://localhost:6381          # Default (host port mapped from container 6379)
CORS_ORIGINS=                              # Comma-separated origins (default: RFC1918 regex)
SECRET_KEY=your-jwt-secret                 # For JWT tokens
```

### Docker Compose Services

```bash
docker compose -f docker-compose-full-stack.yml up -d
```

This starts:
- **PostgreSQL** (port 5434) — session and transcript storage
- **Redis** (port 6381) — real-time pub/sub
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
    main.py                              # FastAPI app, loads 21 routers
    api/                                 # 21 API router modules
      simple_recording_db.py             #   Recording CRUD + search + always-on
      ai_chat.py                         #   Per-meeting AI chat + cross-meeting RAG
      ai_insights.py                     #   AI keyword/sentiment analysis
      batch_export.py                    #   PDF/DOCX/TXT/JSON/SRT export
      analytics_simple.py               #   Speaker & duration analytics
      vocabulary.py                      #   Custom vocabulary CRUD
      websocket_transcription.py         #   Live transcription WebSocket
      websocket_auto_summary.py          #   Progressive AI summaries
      satellite_api.py                   #   Satellite device management
      websocket_satellite.py             #   Satellite audio WebSocket
      websocket_remote_audio.py          #   Companion app audio WebSocket
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
    companion-app-design.md              # Mac/PC companion app architecture
    satellite-devices-design.md          # ESP32/RPi satellite device specs
  docker-compose-full-stack.yml          # Infrastructure services
```

---

## Roadmap

### Done
- [x] Real-time transcription (whisper.cpp Vulkan)
- [x] Speaker diarization (acoustic clustering)
- [x] LLM summaries & chat (Granite 3.3 2B via llama.cpp Vulkan)
- [x] PDF/DOCX export (reportlab + python-docx)
- [x] Full-text search + semantic/vector search (Qdrant + fastembed)
- [x] Analytics & speaker insights
- [x] Mobile responsive UI
- [x] JWT authentication
- [x] Audio device selection
- [x] Whisper hallucination filtering
- [x] Auto-stop idle recordings
- [x] Always-on continuous recording mode with LLM context splitting
- [x] Custom vocabulary
- [x] Storage management (configurable retention, dry-run cleanup)
- [x] Multi-room satellite device backend (ESP32-S3, RPi support)
- [x] Companion app backend (remote audio WebSocket)
- [x] Cross-meeting RAG (hybrid search, AI answers with citations)
- [x] Chat history persistence (PostgreSQL)

### In Progress / Planned
- [ ] Companion app client (macOS Swift -- designed, not yet built)
- [ ] ESP32-S3 firmware (designed, not yet built)
- [ ] Raspberry Pi satellite service (designed, not yet built)
- [ ] Hybrid search with sparse BM25 vectors

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

<div align="center">

**Built by [Magic Unicorn Unconventional Technology & Stuff Inc.](https://magicunicorn.tech)**

*On-premise meeting intelligence. No cloud required.*

</div>
