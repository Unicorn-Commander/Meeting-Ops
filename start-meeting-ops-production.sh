#!/bin/bash

# Meeting-Ops Production Startup Script
# Starts both backend and frontend in production mode

echo "🎯 Meeting-Ops Production Server"
echo "================================"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Start backend in background
echo -e "${BLUE}🚀 Starting backend server...${NC}"
cd backend
./start-backend.sh &
BACKEND_PID=$!

# Wait for backend to be ready
echo -e "${YELLOW}⏳ Waiting for backend to initialize...${NC}"
sleep 5

# Check if backend is running
if ! nc -z localhost 9050 2>/dev/null; then
    echo -e "${YELLOW}⚠️  Backend failed to start!${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Backend running on http://localhost:9050${NC}"

# Start frontend in production mode
echo -e "${BLUE}🎨 Starting frontend production server...${NC}"
cd ../frontend

# Build and serve production
./start-production.sh

# Cleanup on exit
trap "kill $BACKEND_PID 2>/dev/null" EXIT