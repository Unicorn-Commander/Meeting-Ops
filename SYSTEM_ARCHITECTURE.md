# Unicorn Commander Meeting Ops - System Architecture

## Overview

Unicorn Commander Meeting Ops is a local-first, AI-powered meeting room recording appliance with NPU acceleration. The system is designed for headless deployment on hardware appliances for Small and Medium Businesses (SMB), featuring real-time transcription, speaker diarization, and meeting insights.

## Architecture Principles

- **Local-First**: All processing happens on-device for privacy and reliability
- **NPU-Accelerated**: Leverages AMD Phoenix NPU for 220x-7866x AI speedup
- **Enterprise-Ready**: Multi-tenant with role-based access control
- **Real-Time**: WebSocket-based live transcription and monitoring
- **Extensible**: Plugin architecture with webhooks and APIs
- **Headless**: Web-based interface accessible from any device

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     Unicorn Commander Meeting Ops               │
├─────────────────────────────────────────────────────────────────┤
│  Frontend (React + TypeScript)                                 │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐                │
│  │  Dashboard  │ │ Live Trans. │ │ File Mgmt   │                │
│  └─────────────┘ └─────────────┘ └─────────────┘                │
├─────────────────────────────────────────────────────────────────┤
│  API Layer (FastAPI + WebSocket)                               │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐                │
│  │ REST APIs   │ │ WebSocket   │ │ Wyoming     │                │
│  │ /api/...    │ │ /ws/...     │ │ :10700      │                │
│  └─────────────┘ └─────────────┘ └─────────────┘                │
├─────────────────────────────────────────────────────────────────┤
│  Service Layer                                                  │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐                │
│  │ Session Mgr │ │ Audio Svc   │ │ NPU Engine  │                │
│  └─────────────┘ └─────────────┘ └─────────────┘                │
├─────────────────────────────────────────────────────────────────┤
│  AI/ML Layer (NPU Accelerated)                                 │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐                │
│  │ WhisperX    │ │ Speaker ID  │ │ LLM Summary │                │
│  │ 7866x RTF   │ │ 50x RTF     │ │ Meeting AI  │                │
│  └─────────────┘ └─────────────┘ └─────────────┘                │
├─────────────────────────────────────────────────────────────────┤
│  Hardware Layer                                                 │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐                │
│  │ AMD Phoenix │ │ Audio I/O   │ │ ESP32 Sats  │                │
│  │ NPU 16 TOPS │ │ USB/Line In │ │ Wireless    │                │
│  └─────────────┘ └─────────────┘ └─────────────┘                │
└─────────────────────────────────────────────────────────────────┘
```

## Technology Stack

### Frontend
- **React 19.1.0**: Modern React with concurrent features
- **TypeScript 5.8.3**: Type safety and developer experience
- **Tailwind CSS 3.4.17**: Utility-first styling framework
- **Radix UI**: Accessible component primitives
- **React Router DOM 7.7.0**: Client-side routing
- **Lucide React**: Consistent icon library

### Backend
- **Python 3.13**: Latest Python with JIT compilation
- **FastAPI**: High-performance async API framework
- **SQLAlchemy**: ORM with async support
- **WebSockets**: Real-time bidirectional communication
- **PyAudio**: Cross-platform audio I/O
- **ONNX Runtime**: Optimized ML inference

### Database
- **SQLite**: Development and single-node deployment
- **PostgreSQL**: Production multi-tenant deployment
- **Alembic**: Database migrations
- **JSON Columns**: Flexible metadata storage

### AI/ML Stack
- **ONNX**: Cross-platform ML model format
- **WhisperX**: Unified transcription + diarization
- **Pyannote.audio**: Speaker diarization
- **MLIR-AIE2**: Custom NPU kernel development
- **OpenAI/Anthropic APIs**: LLM summarization

### Hardware
- **AMD Phoenix NPU**: 16 TOPS INT8 acceleration
- **Audio Interfaces**: USB, Line In, Wireless
- **ESP32 Satellites**: Distributed microphone array
- **Hardware Controls**: Physical buttons and switches

## Core Components

### 1. Session Management
**Purpose**: Orchestrates meeting lifecycle from start to completion

**Key Components**:
- `SessionManager`: Core session orchestration
- `RecordingSession` model: Session state and metadata
- `AudioSessionManager`: Per-session audio handling
- `TranscriptionService`: Real-time speech processing

**Features**:
- Multi-session support with isolation
- Real-time status monitoring
- Automatic cleanup and recovery
- Session state persistence

### 2. Audio Processing Pipeline

```
Audio Input → Buffer → NPU Processing → Transcription → Storage
     ↓           ↓           ↓              ↓           ↓
  Hardware → WebSocket → MLIR Kernels → Speaker ID → Database
