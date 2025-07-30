#!/bin/bash
#
# Meeting-Ops Automated Setup Script for Ubuntu Server
# Part of the Unicorn Commander Suite
#
# This script automates the installation of Meeting-Ops on a fresh Ubuntu system
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[✓]${NC} $1"
}

print_error() {
    echo -e "${RED}[✗]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

echo "=============================================="
echo "Meeting-Ops Automated Setup for Ubuntu"
echo "Part of Unicorn Commander Suite"
echo "=============================================="
echo

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    print_error "Please run as root (use sudo)"
    exit 1
fi

# Check Ubuntu version
if ! grep -q "Ubuntu" /etc/os-release; then
    print_error "This script is designed for Ubuntu systems"
    exit 1
fi

# Check for NPU device
if [ ! -e "/dev/accel/accel0" ]; then
    print_warning "NPU device not found at /dev/accel/accel0"
    print_warning "Meeting-Ops requires AMD NPU hardware for operation"
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
    NPU_AVAILABLE=false
else
    print_status "NPU device detected at /dev/accel/accel0"
    NPU_AVAILABLE=true
fi

# Update system
print_status "Updating system packages..."
apt update && apt upgrade -y

# Install Python 3.13
print_status "Installing Python 3.13..."
if ! command -v python3.13 &> /dev/null; then
    add-apt-repository ppa:deadsnakes/ppa -y
    apt update
    apt install python3.13 python3.13-venv python3.13-dev python3.13-distutils -y
else
    print_status "Python 3.13 already installed"
fi

# Install system dependencies
print_status "Installing system dependencies..."
apt install -y \
    build-essential \
    git \
    curl \
    wget \
    portaudio19-dev \
    libsndfile1 \
    ffmpeg \
    postgresql \
    postgresql-contrib \
    nginx \
    ufw \
    htop \
    ncdu \
    jq

# Install Docker
if ! command -v docker &> /dev/null; then
    print_status "Installing Docker..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sh get-docker.sh
    rm get-docker.sh
    
    # Install Docker Compose
    apt install docker-compose-plugin -y
else
    print_status "Docker already installed"
fi

# Install Node.js 18+
if ! command -v node &> /dev/null || [ $(node -v | cut -d'v' -f2 | cut -d'.' -f1) -lt 18 ]; then
    print_status "Installing Node.js 18..."
    curl -fsSL https://deb.nodesource.com/setup_18.x | bash -
    apt install nodejs -y
else
    print_status "Node.js 18+ already installed"
fi

# Create application user
print_status "Creating application user..."
if ! id "meeting-ops" &>/dev/null; then
    useradd --system --create-home --home-dir /opt/meeting-ops --shell /bin/bash meeting-ops
    usermod -aG docker,audio,video,render meeting-ops
else
    print_status "User meeting-ops already exists"
fi

# Configure NPU access
if [ "$NPU_AVAILABLE" = true ]; then
    print_status "Configuring NPU access..."
    cat > /etc/udev/rules.d/99-amd-npu.rules <<EOF
# Meeting-Ops NPU access
KERNEL=="accel*", SUBSYSTEM=="accel", MODE="0666", GROUP="render"
EOF
    udevadm control --reload-rules
    udevadm trigger
fi

# Clone repository if not already present
if [ ! -d "/opt/meeting-ops/Meeting-Ops" ]; then
    print_status "Cloning Meeting-Ops repository..."
    cd /opt/meeting-ops
    sudo -u meeting-ops git clone https://github.com/Unicorn-Commander/Meeting-Ops.git
    cd Meeting-Ops
else
    print_status "Repository already exists, pulling latest changes..."
    cd /opt/meeting-ops/Meeting-Ops
    sudo -u meeting-ops git pull
fi

# Set up PostgreSQL
print_status "Setting up PostgreSQL..."
sudo -u postgres psql <<EOF
CREATE DATABASE IF NOT EXISTS meeting_ops;
CREATE USER IF NOT EXISTS meeting_ops WITH PASSWORD 'meeting_ops_secure_password';
GRANT ALL PRIVILEGES ON DATABASE meeting_ops TO meeting_ops;
EOF

# Create directories
print_status "Creating application directories..."
mkdir -p /var/lib/meeting-ops/{recordings,exports,sessions,logs}
mkdir -p /var/log/meeting-ops
chown -R meeting-ops:meeting-ops /var/lib/meeting-ops
chown -R meeting-ops:meeting-ops /var/log/meeting-ops

# Set up backend
print_status "Setting up backend..."
cd /opt/meeting-ops/Meeting-Ops/backend
sudo -u meeting-ops python3.13 -m venv venv
sudo -u meeting-ops ./venv/bin/pip install --upgrade pip wheel setuptools

print_status "Installing Python dependencies..."
sudo -u meeting-ops ./venv/bin/pip install -r requirements.txt

# Download models
print_status "Downloading ONNX models..."
sudo -u meeting-ops ./venv/bin/python download_models.py || print_warning "Model download failed, will retry on first run"

# Check and download NPU binaries if missing
if [ ! -f "whisperx_npu.bin" ] || [ ! -f "models/whisper-base.npubin" ]; then
    print_status "Downloading NPU binaries from GitHub release..."
    LATEST_RELEASE=$(curl -s https://api.github.com/repos/Unicorn-Commander/Meeting-Ops/releases/latest | jq -r .tag_name)
    if [ "$LATEST_RELEASE" != "null" ]; then
        wget -q -O /tmp/npu-binaries.tar.gz \
            "https://github.com/Unicorn-Commander/Meeting-Ops/releases/download/$LATEST_RELEASE/npu-binaries.tar.gz"
        tar -xzf /tmp/npu-binaries.tar.gz -C .
        rm /tmp/npu-binaries.tar.gz
        chown -R meeting-ops:meeting-ops whisperx_npu.bin models/
        print_status "NPU binaries downloaded successfully"
    else
        print_warning "Could not download NPU binaries - using CPU fallback"
    fi
fi

# Create environment file
print_status "Creating environment configuration..."
if [ ! -f .env ]; then
    cat > .env <<EOF
DATABASE_URL=postgresql://meeting_ops:REMOVED@localhost/meeting_ops
SECRET_KEY=$(openssl rand -hex 32)
OLLAMA_BASE_URL=http://localhost:11434
NPU_ENABLED=$NPU_AVAILABLE
EOF
    chown meeting-ops:meeting-ops .env
    chmod 600 .env
fi

# Initialize database
print_status "Initializing database..."
sudo -u meeting-ops ./venv/bin/python init_db.py

# Set up frontend
print_status "Setting up frontend..."
cd /opt/meeting-ops/Meeting-Ops/frontend
sudo -u meeting-ops npm install

print_status "Building frontend..."
sudo -u meeting-ops npm run build

# Install systemd service
print_status "Installing systemd service..."
cat > /etc/systemd/system/meeting-ops.service <<EOF
[Unit]
Description=Meeting-Ops Recording Appliance
After=network.target postgresql.service

[Service]
Type=simple
User=meeting-ops
Group=meeting-ops
WorkingDirectory=/opt/meeting-ops/Meeting-Ops/backend
Environment="PATH=/opt/meeting-ops/Meeting-Ops/backend/venv/bin"
Environment="PYTHONPATH=/opt/meeting-ops/Meeting-Ops/backend"
ExecStart=/opt/meeting-ops/Meeting-Ops/backend/venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 9050
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload

# Configure nginx
print_status "Configuring nginx..."
cat > /etc/nginx/sites-available/meeting-ops <<EOF
server {
    listen 80;
    server_name _;
    
    # Frontend
    location / {
        root /opt/meeting-ops/Meeting-Ops/frontend/dist;
        try_files \$uri \$uri/ /index.html;
    }
    
    # Backend API
    location /api/ {
        proxy_pass http://localhost:9050/api/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
    
    # WebSocket endpoints
    location /ws/ {
        proxy_pass http://localhost:9050/ws/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

ln -sf /etc/nginx/sites-available/meeting-ops /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl restart nginx

# Configure firewall
print_status "Configuring firewall..."
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

# Install Ollama (optional)
if ! command -v ollama &> /dev/null; then
    print_status "Installing Ollama for LLM summarization..."
    curl -fsSL https://ollama.ai/install.sh | sh
    
    # Pull default model
    sudo -u meeting-ops ollama pull gemma:2b
fi

# Start services
print_status "Starting services..."
systemctl enable meeting-ops
systemctl start meeting-ops
systemctl enable nginx
systemctl restart nginx

# Create quick start script
print_status "Creating quick start script..."
cat > /usr/local/bin/meeting-ops <<EOF
#!/bin/bash
case "\$1" in
    status)
        systemctl status meeting-ops
        ;;
    logs)
        journalctl -u meeting-ops -f
        ;;
    restart)
        systemctl restart meeting-ops
        ;;
    stop)
        systemctl stop meeting-ops
        ;;
    start)
        systemctl start meeting-ops
        ;;
    *)
        echo "Usage: meeting-ops {status|logs|restart|stop|start}"
        exit 1
        ;;
