#!/bin/bash

# Install script for Meeting-Ops backend dependencies
# Handles Python 3.13 compatibility issues

echo "🦄 Meeting-Ops Backend Dependency Installer"
echo "==========================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if we're in the backend directory
if [ ! -f "main.py" ]; then
    echo -e "${RED}Error: Not in backend directory. Please run from Meeting-Ops/backend${NC}"
    exit 1
fi

# Check Python version
echo "Checking Python version..."
PYTHON_VERSION=$(python3 --version 2>&1 | grep -Po '(?<=Python )\d+\.\d+')
echo "Found Python $PYTHON_VERSION"

# Create venv if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate venv
source venv/bin/activate

# Upgrade pip
echo -e "${YELLOW}Upgrading pip...${NC}"
pip install --upgrade pip

# Install core requirements
echo -e "${YELLOW}Installing core requirements...${NC}"
pip install fastapi uvicorn python-multipart

# Install database
echo -e "${YELLOW}Installing database packages...${NC}"
pip install sqlalchemy psycopg2-binary alembic

# Install auth
echo -e "${YELLOW}Installing authentication packages...${NC}"
pip install python-jose[cryptography] passlib[bcrypt] email-validator

# Install Redis
echo -e "${YELLOW}Installing Redis...${NC}"
pip install redis

# Install utilities
echo -e "${YELLOW}Installing utilities...${NC}"
pip install python-dotenv pydantic pydantic-settings aiofiles

# Try to install audio packages (may fail on some systems)
echo -e "${YELLOW}Attempting audio packages installation...${NC}"
pip install sounddevice numpy || echo -e "${YELLOW}Warning: Audio packages failed, continuing...${NC}"

# Optional AI packages (don't fail if they don't install)
echo -e "${YELLOW}Attempting AI packages (optional)...${NC}"
pip install openai 2>/dev/null || echo "OpenAI not installed (optional)"
pip install anthropic 2>/dev/null || echo "Anthropic not installed (optional)"

# Create settings directory
mkdir -p ~/.meeting-ops

# Create default AI settings
cat > ~/.meeting-ops/ai_settings.json << EOF
{
  "ollama": {
    "provider": "ollama",
    "url": "http://localhost:11434",
    "model": "gemma3n:latest",
    "enabled": true
  },
  "transcription": {
    "provider": "whisper",
    "model": "base",
    "useNPU": true,
    "device": "/dev/accel/accel0"
  }
}
EOF

echo -e "${GREEN}✅ Installation complete!${NC}"
echo ""
echo "To start the backend:"
echo "  source venv/bin/activate"
echo "  python -m uvicorn main:app --host 0.0.0.0 --port 9050"
echo ""
echo "Note: Some optional packages may not have installed."
echo "The core functionality will still work."