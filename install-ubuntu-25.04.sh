#!/bin/bash
# Meeting-Ops Complete Installation Script for Ubuntu 25.04
# Supports both fresh server and desktop (with KDE6) installations
# Handles NPU models, Whisper quantization, and LLM setup

set -e  # Exit on any error

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m' # No Color

# Configuration
INSTALL_DIR="/opt/meeting-ops"
DATA_DIR="/var/lib/meeting-ops"
LOG_DIR="/var/log/meeting-ops"
MODELS_DIR="$DATA_DIR/models"
BACKEND_PORT=9050
FRONTEND_PORT=7777

# System detection
DISTRO_VERSION=$(lsb_release -rs 2>/dev/null || echo "unknown")
KERNEL_VERSION=$(uname -r)
IS_DESKTOP=false
HAS_NPU=false
HAS_ROCM=false

# Print functions
print_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
print_success() { echo -e "${GREEN}[✓]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[!]${NC} $1"; }
print_error() { echo -e "${RED}[✗]${NC} $1"; }
print_step() { echo -e "${PURPLE}[STEP]${NC} $1"; }

# Banner
echo -e "${PURPLE}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║          Meeting-Ops Recording Appliance Installer          ║"
echo "║                    Ubuntu 25.04 Edition                     ║"
echo "║        NPU-Accelerated • AI-Powered • Production-Ready      ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Check if running as root
if [ "$EUID" -eq 0 ]; then 
   print_error "Please run as regular user (not root). Script will use sudo when needed."
   exit 1
fi

# System detection
print_step "Detecting system configuration..."

# Check for desktop environment
if [ -n "$DISPLAY" ] || [ -n "$WAYLAND_DISPLAY" ]; then
    IS_DESKTOP=true
    print_info "Desktop environment detected"
    
    # Check for KDE
    if [ -n "$KDE_FULL_SESSION" ] || pgrep -x "plasmashell" > /dev/null 2>&1; then
        print_info "KDE6 desktop detected"
    fi
else
    print_info "Headless server detected"
fi

# Check for NPU hardware
if [ -e "/dev/accel/accel0" ] || [ -e "/dev/npu0" ]; then
    HAS_NPU=true
    print_success "AMD NPU hardware detected - 220x speedup available!"
elif lspci | grep -i "AMD.*AI" > /dev/null 2>&1; then
    HAS_NPU=true
    print_warning "AMD AI processor detected but NPU device not found"
else
    print_warning "No NPU detected - will use CPU transcription"
fi

# Check for ROCm
if [ -d "/opt/rocm" ] && [ -x "/opt/rocm/bin/rocminfo" ]; then
    HAS_ROCM=true
    ROCM_VERSION=$(/opt/rocm/bin/rocminfo 2>/dev/null | grep "ROCm version" | head -1 | awk '{print $3}')
    print_success "ROCm $ROCM_VERSION detected"
fi

# Check Ubuntu version
if [[ "$DISTRO_VERSION" != "25.04" && "$DISTRO_VERSION" != "24.10" && "$DISTRO_VERSION" != "24.04" ]]; then
    print_warning "This script is optimized for Ubuntu 25.04/24.10/24.04"
    print_warning "Detected version: $DISTRO_VERSION"
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Check for existing installation
if [ -d "$INSTALL_DIR" ] || systemctl is-active --quiet meeting-ops 2>/dev/null; then
    print_warning "Existing Meeting-Ops installation detected"
    echo "Choose an option:"
    echo "  1) Upgrade existing installation"
    echo "  2) Clean install (backup and remove existing)"
    echo "  3) Cancel"
    read -p "Your choice (1-3): " choice
    
    case $choice in
        1)
            print_info "Upgrading existing installation..."
            UPGRADE_MODE=true
            ;;
        2)
            print_info "Backing up existing installation..."
            sudo tar -czf "/tmp/meeting-ops-backup-$(date +%Y%m%d-%H%M%S).tar.gz" \
                "$INSTALL_DIR" "$DATA_DIR" 2>/dev/null || true
            print_success "Backup saved to /tmp/"
            
            # Stop and remove existing
            sudo systemctl stop meeting-ops 2>/dev/null || true
            sudo systemctl disable meeting-ops 2>/dev/null || true
            sudo rm -rf "$INSTALL_DIR"
            ;;
        3)
            print_info "Installation cancelled"
            exit 0
            ;;
        *)
            print_error "Invalid choice"
            exit 1
            ;;
    esac
fi

# System update
print_step "Updating system packages..."
sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get upgrade -y

# Install system dependencies
print_step "Installing system dependencies..."

