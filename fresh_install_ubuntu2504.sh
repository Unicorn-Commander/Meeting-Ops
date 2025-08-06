#!/bin/bash
# Meeting-Ops Complete Installation Script for Ubuntu 25.04 Headless Server
# This script installs everything needed for a fresh Ubuntu 25.04 system

set -e  # Exit on any error

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Print colored output
print_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
print_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Check if running as root
if [ "$EUID" -eq 0 ]; then 
   print_error "Please run this script as a regular user (not root)"
   print_info "The script will use sudo when needed"
   exit 1
fi

echo "=================================================="
echo "Meeting-Ops Installation for Ubuntu 25.04"
echo "Headless Server Configuration"
echo "=================================================="
echo

# Verify system requirements
print_info "Checking system requirements..."

# Check Ubuntu version
if ! lsb_release -a 2>/dev/null | grep -q "25.04"; then
    print_warning "This script is designed for Ubuntu 25.04"
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Check kernel version
KERNEL_VERSION=$(uname -r | cut -d. -f1,2)
if (( $(echo "$KERNEL_VERSION < 6.14" | bc -l) )); then
    print_warning "Kernel version is below 6.14. NPU support may not work."
fi

# Update system
print_info "Updating system packages..."
sudo apt-get update
sudo apt-get upgrade -y

# Install basic dependencies
print_info "Installing basic system dependencies..."
sudo apt-get install -y \
    curl \
    wget \
    git \
    build-essential \
    software-properties-common \
    ca-certificates \
    gnupg \
    lsb-release \
    bc \
    jq

# Install Docker
print_info "Installing Docker..."
if ! command -v docker &> /dev/null; then
    # Add Docker's official GPG key
    sudo install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    sudo chmod a+r /etc/apt/keyrings/docker.gpg

    # Add Docker repository
    echo \
      "deb [arch="$(dpkg --print-architecture)" signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
      "$(. /etc/os-release && echo "$VERSION_CODENAME")" stable" | \
      sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

    # Install Docker
    sudo apt-get update
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    
    # Add user to docker group
    sudo usermod -aG docker $USER
    print_success "Docker installed successfully"
else
    print_info "Docker already installed"
fi

# Install audio dependencies
print_info "Installing audio dependencies..."
sudo apt-get install -y \
    alsa-utils \
    libasound2-dev \
    portaudio19-dev \
    pulseaudio \
    pulseaudio-utils

# Add user to audio and render groups
sudo usermod -aG audio,render $USER
print_success "User added to audio and render groups"

# Install Python 3.13
print_info "Installing Python 3.13..."
if ! command -v python3.13 &> /dev/null; then
    # For Ubuntu 25.04, Python 3.13 should be in the repos
    sudo apt-get install -y python3.13 python3.13-venv python3.13-dev python3-pip
else
    print_info "Python 3.13 already installed"
fi

# Install Node.js 20
print_info "Installing Node.js 20..."
if ! command -v node &> /dev/null || [ $(node -v | cut -d. -f1 | cut -dv -f2) -lt 20 ]; then
    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
    sudo apt-get install -y nodejs
else
    print_info "Node.js 20+ already installed"
fi

# Install additional dependencies
print_info "Installing additional dependencies..."
sudo apt-get install -y \
    ffmpeg \
    redis-tools \
    postgresql-client \
    nginx \
    supervisor \
    htop \
    iotop \
    net-tools

# Clone Meeting-Ops repository if not already present
if [ ! -d "/home/$USER/Meeting-Ops" ]; then
    print_info "Cloning Meeting-Ops repository..."
    cd /home/$USER
    git clone https://github.com/your-org/Meeting-Ops.git || {
        print_warning "Could not clone from GitHub. Using local copy..."
    }
else
    print_info "Meeting-Ops directory already exists"
fi

cd /home/$USER/Meeting-Ops

# Start Docker services
print_info "Starting Docker services (PostgreSQL, Redis, Qdrant)..."
if [ -f "docker-compose.yml" ]; then
    docker compose up -d
else
    # Create docker-compose.yml if it doesn't exist
    cat > docker-compose.yml << 'EOF'
version: '3.8'

services:
  postgres:
    image: postgres:16-alpine
    container_name: meetingops-postgres
    environment:
      POSTGRES_USER: meetingops
      POSTGRES_PASSWORD: REMOVED
      POSTGRES_DB: meeting_sessions
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U meetingops"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    container_name: meetingops-redis
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  qdrant:
    image: qdrant/qdrant:latest
    container_name: meetingops-qdrant
    ports:
      - "6333:6333"
      - "6334:6334"
    volumes:
      - qdrant_data:/qdrant/storage

volumes:
  postgres_data:
  qdrant_data:
EOF
    docker compose up -d
fi

# Wait for services to be ready
print_info "Waiting for Docker services to be ready..."
sleep 10

# Setup Python backend
print_info "Setting up Python backend..."
cd backend

# Create virtual environment
python3.13 -m venv venv
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip setuptools wheel

