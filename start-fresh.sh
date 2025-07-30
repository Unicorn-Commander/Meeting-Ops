#!/bin/bash
# Start Meeting-Ops with PostgreSQL and Qdrant (Fresh Start)

set -e

echo "========================================"
echo "Starting Fresh Meeting-Ops Installation"
echo "========================================"

# Set environment variables
export DB_PASSWORD=${DB_PASSWORD:-unicorn2025}
export PGADMIN_PASSWORD=${PGADMIN_PASSWORD:-admin123}

# Clean up any existing data
echo "Cleaning up existing data..."
docker-compose down -v 2>/dev/null || true
rm -f .postgres-initialized 2>/dev/null || true
rm -f ./backend/meeting_sessions.db 2>/dev/null || true
rm -rf ./backend/data/* 2>/dev/null || true
rm -rf ./backend/recordings/* 2>/dev/null || true

# Pull latest images
echo "Pulling latest Docker images..."
docker-compose pull

# Build backend with PostgreSQL support
echo "Building backend with PostgreSQL support..."
docker-compose build backend

# Start the stack
echo "Starting services..."
docker-compose up -d

# Wait for services to be ready
echo "Waiting for services to be ready..."
sleep 15

# Initialize fresh database
echo "Initializing fresh database..."
docker exec unicorn-backend /docker-entrypoint-initdb.d/init_postgres_fresh.sh || {
    echo "Initialization from container failed, trying from host..."
    cd backend
    export DATABASE_URL="postgresql://meeting_ops:${DB_PASSWORD}@localhost:5432/meeting_ops"
    export QDRANT_URL="http://localhost:6333"
    ./scripts/init_postgres_fresh.sh
    cd ..
}

# Check service health
echo ""
echo "Service Status:"
echo "---------------"
docker-compose ps

echo ""
echo "========================================"
echo "Fresh Meeting-Ops Installation Complete!"
echo "========================================"
echo ""
echo "Access points:"
echo "  - Frontend: http://localhost:7777"
echo "  - Backend API: http://localhost:9050"
echo "  - PostgreSQL: localhost:5432"
echo "  - Qdrant: http://localhost:6333"
echo ""
echo "Default admin credentials:"
echo "  Username: admin"
echo "  Password: changeme123!"
echo ""
echo "To include pgAdmin: docker-compose --profile tools up -d"
echo "To view logs: docker-compose logs -f"
echo "To stop: docker-compose down"
echo ""
echo "Enjoy your fresh installation! 🚀"
echo "========================================"