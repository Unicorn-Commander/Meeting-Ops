# Unicorn Commander - Docker Deployment Guide

## Quick Start

### Development Mode
```bash
# Start development environment with hot reload
make dev

# Or manually:
docker-compose -f docker-compose.dev.yml up
```

Access:
- Frontend: http://localhost:5173
- Backend API: http://localhost:9050

### Production Mode
```bash
# Copy and configure environment
cp .env.example .env
# Edit .env with your settings

# Build and start production stack
make build
make prod

# Or manually:
docker-compose build
docker-compose up -d
```

Access: http://localhost (nginx on port 80)

## Docker Stack Overview

### Basic Stack (docker-compose.yml)
- **backend**: FastAPI application with audio processing
- **frontend**: Nginx serving React build

### Development Stack (docker-compose.dev.yml)
- **backend**: With hot reload and volume mounts
- **frontend-dev**: Vite dev server with hot reload

### Production Stack (docker-compose.prod.yml)
- **backend**: Optimized Python container
- **frontend**: Static files served by nginx
- **nginx**: Reverse proxy with SSL support
- **postgres**: Production database
- **redis**: Cache and session storage
- **backup**: Automated backup service

## Audio Device Access

The Docker setup includes audio device passthrough for Linux systems:

```yaml
devices:
  - /dev/snd:/dev/snd
privileged: true
group_add:
  - audio
```

**Note**: Audio device access in Docker requires:
1. Host system audio devices
2. User in `audio` group
3. Privileged mode or specific device permissions

For production, consider using a dedicated audio capture service or USB audio device.

## Configuration

### Environment Variables
Create `.env` file:
```env
# Database
DATABASE_URL=postgresql://unicorn:REMOVED@postgres:5432/unicorn_commander

# Security
SECRET_KEY=your-secret-key-here

# HuggingFace (for speaker diarization)
HUGGINGFACE_TOKEN=your-token

# Audio
DEFAULT_AUDIO_DEVICE=default
DEFAULT_SAMPLE_RATE=16000
```

### Volumes
- `./data`: Database files (SQLite mode)
- `./recordings`: Audio recordings
- `./whisper_cache`: Model cache
- `./backups`: Automated backups (prod)

## Common Commands

```bash
# View logs
make logs
make logs-backend
make logs-frontend

# Shell access
make shell-backend
make shell-frontend

# Database
make db-shell
make db-backup

# Restart services
make restart
make restart-dev

# Clean up
make clean      # Remove containers and volumes
make clean-all  # Also remove images
```

## Production Deployment

### 1. SSL/TLS Setup
Create SSL certificates and place in `nginx/ssl/`:
```bash
mkdir -p nginx/ssl
# Add your cert.pem and key.pem files
```

### 2. Nginx Configuration
Create `nginx/nginx.prod.conf` for custom nginx settings.

### 3. Systemd Service (Alternative to Docker)
For systemd deployment on host:
```bash
sudo cp deploy/unicorn-commander.service /etc/systemd/system/
sudo systemctl enable unicorn-commander
sudo systemctl start unicorn-commander
```

### 4. Firewall Rules
```bash
# Allow HTTP/HTTPS
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
```

## Troubleshooting

### Audio Not Working
1. Check host audio devices: `arecord -l`
2. Verify Docker audio access: `docker exec unicorn-backend arecord -l`
3. Check user permissions: `groups` should include `audio`

### Database Issues
1. Check logs: `docker-compose logs postgres`
2. Connect directly: `make db-shell`
3. Reset database: `docker-compose down -v` (WARNING: Deletes data)

### Performance Issues
1. Check resource usage: `docker stats`
2. Increase memory limits in docker-compose.yml
3. Use production build: `make prod`

### Network Issues
1. Check nginx logs: `docker-compose logs nginx`
2. Verify backend health: `curl http://localhost:9050/api/status`
3. Check CORS settings in backend

## Backup and Restore

### Automatic Backups (Production)
The production stack includes automated daily backups:
- Location: `./backups/`
- Retention: 7 days
- Includes: Database, recordings, settings

### Manual Backup
```bash
# Database
make db-backup

# Full backup
tar -czf backup-$(date +%Y%m%d).tar.gz data/ recordings/
```

### Restore
```bash
# Stop services
make down

# Restore files
tar -xzf backup-20240118.tar.gz

# Start services
make up
```

## Scaling

For high-load scenarios:
1. Use PostgreSQL instead of SQLite
2. Add Redis for caching
3. Scale backend with multiple workers
4. Use external audio processing service
5. Implement load balancing

## Security Considerations

1. Change default passwords in `.env`
2. Use strong SECRET_KEY
3. Enable HTTPS in production
4. Restrict CORS origins
5. Implement rate limiting
6. Regular security updates
7. Monitor access logs