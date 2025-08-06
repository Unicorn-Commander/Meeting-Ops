#\!/bin/bash

# Meeting-Ops Service Installation Script

set -e

echo "Meeting-Ops Service Installer"
echo "=============================="

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo "This script must be run as root (use sudo)" 
   exit 1
fi

# Variables
SERVICE_FILE="/etc/systemd/system/meeting-ops.service"
CURRENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$CURRENT_DIR")"

echo "Project directory: $PROJECT_DIR"

# Copy service file
echo "Installing systemd service..."
cp "$CURRENT_DIR/meeting-ops.service" "$SERVICE_FILE"

# Update paths in service file
sed -i "s|/home/ucadmin/Development/Meeting-Ops|$PROJECT_DIR|g" "$SERVICE_FILE"

# Reload systemd
echo "Reloading systemd daemon..."
systemctl daemon-reload

# Enable service
echo "Enabling Meeting-Ops service..."
systemctl enable meeting-ops.service

echo ""
echo "Installation complete\!"
echo ""
echo "To start the service:"
echo "  sudo systemctl start meeting-ops"
echo ""
echo "To check status:"
echo "  sudo systemctl status meeting-ops"
echo ""
echo "To view logs:"
echo "  sudo journalctl -u meeting-ops -f"
echo ""
echo "To stop the service:"
echo "  sudo systemctl stop meeting-ops"
