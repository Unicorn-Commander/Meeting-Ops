#!/bin/bash
# Meeting-Ops Hardware Appliance Setup - Step 5: Start Everything
# Run this to start the complete Meeting-Ops stack

set -e

echo "=================================================="
echo "Meeting-Ops Hardware Appliance Setup - Step 5"
echo "Starting Complete Stack"
echo "=================================================="
echo

# Function to check if port is in use
check_port() {
    if lsof -Pi :$1 -sTCP:LISTEN -t >/dev/null 2>&1; then
        echo "⚠️  Port $1 is already in use!"
        echo "   Run: sudo lsof -i :$1 to see what's using it"
        return 1
    fi
    return 0
}

# Kill any existing backend/frontend processes
echo "→ Stopping any existing Meeting-Ops processes..."
pkill -f "uvicorn.*9050" || true
pkill -f "vite.*7777" || true
pkill -f "no_auth_backend" || true
sleep 2

# Check Docker services
echo "→ Checking Docker services..."
docker compose -f docker-compose-services.yml ps

# Start Docker services if not running
echo "→ Ensuring Docker services are running..."
docker compose -f docker-compose-services.yml up -d

# Wait for services
echo "→ Waiting for services to be ready..."
for i in {1..30}; do
    if docker exec meetingops-postgres pg_isready -U meetingops &>/dev/null && \
       docker exec meetingops-redis redis-cli ping &>/dev/null && \
       curl -s http://localhost:6333/health &>/dev/null; then
        echo "✅ All services ready!"
        break
    fi
    echo -n "."
    sleep 1
done
echo

# Check required ports
echo "→ Checking ports..."
check_port 9050 || { echo "Please free up port 9050 for backend"; exit 1; }
check_port 7777 || { echo "Please free up port 7777 for frontend"; exit 1; }

# Start backend
echo "→ Starting backend service..."
cd /home/ucadmin/Meeting-Ops/backend
if [ -f venv/bin/activate ]; then
    source venv/bin/activate
    nohup python -m uvicorn main:app --host 0.0.0.0 --port 9050 > backend.log 2>&1 &
    BACKEND_PID=$!
    echo "   Backend started (PID: $BACKEND_PID)"
else
    echo "⚠️  Python virtual environment not found!"
    echo "   Using simple backend instead..."
    nohup python3 no_auth_backend_with_audio.py > backend.log 2>&1 &
    BACKEND_PID=$!
    echo "   Simple backend started (PID: $BACKEND_PID)"
fi

# Start frontend
echo "→ Starting frontend service..."
cd /home/ucadmin/Meeting-Ops/frontend
nohup npm run dev -- --host 0.0.0.0 --port 7777 > frontend.log 2>&1 &
FRONTEND_PID=$!
echo "   Frontend started (PID: $FRONTEND_PID)"

# Wait for services to start
echo "→ Waiting for services to start..."
sleep 5

# Check if services are running
echo
echo "→ Service Status:"
echo -n "  Backend API: "
curl -s http://localhost:9050/api/status &>/dev/null && echo "✅ Running" || echo "❌ Not responding"
echo -n "  Frontend UI: "
curl -s http://localhost:7777 &>/dev/null && echo "✅ Running" || echo "❌ Not responding"

# Show access information
echo
echo "=================================================="
echo "✅ Meeting-Ops Stack Started!"
echo "=================================================="
echo
echo "Access Points:"
echo "  Frontend: http://localhost:7777"
echo "  Backend API: http://localhost:9050"
echo "  API Docs: http://localhost:9050/docs"
echo
echo "Network Access:"
IP_ADDR=$(hostname -I | awk '{print $1}')
echo "  Frontend: http://$IP_ADDR:7777"
echo "  Backend API: http://$IP_ADDR:9050"
echo
echo "Default Credentials:"
echo "  Username: admin"
echo "  Password: admin"
echo
echo "Docker Services:"
docker ps --format "table {{.Names}}\t{{.Status}}" | grep meetingops
echo
echo "Logs:"
echo "  Backend: tail -f backend/backend.log"
echo "  Frontend: tail -f frontend/frontend.log"
echo
echo "To stop everything: ./stop-stack.sh"
echo "To enable auto-start on boot: ./enable-autostart.sh"
echo