esac
EOF
chmod +x /usr/local/bin/meeting-ops

# Final checks
print_status "Running final checks..."

# Check services
if systemctl is-active --quiet meeting-ops; then
    print_status "Meeting-Ops service is running"
else
    print_error "Meeting-Ops service failed to start"
fi

if systemctl is-active --quiet nginx; then
    print_status "Nginx is running"
else
    print_error "Nginx failed to start"
fi

# Get IP addresses
IP_ADDR=$(ip -4 addr show | grep -oP '(?<=inet\s)\d+(\.\d+){3}' | grep -v 127.0.0.1 | head -n1)

echo
echo "=============================================="
echo -e "${GREEN}Installation Complete!${NC}"
echo "=============================================="
echo
echo "Meeting-Ops is now installed and running!"
echo
echo "Access the application at:"
echo "  Local: http://localhost"
echo "  Network: http://$IP_ADDR"
echo
echo "Default credentials:"
echo "  Username: admin"
echo "  Password: admin123"
echo
echo "Useful commands:"
echo "  meeting-ops status  - Check service status"
echo "  meeting-ops logs    - View logs"
echo "  meeting-ops restart - Restart service"
echo
if [ "$NPU_AVAILABLE" = false ]; then
    print_warning "NPU hardware not detected - running in CPU mode"
    print_warning "Performance will be significantly reduced"
fi
echo
echo "Part of the Unicorn Commander Suite"
echo "By Magic Unicorn Unconventional Technology & Stuff Inc."
echo "=============================================="