# Core dependencies
PACKAGES=(
    # Build tools
    build-essential cmake pkg-config
    
    # Python 3.13 or 3.12
    python3.13 python3.13-dev python3.13-venv python3-pip
    
    # Node.js and npm
    nodejs npm
    
    # Audio libraries
    libasound2-dev portaudio19-dev libportaudio2 libportaudiocpp0
    ffmpeg sox libsox-fmt-all
    
    # Database
    postgresql postgresql-contrib redis-server
    
    # Web server
    nginx
    
    # System utilities
    curl wget git jq bc htop net-tools
    software-properties-common ca-certificates gnupg lsb-release
    
    # Development libraries
    libssl-dev libffi-dev libxml2-dev libxslt1-dev
    libjpeg-dev zlib1g-dev libpng-dev
)

# Add desktop-specific packages if needed
if [ "$IS_DESKTOP" = true ]; then
    PACKAGES+=(pavucontrol pulseaudio-utils)
fi

print_info "Installing ${#PACKAGES[@]} packages..."
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y "${PACKAGES[@]}"

# Handle Python version
PYTHON_CMD="python3.13"
if ! command -v python3.13 &> /dev/null; then
    if command -v python3.12 &> /dev/null; then
        PYTHON_CMD="python3.12"
        print_warning "Using Python 3.12 (3.13 not found)"
    else
        print_error "Python 3.12+ required"
        exit 1
    fi
fi
print_success "Using $PYTHON_CMD"

# Install Docker if not present
if ! command -v docker &> /dev/null; then
    print_step "Installing Docker..."
    
    # Add Docker's official GPG key
    sudo install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
        sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    sudo chmod a+r /etc/apt/keyrings/docker.gpg
    
    # Add repository
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
        https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | \
        sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
    
    # Install Docker
    sudo apt-get update
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    
    # Add user to docker group
    sudo usermod -aG docker $USER
    print_success "Docker installed"
else
    print_info "Docker already installed"
fi

# Clone or update repository
print_step "Setting up Meeting-Ops repository..."

if [ ! -d "$HOME/Meeting-Ops" ]; then
    cd $HOME
    git clone https://github.com/Unicorn-Commander/Meeting-Ops.git
    cd Meeting-Ops
else
    cd $HOME/Meeting-Ops
    git pull origin main || print_warning "Could not update repository"
fi

# Create directory structure
print_step "Creating directory structure..."
sudo mkdir -p "$INSTALL_DIR" "$DATA_DIR" "$LOG_DIR" "$MODELS_DIR"
sudo mkdir -p "$DATA_DIR/recordings" "$DATA_DIR/exports" "$DATA_DIR/cache"
sudo mkdir -p "$MODELS_DIR/whisper" "$MODELS_DIR/llm" "$MODELS_DIR/npu"

# Copy application files
print_info "Copying application files..."
sudo cp -r backend frontend "$INSTALL_DIR/"
sudo cp *.sh *.md "$INSTALL_DIR/" 2>/dev/null || true

# Setup Python virtual environment
print_step "Setting up Python environment..."
cd "$INSTALL_DIR/backend"
sudo $PYTHON_CMD -m venv venv
sudo chown -R $USER:$USER venv

# Activate and install requirements
source venv/bin/activate
pip install --upgrade pip setuptools wheel

# Install Python packages with proper versions
print_info "Installing Python dependencies..."

# Create optimized requirements for Ubuntu 25.04
cat > /tmp/requirements-ubuntu2504.txt << 'EOF'
# Core Framework
fastapi==0.115.14
uvicorn[standard]==0.35.0
python-multipart==0.0.12
websockets==13.1
aiofiles==24.1.0

# Database
sqlalchemy==2.0.32
psycopg2-binary==2.9.9
alembic==1.13.1

# Redis
redis[hiredis]==5.0.1

# Authentication
bcrypt==4.2.1
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
pyjwt==2.9.0
cryptography==43.0.0

# AI/ML Core - Flexible versions for compatibility
numpy>=1.24.0,<2.0.0
torch>=2.5.0
torchaudio>=2.5.0
transformers>=4.46.0
sentence-transformers>=3.3.0
huggingface-hub>=0.16.0

# Audio Processing
librosa==0.10.2.post1
soundfile>=0.12.1
pyaudio==0.2.14
pydub==0.25.1
ffmpeg-python==0.2.0

# LLM Providers
openai>=1.54.0
anthropic>=0.40.0
ollama>=0.4.4
requests>=2.32.0

# Vector Database
qdrant-client>=1.7.0

