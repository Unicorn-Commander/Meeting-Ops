# Fresh PostgreSQL + Qdrant Installation

Since you want to start fresh without any previous data, I've created a simplified setup process.

## Quick Start

```bash
# Start with a completely fresh installation
./start-fresh.sh
```

This script will:
1. **Remove all existing data** (SQLite, recordings, etc.)
2. **Create fresh PostgreSQL database**
3. **Initialize empty Qdrant collection**
4. **Create new admin user** (admin/changeme123!)
5. **Start all services**

## What Happens

The fresh start process:
- Drops any existing PostgreSQL database and creates a new one
- Deletes any existing Qdrant collections
- Removes all local SQLite files
- Clears recordings and data directories
- Creates a pristine installation

## Access Points

After running `./start-fresh.sh`:

- **Frontend**: http://localhost:7777
- **Backend API**: http://localhost:9050
- **PostgreSQL**: localhost:5432
- **Qdrant**: http://localhost:6333
- **pgAdmin** (optional): http://localhost:5050

## Default Credentials

- **Admin User**: 
  - Username: `admin`
  - Password: `changeme123!`

## Benefits of Fresh Start

1. **Clean State**: No legacy data or configurations
2. **Optimal Performance**: Fresh indexes and statistics
3. **Latest Schema**: All tables use the newest structure
4. **No Migration Overhead**: Faster startup

## Managing Your Installation

```bash
# View logs
docker-compose logs -f

# Stop services
docker-compose down

# Stop and remove all data
docker-compose down -v

# Start with pgAdmin included
docker-compose --profile tools up -d

# Restart services
docker-compose restart
```

## Next Steps

1. Login with admin credentials
2. Create additional users as needed
3. Start recording meetings
4. Enjoy semantic search capabilities!

The system is now running with PostgreSQL for data storage and Qdrant for semantic search - both starting completely fresh! 🎉