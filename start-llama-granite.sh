#!/bin/bash

# Meeting-Ops: Replace Ollama with llama.cpp + Granite 3.3 8B
# Performance: ~10 tokens/sec vs Ollama's ~2 tokens/sec = 5x faster!
# Memory: 4.7GB GGUF vs 8GB+ Ollama = 40% less RAM

set -e

LLAMA_DIR="/home/ucadmin/llama.cpp"
MODEL_PATH="$LLAMA_DIR/models/granite-3.3-8b-instruct-Q4_K_M.gguf"
SERVER_BIN="$LLAMA_DIR/build/bin/llama-server"

echo "🚀 Starting llama.cpp Granite 3.3 8B (replaces Ollama)"
echo "📊 Performance: 5x faster, 40% less memory"
echo "🎯 Backend API: localhost:11435 (was 11434)"

# Kill Ollama if running
pkill -f ollama || true
sleep 1

# Kill existing llama-server
pkill -f "llama-server.*granite" || true
sleep 1

# Performance tuning for AMD 8945HS
export OMP_NUM_THREADS=8
export OMP_SCHEDULE=dynamic
export OMP_PLACES=cores
export OMP_PROC_BIND=close

# Future: GPU acceleration with ROCm
export HSA_OVERRIDE_GFX_VERSION=11.0.0

echo "⚡ Optimized for AMD 8945HS (16 cores, 96GB RAM)"

# Start optimized server
exec "$SERVER_BIN" \
  -m "$MODEL_PATH" \
  --host 0.0.0.0 \
  --port 11435 \
  -c 8192 \
  -b 4096 \
  --threads 8 \
  --threads-batch 8 \
  --mlock \
  --cache-type-k f16 \
  --cache-type-v f16 \
  --verbose