#!/bin/bash
# Enable Meeting-Ops to start automatically on boot

echo "Enabling Meeting-Ops autostart..."

# Enable Docker services
sudo systemctl enable docker

# Create startup service
sudo tee /etc/systemd/system/meetingops-stack.service > /dev/null << 'EOF'
[Unit]
Description=Meeting-Ops Complete Stack
After=docker.service network-online.target
Wants=network-online.target
Requires=docker.service

[Service]
Type=forking
User=ucadmin
WorkingDirectory=/home/ucadmin/Meeting-Ops
ExecStartPre=/bin/sleep 15
ExecStart=/home/ucadmin/Meeting-Ops/05-start-stack.sh
ExecStop=/home/ucadmin/Meeting-Ops/stop-stack.sh
Restart=on-failure
RestartSec=30

[Install]
WantedBy=multi-user.target
EOF

# Reload and enable
sudo systemctl daemon-reload
sudo systemctl enable meetingops-stack.service

echo "✅ Meeting-Ops will now start automatically on boot"
echo "To start now: sudo systemctl start meetingops-stack"
echo "To check status: sudo systemctl status meetingops-stack"