# Installing Unicorn Commander on Port 7777

This guide explains how to run Unicorn Commander on the extra special magical port 7777.

## Prerequisites

- Ubuntu/Debian Linux system
- Python 3.12+ installed
- Root/sudo access (required for port 80)

## Option 1: Quick Start (Development)

```bash
# Navigate to backend directory
cd /home/ucadmin/Development/Unicorn-Commander-Meeting-Ops/backend

# Run the port 7777 script
./run-port7777.sh
```

The application will be available at: http://localhost:7777/

## Option 2: Systemd Service (Production)

### 1. Install the systemd service

```bash
# Copy service file to systemd directory
sudo cp unicorn-commander.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable the service to start on boot
sudo systemctl enable unicorn-commander

# Start the service
sudo systemctl start unicorn-commander
```

### 2. Check service status

```bash
# Check if service is running
sudo systemctl status unicorn-commander

# View logs
sudo journalctl -u unicorn-commander -f
```

### 3. Service management

```bash
# Stop the service
sudo systemctl stop unicorn-commander

# Restart the service
sudo systemctl restart unicorn-commander

# Disable auto-start on boot
sudo systemctl disable unicorn-commander
```

## Option 3: Docker Deployment

### 1. Build and run with Docker Compose

```bash
# Navigate to project root
cd /home/ucadmin/Development/Unicorn-Commander-Meeting-Ops

# Build and start services
sudo docker-compose up -d

# Check status
sudo docker-compose ps

# View logs
sudo docker-compose logs -f
```

The application will be available at: http://localhost:7777/

### 2. Docker management

```bash
# Stop services
sudo docker-compose down

# Rebuild and restart
sudo docker-compose up -d --build

# View specific service logs
sudo docker-compose logs backend
sudo docker-compose logs frontend
```

## Port 7777 Considerations

### Why Port 7777 is Special

Port 7777 is an unprivileged port that doesn't require root access and is commonly unused by system services.

### Benefits of Port 7777

#### No Root Access Required
Port 7777 is above 1024, so it doesn't require privileged access like port 80.

#### Unlikely Conflicts
Port 7777 is rarely used by system services, making conflicts unlikely.

#### Easy to Remember
The "lucky sevens" make it memorable while being functional.

## Troubleshooting

### Port 7777 Already in Use

Check what's using port 7777:
```bash
sudo lsof -i :7777
sudo ss -tlnp | grep :7777
```

If something is using port 7777 (unlikely), stop that service or choose another port.

### Permission Denied

Port 7777 shouldn't require special permissions, but if you encounter issues:
```bash
./run-port7777.sh
# or
systemctl start unicorn-commander
```

### Service Won't Start

Check the logs:
```bash
sudo journalctl -u unicorn-commander -f
```

Common issues:
- Virtual environment not found
- Python dependencies missing
- Database permissions
- Port already in use

### Virtual Environment Issues

Recreate the virtual environment:
```bash
rm -rf venv
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Security Notes

- Running web applications as root has security implications
- Consider using a reverse proxy (nginx/apache) for production
- Ensure firewall is properly configured
- Use HTTPS in production (port 443)
- Regularly update dependencies and system packages

## Network Configuration

The application is configured to:
- Listen on all interfaces (0.0.0.0)
- Accept connections on port 7777
- Handle both HTTP and WebSocket connections
- Support the new admin panel and user interface

Access the application:
- **User Interface**: http://localhost:7777/
- **Admin Panel**: http://localhost:7777/admin
- **Legacy Interface**: http://localhost:7777/legacy
- **API Documentation**: http://localhost:7777/docs