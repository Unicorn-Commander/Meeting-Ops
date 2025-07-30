#!/bin/bash
# Start backend with minimal GPU usage

# Kill any existing backend processes
pkill -f "uvicorn main:app"
sleep 1

# Set environment variables to disable GPU-heavy features
export DISABLE_SPEAKER_DIARIZATION=true
export CUDA_VISIBLE_DEVICES=""  # Hide CUDA devices
export ROCR_VISIBLE_DEVICES=""  # Hide ROCm devices

echo "Starting minimal backend (no GPU features)..."
nohup python -m uvicorn main:app --host 0.0.0.0 --port 1950 > backend_minimal.log 2>&1 &
echo "Backend started with PID $!"
echo "Logs: tail -f backend_minimal.log"