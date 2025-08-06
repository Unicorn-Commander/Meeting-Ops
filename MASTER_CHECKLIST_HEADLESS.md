# Meeting-Ops Master Deployment Checklist - Ubuntu 25.04 Headless Server

## ⚠️ SYSTEM VALIDATION STATUS (August 6, 2025)
**Basic Recording Infrastructure: PARTIALLY WORKING**
- ✅ **Authentication**: User login successful with PostgreSQL backend
- ✅ **Basic Recording**: Can record audio from USB microphone to files
- ✅ **Audio Monitoring**: Real-time audio levels working via WebSocket
- ✅ **Session Creation**: Can create and start recording sessions
- ❌ **Transcription**: Whisper command missing - "No such file or directory: 'whisper'"
- ❌ **File Management**: Database errors - "AudioFile has no attribute 'deleted_at'"
- ❌ **Settings API**: Multiple endpoints returning 404 errors
- ❌ **Summarization**: No working LLM integration yet
- ❌ **Audio Device Testing**: Test endpoints not working

**System Requirements Status:**
- ✅ Ubuntu Server 25.04 with Linux 6.14 kernel
- ✅ AMD Ryzen CPU with Phoenix NPU detected
- ✅ USB audio device working (hw:0,0)
- ✅ PostgreSQL, Redis, Qdrant services operational
- ✅ Python 3.13 environment with basic dependencies

## System Requirements
- [ ] Ubuntu Server 25.04 (headless) with Linux 6.14+ kernel
- [ ] AMD Ryzen CPU with NPU (Phoenix/Hawk Point/Strix Point)
- [ ] Minimum 16GB RAM, 100GB storage SSD
- [ ] USB audio device (USB microphone required)
- [ ] Network connectivity for remote access
- [ ] SSH access configured

## Pre-Installation Verification
- [ ] Check Ubuntu version: `lsb_release -a` (should show 25.04)
- [ ] Verify kernel: `uname -r` (should be 6.14 or higher)
- [ ] Check NPU device: `ls -la /dev/accel/accel0`
- [ ] Verify audio device: `arecord -l` (should show USB device)
- [ ] Check available disk space: `df -h` (need 50GB+ free)
- [ ] Verify network: `ip a` (note IP for remote access)

## Docker & Services Installation

### Step 1: Docker Setup
- [ ] Run: `./01-install-docker.sh`
- [ ] Log out and log back in (for docker group)
- [ ] Verify: `docker run hello-world` (should work without sudo)

### Step 2: Audio Configuration  
- [ ] Run: `./02-setup-audio.sh`
- [ ] Add user to audio and render groups
- [ ] Verify USB mic: `arecord -l | grep USB`
- [ ] Test recording: `arecord -d 5 test.wav`

### Step 3: Start Docker Services
- [ ] Run: `./05-start-stack.sh`
- [ ] Verify PostgreSQL: `docker ps | grep postgres` (port 5432)
- [ ] Verify Redis: `docker ps | grep redis` (port 6379)
- [ ] Verify Qdrant: `docker ps | grep qdrant` (port 6333)

## Backend Installation

### Python Environment
- [ ] Install Python 3.13: `sudo apt install python3.13 python3.13-venv python3.13-dev`
- [ ] Create venv: `cd backend && python3.13 -m venv venv`
- [ ] Activate: `source venv/bin/activate`
- [ ] Upgrade pip: `pip install --upgrade pip`

### Dependencies Installation
- [ ] Install core: `pip install fastapi uvicorn python-multipart`
- [ ] Install database: `pip install sqlalchemy psycopg2-binary`
- [ ] Install Redis: `pip install redis`
- [ ] Install audio: `pip install sounddevice numpy scipy librosa`
- [ ] Install auth: `pip install python-jose passlib bcrypt`
- [ ] Install email: `pip install email-validator`
- [ ] Install websockets: `pip install websockets`