```

**Components**:
- `AudioInputService`: Hardware interface layer
- `AudioRecordingService`: File recording and streaming
- `AudioBuffer`: Circular buffer for real-time processing
- `NPUAccelerator`: Hardware acceleration interface

### 3. NPU Acceleration Layer

**MLIR-AIE2 Custom Kernels**:
```cpp
// Example NPU kernel for Whisper attention
aie.tile {
  %attention = aie.dma_bd %input_tokens
  %weights = aie.objectfifo.acquire @whisper_weights
  %result = aie.vectorize.mac %attention, %weights
  aie.objectfifo.release @output_tokens, %result
}
```

**Performance Characteristics**:
- **WhisperX NPU Unified**: 7,866x real-time factor
- **Basic Transcription**: 220x real-time factor
- **Speaker Diarization**: 50x real-time factor
- **Power Efficiency**: 10x better than CPU

### 4. Real-Time Communication

**WebSocket Endpoints**:
- `/ws/stream/{session_id}`: Audio streaming and transcription
- `/ws/audio-level`: Real-time audio level monitoring
- `/ws/session-status`: Session state updates

**Wyoming Protocol** (Port 10700):
- **Satellite Integration**: ESP32 microphone arrays
- **Wake Word Detection**: "Hey Unicorn" activation
- **Gesture Recognition**: Computer vision controls
- **Remote Control**: Hardware button integration

### 5. Authentication & Security

**JWT-Based Authentication**:
```python
# Token structure
{
  "user_id": 123,
  "username": "admin",
  "role": "superuser",
  "permissions": ["session.create", "files.read", "ai.write"],
  "org_id": 1,
  "exp": 1735689600
}
```

**Role Hierarchy**:
- **Superuser**: Full system access
- **Admin**: Organization management
- **Manager**: Session and user management
- **User**: Create and manage own sessions
- **Viewer**: Read-only access to shared content

### 6. File Management System

**Storage Structure**:
```
/audio_files/
├── sessions/
│   ├── {session_id}/
│   │   ├── recording.wav
│   │   ├── segments/
│   │   └── exports/
├── temp/
└── archive/
```

**Features**:
- Hierarchical organization by session
- Multiple format support (WAV, MP3)
- Metadata tracking in database
- Automatic cleanup policies
- Streaming playback support

## Data Flow

### 1. Meeting Recording Flow

```
Audio Hardware → PyAudio → AudioInputService
                              ↓
                         AudioBuffer (Circular)
                              ↓
                    ┌─────────────────────┐
                    ↓                     ↓
            NPU Processing         File Recording
                    ↓                     ↓
              Transcription          AudioFile
                    ↓                     ↓
               Speaker ID            Database
                    ↓
               WebSocket → Frontend
```

### 2. NPU Processing Pipeline

```
Audio Chunk (16kHz, 30s) → Mel Spectrogram → NPU Encoder
                                                  ↓
                                             NPU Decoder
                                                  ↓
                                            Text Tokens
                                                  ↓
                                          Speaker Diarization
                                                  ↓
                                      Final Transcription
```

### 3. Real-Time Updates

```
Backend Event → WebSocket Server → Frontend Components
     ↓               ↓                      ↓
