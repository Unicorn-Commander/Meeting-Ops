#!/bin/bash

# Start Gemma2-27b with optimized settings for Meeting-Ops
# This script ensures Gemma is properly loaded with 128k context and memory mapping

echo "🚀 Starting Optimized Gemma2-27b for Meeting-Ops..."
echo "=========================================="

# Check if docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker first."
    exit 1
fi

# Stop existing Gemma containers if running
echo "🔄 Stopping any existing Gemma containers..."
docker stop meeting-ops-gemma meeting-ops-gemma-optimized 2>/dev/null || true
docker rm meeting-ops-gemma meeting-ops-gemma-optimized 2>/dev/null || true

# Create models directory if it doesn't exist
mkdir -p models ollama ollama-webui

# Start the optimized Gemma container
echo "🐳 Starting Gemma2-27b container with optimized settings..."
docker compose -f docker-compose-gemma-optimized.yml up -d

# Wait for Ollama to be ready
echo "⏳ Waiting for Ollama to start..."
sleep 10

# Check if Ollama is responding
MAX_RETRIES=30
RETRY_COUNT=0

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
        echo "✅ Ollama is ready!"
        break
    else
        echo "⏳ Waiting for Ollama... ($RETRY_COUNT/$MAX_RETRIES)"
        sleep 5
        RETRY_COUNT=$((RETRY_COUNT+1))
    fi
done

if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
    echo "❌ Ollama failed to start. Check docker logs:"
    echo "   docker logs meeting-ops-gemma-optimized"
    exit 1
fi

# Check model status
echo ""
echo "📊 Checking model status..."
echo "=========================================="

# List available models
echo "Available models:"
curl -s http://localhost:11434/api/tags | python3 -m json.tool 2>/dev/null | grep '"name"' || echo "No models found"

# Check if our optimized model exists
if curl -s http://localhost:11434/api/tags | grep -q "meeting-ops-gemma"; then
    echo ""
    echo "✅ Meeting-Ops Gemma model is ready!"
    echo ""
    echo "📋 Model Details:"
    echo "  - Model: Gemma2-27b (optimized)"
    echo "  - Context: 128k tokens"
    echo "  - Memory: Mapped and locked in RAM"
    echo "  - Status: Preloaded and ready"
else
    echo ""
    echo "⚠️ Meeting-Ops Gemma model not found. The container is building it..."
    echo "This may take 10-15 minutes on first run while downloading the 27B model."
    echo ""
    echo "You can monitor progress with:"
    echo "  docker logs -f meeting-ops-gemma-optimized"
fi

echo ""
echo "=========================================="
echo "🎯 Gemma2-27b Service Information:"
echo "  - API Endpoint: http://localhost:11434"
echo "  - Model Name: meeting-ops-gemma"
echo "  - Context Window: 128k tokens"
echo "  - Optimizations: mmap, mlock, flash attention"
echo ""
echo "📝 Test the model with:"
echo '  curl -X POST http://localhost:11434/api/generate \'
echo '    -d '"'"'{"model": "meeting-ops-gemma", "prompt": "Hello, test", "stream": false}'"'"
echo ""
echo "📊 View container logs:"
echo "  docker logs -f meeting-ops-gemma-optimized"
echo ""
echo "🛑 To stop Gemma:"
echo "  docker compose -f docker-compose-gemma-optimized.yml down"
echo "=========================================="