### NPU Setup (Optional but Recommended)
- [ ] Check NPU permissions: `ls -la /dev/accel/accel0`
- [ ] Add user to render group: `sudo usermod -a -G render $USER`
- [ ] Download Whisper models: `python download_whisper_models.py`
- [ ] Test NPU access: `python test_npu_access.py`

### Database Initialization
- [ ] Run migrations: `python init_db.py`
- [ ] Create admin user: `python reset_admin.py`
- [ ] Default credentials: admin / Changeme123!

### Backend Startup
- [ ] Set environment variables:
  ```bash
  export DATABASE_URL="postgresql://meetingops:REMOVED@localhost:5432/meeting_sessions"
  export REDIS_URL="redis://localhost:6379"
  ```
- [ ] Start backend: `./venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 9050`
- [ ] Verify API: `curl http://localhost:9050/api/status`

## Frontend Installation

### Node.js Setup
- [ ] Install Node.js 20: `curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -`
- [ ] Install: `sudo apt-get install -y nodejs`
- [ ] Verify: `node --version` (should be 20.x)

### Frontend Build
- [ ] Navigate: `cd frontend`
- [ ] Install deps: `npm install`
- [ ] Build production: `npm run build`
- [ ] Start dev server: `npm run dev -- --host 0.0.0.0`
- [ ] Note: Frontend runs on port 7777/7778

## Integration Testing

### Audio Recording
- [ ] Access Recording Page: http://[SERVER_IP]:7777
- [ ] Login with admin/Changeme123!
- [ ] Navigate to "Record Meeting"
- [ ] Create new recording session
- [ ] Start recording (verify audio device hw:0,0)
- [ ] Stop recording after 10 seconds
- [ ] Verify file created in ~/.meeting-ops/recordings/

### Core Features
- [ ] Recording creates WAV files (44.1kHz, mono)
- [ ] Session list shows recordings
- [ ] Export to TXT works
- [ ] Export to JSON works
- [ ] Auto-rename feature works
- [ ] File playback works (if audio player available)

### Known Limitations (Headless)
- [ ] No GUI audio playback (use export/download)
- [ ] Transcription returns mock data (Whisper models not loaded)
- [ ] Summarization empty (Ollama not running)
- [ ] Audio monitor conflicts with recording (both use hw:0,0)

## Production Deployment

### Systemd Services
- [ ] Create service files in /etc/systemd/system/
- [ ] Enable services: `sudo systemctl enable meeting-ops-backend`
- [ ] Start services: `sudo systemctl start meeting-ops-backend`
- [ ] Check logs: `sudo journalctl -u meeting-ops-backend -f`

