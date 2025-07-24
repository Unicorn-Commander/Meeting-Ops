#!/bin/bash
# Unicorn Commander - Complete Startup Script
# Starts both backend (port 9050) and frontend (port 7777 - the magical port!)

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🦄 Starting Unicorn Commander${NC}"
echo -e "${BLUE}============================${NC}"
echo ""

# Configuration
BACKEND_PORT=9050
FRONTEND_PORT=7777
BACKEND_DIR="$(pwd)/backend"
FRONTEND_DIR="$(pwd)/frontend"

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

# Check if ports are available
print_status "Checking if ports are available..."

for port in $BACKEND_PORT $FRONTEND_PORT; do
    if ss -tlnp | grep -q ":$port "; then
        print_error "Port $port is already in use!"
        echo "Please stop the service using port $port first:"
        echo "  sudo lsof -i :$port"
        exit 1
    fi
done

print_success "Ports $BACKEND_PORT and $FRONTEND_PORT are available"

# Start backend
print_status "Starting backend on port $BACKEND_PORT..."

cd "$BACKEND_DIR"

# Check if virtual environment exists
if [ ! -d "venv313" ] && [ ! -d "venv" ]; then
    print_error "No Python virtual environment found. Please run the install script first."
    exit 1
fi

# Use the best available virtual environment
if [ -d "venv313" ]; then
    VENV_DIR="venv313"
elif [ -d "venv" ]; then
    VENV_DIR="venv"
fi

print_status "Using virtual environment: $VENV_DIR"

# Start backend in background
source "$VENV_DIR/bin/activate"
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
export DATABASE_URL="sqlite:///./meeting_sessions.db"

print_status "Starting backend server..."
python -m uvicorn main:app --host 0.0.0.0 --port $BACKEND_PORT --reload &
BACKEND_PID=$!

# Wait for backend to start
print_status "Waiting for backend to start..."
sleep 5

# Check if backend is running
if ! kill -0 $BACKEND_PID 2>/dev/null; then
    print_error "Backend failed to start"
    exit 1
fi

# Test backend health
if curl -s http://localhost:$BACKEND_PORT/api/status >/dev/null 2>&1; then
    print_success "Backend is running on port $BACKEND_PORT"
else
    print_warning "Backend may still be starting up..."
fi

# Start frontend
print_status "Starting frontend on port $FRONTEND_PORT (the magical port!)..."

cd "$FRONTEND_DIR"

# Check if node_modules exists
if [ ! -d "node_modules" ]; then
    print_status "Installing frontend dependencies..."
    npm install
fi

# Start frontend in background
print_status "Starting frontend server..."
npm run dev -- --port $FRONTEND_PORT --host 0.0.0.0 &
FRONTEND_PID=$!

# Wait for frontend to start
print_status "Waiting for frontend to start..."
sleep 5

# Check if frontend is running
if ! kill -0 $FRONTEND_PID 2>/dev/null; then
    print_error "Frontend failed to start"
    # Kill backend if frontend fails
    kill $BACKEND_PID 2>/dev/null
    exit 1
fi

# Test frontend
if curl -s http://localhost:$FRONTEND_PORT >/dev/null 2>&1; then
    print_success "Frontend is running on port $FRONTEND_PORT"
else
    print_warning "Frontend may still be starting up..."
fi

# Installation complete
echo ""
echo -e "${GREEN}🎉 Unicorn Commander is Running! 🎉${NC}"
echo -e "${GREEN}=================================${NC}"
echo ""
echo -e "${BLUE}Access your application:${NC}"
echo -e "  🌐 Web Interface: ${GREEN}http://localhost:$FRONTEND_PORT/${NC} ${YELLOW}← The magical port!${NC}"
echo -e "  🔧 Backend API:   ${GREEN}http://localhost:$BACKEND_PORT/docs${NC}"
echo ""
echo -e "${BLUE}Default Admin Credentials:${NC}"
echo -e "  👤 Username: ${YELLOW}admin${NC}"
echo -e "  🔑 Password: ${YELLOW}changeme123!${NC}"
echo ""
echo -e "${BLUE}Process Information:${NC}"
echo -e "  🔧 Backend PID:  ${GREEN}$BACKEND_PID${NC}"
echo -e "  🌐 Frontend PID: ${GREEN}$FRONTEND_PID${NC}"
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop both services${NC}"
echo ""

# Function to cleanup on exit
cleanup() {
    echo ""
    print_status "Shutting down services..."
    kill $FRONTEND_PID 2>/dev/null || true
    kill $BACKEND_PID 2>/dev/null || true
    print_success "Services stopped"
    exit 0
}

# Set trap to cleanup on script exit
trap cleanup INT TERM

# Wait for either process to exit
wait $BACKEND_PID $FRONTEND_PID