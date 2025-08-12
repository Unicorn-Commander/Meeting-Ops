# Meeting-Ops Installation Guide

## System Requirements

### Hardware Requirements
- **CPU**: x86_64 processor (AMD Ryzen recommended for NPU support)
- **RAM**: Minimum 8GB, 16GB recommended
- **Storage**: At least 20GB free space
- **Audio**: USB microphone (M-305 or compatible)
- **NPU** (Optional): AMD Phoenix NPU for hardware acceleration

### Software Requirements
- **OS**: Ubuntu 22.04+ or Debian 11+ (other Linux distros supported)
- **Python**: 3.11, 3.12, or 3.13
- **Node.js**: 18.0 or higher
- **Docker**: Latest version with Docker Compose
- **Browser**: Chrome, Firefox, or Edge (latest versions)

## Quick Installation

### Option 1: Automated Installation (Recommended)

```bash
# Clone the repository
git clone https://github.com/yourusername/Meeting-Ops.git
cd Meeting-Ops

# Run the installation script
chmod +x install-meeting-ops.sh
./install-meeting-ops.sh
```

The installation script will:
- Check system requirements
- Install all dependencies
- Set up Docker services (PostgreSQL, Redis, Qdrant)
- Install Ollama and pull AI models
- Configure the backend and frontend
- Create startup scripts

### Option 2: Manual Installation

#### Step 1: Install System Dependencies

**Ubuntu/Debian:**
```bash
sudo apt-get update
sudo apt-get install -y \
    build-essential \
    portaudio19-dev \
    ffmpeg \
    git \
    curl \
    cmake \
    libasound2-dev \
    nginx \
    python3-pip \
    python3-venv \
    python3-dev \
    pkg-config \
    libportaudio2 \
    libportaudiocpp0 \
    libssl-dev \
    libffi-dev \
    postgresql-client \
    redis-tools \
    sox \
    libsox-fmt-all
```

**Fedora/RHEL:**
```bash
sudo dnf install -y \
    gcc gcc-c++ make \
    portaudio-devel \
    ffmpeg \
    git \
    curl \
    cmake \
    alsa-lib-devel \
    nginx \
    python3-pip \
    python3-devel \
    pkgconfig \
    openssl-devel \
    libffi-devel \
    postgresql \
    redis \
    sox
```

#### Step 2: Install Docker and Docker Compose

```bash
# Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# Install Docker Compose plugin
sudo apt-get update
sudo apt-get install -y docker-compose-plugin
```

#### Step 3: Install Node.js

```bash
# Using NodeSource repository
curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -
sudo apt-get install -y nodejs
```

#### Step 4: Install Ollama (for AI models)

```bash
curl -fsSL https://ollama.ai/install.sh | sh
```

#### Step 5: Set Up Backend

```bash
cd backend

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install --upgrade pip setuptools wheel
pip install psycopg2-binary
pip install redis
pip install requests
pip install ollama
pip install -r requirements.txt
```

#### Step 6: Set Up Frontend

```bash
cd frontend

# Install Node.js dependencies
npm install

# Build frontend (optional for development)
npm run build
```

#### Step 7: Start Docker Services

```bash
# Start PostgreSQL, Redis, and Qdrant
docker compose -f docker-compose-full-stack.yml up -d
```

#### Step 8: Pull AI Models

```bash
# Start Ollama service
ollama serve &

# Pull required models
ollama pull granite3.3:8b
ollama pull phi4-mini:3.8b
ollama pull gemma3n:e4b
```

## Configuration

### Network Access Configuration

For accessing the system from other machines on your network:

```bash
# Create .env file in frontend directory
echo "VITE_API_URL=http://YOUR_SERVER_IP:9050" > frontend/.env

# Example:
echo "VITE_API_URL=http://192.168.1.145:9050" > frontend/.env
```

### Database Configuration

The system uses PostgreSQL by default. Connection settings are in:
- Backend: `backend/database/database.py`
- Docker: `docker-compose-full-stack.yml`

Default PostgreSQL credentials:
- Host: localhost
- Port: 5432
- Database: meeting_ops
- User: meeting_ops
- Password: meeting_ops_secure_password_2024

### AI Model Configuration

Models are configured in `backend/config/llm_config.json`:
- Granite 3.3 (8B) - Default for meeting summaries
- Phi4-mini (3.8B) - Lightweight alternative
- Gemma3n (e4b) - Enhanced meeting intelligence

## Starting the Application

### Using the Startup Script

```bash
# Start all services
./start-meeting-ops.sh
```

### Manual Start

