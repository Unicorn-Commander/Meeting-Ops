#!/bin/bash
# Meeting-Ops Hardware Appliance Setup - Step 1: Docker Installation
# Run this script first, then log out and log back in before running the next script

set -e

echo "=================================================="
echo "Meeting-Ops Hardware Appliance Setup - Step 1"
echo "Docker Installation and User Configuration"
echo "=================================================="
echo

# Check if running as root
if [ "$EUID" -eq 0 ]; then 
   echo "Please run this script as a regular user (not root)"
   echo "The script will use sudo when needed"
   exit 1
fi

# Update system
echo "→ Updating system packages..."
sudo apt-get update
sudo apt-get upgrade -y

# Install prerequisites
echo "→ Installing prerequisites..."
sudo apt-get install -y \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    software-properties-common

# Add Docker's official GPG key
echo "→ Adding Docker GPG key..."
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

# Add Docker repository
echo "→ Adding Docker repository..."
echo \
  "deb [arch="$(dpkg --print-architecture)" signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  "$(. /etc/os-release && echo "$VERSION_CODENAME")" stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Update package index
echo "→ Updating package index..."
sudo apt-get update

# Install Docker Engine
echo "→ Installing Docker Engine, CLI, and Compose..."
sudo apt-get install -y \
    docker-ce \
    docker-ce-cli \
    containerd.io \
    docker-buildx-plugin \
    docker-compose-plugin

# Start and enable Docker
echo "→ Starting Docker service..."
sudo systemctl start docker
sudo systemctl enable docker

# Add current user to docker group
echo "→ Adding user '$USER' to docker group..."
sudo usermod -aG docker $USER

# Verify Docker installation
echo "→ Verifying Docker installation..."
sudo docker --version
sudo docker compose version

echo
echo "=================================================="
echo "✅ Docker Installation Complete!"
echo "=================================================="
echo
echo "IMPORTANT: You need to log out and log back in for group changes to take effect!"
echo
echo "After logging back in, run: ./02-setup-audio.sh"
echo
echo "To verify Docker works without sudo after re-login:"
echo "  docker run hello-world"
echo