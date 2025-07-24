#!/bin/bash
# Script to run Unicorn Commander Backend on port 9050
# Frontend will be accessible on port 7777 (the magical port!)

set -e

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Virtual environment not found. Please run: python -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

# Set environment variables
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
export DATABASE_URL="sqlite:///./meeting_sessions.db"

# Check if port 9050 is available
if ss -tlnp | grep -q ":9050 "; then
    echo "Error: Port 9050 is already in use!"
    echo "Please stop the service using port 9050 first:"
    echo "  sudo lsof -i :9050"
    exit 1
fi

echo "Starting Unicorn Commander Backend on port 9050..."
echo "Backend API available at: http://localhost:9050/"
echo "Frontend (when running) will be at: http://localhost:7777/"
echo "Press Ctrl+C to stop"

# Start the server
cd "$(dirname "$0")"
source venv/bin/activate
python -m uvicorn main:app --host 0.0.0.0 --port 9050 --reload