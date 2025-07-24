#!/bin/bash
# Unicorn Commander - Complete Installation Script
# Installs the latest version with port 7777 configuration
# Includes cleanup of previous versions

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
APP_NAME="Unicorn Commander"
SERVICE_NAME="unicorn-commander"
BACKEND_PORT=9050
FRONTEND_PORT=7777
USER="unicorn"

# Current directory (development mode)
CURRENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$CURRENT_DIR/backend"
FRONTEND_DIR="$CURRENT_DIR/frontend"

echo -e "${BLUE}🦄 ${APP_NAME} Installation Script${NC}"
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

# Check Python 3.13
if ! command_exists python3.13; then
    print_warning "Python 3.13 not found. Checking for Python 3.12..."
    if ! command_exists python3.12; then
        print_error "Python 3.12+ is required. Please install Python 3.12 or newer."
        exit 1
    else
        PYTHON_CMD="python3.12"
        print_success "Found Python 3.12"
    fi
else
    PYTHON_CMD="python3.13"
    print_success "Found Python 3.13"
fi

# Check Node.js
if ! command_exists node; then
    print_error "Node.js is required for frontend. Please install Node.js 18+ first."
    exit 1
fi

NODE_VERSION=$(node --version | sed 's/v//')
NODE_MAJOR=$(echo $NODE_VERSION | cut -d. -f1)
if [ "$NODE_MAJOR" -lt 18 ]; then
    print_error "Node.js 18+ is required. Found version $NODE_VERSION"
    exit 1
fi
print_success "Found Node.js $NODE_VERSION"

# Check npm
if ! command_exists npm; then
    print_error "npm is required. Please install npm."
    exit 1
fi
print_success "Found npm"

# Cleanup previous installations
print_status "Cleaning up previous installations..."

# Stop existing services
if systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
    print_status "Stopping existing $SERVICE_NAME service..."
    sudo systemctl stop "$SERVICE_NAME"
fi

# Also check for variations
for service_variant in "unicorn-commander-backend" "unicorn-commander.target"; do
    if systemctl is-active --quiet "$service_variant" 2>/dev/null; then
        print_status "Stopping existing $service_variant service..."
        sudo systemctl stop "$service_variant"
    fi
done

# Remove old systemd services
for service_file in "/etc/systemd/system/$SERVICE_NAME.service" "/etc/systemd/system/unicorn-commander-backend.service" "/etc/systemd/system/unicorn-commander.target"; do
    if [ -f "$service_file" ]; then
        print_status "Removing old systemd service: $(basename $service_file)..."
        sudo systemctl disable "$(basename $service_file)" 2>/dev/null || true
        sudo rm -f "$service_file"
    fi
done

sudo systemctl daemon-reload

# Kill any running processes on our ports
print_status "Checking for processes using ports $BACKEND_PORT and $FRONTEND_PORT..."
for port in $BACKEND_PORT $FRONTEND_PORT 80 8080; do
    if ss -tlnp | grep -q ":$port "; then
        print_warning "Port $port is in use. Attempting to free it..."
        sudo fuser -k $port/tcp 2>/dev/null || true
        sleep 2
    fi
done

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
            libffi-dev
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
            libffi-devel
        ;;
    *)
        print_warning "Unknown distribution. Please install dependencies manually."
        ;;
esac

print_success "System dependencies installed"

# Create user if doesn't exist
if ! id "$USER" &>/dev/null; then
    print_status "Creating user '$USER'..."
    sudo useradd --system --shell /bin/bash --home-dir /home/$USER --create-home $USER
    sudo usermod -a -G audio $USER
    print_success "User '$USER' created"
else
    print_success "User '$USER' already exists"
    sudo usermod -a -G audio $USER
fi

# Setup backend
print_status "Setting up backend..."

cd "$BACKEND_DIR"

# Remove old virtual environments
rm -rf venv venv-py313 venv313

# Create new virtual environment
print_status "Creating Python virtual environment..."
$PYTHON_CMD -m venv venv
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip setuptools wheel

# Install backend dependencies
print_status "Installing Python dependencies..."
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
elif [ -f "pyproject.toml" ]; then
    pip install .
else
    print_error "No requirements.txt or pyproject.toml found"
    exit 1
fi

print_success "Backend dependencies installed"

# Initialize database
print_status "Initializing database..."
python init_db.py 2>/dev/null || true
print_success "Database initialized"

# Setup frontend
print_status "Setting up frontend..."

cd "$FRONTEND_DIR"

# Clean old node modules
rm -rf node_modules package-lock.json

# Install frontend dependencies
print_status "Installing Node.js dependencies..."
npm install

