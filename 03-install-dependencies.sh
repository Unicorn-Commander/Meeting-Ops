#!/bin/bash
# Meeting-Ops Hardware Appliance Setup - Step 3: Python Dependencies
# Run this after verifying audio setup from Step 2

set -e

echo "=================================================="
echo "Meeting-Ops Hardware Appliance Setup - Step 3"
echo "Python Dependencies and Backend Setup"
echo "=================================================="
echo

# Check prerequisites
if ! docker --version &>/dev/null; then
    echo "❌ ERROR: Docker not accessible. Please complete steps 1 and 2 first."
    exit 1
fi

if ! groups | grep -q audio; then
    echo "⚠️  WARNING: Current user not in audio group."
    echo "Did you log out and back in after running 02-setup-audio.sh?"
    echo "Continuing anyway, but audio might not work..."
    echo
fi

# Install Python and development packages
echo "→ Installing Python 3 and development packages..."
sudo apt-get update
sudo apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    build-essential \
    git \
    ffmpeg \
    libffi-dev \
    libssl-dev

# Install Node.js for frontend
echo "→ Installing Node.js 20.x..."
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs

# Create Python virtual environment for backend
echo "→ Creating Python virtual environment..."
cd /home/ucadmin/Meeting-Ops/backend
python3 -m venv venv

# Activate venv and install basic requirements
echo "→ Installing Python dependencies..."
source venv/bin/activate

# Install core dependencies first
pip install --upgrade pip setuptools wheel

# Create minimal requirements file for core functionality
cat > requirements-minimal.txt << 'EOF'
# Core web framework
fastapi==0.104.1
uvicorn[standard]==0.24.0
python-multipart==0.0.6

# Database
sqlalchemy==2.0.23
psycopg2-binary==2.9.9

# Redis
redis==5.0.1

# Audio processing
sounddevice==0.4.6
numpy==1.26.2
scipy==1.11.4
librosa==0.10.1

# Authentication
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4

# Utilities
python-dotenv==1.0.0
pydantic==2.5.0
pydantic-settings==2.1.0
httpx==0.25.2
EOF

echo "→ Installing minimal Python requirements..."
# Try to install all at once, but handle psycopg2-binary separately for Python 3.13
pip install -r requirements-minimal.txt || {
    echo "→ Some packages failed. Installing individually for Python 3.13 compatibility..."
    
    # Install packages that work fine with Python 3.13
    pip install fastapi uvicorn python-multipart sqlalchemy redis \
                sounddevice numpy scipy librosa python-jose passlib \
                python-dotenv pydantic pydantic-settings httpx
    
    # Install psycopg2-binary separately (needs newer version for Python 3.13)
    pip install psycopg2-binary || pip install psycopg2-binary==2.9.10
}

# Install Qdrant client
echo "→ Installing Qdrant client..."
pip install qdrant-client==1.7.0

# Install WhisperX and dependencies (if available)
echo "→ Attempting to install WhisperX..."
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu || echo "Note: PyTorch installation failed, WhisperX may not work"
pip install git+https://github.com/m-bain/whisperx.git || echo "Note: WhisperX installation failed, will use fallback transcription"

# Download ONNX Whisper models
echo "→ Downloading ONNX Whisper models..."
mkdir -p models/whisper-base-onnx
cd models/whisper-base-onnx

# Download encoder and decoder models from Hugging Face
echo "  Downloading encoder.onnx..."
curl -L -o encoder.onnx "https://huggingface.co/onnx-community/whisper-base/resolve/main/encoder.onnx" || echo "Note: Failed to download encoder.onnx"

echo "  Downloading decoder.onnx..."
curl -L -o decoder.onnx "https://huggingface.co/onnx-community/whisper-base/resolve/main/decoder.onnx" || echo "Note: Failed to download decoder.onnx"

echo "  Downloading config.json..."
curl -L -o config.json "https://huggingface.co/onnx-community/whisper-base/resolve/main/config.json" || echo "Note: Failed to download config.json"

cd ../..

# Deactivate virtual environment
deactivate

# Install frontend dependencies
echo "→ Installing frontend dependencies..."
cd /home/ucadmin/Meeting-Ops/frontend
npm install

# Create environment files
echo "→ Creating environment configuration files..."

# Backend .env
cat > /home/ucadmin/Meeting-Ops/backend/.env << 'EOF'
# Database
DATABASE_URL=postgresql://meetingops:REMOVED@localhost:5432/meeting_sessions

# Redis
REDIS_URL=redis://localhost:6379

# Qdrant
QDRANT_URL=http://localhost:6333

# Security
SECRET_KEY=your-secret-key-change-this-in-production
ALGORITHM=HS256

# Audio
AUDIO_SAMPLE_RATE=48000
AUDIO_CHANNELS=1

# NPU (will be auto-detected)
USE_NPU=auto
EOF

# Frontend .env
cat > /home/ucadmin/Meeting-Ops/frontend/.env << 'EOF'
VITE_API_URL=http://localhost:9050
VITE_WS_URL=ws://localhost:9050
EOF

echo "=================================================="
echo "✅ Dependencies Installation Complete!"
echo "=================================================="
echo
echo "Next step: Run ./04-setup-services.sh"
echo