#!/bin/bash
# Meeting-Ops Complete Installation Script
# Installs all components including Docker services, AI models, and dependencies
# Version: 2.0.0

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
APP_NAME="Meeting-Ops Recording Appliance"
SERVICE_NAME="meeting-ops"
BACKEND_PORT=9050
FRONTEND_PORT=7777
USER="ucadmin"

# Current directory
CURRENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$CURRENT_DIR/backend"
FRONTEND_DIR="$CURRENT_DIR/frontend"

echo -e "${BLUE}🎯 ${APP_NAME} Installation Script${NC}"
echo -e "${BLUE}=================================${NC}"
echo ""

# Function to print status messages
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as root
if [ "$EUID" -eq 0 ]; then
    print_error "Please don't run this script as root. It will ask for sudo when needed."
    exit 1
fi

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to get Linux distribution
get_distro() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        echo $ID
    else
        echo "unknown"
    fi
}

# System requirements check
print_status "Checking system requirements..."

# Check Python version
if command_exists python3.13; then
    PYTHON_CMD="python3.13"
    print_success "Found Python 3.13"
elif command_exists python3.12; then
    PYTHON_CMD="python3.12"
    print_success "Found Python 3.12"
elif command_exists python3.11; then
    PYTHON_CMD="python3.11"
    print_success "Found Python 3.11"
else
    print_error "Python 3.11+ is required. Please install Python 3.11 or newer."
    exit 1
fi

# Check Node.js
if ! command_exists node; then
    print_error "Node.js is required for frontend. Please install Node.js 18+ first."
    print_status "To install Node.js:"
    print_status "  curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -"
    print_status "  sudo apt-get install -y nodejs"
    exit 1
fi

NODE_VERSION=$(node --version | sed 's/v//')
NODE_MAJOR=$(echo $NODE_VERSION | cut -d. -f1)
if [ "$NODE_MAJOR" -lt 18 ]; then
    print_error "Node.js 18+ is required. Found version $NODE_VERSION"
    exit 1
fi
print_success "Found Node.js $NODE_VERSION"

# Check Docker
if ! command_exists docker; then
    print_warning "Docker is not installed. Installing Docker..."
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker $USER
    print_success "Docker installed. You may need to log out and back in for group changes to take effect."
else
    print_success "Docker is already installed"
fi

# Check Docker Compose
if ! command_exists docker-compose && ! docker compose version >/dev/null 2>&1; then
    print_warning "Docker Compose is not installed. Installing Docker Compose..."
    sudo apt-get update
    sudo apt-get install -y docker-compose-plugin
    print_success "Docker Compose installed"
else
    print_success "Docker Compose is already installed"
fi

# Install system dependencies
print_status "Installing system dependencies..."

DISTRO=$(get_distro)
case $DISTRO in
    ubuntu|debian)
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
        ;;
    fedora|centos|rhel)
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
        ;;
    *)
        print_warning "Unknown distribution. Please install dependencies manually."
        ;;
esac

print_success "System dependencies installed"

# Setup backend
print_status "Setting up backend..."

cd "$BACKEND_DIR"

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    print_status "Creating Python virtual environment..."
    $PYTHON_CMD -m venv venv
fi

source venv/bin/activate

# Upgrade pip
pip install --upgrade pip setuptools wheel

# Install backend dependencies
print_status "Installing Python dependencies..."
if [ -f "requirements.txt" ]; then
    # Install in order to handle dependencies properly
    pip install psycopg2-binary  # Install PostgreSQL adapter first
    pip install redis  # Install Redis client
    pip install requests  # Install requests for API calls
    pip install ollama  # Install Ollama client
    
    # Handle PyTorch installation separately for version compatibility
    print_status "Installing PyTorch packages..."
    pip install torch torchaudio torchvision --index-url https://download.pytorch.org/whl/cpu
    
    # Install remaining requirements, ignoring PyTorch packages already installed
    pip install -r requirements.txt || {
        print_warning "Some packages may have failed. Attempting to install core packages..."
        # Install core packages that we know work
        pip install fastapi uvicorn sqlalchemy alembic
        pip install openai anthropic ollama
        pip install numpy librosa soundfile pyaudio
    }
else
    print_error "No requirements.txt found"
    exit 1
fi

print_success "Backend dependencies installed"

# Setup frontend
print_status "Setting up frontend..."

cd "$FRONTEND_DIR"

# Install frontend dependencies
print_status "Installing Node.js dependencies..."
if [ ! -d "node_modules" ]; then
    npm install
