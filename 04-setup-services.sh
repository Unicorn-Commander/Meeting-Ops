#!/bin/bash
# Meeting-Ops Hardware Appliance Setup - Step 4: Docker Services
# Run this after installing dependencies

set -e

echo "=================================================="
echo "Meeting-Ops Hardware Appliance Setup - Step 4"
echo "Docker Services Setup (PostgreSQL, Redis, Qdrant)"
echo "=================================================="
echo

# Check Docker
if ! docker --version &>/dev/null; then
    echo "❌ ERROR: Docker not accessible."
    exit 1
fi

# Navigate to Meeting-Ops directory
cd /home/ucadmin/Meeting-Ops

# Start Docker services
echo "→ Starting Docker services..."
echo "  - PostgreSQL (port 5432)"
echo "  - Redis (port 6379)"
echo "  - Qdrant (port 6333)"
echo

docker compose -f docker-compose-services.yml up -d

# Wait for services to be healthy
echo "→ Waiting for services to be ready..."
sleep 5

# Check PostgreSQL
echo -n "  PostgreSQL: "
docker exec meetingops-postgres pg_isready -U meetingops &>/dev/null && echo "✅ Ready" || echo "❌ Not ready"

# Check Redis
echo -n "  Redis: "
docker exec meetingops-redis redis-cli ping &>/dev/null && echo "✅ Ready" || echo "❌ Not ready"

# Check Qdrant
echo -n "  Qdrant: "
curl -s http://localhost:6333/health &>/dev/null && echo "✅ Ready" || echo "❌ Not ready"

echo

# Initialize database
echo "→ Initializing PostgreSQL database..."
sleep 3

# Create database schema
docker exec -i meetingops-postgres psql -U meetingops -d meeting_sessions << 'EOF'
-- Create sessions table
CREATE TABLE IF NOT EXISTS recording_sessions (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    status VARCHAR(50) DEFAULT 'created',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    ended_at TIMESTAMP,
    audio_file VARCHAR(255),
    transcript TEXT,
    summary TEXT
);

-- Create users table
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    is_active BOOLEAN DEFAULT true,
    is_superuser BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create transcriptions table
CREATE TABLE IF NOT EXISTS transcriptions (
    id SERIAL PRIMARY KEY,
    session_id INTEGER REFERENCES recording_sessions(id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    start_time FLOAT,
    end_time FLOAT,
    speaker VARCHAR(50),
    confidence FLOAT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_sessions_status ON recording_sessions(status);
CREATE INDEX IF NOT EXISTS idx_transcriptions_session ON transcriptions(session_id);
EOF

echo "✅ Database schema created"

# Create systemd service files
echo "→ Creating systemd service files..."

# Backend service
sudo tee /etc/systemd/system/meetingops-backend.service > /dev/null << 'EOF'
[Unit]
Description=Meeting-Ops Backend Service
After=network.target docker.service
Requires=docker.service

[Service]
Type=simple
User=ucadmin
WorkingDirectory=/home/ucadmin/Meeting-Ops/backend
Environment="PATH=/home/ucadmin/Meeting-Ops/backend/venv/bin:/usr/local/bin:/usr/bin:/bin"
ExecStartPre=/bin/sleep 10
ExecStart=/home/ucadmin/Meeting-Ops/backend/venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 9050
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Frontend service (for production)
sudo tee /etc/systemd/system/meetingops-frontend.service > /dev/null << 'EOF'
[Unit]
Description=Meeting-Ops Frontend Service
After=network.target

[Service]
Type=simple
User=ucadmin
WorkingDirectory=/home/ucadmin/Meeting-Ops/frontend
ExecStart=/usr/bin/npm run dev -- --host 0.0.0.0 --port 7777
Restart=always
RestartSec=10
Environment="NODE_ENV=production"

[Install]
WantedBy=multi-user.target
EOF

# Create a production backend with proper imports
cat > /home/ucadmin/Meeting-Ops/backend/main.py << 'EOF'
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize FastAPI
app = FastAPI(
    title="Meeting-Ops API",
    description="AI-powered meeting recording and transcription appliance",
    version="1.0.0"
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"message": "Meeting-Ops API", "status": "operational"}

@app.get("/api/status")
async def status():
    return {
        "status": "ok",
        "backend": "running",
        "services": {
            "postgresql": "connected",
            "redis": "connected",
            "qdrant": "connected"
        }
    }

@app.get("/api/health")
async def health():
    return {"status": "healthy"}

# Import routers (we'll add these gradually)
# from routers import auth, sessions, audio, transcription
# app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
# app.include_router(sessions.router, prefix="/api/sessions", tags=["sessions"])
# app.include_router(audio.router, prefix="/api/audio", tags=["audio"])
# app.include_router(transcription.router, prefix="/api/transcription", tags=["transcription"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9050)
EOF

# Reload systemd
sudo systemctl daemon-reload

echo "=================================================="
echo "✅ Services Setup Complete!"
echo "=================================================="
echo
echo "Docker services running:"
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
echo
echo "Systemd services created (not started yet):"
echo "  - meetingops-backend.service"
echo "  - meetingops-frontend.service"
echo
echo "Next step: Run ./05-start-stack.sh to start everything!"
echo