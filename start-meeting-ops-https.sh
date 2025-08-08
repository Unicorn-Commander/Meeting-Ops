#!/bin/bash
# Start Meeting-Ops with Full HTTPS Support
# Magic Unicorn Unconventional Technology & Stuff Inc.

echo "🦄 Meeting-Ops Complete Startup (HTTPS Edition)"
echo "================================================"
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
PURPLE='\033[0;35m'
NC='\033[0m' # No Color

# Get the script directory
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Step 1: Start backend
echo -e "${PURPLE}📡 Starting Backend Server...${NC}"
cd backend
if ! pgrep -f "uvicorn main:app" > /dev/null; then
    ./start-backend.sh &
    echo -e "${GREEN}✅ Backend starting on port 9050${NC}"
    sleep 3
else
    echo -e "${YELLOW}⚠️  Backend already running${NC}"
fi
cd ..

# Step 2: Generate certificates if needed
echo ""
echo -e "${PURPLE}🔐 Checking certificates...${NC}"
cd frontend
if [ ! -f "certs/magic-unicorn-ca.crt" ]; then
    echo "Generating Magic Unicorn certificates..."
    ./generate-magic-unicorn-cert.sh
    echo -e "${GREEN}✅ Certificates generated${NC}"
else
    echo -e "${GREEN}✅ Certificates already exist${NC}"
fi

# Step 3: Start certificate server
echo ""
echo -e "${PURPLE}📥 Starting certificate download server...${NC}"
if ! pgrep -f "serve-certificate.py" > /dev/null; then
    python3 serve-certificate.py &
    CERT_PID=$!
    echo -e "${GREEN}✅ Certificate server started on port 8888${NC}"
    sleep 1
else
    echo -e "${YELLOW}⚠️  Certificate server already running${NC}"
fi

# Step 4: Start frontend with HTTPS
echo ""
echo -e "${PURPLE}🌐 Starting Frontend with HTTPS...${NC}"
echo ""
echo "════════════════════════════════════════════════════════════════"
echo "🦄 MEETING-OPS IS READY!"
echo "════════════════════════════════════════════════════════════════"
echo ""
echo -e "${GREEN}📱 Access Points:${NC}"
echo "   HTTPS (Secure):  https://localhost:7777"
echo "   HTTP (Standard): http://localhost:7777"
echo ""
echo -e "${GREEN}🔐 Certificate Installation:${NC}"
echo "   1. Visit: http://$(hostname -I | awk '{print $1}'):8888"
echo "   2. Download and install the Magic Unicorn certificate"
echo "   3. Access via HTTPS from any device on your network"
echo ""
echo -e "${GREEN}🎯 Server-Side Features:${NC}"
echo "   • NPU Transcription: Active (16 TOPS)"
echo "   • USB Microphone: Ready (M-305 on server)"
echo "   • AI Insights: Gemma3n:e4b via iGPU"
echo "   • Recording: Server-side from USB mic"
echo ""
echo -e "${PURPLE}Default Login:${NC}"
echo "   Admin: admin / admin123"
echo "   User:  user / user123"
echo ""
echo "Press Ctrl+C to stop all services"
echo "════════════════════════════════════════════════════════════════"
echo ""

# Start frontend (this blocks)
npm run dev:https

# Cleanup on exit
echo ""
echo "Shutting down services..."
kill $CERT_PID 2>/dev/null
pkill -f "uvicorn main:app"
echo "✨ Meeting-Ops stopped"