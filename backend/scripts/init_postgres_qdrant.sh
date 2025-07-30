#!/bin/bash
# Initialize PostgreSQL and Qdrant for Meeting-Ops

set -e

echo "========================================"
echo "PostgreSQL + Qdrant Initialization"
echo "========================================"

# Check if running in Docker
if [ -f /.dockerenv ]; then
    echo "Running in Docker container"
    POSTGRES_HOST=${POSTGRES_HOST:-postgres}
    QDRANT_HOST=${QDRANT_HOST:-qdrant}
else
    echo "Running on host system"
    POSTGRES_HOST=${POSTGRES_HOST:-localhost}
    QDRANT_HOST=${QDRANT_HOST:-localhost}
fi

# Database credentials
DB_NAME=${DB_NAME:-meeting_ops}
DB_USER=${DB_USER:-meeting_ops}
DB_PASSWORD=${DB_PASSWORD:-unicorn2025}

# Wait for PostgreSQL to be ready
echo "Waiting for PostgreSQL to be ready..."
until PGPASSWORD=$DB_PASSWORD psql -h $POSTGRES_HOST -U $DB_USER -d postgres -c '\q' 2>/dev/null; do
    echo "PostgreSQL is unavailable - sleeping"
    sleep 2
done

echo "PostgreSQL is ready!"

# Create database if it doesn't exist
PGPASSWORD=$DB_PASSWORD psql -h $POSTGRES_HOST -U $DB_USER -d postgres <<EOF
SELECT 'CREATE DATABASE $DB_NAME'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '$DB_NAME')\gexec
EOF

echo "Database '$DB_NAME' is ready"

# Wait for Qdrant to be ready
echo "Waiting for Qdrant to be ready..."
until curl -s http://$QDRANT_HOST:6333/readiness > /dev/null 2>&1; do
    echo "Qdrant is unavailable - sleeping"
    sleep 2
done

echo "Qdrant is ready!"

# Check Qdrant collections
echo "Checking Qdrant collections..."
curl -s http://$QDRANT_HOST:6333/collections | jq .

# Export environment variables for the application
export DATABASE_URL="postgresql://$DB_USER:$DB_PASSWORD@$POSTGRES_HOST:5432/$DB_NAME"
export QDRANT_URL="http://$QDRANT_HOST:6333"

echo ""
echo "✅ PostgreSQL and Qdrant are initialized and ready!"
echo "DATABASE_URL: $DATABASE_URL"
echo "QDRANT_URL: $QDRANT_URL"
echo ""

# Initialize Python application database
if [ -f "/app/create_all_tables.py" ]; then
    echo "Initializing application database schema..."
    cd /app
    python create_all_tables.py
fi

# Run migration if needed
if [ "$RUN_MIGRATION" = "true" ] && [ -f "/app/migrate_to_postgres.py" ]; then
    echo "Running database migration from SQLite to PostgreSQL..."
    cd /app
    python migrate_to_postgres.py
fi

echo "Initialization complete!"