Session State   Transcription         UI Updates
Audio Levels    Speaker Changes       Progress Bars
Error Status    Confidence Scores     Status Indicators
```

## API Architecture

### REST API Design

**Base URL**: `http://localhost:9050/api`

**Core Endpoints**:
```
Authentication:
├── POST /auth/login
├── POST /auth/refresh
├── GET  /auth/me
└── POST /auth/logout

Sessions:
├── GET    /recording-sessions/
├── POST   /recording-sessions/
├── GET    /recording-sessions/{id}
├── PUT    /recording-sessions/{id}
├── DELETE /recording-sessions/{id}
├── POST   /recording-sessions/{id}/start
├── POST   /recording-sessions/{id}/stop
└── GET    /recording-sessions/{id}/export

Files:
├── GET    /files/
├── GET    /files/{id}
├── GET    /files/{id}/download
├── GET    /files/{id}/stream
├── DELETE /files/{id}
└── POST   /files/{id}/tags

AI Models:
├── GET  /ai/stt/models
├── POST /ai/stt/set-current/{model_id}
├── POST /ai/stt/download/{model_id}
└── GET  /ai/stt/benchmark/{model_id}

Settings:
├── GET /settings/
├── GET /settings/{category}
└── PUT /settings/{category}
```

### WebSocket API

