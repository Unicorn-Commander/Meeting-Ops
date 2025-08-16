#!/bin/bash

# Install ROCm for AMD 780M iGPU acceleration
# Ubuntu 25.04 + AMD 8945HS support

set -e

echo "🎯 Installing ROCm for AMD Radeon 780M iGPU"
echo "📊 Target: 16GB VRAM acceleration for Granite 3.3 8B"

# Add ROCm repository
wget -q -O - https://repo.radeon.com/rocm/rocm.gpg.key | sudo apt-key add -
echo 'deb [arch=amd64] https://repo.radeon.com/rocm/apt/5.7/ jammy main' | sudo tee /etc/apt/sources.list.d/rocm.list

# Update package list
sudo apt update

# Install ROCm packages for iGPU
sudo apt install -y \
    rocm-dev \
    hip-dev \
    rocm-libs \
    rocm-cmake \
    rocminfo \
    rocm-clang-ocl

# Add user to render group for iGPU access
sudo usermod -a -G render,video $USER

# Set environment variables
echo "export PATH=/opt/rocm/bin:\$PATH" >> ~/.bashrc
echo "export LD_LIBRARY_PATH=/opt/rocm/lib:\$LD_LIBRARY_PATH" >> ~/.bashrc
echo "export HSA_OVERRIDE_GFX_VERSION=11.0.0" >> ~/.bashrc

echo "✅ ROCm installed! Reboot required to activate iGPU acceleration."
echo "🔄 After reboot: rebuild llama.cpp with -DGGML_ROCM=ON"