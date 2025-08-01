#!/bin/bash

# Update and install headless server
sudo apt update && sudo apt upgrade -y
sudo apt install -y tasksel
sudo tasksel install server

# Install deps
sudo apt install -y python3 python3-venv python3-pip npm git alsa-utils curl libasound2-dev portaudio19-dev build-essential

# Clone repo (replace with your URL if private)
mkdir -p /home/ucadmin/Development
cd /home/ucadmin/Development
git clone https://github.com/your-repo/Unicorn-Commander-Meeting-Ops.git
cd Unicorn-Commander-Meeting-Ops

# Install NPU drivers
sudo ./FPGAs_AdaptiveSoCs_Unified_2025.1_0530_0145_Lin64.bin --force
sudo chmod 666 /dev/accel/accel0

# Setup backend
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Disable auth in main.py (comment out middleware)
sed -i 's/app.add_middleware(AuthRecoveryMiddleware/# app.add_middleware(AuthRecoveryMiddleware/g' main.py
sed -i 's/app.add_middleware(SessionRecoveryMiddleware/# app.add_middleware(SessionRecoveryMiddleware/g' main.py
echo "Authentication disabled"

# Setup frontend
cd ../frontend
npm install

# Start services in background
cd ../backend
nohub python3 -m uvicorn main:app --host 0.0.0.0 --port 9050 --reload > backend.log 2>&1 &

cd ../frontend
nohub npm run dev -- --port 7777 --host 0.0.0.0 > frontend.log 2>&1 &

echo "Setup complete! App running on 9050 (backend) and 7777 (frontend) with auth disabled."
echo "Access frontend via http://<machine-ip>:7777 (since headless)."
echo "Logs: backend.log, frontend.log"
echo "To stop: pkill -f uvicorn; pkill -f vite"
