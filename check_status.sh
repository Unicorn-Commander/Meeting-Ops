#!/bin/bash
# Quick status check for Meeting-Ops

echo "=== Meeting-Ops Status Check ==="
echo ""

# Check what's running
echo "1. Process Status:"
if pgrep -f "uvicorn.*9050" > /dev/null; then
    echo "✓ Backend is running (PID: $(pgrep -f 'uvicorn.*9050'))"
else
    echo "✗ Backend is NOT running"
fi

if pgrep -f "vite|npm.*dev" > /dev/null; then
    echo "✓ Frontend is running (PID: $(pgrep -f 'vite|npm.*dev'))"
else
    echo "✗ Frontend is NOT running"
fi

# Check ports
echo ""
echo "2. Port Status:"
ss -tlnp 2>/dev/null | grep -E ":7777|:9050|:80" || echo "No services listening"

# Check systemd services
echo ""
echo "3. Systemd Services:"
systemctl is-active meeting-ops-backend >/dev/null 2>&1 && echo "✓ Backend service active" || echo "✗ Backend service not active"
systemctl is-active meeting-ops-frontend >/dev/null 2>&1 && echo "✓ Frontend service active" || echo "✗ Frontend service not active"

# Network info
echo ""
echo "4. Network Info:"
echo "Your IP: $(hostname -I | awk '{print $1}')"

# Quick start if nothing running
echo ""
if ! pgrep -f "uvicorn.*9050" > /dev/null; then
    echo "To start services:"
    echo "  sudo systemctl start meeting-ops-backend meeting-ops-frontend"
    echo "  OR"
    echo "  ./COMPLETE_SETUP.sh"
fi