else
    print_status "Node modules already installed. Run 'npm update' to update."
fi

print_success "Frontend dependencies installed"

# Setup Docker services
print_status "Setting up Docker services..."

cd "$CURRENT_DIR"

# Start Docker services
print_status "Starting PostgreSQL, Redis, and Qdrant..."
docker compose -f docker-compose-full-stack.yml up -d postgres redis qdrant

# Wait for services to be ready
print_status "Waiting for services to start..."
sleep 10

# Check if services are running
if docker ps | grep -q postgres; then
    print_success "PostgreSQL is running"
else
    print_error "PostgreSQL failed to start"
fi

if docker ps | grep -q redis; then
    print_success "Redis is running"
else
    print_error "Redis failed to start"
fi

if docker ps | grep -q qdrant; then
    print_success "Qdrant is running"
else
    print_error "Qdrant failed to start"
fi

# Setup Ollama for LLM support
print_status "Setting up Ollama for AI models..."

if ! command_exists ollama; then
    print_warning "Ollama not installed. Installing Ollama..."
    curl -fsSL https://ollama.ai/install.sh | sh
    print_success "Ollama installed"
else
    print_success "Ollama is already installed"
fi

# Start Ollama service
if ! pgrep -x "ollama" > /dev/null; then
    print_status "Starting Ollama service..."
    ollama serve > /dev/null 2>&1 &
    sleep 5
fi

# Pull required models
print_status "Pulling AI models (this may take a while)..."
ollama pull granite3.3:8b || print_warning "Failed to pull Granite model"
ollama pull phi4-mini:3.8b || print_warning "Failed to pull Phi4 model"
ollama pull gemma3n:e4b || print_warning "Failed to pull Gemma model"

print_success "AI models setup complete"

# Initialize database
print_status "Initializing database..."
cd "$BACKEND_DIR"
source venv/bin/activate

# Create database tables
python -c "
from database.database import init_database
init_database()
print('Database initialized successfully')
" || print_warning "Database initialization failed - may already exist"

# Create startup script
print_status "Creating startup script..."

cat > "$CURRENT_DIR/start-meeting-ops.sh" << 'EOF'
#!/bin/bash
# Meeting-Ops Startup Script

echo "Starting Meeting-Ops services..."

# Start Docker services
docker compose -f docker-compose-full-stack.yml up -d

# Wait for services
sleep 5

# Start Ollama if not running
if ! pgrep -x "ollama" > /dev/null; then
    ollama serve > /dev/null 2>&1 &
fi

# Start backend
cd backend
source venv/bin/activate
./start-backend.sh &

# Start frontend
cd ../frontend
npm run dev &

echo "Meeting-Ops is starting..."
echo "Backend: http://localhost:9050"
echo "Frontend: http://localhost:7777"
echo "API Docs: http://localhost:9050/docs"
EOF

chmod +x "$CURRENT_DIR/start-meeting-ops.sh"

# Create systemd service (optional)
print_status "Creating systemd service (optional)..."

cat > /tmp/meeting-ops.service << EOF
[Unit]
Description=Meeting-Ops Recording Appliance
After=network.target docker.service

[Service]
Type=forking
User=$USER
WorkingDirectory=$CURRENT_DIR
ExecStart=$CURRENT_DIR/start-meeting-ops.sh
ExecStop=/usr/bin/pkill -f "meeting-ops"
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

print_status "To install as a system service, run:"
print_status "  sudo cp /tmp/meeting-ops.service /etc/systemd/system/"
print_status "  sudo systemctl daemon-reload"
print_status "  sudo systemctl enable meeting-ops"
print_status "  sudo systemctl start meeting-ops"

# Final instructions
echo ""
print_success "🎉 Installation complete!"
echo ""
echo -e "${GREEN}To start Meeting-Ops:${NC}"
echo "  ./start-meeting-ops.sh"
echo ""
echo -e "${GREEN}Access points:${NC}"
echo "  Frontend: http://localhost:$FRONTEND_PORT"
echo "  Backend API: http://localhost:$BACKEND_PORT"
echo "  API Documentation: http://localhost:$BACKEND_PORT/docs"
echo ""
echo -e "${GREEN}Default credentials:${NC}"
echo "  Username: admin"
echo "  Password: admin123"
echo ""
echo -e "${YELLOW}Important notes:${NC}"
echo "  - Make sure your USB microphone is connected"
echo "  - Grant browser permissions for microphone access"
echo "  - For network access, update frontend/.env with your server IP"
echo ""
print_success "Happy recording! 🎙️"