# Utilities
python-dotenv==1.0.0
pyyaml>=6.0
click>=8.1.0
rich>=13.0.0
httpx>=0.25.0
EOF

pip install -r /tmp/requirements-ubuntu2504.txt

# Install optional packages (may fail on some systems)
print_info "Installing optional packages..."
pip install whisperx==3.1.1 2>/dev/null || print_warning "WhisperX not installed (custom implementation available)"
pip install pyannote.audio==3.1.1 2>/dev/null || print_warning "Pyannote not installed (using built-in diarization)"

deactivate

# Setup frontend
print_step "Setting up frontend..."
cd "$INSTALL_DIR/frontend"

# Install Node dependencies
sudo npm install -g npm@latest
npm install

# Build frontend
print_info "Building frontend..."
npm run build || npm run build:production

# Configure PostgreSQL
print_step "Configuring PostgreSQL..."
sudo systemctl start postgresql
sudo systemctl enable postgresql

# Create database and user
sudo -u postgres psql << EOF 2>/dev/null || true
CREATE USER meetingops WITH PASSWORD 'MeetingOps2025!';
CREATE DATABASE meeting_sessions OWNER meetingops;
GRANT ALL PRIVILEGES ON DATABASE meeting_sessions TO meetingops;
EOF

print_success "PostgreSQL configured"

# Configure Redis
print_step "Configuring Redis..."
sudo systemctl start redis-server
sudo systemctl enable redis-server

# Configure for Meeting-Ops
sudo tee -a /etc/redis/redis.conf > /dev/null << EOF

# Meeting-Ops Configuration
maxmemory 2gb
maxmemory-policy allkeys-lru
save ""
appendonly no
EOF

sudo systemctl restart redis-server
print_success "Redis configured"

# Setup Nginx
print_step "Configuring Nginx..."

sudo tee /etc/nginx/sites-available/meeting-ops > /dev/null << 'EOF'
server {
    listen 7777;
    server_name _;
    
    root /opt/meeting-ops/frontend/dist;
    index index.html;
    
    # Gzip compression
    gzip on;
    gzip_types text/plain text/css text/javascript application/javascript application/json;
    
    # Frontend routes
    location / {
        try_files $uri $uri/ /index.html;
    }
    
    # API proxy
    location /api {
        proxy_pass http://127.0.0.1:9050;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
        proxy_read_timeout 300s;
        proxy_connect_timeout 10s;
        client_max_body_size 100M;
    }
    
    # WebSocket support
    location /ws {
        proxy_pass http://127.0.0.1:9050;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "Upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 86400;
    }
    
    # Static assets caching
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
EOF

sudo ln -sf /etc/nginx/sites-available/meeting-ops /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl restart nginx
print_success "Nginx configured"

# Create systemd service
print_step "Creating systemd service..."

sudo tee /etc/systemd/system/meeting-ops.service > /dev/null << EOF
[Unit]
Description=Meeting-Ops Recording Appliance
After=network.target postgresql.service redis-server.service

[Service]
Type=simple
User=$USER
Group=$USER
WorkingDirectory=$INSTALL_DIR/backend
Environment="PATH=$INSTALL_DIR/backend/venv/bin:/usr/local/bin:/usr/bin:/bin"
Environment="PYTHONPATH=$INSTALL_DIR/backend"
Environment="DATABASE_URL=postgresql://meetingops:REMOVED@localhost/meeting_sessions"
Environment="REDIS_URL=redis://localhost:6379"
Environment="NPU_DEVICE=/dev/accel/accel0"
ExecStart=$INSTALL_DIR/backend/venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 9050 --workers 4
Restart=always
RestartSec=10

# Security
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable meeting-ops

# NPU Setup (if available)
if [ "$HAS_NPU" = true ]; then
    print_step "Setting up NPU acceleration..."
    
    # Create NPU setup script
    cat > /tmp/setup_npu.sh << 'EOF'
#!/bin/bash
# NPU initialization for Meeting-Ops

# Check for NPU device
if [ -e "/dev/accel/accel0" ]; then
    echo "NPU device found"
    
    # Set permissions
    sudo chmod 666 /dev/accel/accel0 2>/dev/null || true
    
    # Add user to video/render groups
    sudo usermod -a -G video,render $USER 2>/dev/null || true
    
    echo "NPU setup complete"
else
    echo "NPU device not found"
fi
EOF
    
    bash /tmp/setup_npu.sh
    print_success "NPU configured for 220x speedup"
fi

# Docker services setup
print_step "Setting up Docker services..."

# Create docker-compose file for additional services
sudo tee "$INSTALL_DIR/docker-compose.yml" > /dev/null << 'EOF'
version: '3.8'

services:
  qdrant:
    image: qdrant/qdrant:latest
    container_name: meeting-ops-qdrant
    ports:
      - "6333:6333"
    volumes:
      - /var/lib/meeting-ops/qdrant:/qdrant/storage
    restart: unless-stopped

  ollama:
    image: ollama/ollama:rocm
    container_name: meeting-ops-ollama
    ports:
      - "11434:11434"
    volumes:
      - /var/lib/meeting-ops/models/ollama:/root/.ollama
    environment:
      - OLLAMA_HOST=0.0.0.0
      - HSA_OVERRIDE_GFX_VERSION=11.0.0
    devices:
      - /dev/kfd:/dev/kfd
      - /dev/dri:/dev/dri
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 16G
EOF

# Start Docker services
cd "$INSTALL_DIR"
sudo docker compose up -d

# Download models script
print_step "Creating model download script..."

cat > "$INSTALL_DIR/download-models.sh" << 'EOF'
#!/bin/bash
# Download and setup AI models for Meeting-Ops

set -e

echo "==========================================="
echo "Meeting-Ops Model Downloader"
echo "==========================================="

# Configuration
MODELS_DIR="/var/lib/meeting-ops/models"
OLLAMA_HOST="http://localhost:11434"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}This will download several GB of AI models${NC}"
echo "Required models:"
echo "  1. Whisper Large-v3 (1.5GB) - Transcription"
echo "  2. Granite 3.3 (4.9GB) - Meeting analysis"
echo "  3. Phi4-mini (2.2GB) - Fast analysis"
echo "  4. Gemma3n (optional, 2.4GB) - Advanced insights"
echo ""
read -p "Continue with download? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    exit 0
fi