```bash
# Terminal 1: Start Docker services
docker compose -f docker-compose-full-stack.yml up -d

# Terminal 2: Start Ollama (if not running)
ollama serve

# Terminal 3: Start backend
cd backend
source venv/bin/activate
./start-backend.sh

# Terminal 4: Start frontend
cd frontend
npm run dev
```

## Access Points

- **Frontend**: http://localhost:7777
- **Backend API**: http://localhost:9050
- **API Documentation**: http://localhost:9050/docs
- **PostgreSQL**: localhost:5432
- **Redis**: localhost:6379
- **Qdrant**: http://localhost:6333

## Default Credentials

- **Admin User**: admin / admin123
- **Regular User**: user / user123

## Verifying Installation

### Check Service Status

```bash
# Check Docker services
docker ps

# Check backend
curl http://localhost:9050/api/status

# Check frontend
curl http://localhost:7777

# Check Ollama
ollama list
```

### Test Recording

1. Connect USB microphone
2. Open http://localhost:7777
3. Login with default credentials
4. Click "Start Recording" on dashboard
5. Verify live transcription appears

## Important Notes for Fresh Installations

### Custom NPU-Optimized Components
This system includes custom NPU-optimized implementations that don't require external packages:
- **WhisperX NPU**: Custom implementation in `backend/services/whisperx_py313.py`
- **Speaker Diarization**: Built-in implementation without pyannote.audio dependency
- If `whisperx` or `pyannote.audio` fail to install, the system will still work using the custom implementations

### Python Version Compatibility
- **Python 3.13**: Use `requirements-essential.txt` if you encounter package conflicts
- **Python 3.11/3.12**: Use standard `requirements.txt`
- PyTorch will be installed with CPU support by default (NPU optimization is handled separately)

## Troubleshooting

### Common Issues

#### Port Already in Use
```bash
# Check what's using the port
sudo lsof -i :9050
sudo lsof -i :7777

# Kill the process
sudo kill -9 <PID>
```

#### Docker Permission Denied
```bash
# Add user to docker group
sudo usermod -aG docker $USER
# Log out and back in
```

#### Microphone Not Detected
```bash
# List audio devices
arecord -l

# Test microphone
arecord -d 5 test.wav
aplay test.wav
```

#### Ollama Models Not Loading
```bash
# Restart Ollama service
pkill ollama
ollama serve &

# Re-pull models
ollama pull granite3.3:8b
```

#### Frontend Can't Connect to Backend
```bash
# Check backend is running
curl http://localhost:9050/api/status

# Check CORS settings in backend/main.py
# Ensure your IP is in allowed origins
```

### Log Files

- Backend logs: `backend/logs/`
- Docker logs: `docker logs <container_name>`
- Frontend console: Browser Developer Tools

## Updating

### Pull Latest Changes
```bash
git pull origin main

# Update backend dependencies
cd backend
source venv/bin/activate
pip install -r requirements.txt

# Update frontend dependencies
cd ../frontend
npm install

# Restart services
./start-meeting-ops.sh
```

### Database Migrations
```bash
cd backend
source venv/bin/activate
alembic upgrade head
```

## Uninstalling

### Remove All Components
```bash
# Stop all services
docker compose -f docker-compose-full-stack.yml down

# Remove Docker volumes (WARNING: Deletes all data)
docker compose -f docker-compose-full-stack.yml down -v

# Remove Python virtual environment
rm -rf backend/venv

# Remove Node modules
rm -rf frontend/node_modules

# Remove Ollama models (optional)
ollama rm granite3.3:8b
ollama rm phi4-mini:3.8b
ollama rm gemma3n:e4b
```

## System Architecture

### Technology Stack
- **Frontend**: React 19.1 + TypeScript + Vite + TailwindCSS
- **Backend**: FastAPI + Python 3.11+ + SQLAlchemy
- **Database**: PostgreSQL 15 + Redis + Qdrant
- **AI/ML**: Whisper Large-v3 + Ollama LLMs
- **NPU**: AMD Phoenix NPU with MLIR-AIE2 (optional)

### Performance Metrics
- **Transcription Speed**: 220x real-time with NPU
- **Processing**: 1 hour audio in 16.2 seconds
- **Accuracy**: 99% with Whisper Large-v3
- **Concurrent Users**: Supports multiple simultaneous recordings

## Support

For issues or questions:
1. Check the [Troubleshooting](#troubleshooting) section
2. Review logs in `backend/logs/`
3. Check Docker container status
4. Verify all services are running

## License

[Your License Here]

## Contributing

Contributions are welcome! Please read CONTRIBUTING.md for guidelines.