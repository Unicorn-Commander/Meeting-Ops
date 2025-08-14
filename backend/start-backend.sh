#!/bin/bash
# Meeting-Ops Backend Startup Script

echo "🚀 Starting Meeting-Ops Backend with NPU..."

# Load environment variables from .env file (supports both regular and SSO configs)
if [ -f ../.env ]; then
    echo "📄 Loading configuration from parent .env file..."
    export $(cat ../.env | grep -v '^#' | xargs)
elif [ -f .env ]; then
    echo "📄 Loading configuration from .env file..."
    export $(cat .env | grep -v '^#' | xargs)
else
    echo "⚠️ No .env file found, using defaults..."
    export DATABASE_URL="postgresql://meetingops:REMOVED@localhost:5432/meeting_sessions"
    export REDIS_URL="redis://localhost:6379"
    export HOST="0.0.0.0"
    export PORT="9050"
fi

# Set SSO-related environment variables if using Authentik
if [ ! -z "$AUTHENTIK_SECRET_KEY" ]; then
    echo "🔐 SSO Configuration detected (Authentik)"
    export AUTHENTIK_URL="${AUTHENTIK_URL:-http://authentik-server:9000}"
    export AUTHENTIK_API_TOKEN="${AUTHENTIK_API_TOKEN:-}"
    export AUTHENTIK_ADMIN_GROUPS="${AUTHENTIK_ADMIN_GROUPS:-admin,Meeting-Ops-Admins}"
    export AUTHENTIK_VERIFY_SSL="${AUTHENTIK_VERIFY_SSL:-false}"
    
    # Development mode for testing without full SSO
    export DEVELOPMENT_MODE="${DEVELOPMENT_MODE:-false}"
    
    if [ "$DEVELOPMENT_MODE" = "true" ]; then
        echo "⚠️  Running in DEVELOPMENT MODE - using mock authentication"
    fi
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

# Show authentication mode
if [ ! -z "$AUTHENTIK_SECRET_KEY" ]; then
    echo "🔐 Authentication: Authentik SSO"
    if [ "$DEVELOPMENT_MODE" = "true" ]; then
        echo "   Mode: Development (mock auth)"
    else
        echo "   Mode: Production (full SSO)"
        echo "   Authentik URL: ${AUTHENTIK_URL}"
    fi
else
    echo "🔑 Authentication: Local (JWT)"
fi
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

# Kill any existing audio processes that might block the device
echo "🧹 Cleaning up existing audio processes..."
pkill -f arecord 2>/dev/null || true
pkill -f "uvicorn main:app" 2>/dev/null || true
sleep 1

# Start the FULL backend (without --reload for production stability)
echo "🚀 Starting backend with WORKING audio recording (ffmpeg)..."
./venv/bin/python -m uvicorn main:app --host ${HOST} --port ${PORT}