# Build frontend
print_status "Building frontend..."
npm run build

print_success "Frontend built successfully"

# Configure nginx
print_status "Configuring nginx..."

# Backup existing nginx config if it exists
if [ -f "/etc/nginx/sites-available/default" ]; then
    sudo cp /etc/nginx/sites-available/default /etc/nginx/sites-available/default.backup.$(date +%Y%m%d_%H%M%S)
fi

# Create nginx configuration
sudo tee /etc/nginx/sites-available/unicorn-commander > /dev/null << EOF
server {
    listen $FRONTEND_PORT;
    server_name localhost _;
    root $FRONTEND_DIR/dist;
    index index.html;

    # Enable gzip compression
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_types text/plain text/css text/xml text/javascript application/json application/javascript application/xml+rss;

    # Frontend routes
    location / {
        try_files \$uri \$uri/ /index.html;
    }

    # API proxy to backend on port 7777
    location /api {
        proxy_pass http://127.0.0.1:$BACKEND_PORT;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host \$host;
        proxy_cache_bypass \$http_upgrade;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 300s;
        proxy_connect_timeout 10s;
    }

    # WebSocket proxy on port 7777
    location /ws {
        proxy_pass http://127.0.0.1:$BACKEND_PORT;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 86400;
    }

    # Cache static assets
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "no-referrer-when-downgrade" always;

    # Max upload size
    client_max_body_size 100M;
}
EOF

# Enable the site
sudo rm -f /etc/nginx/sites-enabled/default
sudo rm -f /etc/nginx/sites-enabled/unicorn-commander
sudo ln -sf /etc/nginx/sites-available/unicorn-commander /etc/nginx/sites-enabled/

# Test nginx configuration
if sudo nginx -t; then
    print_success "Nginx configuration is valid"
else
    print_error "Nginx configuration is invalid"
    exit 1
fi

# Create systemd service
print_status "Creating systemd service..."

sudo tee /etc/systemd/system/$SERVICE_NAME.service > /dev/null << EOF
[Unit]
Description=Unicorn Commander Meeting Recording Backend
After=network.target

[Service]
Type=simple
User=$USER
Group=$USER
WorkingDirectory=$BACKEND_DIR
Environment="PATH=$BACKEND_DIR/venv/bin"
Environment="PYTHONPATH=$BACKEND_DIR"
Environment="DATABASE_URL=sqlite:///$BACKEND_DIR/meeting_sessions.db"
ExecStart=$BACKEND_DIR/venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port $BACKEND_PORT
Restart=always
RestartSec=10

# Security settings
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$BACKEND_DIR
ReadWritePaths=/tmp

[Install]
WantedBy=multi-user.target
EOF

# Set permissions
print_status "Setting permissions..."
sudo chown -R $USER:$USER "$BACKEND_DIR"
sudo chmod +x "$BACKEND_DIR/run-port7777.sh"

# Create data directories
sudo mkdir -p "$BACKEND_DIR/storage/audio_files/recordings"
sudo mkdir -p "$BACKEND_DIR/storage/audio_files/exports"
sudo mkdir -p "$BACKEND_DIR/storage/audio_files/temp"
sudo chown -R $USER:$USER "$BACKEND_DIR/storage"

# Reload systemd and enable services
sudo systemctl daemon-reload
sudo systemctl enable $SERVICE_NAME
sudo systemctl enable nginx

# Start services
print_status "Starting services..."

# Start backend
sudo systemctl start $SERVICE_NAME

# Wait a moment for backend to start
sleep 5

# Check if backend is running
if systemctl is-active --quiet $SERVICE_NAME; then
    print_success "Backend service started successfully"
else
    print_error "Backend service failed to start"
    print_status "Checking logs..."
    sudo journalctl -u $SERVICE_NAME --no-pager --lines=20
    exit 1
fi

# Start nginx
sudo systemctl restart nginx

if systemctl is-active --quiet nginx; then
    print_success "Nginx started successfully"
else
    print_error "Nginx failed to start"
    sudo journalctl -u nginx --no-pager --lines=10
    exit 1
fi

# Create admin user
print_status "Setting up admin user..."
cd "$BACKEND_DIR"
source venv/bin/activate

# Run admin creation script
python -c "
import sys
sys.path.append('.')

try:
    from auth.service import AuthService
    from database.database import get_db

    auth_service = AuthService()
    db = next(get_db())

    try:
        user = auth_service.create_user(
            db,
            username='admin',
            email='admin@localhost',
            password='changeme123!',
            role='superuser',
            is_active=True
        )
        print('✅ Admin user created successfully')
    except Exception as e:
        if 'already exists' in str(e).lower():
            print('✅ Admin user already exists')
        else:
            print(f'❌ Error creating admin user: {e}')
    finally:
        db.close()
