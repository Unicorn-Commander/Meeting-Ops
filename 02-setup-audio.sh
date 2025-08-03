#!/bin/bash
# Meeting-Ops Hardware Appliance Setup - Step 2: Audio Configuration
# Run this after logging back in from Step 1

set -e

echo "=================================================="
echo "Meeting-Ops Hardware Appliance Setup - Step 2"
echo "Audio Device Configuration"
echo "=================================================="
echo

# Check if Docker works without sudo
if ! docker --version &>/dev/null; then
    echo "❌ ERROR: Cannot run Docker without sudo."
    echo "Did you log out and log back in after running 01-install-docker.sh?"
    exit 1
fi

echo "✅ Docker access verified"
echo

# Install audio packages
echo "→ Installing audio packages..."
sudo apt-get update
sudo apt-get install -y \
    alsa-utils \
    pulseaudio \
    pulseaudio-utils \
    libasound2-dev \
    portaudio19-dev

# Add user to audio and render groups
echo "→ Adding user '$USER' to audio group..."
sudo usermod -aG audio $USER

echo "→ Adding user '$USER' to render group (for NPU access)..."
sudo usermod -aG render $USER

# Check USB audio devices
echo "→ Checking for USB audio devices..."
echo
if [ -e /proc/asound/cards ]; then
    echo "Sound cards detected:"
    cat /proc/asound/cards
    echo
fi

# List audio devices
echo "→ Listing audio capture devices:"
arecord -l || echo "No recording devices found"
echo

# Check device permissions
echo "→ Checking audio device permissions:"
ls -la /dev/snd/ 2>/dev/null || echo "No sound devices found"
echo

# Create audio test script
cat > check-audio.sh << 'EOF'
#!/bin/bash
echo "Audio Device Check"
echo "=================="
echo
echo "1. Sound Cards:"
cat /proc/asound/cards 2>/dev/null || echo "No cards file"
echo
echo "2. Recording Devices:"
arecord -l 2>/dev/null || echo "No recording devices"
echo
echo "3. Device Permissions:"
ls -la /dev/snd/ 2>/dev/null || echo "No /dev/snd directory"
echo
echo "4. Current User Groups:"
groups
echo
echo "5. USB Devices:"
lsusb | grep -i audio || echo "No USB audio devices detected"
EOF

chmod +x check-audio.sh

echo "=================================================="
echo "✅ Audio Setup Complete!"
echo "=================================================="
echo
echo "IMPORTANT: You need to log out and log back in for audio group changes to take effect!"
echo
echo "After logging back in:"
echo "1. Run: ./check-audio.sh to verify audio setup"
echo "2. Then run: ./03-install-dependencies.sh"
echo
echo "If you see 'Permission denied' errors for audio devices,"
echo "you'll need to log out and back in first."
echo