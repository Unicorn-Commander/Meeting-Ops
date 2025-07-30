#!/bin/bash
# Initialize PostgreSQL and Qdrant for Meeting-Ops (Fresh Start)

set -e

echo "========================================"
echo "Fresh PostgreSQL + Qdrant Initialization"
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

# Drop and recreate database for fresh start
echo "Creating fresh database..."
PGPASSWORD=$DB_PASSWORD psql -h $POSTGRES_HOST -U $DB_USER -d postgres <<EOF
DROP DATABASE IF EXISTS $DB_NAME;
CREATE DATABASE $DB_NAME;
EOF

echo "Database '$DB_NAME' created fresh"

# Wait for Qdrant to be ready
echo "Waiting for Qdrant to be ready..."
until curl -s http://$QDRANT_HOST:6333/readiness > /dev/null 2>&1; do
    echo "Qdrant is unavailable - sleeping"
    sleep 2
done

echo "Qdrant is ready!"

# Delete existing collection if present
echo "Creating fresh Qdrant collection..."
curl -X DELETE http://$QDRANT_HOST:6333/collections/meeting_transcripts 2>/dev/null || true

# Export environment variables for the application
export DATABASE_URL="postgresql://$DB_USER:$DB_PASSWORD@$POSTGRES_HOST:5432/$DB_NAME"
export QDRANT_URL="http://$QDRANT_HOST:6333"

echo ""
echo "✅ PostgreSQL and Qdrant are initialized fresh!"
echo "DATABASE_URL: $DATABASE_URL"
echo "QDRANT_URL: $QDRANT_URL"
echo ""

# Initialize Python application database
if [ -f "/app/init_db.py" ]; then
    echo "Initializing application database schema..."
    cd /app
    python init_db.py
else
    echo "Running database initialization..."
    cd /app
    python -c "
from database.database import init_database
from auth.service import AuthService
import asyncio

# Initialize database
init_database()

# Create initial admin user
async def create_admin():
    auth_service = AuthService()
    try:
        admin_user = await auth_service.create_initial_admin()
        if admin_user:
            print('✅ Admin user created: admin / changeme123!')
    except Exception as e:
        print(f'Admin user may already exist: {e}')

asyncio.run(create_admin())
print('✅ Database initialized successfully!')
"
fi

echo ""
echo "========================================"
echo "Fresh initialization complete!"
echo "Admin credentials: admin / changeme123!"
echo "========================================"