# Install Python dependencies
print_info "Installing Python dependencies..."
cat > requirements-ubuntu2504.txt << 'EOF'
# Core dependencies
fastapi==0.110.0
uvicorn[standard]==0.29.0
python-multipart==0.0.9
websockets==12.0

# Database
sqlalchemy==2.0.28
psycopg2-binary==2.9.9
alembic==1.13.1

# Redis
redis==5.0.1

# Audio processing
sounddevice==0.4.6
numpy==1.26.4
scipy==1.12.0
librosa==0.10.1

# Authentication
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
bcrypt==4.1.2
email-validator==2.1.1

# Utilities
python-dotenv==1.0.1
pydantic==2.6.1
pydantic-settings==2.2.1
httpx==0.27.0
aiofiles==23.2.1

# Vector database
qdrant-client==1.8.0

# Optional: WhisperX dependencies (if available)
# torch==2.2.0
# torchaudio==2.2.0
# git+https://github.com/m-bain/whisperx.git

# Optional: Custom Gemma3n inference
# onnxruntime==1.17.1
EOF

# Install requirements
pip install -r requirements-ubuntu2504.txt || {
    print_warning "Some packages failed to install. Installing core packages..."
    pip install fastapi uvicorn python-multipart websockets
    pip install sqlalchemy psycopg2-binary
    pip install redis
    pip install python-jose passlib bcrypt email-validator
    pip install python-dotenv pydantic pydantic-settings
}

# Create .env file
print_info "Creating environment configuration..."
cat > .env << 'EOF'
# Database
DATABASE_URL=postgresql://meetingops:REMOVED@localhost:5432/meeting_sessions

# Redis
REDIS_URL=redis://localhost:6379

# Qdrant
QDRANT_URL=http://localhost:6333

# Security
SECRET_KEY=your-secret-key-change-this-in-production-$(openssl rand -hex 32)
ALGORITHM=HS256

# Audio
AUDIO_DEVICE=hw:0,0
AUDIO_SAMPLE_RATE=44100
AUDIO_CHANNELS=1

# NPU
USE_NPU=auto
NPU_DEVICE=/dev/accel/accel0

# Gemma3n Custom Inference (if available)
GEMMA_ENGINE_PATH=/home/$USER/gemma-engine/
GEMMA_MODEL_PATH=/home/$USER/gemma-engine/models/gemma3n.gguf
USE_CUSTOM_GEMMA=false

# Email (configure for production)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=person128@example.com
SMTP_PASSWORD=your-app-password
EOF

# Initialize database
print_info "Initializing database..."
cat > init_db.py << 'EOF'
import sys
sys.path.append('.')
from database import engine, Base
from models import *

print("Creating database tables...")
Base.metadata.create_all(bind=engine)
print("Database initialized successfully!")
EOF

python init_db.py

# Create admin user
print_info "Creating admin user..."
cat > create_admin.py << 'EOF'
import sys
sys.path.append('.')
from database import SessionLocal
from models import User
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

db = SessionLocal()
try:
    # Check if admin exists
    admin = db.query(User).filter(User.username == "admin").first()
    if not admin:
        admin = User(
            username="admin",
            email="admin@meeting-ops.local",
            full_name="System Administrator",
            hashed_password=pwd_context.hash("Changeme123!"),
            is_active=True,
            is_superuser=True,
            role="admin"
        )
        db.add(admin)
        db.commit()
        print("Admin user created successfully!")
        print("Username: admin")
        print("Password: Changeme123!")
        print("IMPORTANT: Change this password after first login!")
    else:
        print("Admin user already exists")
finally:
    db.close()
EOF

python create_admin.py

# Deactivate virtual environment
deactivate

# Setup frontend
print_info "Setting up frontend..."
cd ../frontend

# Install frontend dependencies
npm install

# Create frontend .env
cat > .env << 'EOF'
VITE_API_URL=http://localhost:9050
VITE_WS_URL=ws://localhost:9050
EOF

# Build frontend
print_info "Building frontend..."
npm run build

# Check for NPU
print_info "Checking for NPU device..."
if [ -e /dev/accel/accel0 ]; then
    print_success "NPU device found at /dev/accel/accel0"
    
    # Check permissions
    if [ -r /dev/accel/accel0 ] && [ -w /dev/accel/accel0 ]; then
        print_success "NPU device is accessible"
    else
        print_warning "NPU device found but not accessible. Setting permissions..."
        sudo chmod 666 /dev/accel/accel0
    fi
else
    print_warning "NPU device not found. Transcription will use CPU fallback."
fi

# Check for USB audio device
print_info "Checking for USB audio device..."
if arecord -l | grep -q "USB"; then
    print_success "USB audio device found"
    arecord -l | grep "USB"
else
    print_warning "No USB audio device found. Please connect a USB microphone."
fi

# Create systemd service files
print_info "Creating systemd service files..."
sudo tee /etc/systemd/system/meeting-ops-backend.service > /dev/null << EOF
[Unit]
Description=Meeting-Ops Backend Service
After=network.target docker.service
Requires=docker.service