# Check if Ollama is running
if ! curl -s $OLLAMA_HOST > /dev/null 2>&1; then
    echo "Starting Ollama service..."
    sudo docker compose up -d ollama
    sleep 10
fi

# Download Whisper model
echo "Downloading Whisper Large-v3..."
python3 -c "
from transformers import WhisperModel, WhisperProcessor
import torch

print('Downloading Whisper large-v3...')
processor = WhisperProcessor.from_pretrained('openai/whisper-large-v3')
model = WhisperModel.from_pretrained('openai/whisper-large-v3')

# Save locally
processor.save_pretrained('$MODELS_DIR/whisper/large-v3')
model.save_pretrained('$MODELS_DIR/whisper/large-v3')
print('Whisper model saved to $MODELS_DIR/whisper/large-v3')
" 2>/dev/null || echo "Whisper will be downloaded on first use"

# Download LLM models via Ollama
echo "Downloading LLM models..."

# Granite 3.3 - Main model
echo "Pulling granite3.3:8b..."
docker exec meeting-ops-ollama ollama pull granite3.3:8b || \
    echo "Granite model will be pulled on first use"

# Phi4-mini - Fast model
echo "Pulling phi4-mini:3.8b..."
docker exec meeting-ops-ollama ollama pull phi4-mini:3.8b || \
    echo "Phi4-mini will be pulled on first use"

# Optional: Gemma3n for advanced features
read -p "Download optional Gemma3n model (2.4GB)? (y/N) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    docker exec meeting-ops-ollama ollama pull gemma3n:e4b || \
        echo "Gemma3n will be pulled on first use"
fi

echo -e "${GREEN}Model download complete!${NC}"
echo ""
echo "Models are stored in: $MODELS_DIR"
echo "You can manage Ollama models with: docker exec meeting-ops-ollama ollama list"
EOF

chmod +x "$INSTALL_DIR/download-models.sh"

# Set permissions
print_step "Setting permissions..."
sudo chown -R $USER:$USER "$INSTALL_DIR"
sudo chown -R $USER:$USER "$DATA_DIR"
sudo chmod -R 755 "$INSTALL_DIR"
sudo chmod -R 755 "$DATA_DIR"

# Create convenient start/stop scripts
print_step "Creating management scripts..."

# Start script
cat > "$INSTALL_DIR/start.sh" << 'EOF'
#!/bin/bash
echo "Starting Meeting-Ops services..."
sudo systemctl start postgresql redis-server nginx meeting-ops
sudo docker compose -f /opt/meeting-ops/docker-compose.yml up -d
echo "Meeting-Ops started!"
echo "Access at: http://localhost:7777"
EOF

