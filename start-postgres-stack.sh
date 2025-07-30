#!/bin/bash
# Start Meeting-Ops with PostgreSQL and Qdrant

set -e

# Change to the script's directory
cd "$(dirname "$0")"

echo "========================================"
echo "Starting Meeting-Ops with PostgreSQL"
echo "========================================"

# Set environment variables
export DB_PASSWORD=${DB_PASSWORD:-unicorn2025}
export PGADMIN_PASSWORD=${PGADMIN_PASSWORD:-admin123}

# Check if this is the first run
if [ ! -f ".postgres-initialized" ]; then
    echo "First run detected. Will migrate data from SQLite if available."
    export RUN_MIGRATION=true
    
    # Check if SQLite database exists
    if [ -f "./backend/meeting_sessions.db" ]; then
        echo "✅ Found existing SQLite database. Will migrate to PostgreSQL."
    else
        echo "ℹ️  No existing SQLite database found. Starting fresh."
    fi
fi

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
sleep 10

# Check service health
echo ""
echo "Service Status:"
echo "---------------"
docker-compose ps

# Show logs for initialization
echo ""
echo "Checking initialization logs..."
docker-compose logs backend | tail -20

# Mark as initialized
touch .postgres-initialized

echo ""
echo "========================================"
echo "Meeting-Ops is starting up!"
echo "========================================"
echo ""
echo "Access points:"
echo "  - Frontend: http://localhost:7777"
echo "  - Backend API: http://localhost:9050"
echo "  - PostgreSQL: localhost:5432 (user: meeting_ops, password: $DB_PASSWORD)"
echo "  - Qdrant: http://localhost:6333"
echo ""
echo "To include pgAdmin, run: docker-compose --profile tools up -d"
echo "To view logs: docker-compose logs -f"
echo "To stop: docker-compose down"
echo ""
echo "First time setup may take a few minutes while models are downloaded."
echo "========================================"