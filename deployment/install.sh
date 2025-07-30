#!/bin/bash
#
# Meeting-Ops Installation Script
# Part of the Unicorn Commander Suite
#

set -e

INSTALL_DIR="/opt/meeting-ops"
SERVICE_USER="meeting-ops"
SERVICE_GROUP="meeting-ops"
DATA_DIR="/var/lib/meeting-ops"
LOG_DIR="/var/log/meeting-ops"

echo "======================================"
echo "Meeting-Ops Installation"
echo "Part of Unicorn Commander Suite"
echo "======================================"
echo

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "Please run as root (use sudo)"
    exit 1
fi

# Check for NPU device
if [ ! -e "/dev/accel/accel0" ]; then
    echo "WARNING: NPU device not found at /dev/accel/accel0"
    echo "Meeting-Ops requires NPU hardware for operation"
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo "1. Creating service user..."
if ! id "$SERVICE_USER" &>/dev/null; then
    useradd --system --home-dir "$DATA_DIR" --shell /bin/false "$SERVICE_USER"
    echo "   Created user: $SERVICE_USER"
else
    echo "   User $SERVICE_USER already exists"
fi

# Add user to necessary groups
usermod -a -G render,video,audio "$SERVICE_USER" 2>/dev/null || true

echo "2. Creating directories..."
mkdir -p "$INSTALL_DIR"
mkdir -p "$DATA_DIR"/{recordings,exports,sessions}
mkdir -p "$LOG_DIR"

echo "3. Copying application files..."
cp -r ../backend/* "$INSTALL_DIR/"

echo "4. Setting up Python virtual environment..."
cd "$INSTALL_DIR"
python3 -m venv venv
source venv/bin/activate

echo "5. Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Install optional dependencies
echo "6. Installing optional dependencies..."
pip install reportlab  # For PDF export
pip install tokenizers # For Whisper tokenization

echo "7. Setting permissions..."
chown -R "$SERVICE_USER:$SERVICE_GROUP" "$INSTALL_DIR"
chown -R "$SERVICE_USER:$SERVICE_GROUP" "$DATA_DIR"
chown -R "$SERVICE_USER:$SERVICE_GROUP" "$LOG_DIR"

# NPU device permissions
if [ -e "/dev/accel/accel0" ]; then
    echo "8. Configuring NPU access..."
    # Create udev rule for NPU device
    cat > /etc/udev/rules.d/99-meeting-ops-npu.rules <<EOF
# Meeting-Ops NPU access
KERNEL=="accel*", SUBSYSTEM=="accel", MODE="0666", GROUP="render"
EOF
    udevadm control --reload-rules
    udevadm trigger
fi

echo "9. Installing systemd service..."
cp meeting-ops.service /etc/systemd/system/
systemctl daemon-reload

echo "10. Creating initial configuration..."
cat > "$DATA_DIR/settings.json" <<EOF
{
    "device_name": "Meeting-Ops Appliance",
    "organization": "Your Organization",
    "audio": {
        "device": "default",
        "sample_rate": 16000,
        "channels": 1
    },
    "ai": {
        "whisper_model": "npu-runtime",
        "enable_diarization": true,
        "ollama_url": "http://localhost:11434"
    }
}
EOF

chown "$SERVICE_USER:$SERVICE_GROUP" "$DATA_DIR/settings.json"

echo "11. Migrating existing data..."
if [ -d "/tmp/recordings" ]; then
    echo "   Found existing recordings, migrating..."
    cp -r /tmp/recordings/* "$DATA_DIR/recordings/" 2>/dev/null || true
    chown -R "$SERVICE_USER:$SERVICE_GROUP" "$DATA_DIR/recordings"
fi

echo
echo "======================================"
echo "Installation Complete!"
echo "======================================"
echo
echo "Next steps:"
echo "1. Start the service: sudo systemctl start meeting-ops"
echo "2. Enable auto-start: sudo systemctl enable meeting-ops"
echo "3. Check status: sudo systemctl status meeting-ops"
echo "4. View logs: sudo journalctl -u meeting-ops -f"
echo
echo "Web interface will be available at:"
echo "  http://localhost:9050"
echo
echo "Default admin credentials:"
echo "  Username: admin"
echo "  Password: changeme123!"
echo
echo "Part of the Unicorn Commander Suite"
echo "======================================"