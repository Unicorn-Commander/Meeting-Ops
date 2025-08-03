#!/bin/bash
# Setup hardware acceleration for Meeting-Ops

set -e

echo "=== Hardware Acceleration Setup ==="
echo ""

# Color codes
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Functions
print_status() {
    echo -e "${GREEN}[✓]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

print_error() {
    echo -e "${RED}[✗]${NC} $1"
}

# 1. Check NPU device
echo "1. Checking NPU device..."
if [ -e /dev/accel/accel0 ]; then
    print_status "NPU device found at /dev/accel/accel0"
    
    # Check permissions
    if [ -r /dev/accel/accel0 ] && [ -w /dev/accel/accel0 ]; then
        print_status "NPU device is accessible"
    else
        print_warning "NPU device not accessible"
        echo "   Fixing permissions..."
        sudo chmod 666 /dev/accel/accel0
        print_status "NPU permissions fixed"
    fi
else
    print_error "NPU device not found"
    echo "   Checking kernel module..."
    if lsmod | grep -q amdxdna; then
        print_status "amdxdna module loaded"
    else
        print_warning "amdxdna module not loaded"
        echo "   Loading module..."
        sudo modprobe amdxdna || print_error "Failed to load amdxdna module"
    fi
fi

# 2. Check for iGPU
echo ""
echo "2. Checking for AMD iGPU..."
if lspci | grep -i "vga.*amd\|display.*amd" > /dev/null; then
    print_status "AMD GPU detected"
    
    # Check for ROCm
    if command -v rocm-smi &> /dev/null; then
        print_status "ROCm installed"
    else
        print_warning "ROCm not installed"
        echo "   For iGPU acceleration, install ROCm:"
        echo "   https://rocm.docs.amd.com/en/latest/deploy/linux/quick_start.html"
    fi
else
    print_warning "No AMD GPU detected"
fi

# 3. Install Python packages for hardware acceleration
echo ""
echo "3. Installing Python packages..."

# Activate virtual environment if it exists
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
    print_status "Virtual environment activated"
fi

# Install packages
pip install --upgrade onnxruntime || print_error "Failed to install onnxruntime"

# Try to install ROCm support
pip install onnxruntime-rocm || print_warning "ROCm support not available"

# Try to install OpenVINO
pip install openvino || print_warning "OpenVINO not available"

print_status "Python packages installed"

# 4. Apply NPU fixes
echo ""
echo "4. Applying NPU integration fixes..."
if [ -f "fix_npu_integration.py" ]; then
    python fix_npu_integration.py
else
    print_error "fix_npu_integration.py not found"
fi

# 5. Download models if needed
echo ""
echo "5. Checking AI models..."
if [ ! -d "models/whisper-base-onnx" ]; then
    print_warning "Whisper models not found"
    echo "   Downloading models..."
    python download_models.py || print_error "Failed to download models"
else
    print_status "AI models found"
fi

# 6. Run hardware test
echo ""
echo "6. Testing hardware acceleration..."
if [ -f "test_npu_integration.py" ]; then
    python test_npu_integration.py
else
    # Quick inline test
    python3 << EOF
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Test NPU
if os.path.exists("/dev/accel/accel0"):
    if os.access("/dev/accel/accel0", os.R_OK | os.W_OK):
        logger.info("✅ NPU device accessible")
    else:
        logger.error("❌ NPU device not accessible")
else:
    logger.error("❌ NPU device not found")

# Test imports
try:
    from npu_runtime import NPURuntime
    logger.info("✅ NPU runtime importable")
except Exception as e:
    logger.error(f"❌ NPU runtime import failed: {e}")

try:
    from services.hardware_accelerated_transcription import get_hardware_transcription_service
    logger.info("✅ Hardware acceleration service importable")
except Exception as e:
    logger.error(f"❌ Hardware acceleration import failed: {e}")
EOF
fi

# Summary
echo ""
echo "=== Setup Complete ==="
echo ""
echo "Next steps:"
echo "1. If you were added to render group, log out and log back in"
echo "2. Start the backend: python main.py"
echo "3. Test transcription with real audio"
echo ""
echo "To verify NPU is working:"
echo "  python test_npu_access.py"
echo "  python test_npu_integration.py"
echo ""