[Service]
Type=simple
User=$USER
WorkingDirectory=/home/$USER/Meeting-Ops/backend
Environment="PATH=/home/$USER/Meeting-Ops/backend/venv/bin:/usr/local/bin:/usr/bin:/bin"
Environment="DATABASE_URL=postgresql://meetingops:REMOVED@localhost:5432/meeting_sessions"
Environment="REDIS_URL=redis://localhost:6379"
ExecStart=/home/$USER/Meeting-Ops/backend/venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 9050
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo tee /etc/systemd/system/meeting-ops-frontend.service > /dev/null << EOF
[Unit]
Description=Meeting-Ops Frontend Service
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=/home/$USER/Meeting-Ops/frontend
ExecStart=/usr/bin/npm run preview -- --host 0.0.0.0 --port 7777
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Create startup script
print_info "Creating startup script..."
cat > /home/$USER/Meeting-Ops/start-meeting-ops.sh << 'EOF'
#!/bin/bash
# Start Meeting-Ops services

echo "Starting Meeting-Ops services..."

# Start Docker services
cd /home/$USER/Meeting-Ops
docker compose up -d

# Wait for services
echo "Waiting for Docker services..."
sleep 10

# Start backend
cd backend
source venv/bin/activate
export DATABASE_URL="postgresql://meetingops:REMOVED@localhost:5432/meeting_sessions"
export REDIS_URL="redis://localhost:6379"
nohup python -m uvicorn main:app --host 0.0.0.0 --port 9050 > backend.log 2>&1 &
echo $! > backend.pid

# Start frontend
cd ../frontend
nohup npm run dev -- --host 0.0.0.0 > frontend.log 2>&1 &
echo $! > frontend.pid

echo "Meeting-Ops started!"
echo "Backend: http://$(hostname -I | awk '{print $1}'):9050"
echo "Frontend: http://$(hostname -I | awk '{print $1}'):7777"
echo "Logs: backend/backend.log and frontend/frontend.log"
EOF

chmod +x /home/$USER/Meeting-Ops/start-meeting-ops.sh

# Create stop script
cat > /home/$USER/Meeting-Ops/stop-meeting-ops.sh << 'EOF'
#!/bin/bash
# Stop Meeting-Ops services

echo "Stopping Meeting-Ops services..."

# Stop backend
if [ -f backend/backend.pid ]; then
    kill $(cat backend/backend.pid) 2>/dev/null
    rm backend/backend.pid
fi

# Stop frontend  
if [ -f frontend/frontend.pid ]; then
    kill $(cat frontend/frontend.pid) 2>/dev/null
    rm frontend/frontend.pid
fi

# Kill any remaining processes
pkill -f "uvicorn main:app"
pkill -f "npm run dev"
pkill -f arecord

echo "Meeting-Ops stopped!"
EOF

chmod +x /home/$USER/Meeting-Ops/stop-meeting-ops.sh

# Setup nginx (optional)
print_info "Setting up nginx configuration..."
sudo tee /etc/nginx/sites-available/meeting-ops > /dev/null << 'EOF'
server {
    listen 80;
    server_name _;

    # Frontend
    location / {
        proxy_pass http://127.0.0.1:7777;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Backend API
    location /api {
        proxy_pass http://127.0.0.1:9050;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # WebSocket endpoints
    location /ws {
        proxy_pass http://127.0.0.1:9050;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF

# Check if Gemma3n custom inference engine is available
if [ -d "/home/$USER/gemma-engine" ]; then
    print_success "Gemma3n custom inference engine detected"
    print_info "To enable, set USE_CUSTOM_GEMMA=true in backend/.env"
fi

# Final summary
echo
echo "=================================================="
print_success "Installation Complete!"
echo "=================================================="
echo
print_info "Next steps:"
echo "1. Log out and log back in (for group permissions)"
echo "2. Connect your USB microphone"
echo "3. Start services: ./start-meeting-ops.sh"
echo "4. Access the application:"
echo "   - Frontend: http://$(hostname -I | awk '{print $1}'):7777"
echo "   - Backend API: http://$(hostname -I | awk '{print $1}'):9050/docs"
echo "   - Default login: admin / Changeme123!"
echo
print_warning "IMPORTANT: Change the admin password after first login!"
echo
print_info "To enable systemd services (auto-start on boot):"
echo "   sudo systemctl daemon-reload"
echo "   sudo systemctl enable meeting-ops-backend"
echo "   sudo systemctl enable meeting-ops-frontend"
echo "   sudo systemctl start meeting-ops-backend"
echo "   sudo systemctl start meeting-ops-frontend"
echo
print_info "For Gemma3n custom inference (if available):"
echo "   1. Edit backend/.env"
echo "   2. Set USE_CUSTOM_GEMMA=true"
echo "   3. Set GEMMA_MODEL_PATH to your model file"
echo "   4. Restart backend service"
echo
print_info "Check installation log: /tmp/meeting-ops-install.log"