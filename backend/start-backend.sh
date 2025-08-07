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
echo "📊 Using PostgreSQL: ${DATABASE_URL}"
echo "🔄 Using Redis: ${REDIS_URL}"
echo ""

./venv/bin/python -m uvicorn npu_main:app --host ${HOST} --port ${PORT} --reload