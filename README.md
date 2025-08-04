# Meeting-Ops Recording Appliance

Part of the Unicorn Commander Suite by Magic Unicorn Unconventional Technology & Stuff Inc.

## Overview

Meeting-Ops is a professional-grade meeting recording and transcription appliance designed for Small and Medium Businesses (SMB). Built on AMD Ryzen hardware with NPU acceleration, it provides real-time transcription, speaker diarization, and intelligent meeting insights.

## Key Features

- **Real-time Transcription**: Hardware-accelerated transcription with 220x+ speedup using AMD NPU
- **Speaker Diarization**: Automatic speaker identification and separation
- **Meeting Insights**: Automated summarization and action item extraction
- **Web-based Interface**: Access from any device on your network
- **Enterprise Security**: JWT authentication with role-based access control
- **Multiple Export Formats**: TXT, JSON, and PDF exports
- **Email Notifications**: Automated meeting summaries via email
- **Calendar Integration**: Microsoft 365 and Google Workspace support

## Technical Specifications

- **Hardware**: AMD Ryzen with NPU (16 TOPS INT8)
- **Performance**: 2,985x real-time processing (0.175s for 8.7min audio)
- **Models**: Whisper-base with INT8 quantization
- **Backend**: Python 3.13, FastAPI, PostgreSQL
- **Frontend**: React, TypeScript, Tailwind CSS
- **Deployment**: Docker, nginx, systemd

## Quick Start

### Prerequisites
- Linux system with AMD NPU hardware
- Docker and Docker Compose
- Node.js 18+ and npm
- Python 3.13+

### Installation

1. Clone the repository:
```bash
git clone https://github.com/Unicorn-Commander/Meeting-Ops.git
cd Meeting-Ops
```

2. Set up the backend environment:
```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

3. Configure environment variables:
```bash
cp .env.example .env
# Edit .env with your database credentials
```

4. Start the services:
```bash
# Terminal 1: Start PostgreSQL, Redis, Qdrant
cd ~/Meeting-Ops
docker compose -f docker-compose-services.yml up -d

# Terminal 2: Start backend
cd ~/Meeting-Ops/backend
./venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 9050 --reload

# Terminal 3: Start frontend
cd ~/Meeting-Ops/frontend
npm install
npm run dev
```

5. Access the application:
- Frontend: http://localhost:7777
- API Documentation: http://localhost:9050/docs
- Default credentials: admin / admin

### USB Microphone Setup

The system automatically detects USB microphones:

1. Plug in your USB microphone
2. Verify detection:
```bash
arecord -l | grep USB
# Should show: card 0: Device [USB PnP Sound Device], device 0: USB Audio [USB Audio]
```

3. The backend automatically configures:
   - Device: hw:0,0 (USB device takes priority)
   - Sample rate: 44.1kHz (standard for USB mics)
   - Channels: Mono
   - Gain: 100x amplification for optimal levels

4. Audio level meter shows:
   - Background noise: 5-20%
   - Normal speech: 30-60%
   - Loud speech: 80-100%

Note: The system uses direct ALSA access via `arecord` for reliability.

### Development Setup

Backend:
```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m uvicorn main:app --host 0.0.0.0 --port 9050 --reload
```

Frontend:
```bash
cd frontend
npm install
npm run dev
```

## Architecture

Meeting-Ops uses a modern microservices architecture:

- **Recording Service**: Captures audio from USB microphones or line-in
- **Transcription Engine**: NPU-accelerated Whisper model processing
- **Session Manager**: Handles recording sessions and metadata
- **Analytics Engine**: Generates meeting insights and metrics
- **WebSocket Server**: Real-time audio streaming and transcription
- **API Gateway**: RESTful API with JWT authentication

## NPU Acceleration

The system leverages AMD NPU hardware for exceptional performance:

- Custom MLIR-AIE2 kernels for INT8 operations
- Direct hardware access via /dev/accel/accel0
- DMA-optimized data flow
- Zero CPU usage during transcription

## API Overview

Core endpoints:
- `POST /api/auth/login` - User authentication
- `POST /api/recording-sessions` - Create recording session
- `GET /api/recording-sessions/{id}/export` - Export transcription
- `WS /ws/transcription` - Live transcription stream
- `GET /api/analytics/meetings` - Meeting analytics

See full API documentation at http://localhost:9050/docs

## Configuration

Environment variables:
- `DATABASE_URL` - PostgreSQL connection string
- `SECRET_KEY` - JWT signing key
- `SMTP_HOST` - Email server configuration
- `SMTP_USER` - Email authentication
- `OPENAI_API_KEY` - Optional OpenAI integration
- `ANTHROPIC_API_KEY` - Optional Anthropic integration

### LLM Configuration

Meeting-Ops supports multiple LLM backends for summarization:

1. **llama.cpp (Recommended)**:
   - Automatic detection of GGUF models
   - GPU acceleration via Vulkan
   - No API keys required
   - 35-40 tokens/sec with Gemma 2B Q4

2. **Ollama (Fallback)**:
   - Set `OLLAMA_URL=http://localhost:11434`
   - Uses gemma3n model by default

3. **Cloud APIs (Optional)**:
   - OpenAI or Anthropic via API keys
   - Higher quality but requires internet

## Production Deployment

1. Configure nginx reverse proxy:
```bash
sudo ./setup-nginx.sh
```

2. Install systemd service:
```bash
cd deployment
sudo ./install.sh
```

3. Enable SSL (optional):
```bash
sudo ./setup-ssl.sh
```

## Features in Detail

### Recording Sessions
- Start/stop/pause recording controls
- Automatic file management
- Session metadata and tagging

### Real-time Transcription
- Live WebSocket streaming
- 2-second chunk processing
- Word-level timestamps

### Speaker Diarization
- Automatic speaker detection
- Speaker time analytics
- Exportable speaker segments

### Meeting Analytics
- Duration and participation metrics
- Key topics extraction
- Action items identification
- Trend analysis over time

### Integration Options
- Webhook notifications
- Calendar synchronization
- Email summaries
- API automation

## Security

- JWT-based authentication
- Role-based permissions (admin, manager, user, viewer)
- API key support for automation
- Audit logging
- Encrypted storage

## Performance

Benchmarked performance metrics:
- Audio processing: 2,985x real-time
- Transcription latency: <100ms per chunk
- Speaker diarization: 7,866x speedup
- Token throughput: 4,789 tokens/second

## Troubleshooting

Common issues:

1. **NPU not detected**: Ensure AMD NPU drivers are installed
2. **Audio device errors**: Check USB microphone permissions
3. **Database connection**: Verify PostgreSQL is running
4. **WebSocket disconnects**: Check firewall settings

## Contributing

This is a commercial product by Magic Unicorn Unconventional Technology & Stuff Inc. For support and licensing inquiries, please contact aaron@magicunicorn.tech.

## License

Proprietary software. All rights reserved by Magic Unicorn Unconventional Technology & Stuff Inc.

## Acknowledgments

Built with modern open-source technologies including FastAPI, React, PostgreSQL, and Whisper.

---

Meeting-Ops - Professional Meeting Intelligence for Modern Businesses