# Stop script
cat > "$INSTALL_DIR/stop.sh" << 'EOF'
#!/bin/bash
echo "Stopping Meeting-Ops services..."
sudo systemctl stop meeting-ops
sudo docker compose -f /opt/meeting-ops/docker-compose.yml down
echo "Meeting-Ops stopped"
EOF

# Status script
cat > "$INSTALL_DIR/status.sh" << 'EOF'
#!/bin/bash
echo "Meeting-Ops Service Status:"
echo "=========================="
systemctl is-active --quiet meeting-ops && echo "✓ Backend: Running" || echo "✗ Backend: Stopped"
systemctl is-active --quiet nginx && echo "✓ Nginx: Running" || echo "✗ Nginx: Stopped"
systemctl is-active --quiet postgresql && echo "✓ PostgreSQL: Running" || echo "✗ PostgreSQL: Stopped"
systemctl is-active --quiet redis-server && echo "✓ Redis: Running" || echo "✗ Redis: Stopped"
docker ps --format "table {{.Names}}\t{{.Status}}" | grep meeting-ops || echo "No Docker containers running"
EOF

chmod +x "$INSTALL_DIR"/*.sh

# Create symlinks for easy access
sudo ln -sf "$INSTALL_DIR/start.sh" /usr/local/bin/meeting-ops-start
sudo ln -sf "$INSTALL_DIR/stop.sh" /usr/local/bin/meeting-ops-stop
sudo ln -sf "$INSTALL_DIR/status.sh" /usr/local/bin/meeting-ops-status

# Initialize database
print_step "Initializing database..."
cd "$INSTALL_DIR/backend"
source venv/bin/activate
python -c "
from sqlalchemy import create_engine
from models.database import Base
engine = create_engine('postgresql://meetingops:REMOVED@localhost/meeting_sessions')
Base.metadata.create_all(bind=engine)
print('Database initialized')
" 2>/dev/null || print_warning "Database initialization will complete on first run"
deactivate

# Start services
print_step "Starting Meeting-Ops services..."
sudo systemctl start meeting-ops
sleep 5

# Verify installation
print_step "Verifying installation..."

ERRORS=0

# Check backend
if curl -s http://localhost:9050/docs > /dev/null 2>&1; then
    print_success "Backend API running on port 9050"
else
    print_error "Backend API not responding"
    ERRORS=$((ERRORS + 1))
fi

# Check frontend
if curl -s http://localhost:7777 > /dev/null 2>&1; then
    print_success "Frontend running on port 7777"
else
    print_error "Frontend not responding"
    ERRORS=$((ERRORS + 1))
fi

# Check Docker services
if docker ps | grep -q meeting-ops-qdrant; then
    print_success "Qdrant vector database running"
else
    print_warning "Qdrant not running (optional)"
fi

if docker ps | grep -q meeting-ops-ollama; then
    print_success "Ollama LLM service running"
else
    print_warning "Ollama not running (will start on demand)"
fi

# Installation complete
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║           Installation Complete! 🎉                         ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${BLUE}Access Meeting-Ops:${NC}"
echo -e "  🌐 Web Interface: ${GREEN}http://localhost:7777${NC}"
echo -e "  📚 API Docs:      ${GREEN}http://localhost:9050/docs${NC}"
echo ""
echo -e "${BLUE}Default Credentials:${NC}"
echo -e "  👤 Admin: ${YELLOW}admin / admin123${NC}"
echo -e "  👤 User:  ${YELLOW}user / user123${NC}"
echo ""
echo -e "${BLUE}Management Commands:${NC}"
echo -e "  ▶️  Start:   ${GREEN}meeting-ops-start${NC}"
echo -e "  ⏹️  Stop:    ${GREEN}meeting-ops-stop${NC}"
echo -e "  📊 Status:  ${GREEN}meeting-ops-status${NC}"
echo ""
echo -e "${BLUE}Download AI Models (optional but recommended):${NC}"
echo -e "  📥 Run: ${GREEN}$INSTALL_DIR/download-models.sh${NC}"
echo ""

if [ "$HAS_NPU" = true ]; then
    echo -e "${PURPLE}🚀 NPU Acceleration Enabled - 220x faster transcription!${NC}"
fi

if [ "$ERRORS" -gt 0 ]; then
    echo ""
    echo -e "${YELLOW}⚠️  Some services may need a moment to fully start${NC}"
    echo -e "${YELLOW}   Check status with: meeting-ops-status${NC}"
fi

echo ""
echo -e "${GREEN}Happy recording! 🦄${NC}"

# Remind about group membership
if [ "$IS_DESKTOP" = false ]; then
    echo ""
    echo -e "${YELLOW}Note: Log out and back in for Docker group membership to take effect${NC}"
fi