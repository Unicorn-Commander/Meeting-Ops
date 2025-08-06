#!/bin/bash
# Meeting-Ops Installation Verification Script

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "=================================================="
echo "Meeting-Ops Installation Verification"
echo "=================================================="
echo

# Check system
echo "System Information:"
echo -e "OS: $(lsb_release -ds)"
echo -e "Kernel: $(uname -r)"
echo -e "Architecture: $(uname -m)"
echo

# Check Docker
echo "Docker Status:"
if command -v docker &> /dev/null; then
    echo -e "${GREEN}✓${NC} Docker installed: $(docker --version)"
    
    # Check Docker services
    if docker ps | grep -q postgres; then
        echo -e "${GREEN}✓${NC} PostgreSQL running"
    else
        echo -e "${RED}✗${NC} PostgreSQL not running"
    fi
    
    if docker ps | grep -q redis; then
        echo -e "${GREEN}✓${NC} Redis running"
    else
        echo -e "${RED}✗${NC} Redis not running"
    fi
    
    if docker ps | grep -q qdrant; then
        echo -e "${GREEN}✓${NC} Qdrant running"
    else
        echo -e "${RED}✗${NC} Qdrant not running"
    fi
else
    echo -e "${RED}✗${NC} Docker not installed"
fi
echo

# Check Python
echo "Python Environment:"
if command -v python3.13 &> /dev/null; then
    echo -e "${GREEN}✓${NC} Python 3.13 installed"
else
    echo -e "${YELLOW}⚠${NC} Python 3.13 not found, using: $(python3 --version)"
fi

if [ -d "/home/$USER/Meeting-Ops/backend/venv" ]; then
    echo -e "${GREEN}✓${NC} Python virtual environment exists"
else
    echo -e "${RED}✗${NC} Python virtual environment not found"
fi
echo

# Check Node.js
echo "Node.js Environment:"
if command -v node &> /dev/null; then
    echo -e "${GREEN}✓${NC} Node.js installed: $(node --version)"
else
    echo -e "${RED}✗${NC} Node.js not installed"
fi

if [ -d "/home/$USER/Meeting-Ops/frontend/node_modules" ]; then
    echo -e "${GREEN}✓${NC} Frontend dependencies installed"
else
    echo -e "${RED}✗${NC} Frontend dependencies not installed"
fi
echo

# Check Audio
echo "Audio Configuration:"
if arecord -l 2>/dev/null | grep -q "USB"; then
    echo -e "${GREEN}✓${NC} USB audio device found:"
    arecord -l | grep "USB" | head -1
else
    echo -e "${YELLOW}⚠${NC} No USB audio device found"
fi

if groups | grep -q audio; then
    echo -e "${GREEN}✓${NC} User in audio group"
else
    echo -e "${YELLOW}⚠${NC} User not in audio group"
fi
echo

# Check NPU
echo "NPU Status:"
if [ -e /dev/accel/accel0 ]; then
    echo -e "${GREEN}✓${NC} NPU device found at /dev/accel/accel0"
    if [ -r /dev/accel/accel0 ] && [ -w /dev/accel/accel0 ]; then
        echo -e "${GREEN}✓${NC} NPU device accessible"
    else
        echo -e "${YELLOW}⚠${NC} NPU device not accessible (check permissions)"
    fi
else
    echo -e "${YELLOW}⚠${NC} NPU device not found"
fi

if groups | grep -q render; then
    echo -e "${GREEN}✓${NC} User in render group"
else
    echo -e "${YELLOW}⚠${NC} User not in render group"
fi
echo

# Check Custom Gemma
echo "Gemma3n Custom Engine:"
if [ -d "/home/$USER/gemma-engine" ]; then
    echo -e "${GREEN}✓${NC} Gemma engine directory found"
    if [ -f "/home/$USER/gemma-engine/gemma-cli" ]; then
        echo -e "${GREEN}✓${NC} Gemma CLI binary found"
    else
        echo -e "${YELLOW}⚠${NC} Gemma CLI binary not found"
    fi
else
    echo -e "${YELLOW}⚠${NC} Gemma engine not installed"
fi
echo

# Check Services
echo "Service Accessibility:"

# Backend
if curl -s http://localhost:9050/api/status &>/dev/null; then
    echo -e "${GREEN}✓${NC} Backend API responding"
else
    echo -e "${RED}✗${NC} Backend API not responding"
fi

# Frontend
if curl -s http://localhost:7777 &>/dev/null || curl -s http://localhost:7778 &>/dev/null; then
    echo -e "${GREEN}✓${NC} Frontend responding"
else
    echo -e "${RED}✗${NC} Frontend not responding"
fi
echo

# Check Files
echo "Configuration Files:"
if [ -f "/home/$USER/Meeting-Ops/backend/.env" ]; then
    echo -e "${GREEN}✓${NC} Backend .env exists"
else
    echo -e "${RED}✗${NC} Backend .env missing"
fi

if [ -f "/home/$USER/Meeting-Ops/frontend/.env" ]; then
    echo -e "${GREEN}✓${NC} Frontend .env exists"
else
    echo -e "${RED}✗${NC} Frontend .env missing"
fi
echo

# Network info
echo "Network Information:"
echo "Server IP: $(hostname -I | awk '{print $1}')"
echo "Frontend URL: http://$(hostname -I | awk '{print $1}'):7777"
echo "Backend API: http://$(hostname -I | awk '{print $1}'):9050/docs"
echo

# Summary
echo "=================================================="
echo "Summary:"
if [ -e /dev/accel/accel0 ] && [ -r /dev/accel/accel0 ]; then
    echo -e "${GREEN}NPU hardware is available and accessible${NC}"
else
    echo -e "${YELLOW}NPU hardware not available - will use CPU fallback${NC}"
fi

if arecord -l 2>/dev/null | grep -q "USB"; then
    echo -e "${GREEN}USB microphone is connected and ready${NC}"
else
    echo -e "${YELLOW}Please connect a USB microphone for recording${NC}"
fi

echo
echo "To start Meeting-Ops:"
echo "  ./start-meeting-ops.sh"
echo
echo "Default login credentials:"
echo "  Username: admin"
echo "  Password: Changeme123!"
echo "=================================================="