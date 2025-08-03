#!/bin/bash
# NPU Setup Script for AMD Phoenix NPU
# Part of Meeting-Ops Installation Chain
# Hardware: AMD Ryzen AI (Phoenix) NPU - 16 TOPS INT8

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")"
LOG_FILE="${BACKEND_DIR}/logs/npu_setup.log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Create logs directory
mkdir -p "${BACKEND_DIR}/logs"

# Logging function
log() {
    echo -e "$1" | tee -a "$LOG_FILE"
}

log_error() {
    echo -e "${RED}❌ $1${NC}" | tee -a "$LOG_FILE"
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}" | tee -a "$LOG_FILE"
}

log_info() {
    echo -e "${BLUE}ℹ️  $1${NC}" | tee -a "$LOG_FILE"
}

log_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}" | tee -a "$LOG_FILE"
}

# Start setup
log "=========================================="
log "🚀 NPU Setup for Meeting-Ops"
log "   Date: $(date)"
log "   System: $(uname -a)"
log "=========================================="

# 1. Check system requirements
log_info "Checking system requirements..."

# Check for AMD NPU device
if [ ! -e "/dev/accel/accel0" ]; then
    log_error "NPU device not found at /dev/accel/accel0"
    log_error "This system may not have an AMD Phoenix NPU"
    exit 1
else
    log_success "NPU device found: /dev/accel/accel0"
fi

# Check kernel version (need 6.14+)
KERNEL_VERSION=$(uname -r | cut -d. -f1,2)
KERNEL_MAJOR=$(echo $KERNEL_VERSION | cut -d. -f1)
KERNEL_MINOR=$(echo $KERNEL_VERSION | cut -d. -f2)

if [ "$KERNEL_MAJOR" -lt 6 ] || ([ "$KERNEL_MAJOR" -eq 6 ] && [ "$KERNEL_MINOR" -lt 14 ]); then
    log_warning "Kernel version $KERNEL_VERSION is older than 6.14"
    log_warning "NPU driver (amdxdna) may not be available"
else
    log_success "Kernel version $KERNEL_VERSION supports NPU"
fi

# Check if amdxdna module is loaded
if lsmod | grep -q amdxdna; then
    log_success "amdxdna kernel module is loaded"
else
    log_warning "amdxdna kernel module not loaded"
    log_info "Attempting to load module..."
    if sudo modprobe amdxdna 2>/dev/null; then
        log_success "amdxdna module loaded successfully"
    else
        log_warning "Could not load amdxdna module"
    fi
fi

# 2. Setup user permissions
log_info "Setting up user permissions..."

# Check if user is in render group
if groups $USER | grep -q "\brender\b"; then
    log_success "User $USER is already in render group"
else
    log_warning "User $USER is not in render group"
    log_info "Adding user to render group..."
    sudo usermod -a -G render $USER
    log_success "User added to render group"
    log_warning "You need to logout and login for group changes to take effect!"
    NEED_RELOGIN=1
fi

# 3. Check NPU device permissions
if [ -r "/dev/accel/accel0" ] && [ -w "/dev/accel/accel0" ]; then
    log_success "NPU device is accessible"
else
    log_warning "NPU device is not accessible"
    # Check device permissions
    ls -la /dev/accel/accel0 | tee -a "$LOG_FILE"
fi

# 4. Download and setup Whisper ONNX models
log_info "Setting up Whisper ONNX models..."

cd "$BACKEND_DIR"

# Check if models already exist
if [ -f "models/whisper-base-onnx/onnx/encoder_model.onnx" ] && [ -f "models/whisper-base-onnx/onnx/decoder_model.onnx" ]; then
    log_success "Whisper ONNX models already downloaded"
else
    log_info "Downloading Whisper ONNX models..."
    
    # Create model directory
    mkdir -p models/whisper-base-onnx/onnx
    
    # Download from Hugging Face
    BASE_URL="https://huggingface.co/onnx-community/whisper-base/resolve/main/onnx"
    
    log_info "Downloading encoder model..."
    if wget -q --show-progress "$BASE_URL/encoder_model.onnx" -O "models/whisper-base-onnx/onnx/encoder_model.onnx"; then
        log_success "Encoder model downloaded"
    else
        log_error "Failed to download encoder model"
        exit 1
    fi
    
    log_info "Downloading decoder model..."
    if wget -q --show-progress "$BASE_URL/decoder_model.onnx" -O "models/whisper-base-onnx/onnx/decoder_model.onnx"; then
        log_success "Decoder model downloaded"
    else
        log_error "Failed to download decoder model"
        exit 1
    fi
fi

# 5. Generate NPU machine code
log_info "Generating NPU machine code..."

cd "$BACKEND_DIR"

