# Meeting-Ops Hardware Appliance Installation Guide

This guide will walk you through setting up Meeting-Ops on a fresh Ubuntu Server 25.04 system.

## Prerequisites

- Ubuntu Server 25.04 (or compatible)
- Internet connection
- USB microphone connected
- AMD NPU hardware (optional but recommended)
- At least 8GB RAM
- 20GB free disk space

## Installation Steps

The installation is broken into numbered scripts that must be run in order. Some steps require logging out and back in due to group permission changes.

### Step 1: Install Docker

```bash
./01-install-docker.sh
```

This script will:
- Update system packages
- Install Docker Engine and Docker Compose
- Add your user to the `docker` group

**IMPORTANT**: After this script completes, you MUST log out and log back in for the group changes to take effect.

### Step 2: Configure Audio

```bash
./02-setup-audio.sh
```

This script will:
- Install audio packages (ALSA, PulseAudio)
- Add your user to the `audio` group
- Check for USB audio devices
- Create an audio check utility

**IMPORTANT**: After this script completes, you MUST log out and log back in for the audio group changes to take effect.

After logging back in, verify audio setup:
```bash
./check-audio.sh
```

### Step 3: Install Dependencies

```bash
./03-install-dependencies.sh
```

This script will:
- Install Python 3 and development tools
- Install Node.js 20.x
- Create Python virtual environment
- Install Python packages (FastAPI, WhisperX, etc.)
- Install frontend dependencies
- Create configuration files

### Step 4: Setup Services

```bash
./04-setup-services.sh
```

This script will:
- Start PostgreSQL, Redis, and Qdrant in Docker
- Initialize the database schema
- Create systemd service files
- Set up the production backend

### Step 5: Start Everything

```bash
./05-start-stack.sh
```

This script will:
- Start all Docker services
- Start the backend API (port 9050)
- Start the frontend UI (port 7777)
- Show access information

## Accessing Meeting-Ops

After installation, you can access Meeting-Ops at:

- **Frontend UI**: http://localhost:7777 (or http://[your-ip]:7777)
- **Backend API**: http://localhost:9050
- **API Documentation**: http://localhost:9050/docs

Default credentials:
- Username: `admin`
- Password: `admin`

## Managing the Stack

### Stop Everything
```bash
./stop-stack.sh
```

### Enable Auto-start on Boot
```bash
./enable-autostart.sh
```

### Check Service Status
```bash
# Docker services
docker ps

# Backend logs
tail -f backend/backend.log

# Frontend logs
tail -f frontend/frontend.log
```

## Troubleshooting

### Docker Permission Issues
If you get "permission denied" errors with Docker:
1. Make sure you logged out and back in after running `01-install-docker.sh`
2. Verify you're in the docker group: `groups | grep docker`

### Audio Permission Issues
If audio devices show "permission denied":
1. Make sure you logged out and back in after running `02-setup-audio.sh`
2. Verify you're in the audio group: `groups | grep audio`
3. Check device permissions: `ls -la /dev/snd/`

### Port Already in Use
If ports 9050 or 7777 are already in use:
1. Find what's using the port: `sudo lsof -i :9050`
2. Stop the conflicting service or change Meeting-Ops ports in the configuration

### Services Not Starting
If Docker services fail to start:
1. Check Docker daemon: `sudo systemctl status docker`
2. Check container logs: `docker logs meetingops-postgres`
3. Ensure enough disk space: `df -h`

## Network Configuration

Meeting-Ops binds to all network interfaces (0.0.0.0) by default, making it accessible from other devices on your network.

For production use, consider:
1. Setting up a firewall (ufw or iptables)
2. Using a reverse proxy (nginx) with SSL
3. Restricting access to specific IP ranges

## Hardware Requirements

### Minimum
- 4 CPU cores
- 8GB RAM
- 20GB storage
- USB audio device

### Recommended
- 8+ CPU cores
- 16GB RAM
- 50GB SSD storage
- AMD NPU hardware (16 TOPS)
- Professional USB microphone

## Support

For issues or questions:
1. Check the logs in `backend/backend.log` and `frontend/frontend.log`
2. Review the troubleshooting section above
3. Check Docker service status: `docker compose -f docker-compose-services.yml ps`

## Next Steps

After installation:
1. Change the default admin password
2. Configure audio input settings
3. Test recording functionality
4. Set up email notifications (optional)
5. Configure WhisperX for transcription