### Nginx Reverse Proxy (Optional)
- [ ] Install nginx: `sudo apt install nginx`
- [ ] Configure proxy for ports 9050 and 7777
- [ ] Enable WebSocket support
- [ ] Set up SSL certificates (Let's Encrypt)

### Security Hardening
- [ ] Change default admin password immediately
- [ ] Configure firewall (ufw):
  ```bash
  sudo ufw allow 22/tcp    # SSH
  sudo ufw allow 80/tcp    # HTTP
  sudo ufw allow 443/tcp   # HTTPS
  sudo ufw allow 7777/tcp  # Frontend (restrict to local network)
  sudo ufw allow 9050/tcp  # Backend API (restrict to local network)
  sudo ufw enable
  ```
- [ ] Set up fail2ban for SSH protection
- [ ] Configure CORS origins in backend
- [ ] Set secure JWT secret key

## Troubleshooting

### Audio Issues
- [ ] Kill audio monitor: `pkill -f arecord`
- [ ] Check USB device: `lsusb | grep -i audio`
- [ ] Test direct recording: `arecord -D hw:0,0 -d 5 test.wav`
- [ ] Check permissions: `groups` (should include audio)

### Backend Issues
- [ ] Check logs: Backend console output
- [ ] Verify database: `PGPASSWORD=REMOVED psql -h localhost -U meetingops -d meeting_sessions`
- [ ] Check Redis: `redis-cli ping` (should return PONG)
- [ ] API docs: http://localhost:9050/docs

### Frontend Issues
- [ ] Check dev server: Should bind to 0.0.0.0, not localhost
- [ ] Verify proxy: Frontend should proxy /api to backend
- [ ] Check console: Browser developer tools for errors
- [ ] Clear cache: Hard refresh (Ctrl+Shift+R)

## Performance Optimization

### For Headless Server
- [ ] Disable unnecessary services
- [ ] Configure swap: `sudo fallocate -l 8G /swapfile`
- [ ] Tune PostgreSQL for available RAM
- [ ] Enable Redis persistence
- [ ] Set up log rotation

### Audio Optimization
- [ ] Use 44.1kHz for USB mics (native rate)
- [ ] Buffer size tuning in arecord
- [ ] Disable audio monitor during recording
- [ ] Use direct ALSA, not PulseAudio

## Next Steps

1. **Enable Real Transcription**
   - Download Whisper ONNX models
   - Configure model path
   - Test with real audio

2. **Enable Summarization**
   - Install Ollama or configure LLM API
   - Set up summarization templates
   - Test summary generation

3. **Fix Audio Monitor Conflict**
   - Implement audio device sharing
   - Or disable monitor during recording
   - Or use separate devices

4. **Production Hardening**
   - Automated backups
   - Monitoring and alerts
   - Log aggregation
   - Performance metrics

## Success Criteria - IN PROGRESS ⚠️
- [x] Can access web UI from remote machine ✅ **WORKING**
- [x] Can record audio from microphone ✅ **WORKING** (basic recording only)
- [ ] Recording files with transcription ❌ **NOT WORKING** (Whisper missing)
- [ ] Session management fully functional ⚠️ **PARTIALLY** (basic CRUD only)
- [ ] Export features work (TXT/JSON) ❌ **UNKNOWN** (needs testing)
- [ ] File management working ❌ **NOT WORKING** (database errors)
- [ ] Summarization working ❌ **NOT WORKING** (no LLM integration)
- [ ] System stable for 24 hours (needs long-term testing)
- [ ] No memory leaks or crashes (needs monitoring)

## 📋 CURRENT STATUS SUMMARY
**The Meeting-Ops system has basic infrastructure but core features are not working:**

### ✅ **Working Features**
1. **User Authentication**: Login system working with admin/changeme123!
2. **Basic Audio Recording**: Can capture audio from USB microphone to files
3. **Real-time Audio Monitoring**: WebSocket audio level streaming working
4. **Basic Session Creation**: Can create and start recording sessions
5. **Database Connection**: PostgreSQL storing basic session data

### ❌ **Major Issues Remaining**
1. **Transcription System**: Whisper not installed - critical feature missing
2. **File Management**: Database schema errors preventing file listing
3. **Settings System**: API endpoints missing or not working  
4. **Summarization**: No working LLM integration
5. **Export Features**: Unknown status, needs testing
6. **Audio Device Management**: Test endpoints not functional

### 🎯 **Next Critical Tasks**
1. Install and configure Whisper for transcription
2. Fix database schema issues for file management
3. Implement missing settings API endpoints
4. Set up LLM integration for summarization
5. Test and fix export functionality

## Quick Test Commands
```bash
# Test recording API
curl -X POST http://localhost:9050/api/simple/recording-sessions \
  -H "Content-Type: application/json" \
  -d '{"name": "Test Recording", "description": "Testing audio"}'

# Start recording (replace SESSION_ID)
curl -X POST http://localhost:9050/api/simple/recording-sessions/SESSION_ID/start

# Stop recording
curl -X POST http://localhost:9050/api/simple/recording-sessions/SESSION_ID/stop

# List sessions
curl http://localhost:9050/api/simple/recording-sessions

# Check audio devices
curl http://localhost:9050/api/simple/audio-devices
```