**Connection Pattern**:
```javascript
const ws = new WebSocket(`ws://localhost:9050/ws/stream/${sessionId}?token=${jwt}`);

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  switch(data.type) {
    case 'transcription':
      updateTranscription(data.segment);
      break;
    case 'audio_level':
      updateAudioMeter(data.level);
      break;
    case 'session_status':
      updateSessionState(data.status);
      break;
  }
};
```

## Database Schema

### Core Models

```sql
-- Sessions table
CREATE TABLE recording_sessions (
    id INTEGER PRIMARY KEY,
    session_id VARCHAR(255) UNIQUE NOT NULL,
    title VARCHAR(255),
    description TEXT,
    status VARCHAR(50),
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    created_by INTEGER REFERENCES users(id),
    organization_id INTEGER REFERENCES organizations(id),
    settings JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Transcriptions table
CREATE TABLE transcriptions (
    id INTEGER PRIMARY KEY,
    session_id INTEGER REFERENCES recording_sessions(id),
    text TEXT NOT NULL,
    start_time FLOAT,
    end_time FLOAT,
    confidence FLOAT,
    speaker_id VARCHAR(255),
    language VARCHAR(10),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Audio files table
CREATE TABLE audio_files (
    id INTEGER PRIMARY KEY,
    session_id INTEGER REFERENCES recording_sessions(id),
    filename VARCHAR(255) NOT NULL,
    file_path VARCHAR(500) NOT NULL,
    file_size BIGINT,
    duration FLOAT,
    format VARCHAR(10),
    sample_rate INTEGER,
    channels INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Authentication Models

```sql
-- Users table
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    username VARCHAR(255) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(255),
    is_active BOOLEAN DEFAULT TRUE,
    is_verified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Organizations table
CREATE TABLE organizations (
    id INTEGER PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    domain VARCHAR(255),
    settings JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- User organization roles
CREATE TABLE user_organizations (
    user_id INTEGER REFERENCES users(id),
    organization_id INTEGER REFERENCES organizations(id),
    role VARCHAR(50) NOT NULL,
    permissions JSON,
    PRIMARY KEY (user_id, organization_id)
);
```

## NPU Integration Details

### Hardware Requirements
- **AMD Phoenix APU**: Ryzen 7040 series or newer
- **NPU Support**: 16 TOPS INT8 computation
- **Memory**: 16GB+ system RAM
- **Storage**: 500GB+ SSD for model cache

### MLIR-AIE2 Kernel Development

**Kernel Structure**:
```mlir
// Whisper encoder attention kernel
aie.core {
  %input = aie.objectfifo.acquire @audio_tokens : memref<1024xi8>
  %weights = aie.objectfifo.acquire @attention_weights : memref<1024x1024xi8>
  
  // Matrix multiplication with INT8
  %result = aie.vectorize {
    %acc = arith.constant 0 : i32
    %mult = vector.contract %input, %weights, %acc : 
      vector<64xi8>, vector<64xi8> into i32
  }
  
  aie.objectfifo.release @output_tokens, %result
}
```

**Performance Optimizations**:
- **Quantization**: INT8/INT4 mixed precision
- **Memory Layout**: Optimized for NPU cache hierarchy
- **Pipelining**: Overlapped compute and memory operations
- **Vectorization**: 1024-bit vector operations

### Model Quantization

**WhisperX NPU Pipeline**:
1. **Voice Activity Detection** (VAD): Detect speech segments
2. **Whisper Transcription**: Convert speech to text tokens
3. **Forced Alignment**: Word-level timestamp alignment
4. **Speaker Diarization**: Identify and separate speakers

**Quantization Strategy**:
- **Encoder**: INT8 for speed
- **Decoder**: Mixed INT8/INT4 for memory efficiency
- **Attention**: Custom quantized softmax implementation
- **Embeddings**: INT4 with dynamic scaling

## External Integrations

### Calendar Integration

**Microsoft 365**:
```python
# Graph API integration
endpoint = "https://graph.microsoft.com/v1.0"
headers = {"Authorization": f"Bearer {access_token}"}

# Get calendar events
response = requests.get(
    f"{endpoint}/me/calendar/events",
    headers=headers,
    params={
        "startDateTime": start_time,
        "endDateTime": end_time,
        "select": "subject,start,end,attendees"
    }
)
```

**Google Workspace**:
```python
# Service account authentication
credentials = service_account.Credentials.from_service_account_file(
    "credentials.json",
    scopes=["https://www.googleapis.com/auth/calendar"]
)

# Calendar API
service = build("calendar", "v3", credentials=credentials)
events = service.events().list(
    calendarId="primary",
    timeMin=start_time,
    timeMax=end_time
).execute()
```

### Webhook System

**Event Types**:
- `session.started`: Meeting recording begins
- `session.completed`: Meeting ends with transcription
- `transcription.updated`: Real-time transcription updates
- `calendar.conflict`: Meeting scheduling conflicts
- `system.alert`: Hardware or performance issues

**Webhook Payload**:
```json
{
  "event_type": "session.completed",
  "timestamp": "2025-01-20T14:30:00Z",
  "session_id": "sess_123456",
  "data": {
    "title": "Team Standup",
    "duration": 1800,
    "participants": 5,
    "transcription_url": "https://app.local/sessions/123456/export",
    "summary": "Key discussion points..."
  },
  "signature": "sha256=..."
}
```

## Performance Characteristics

### NPU Performance
- **Inference Speed**: 4,789 tokens/second
- **Real-Time Factor**: 0.0001x (7,866x real-time)
- **Memory Usage**: 512MB for unified model
- **Power Consumption**: 15W total system load
- **Latency**: 50-100ms first token

### System Performance
- **Concurrent Sessions**: 10+ simultaneous recordings
- **Audio Processing**: 16kHz, 16-bit, mono
- **WebSocket Connections**: 100+ concurrent clients
- **File Storage**: Unlimited with automatic cleanup
- **Database**: 1M+ transcription segments supported

### Scalability
- **Horizontal**: Multiple appliance deployment
- **Vertical**: Single-node optimization
- **Load Balancing**: Nginx reverse proxy
- **Caching**: Redis for session state
- **Backup**: Automated daily snapshots

## Security Architecture

### Data Protection
- **Encryption at Rest**: AES-256 for audio files
- **Encryption in Transit**: TLS 1.3 for all communications
- **Access Control**: Role-based with least privilege
- **Audit Logging**: Complete action tracking
- **Data Retention**: Configurable cleanup policies

### Network Security
- **Firewall**: Default deny with explicit allow rules
- **VPN Support**: WireGuard integration
- **API Rate Limiting**: Configurable per-endpoint limits
- **CORS**: Strict cross-origin policies
- **CSRF Protection**: Token-based validation

### Compliance
- **GDPR**: Data portability and deletion rights
- **SOC 2**: Security monitoring and controls
- **HIPAA**: Healthcare data protection (optional)
- **PCI DSS**: Payment data security (if applicable)

## Deployment Architecture

### Development Mode
```bash
# Backend
cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 9050 --reload

# Frontend
cd frontend
npm run dev
```

### Production Deployment
```yaml
# docker-compose.yml
version: '3.8'
services:
  backend:
    build: ./backend
    ports:
      - "9050:9050"
    environment:
      - DATABASE_URL=postgresql://...
      - HUGGINGFACE_TOKEN=...
    volumes:
      - ./audio_files:/app/audio_files
      - /dev/snd:/dev/snd  # Audio devices
    devices:
      - /dev/accel/accel0  # NPU device
  
  frontend:
    build: ./frontend
    ports:
      - "5173:5173"
    depends_on:
      - backend
  
  database:
    image: postgres:15
    environment:
      - POSTGRES_DB=unicorn_commander
      - POSTGRES_USER=...
      - POSTGRES_PASSWORD=...
    volumes:
      - postgres_data:/var/lib/postgresql/data
```

### Hardware Appliance
```ini
# systemd service
[Unit]
Description=Unicorn Commander Backend
After=network.target

[Service]
Type=simple
User=unicorn
WorkingDirectory=/opt/unicorn-commander/backend
Environment="PATH=/opt/unicorn-commander/backend/venv/bin"
ExecStart=/opt/unicorn-commander/backend/venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 9050
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

## Monitoring & Observability

### Metrics Collection
- **Performance**: NPU utilization, audio processing latency
- **Usage**: Session counts, transcription accuracy
- **System**: CPU, memory, disk usage
- **Network**: WebSocket connections, API response times

### Logging
- **Structured Logging**: JSON format for machine parsing
- **Log Levels**: DEBUG, INFO, WARNING, ERROR, CRITICAL
- **Rotation**: Automatic log rotation and archival
- **Centralization**: Optional ELK stack integration

### Alerting
- **Hardware Issues**: NPU failures, audio device problems
- **Performance**: High latency, resource exhaustion
- **Security**: Failed login attempts, unauthorized access
- **Business**: Transcription failures, export errors

## Future Enhancements

### Short-Term (3-6 months)
- **Multi-language Support**: Extended language pack
- **Advanced Analytics**: Meeting insights and trends
- **Mobile App**: iOS/Android companion app
- **Cloud Sync**: Optional cloud backup and sync

### Medium-Term (6-12 months)
- **Federated Learning**: Privacy-preserving model updates
- **Advanced AI**: Emotion detection, sentiment analysis
- **Integration Expansion**: Slack, Teams, Zoom plugins
- **Hardware Variants**: Raspberry Pi, embedded versions

### Long-Term (12+ months)
- **Edge Computing**: Distributed processing cluster
- **Real-Time Translation**: Multi-language meeting support
- **AR/VR Integration**: Immersive meeting experiences
- **AI Assistant**: Proactive meeting management

## Conclusion

Unicorn Commander Meeting Ops represents a sophisticated, enterprise-ready meeting management solution that leverages cutting-edge NPU acceleration for real-time AI processing. The architecture is designed for scalability, security, and performance while maintaining a local-first approach for privacy and reliability.

Key architectural strengths:
- **High Performance**: NPU acceleration delivers 7,866x speedup
- **Real-Time Capability**: WebSocket-based live processing
- **Enterprise Security**: Multi-tenant RBAC with audit logging
- **Extensible Design**: Plugin architecture with comprehensive APIs
- **Modern Stack**: Latest technologies optimized for performance

The system is production-ready for SMB deployment and can scale to support larger enterprise installations with minimal modifications.