# Create Python script to generate NPU binary
cat > generate_npu_binary.py << 'EOF'
#!/usr/bin/env python3
import sys
sys.path.append('.')
from npu_optimization.npu_machine_code import NPUMachineCodeGenerator

try:
    gen = NPUMachineCodeGenerator()
    machine_code = gen.generate_full_whisperx_binary()
    with open("whisperx_npu.bin", "wb") as f:
        f.write(machine_code)
    print("✅ Generated NPU binary: whisperx_npu.bin")
    print(f"   Size: {len(machine_code)} bytes")
except Exception as e:
    print(f"❌ Failed to generate NPU binary: {e}")
    sys.exit(1)
EOF

# Run with venv Python
if [ -f "venv/bin/python" ]; then
    log_info "Using venv Python to generate NPU binary..."
    if ./venv/bin/python generate_npu_binary.py 2>&1 | tee -a "$LOG_FILE"; then
        log_success "NPU binary generated successfully"
    else
        log_warning "NPU binary generation failed (may need dependencies)"
    fi
else
    log_warning "Python venv not found, skipping NPU binary generation"
fi

# Clean up
rm -f generate_npu_binary.py

# 6. Verify NPU setup
log_info "Verifying NPU setup..."

# Create verification script
cat > verify_npu.py << 'EOF'
#!/usr/bin/env python3
import os
import sys

print("=== NPU Setup Verification ===")
checks_passed = 0
total_checks = 0

# Check 1: NPU device
total_checks += 1
if os.path.exists("/dev/accel/accel0"):
    print("✅ NPU device found")
    checks_passed += 1
else:
    print("❌ NPU device not found")

# Check 2: Device permissions
total_checks += 1
if os.access("/dev/accel/accel0", os.R_OK | os.W_OK):
    print("✅ NPU device accessible")
    checks_passed += 1
else:
    print("❌ NPU device not accessible (check permissions)")

# Check 3: ONNX models
total_checks += 1
encoder_path = "models/whisper-base-onnx/onnx/encoder_model.onnx"
decoder_path = "models/whisper-base-onnx/onnx/decoder_model.onnx"
if os.path.exists(encoder_path) and os.path.exists(decoder_path):
    print("✅ Whisper ONNX models found")
    checks_passed += 1
else:
    print("❌ Whisper ONNX models missing")

# Check 4: NPU binary
total_checks += 1
if os.path.exists("whisperx_npu.bin"):
    size = os.path.getsize("whisperx_npu.bin")
    print(f"✅ NPU binary found ({size} bytes)")
    checks_passed += 1
else:
    print("❌ NPU binary not found")

# Check 5: NPU kernel files
total_checks += 1
kernel_files = [
    "npu_optimization/mlir_aie2_kernels.mlir",
    "npu_optimization/aie2_kernel_driver.py",
    "npu_optimization/npu_machine_code.py",
    "npu_optimization/whisperx_npu_integration.py"
]
all_found = all(os.path.exists(f) for f in kernel_files)
if all_found:
    print("✅ All NPU kernel files present")
    checks_passed += 1
else:
    print("❌ Some NPU kernel files missing")

print(f"\nResult: {checks_passed}/{total_checks} checks passed")
sys.exit(0 if checks_passed == total_checks else 1)
EOF

# Run verification
if python3 verify_npu.py 2>&1 | tee -a "$LOG_FILE"; then
    log_success "NPU verification passed"
else
    log_warning "Some NPU checks failed"
fi

# Clean up
rm -f verify_npu.py

# 7. Install optional AMD tools (if available)
log_info "Checking for optional AMD tools..."

# Check for XRT
if command -v xbutil &> /dev/null; then
    log_success "AMD XRT tools found"
    xbutil examine 2>&1 | grep -i npu | tee -a "$LOG_FILE" || true
else
    log_info "AMD XRT tools not found (optional)"
    log_info "To install: https://github.com/Xilinx/XRT/releases"
fi

# 8. Summary
log ""
log "=========================================="
log "📊 NPU Setup Summary"
log "=========================================="

if [ -e "/dev/accel/accel0" ] && [ -r "/dev/accel/accel0" ]; then
    log_success "NPU hardware: Ready"
else
    log_warning "NPU hardware: Not accessible"
fi

if [ -f "models/whisper-base-onnx/onnx/encoder_model.onnx" ]; then
    log_success "ONNX models: Downloaded"
else
    log_warning "ONNX models: Missing"
fi

if [ -f "whisperx_npu.bin" ]; then
    log_success "NPU binary: Generated"
else
    log_warning "NPU binary: Not generated"
fi

if [ -n "$NEED_RELOGIN" ]; then
    log ""
    log_warning "IMPORTANT: You need to logout and login for render group membership to take effect!"
    log_warning "After relogin, run this script again to complete setup."
fi

log ""
log_success "NPU setup complete!"
log "Logs saved to: $LOG_FILE"