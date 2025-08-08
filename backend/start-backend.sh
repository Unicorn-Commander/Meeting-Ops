#!/bin/bash
# Meeting-Ops Backend Startup Script

echo "🚀 Starting Meeting-Ops Backend with NPU..."

# Load environment variables from .env file
if [ -f .env ]; then
    echo "📄 Loading configuration from .env file..."
    export $(cat .env | grep -v '^#' | xargs)
else
    echo "⚠️ No .env file found, using defaults..."
    export DATABASE_URL="postgresql://meetingops:REMOVED@localhost:5432/meeting_sessions"
    export REDIS_URL="redis://localhost:6379"
    export HOST="0.0.0.0"
    export PORT="9050"
fi

# Check if NPU is available
if [ -e /dev/accel/accel0 ]; then
    echo "⚡ NPU device detected: /dev/accel/accel0"
else
    echo "⚠️ NPU device not found - check permissions"
fi

# Start the NPU-optimized backend
echo "🎯 Starting NPU backend on ${HOST}:${PORT}..."
echo "📊 Using Database: ${DATABASE_URL}"
echo "🔄 Using Redis: ${REDIS_URL}"
echo ""

# Check if Docker services are running (don't start/stop them)
echo "🐳 Checking Docker services status..."
cd /home/ucadmin/Meeting-Ops

# Check if services are running
if ! docker ps | grep -q meetingops-postgres; then
    echo "⚠️  PostgreSQL not running. Start with: docker compose -f docker-compose-full-stack.yml up -d"
fi

if ! docker ps | grep -q meetingops-redis; then
    echo "⚠️  Redis not running. Start with: docker compose -f docker-compose-full-stack.yml up -d"
fi

if ! docker ps | grep -q meetingops-ollama; then
    echo "⚠️  Ollama not running. Start with: docker compose -f docker-compose-full-stack.yml up -d"
fi

# Wait for services
echo "⏳ Waiting for services..."
for i in {1..15}; do
    if docker exec meetingops-postgres pg_isready -U meetingops &>/dev/null; then
        echo "✅ PostgreSQL ready"
        break
    fi
    echo -n "."
    sleep 1
done

cd /home/ucadmin/Meeting-Ops/backend

# Start the FULL backend (not npu_main)
./venv/bin/python -m uvicorn main:app --host ${HOST} --port ${PORT} --reload