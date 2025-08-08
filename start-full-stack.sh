#!/bin/bash
# Start Meeting-Ops Full Stack with Optimized Services

echo "🚀 Starting Meeting-Ops Full Stack..."
echo "=================================="

# Check if running as user with docker permissions
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not accessible. Please ensure Docker is running and you have permissions."
    exit 1
fi

# Stop any existing containers
echo "🛑 Stopping existing services..."
docker compose -f docker-compose-full-stack.yml down 2>/dev/null || true

# Start all services
echo "🐳 Starting services..."
docker compose -f docker-compose-full-stack.yml up -d

# Wait for services to be ready
echo "⏳ Waiting for services to initialize..."

# Wait for PostgreSQL
echo -n "   PostgreSQL: "
for i in {1..30}; do
    if docker exec meetingops-postgres pg_isready -U meetingops &>/dev/null; then
        echo "✅ Ready"
        break
    fi
    echo -n "."
    sleep 1
done

# Wait for Redis
echo -n "   Redis: "
for i in {1..10}; do
    if docker exec meetingops-redis redis-cli ping &>/dev/null; then
        echo "✅ Ready"
        break
    fi
    echo -n "."
    sleep 1
done

# Wait for Qdrant
echo -n "   Qdrant: "
for i in {1..10}; do
    if curl -s http://localhost:6333/health &>/dev/null; then
        echo "✅ Ready"
        break
    fi
    echo -n "."
    sleep 1
done

# Wait for Ollama
echo -n "   Ollama: "
for i in {1..15}; do
    if curl -s http://localhost:11434/api/tags &>/dev/null; then
        echo "✅ Ready"
        break
    fi
    echo -n "."
    sleep 1
done

echo ""

# Pull Gemma3n model if not already present
echo "📦 Ensuring Gemma3n:e4b model is available..."
if docker exec meetingops-ollama ollama list | grep -q "gemma3n:e4b"; then
    echo "   ✅ Gemma3n:e4b already installed"
else
    echo "   📥 Pulling Gemma3n:e4b model (this may take a few minutes)..."
    docker exec meetingops-ollama ollama pull gemma3n:e4b
    echo "   ✅ Gemma3n:e4b installed"
fi

# Show service status
echo ""
echo "📊 Service Status:"
echo "=================================="
docker compose -f docker-compose-full-stack.yml ps

echo ""
echo "🎯 Service Endpoints:"
echo "=================================="
echo "   PostgreSQL:  localhost:5432 (meetingops/REMOVED)"
echo "   Redis:       localhost:6379"
echo "   Qdrant:      localhost:6333 (Web UI: localhost:6333/dashboard)"
echo "   Ollama:      localhost:11434 (with Gemma3n:e4b)"
echo ""
echo "✅ Full stack is ready!"
echo ""
echo "To start the backend:"
echo "   cd backend && ./start-backend.sh"
echo ""
echo "To start the frontend:"
echo "   cd frontend && ./start-frontend.sh"
echo ""
echo "To stop all services:"
echo "   docker compose -f docker-compose-full-stack.yml down"