except ImportError as e:
    print(f'⚠️  Could not set up admin user automatically: {e}')
    print('   You can create one manually after first startup')
" 2>/dev/null || print_warning "Admin user setup will be handled on first startup"

# Final status check
print_status "Performing final status check..."

# Wait a bit more for services to fully start
sleep 3

# Check backend health
if curl -s http://localhost:$BACKEND_PORT/api/status >/dev/null 2>&1; then
    print_success "Backend API is responding on port $BACKEND_PORT"
else
    print_warning "Backend API not responding yet (may need a moment to start)"
fi

# Check frontend
if curl -s http://localhost/ >/dev/null 2>&1; then
    print_success "Frontend is accessible on port 80"
else
    print_warning "Frontend not accessible yet"
fi

# Create uninstall script
print_status "Creating uninstall script..."
cat > "$CURRENT_DIR/uninstall.sh" << 'EOF'
#!/bin/bash
# Unicorn Commander Uninstall Script

echo "🗑️  Uninstalling Unicorn Commander..."

# Stop services
sudo systemctl stop unicorn-commander 2>/dev/null || true
sudo systemctl stop unicorn-commander-backend 2>/dev/null || true

# Disable services
sudo systemctl disable unicorn-commander 2>/dev/null || true
sudo systemctl disable unicorn-commander-backend 2>/dev/null || true

# Remove systemd files
sudo rm -f /etc/systemd/system/unicorn-commander*.service
sudo rm -f /etc/systemd/system/unicorn-commander*.target
sudo systemctl daemon-reload

# Remove nginx config
sudo rm -f /etc/nginx/sites-enabled/unicorn-commander
sudo rm -f /etc/nginx/sites-available/unicorn-commander
sudo systemctl restart nginx

# Remove user (optional - commented out for safety)
# sudo userdel unicorn 2>/dev/null || true

echo "✅ Unicorn Commander uninstalled"
echo "Note: Data files and user account preserved for safety"
EOF

chmod +x "$CURRENT_DIR/uninstall.sh"

# Installation complete
echo ""
echo -e "${GREEN}🎉 Installation Complete! 🎉${NC}"
echo -e "${GREEN}=========================${NC}"
echo ""
echo -e "${BLUE}Access your application:${NC}"
echo -e "  🌐 Web Interface: ${GREEN}http://localhost:$FRONTEND_PORT/${NC} ${YELLOW}← The magical port!${NC}"
echo -e "  🔧 Admin Panel:   ${GREEN}http://localhost:$FRONTEND_PORT/admin${NC}"
echo -e "  📚 API Docs:      ${GREEN}http://localhost:$BACKEND_PORT/docs${NC}"
echo ""
echo -e "${BLUE}Default Admin Credentials:${NC}"
echo -e "  👤 Username: ${YELLOW}admin${NC}"
echo -e "  🔑 Password: ${YELLOW}changeme123!${NC}"
echo -e "  ${RED}⚠️  IMPORTANT: Change password after first login!${NC}"
echo ""
echo -e "${BLUE}Service Management:${NC}"
echo -e "  ▶️  Start:   ${GREEN}sudo systemctl start $SERVICE_NAME${NC}"
echo -e "  ⏹️  Stop:    ${GREEN}sudo systemctl stop $SERVICE_NAME${NC}"
echo -e "  🔄 Restart: ${GREEN}sudo systemctl restart $SERVICE_NAME${NC}"
echo -e "  📊 Status:  ${GREEN}sudo systemctl status $SERVICE_NAME${NC}"
echo -e "  📋 Logs:    ${GREEN}sudo journalctl -u $SERVICE_NAME -f${NC}"
echo ""
echo -e "${BLUE}For development:${NC}"
echo -e "  🛠️  Quick Start: ${GREEN}./start-unicorn.sh${NC}"
echo -e "  🔧 Backend Only: ${GREEN}cd $BACKEND_DIR && ./run-backend.sh${NC}"
echo ""
echo -e "${BLUE}Port Configuration:${NC}"
echo -e "  🔧 Backend API: ${GREEN}Port $BACKEND_PORT${NC}"
echo -e "  🌐 Frontend:    ${GREEN}Port $FRONTEND_PORT${NC} (the magical port!)"
echo ""
echo -e "${BLUE}To uninstall:${NC}"
echo -e "  🗑️  Run: ${GREEN}./uninstall.sh${NC}"
echo ""
echo -e "${GREEN}Happy meeting recording! 🦄✨${NC}"