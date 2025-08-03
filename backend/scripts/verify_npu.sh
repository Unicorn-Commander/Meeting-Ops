#!/bin/bash
# NPU Verification Script
# Checks if NPU is properly configured and ready for use

# Don't exit on error for individual checks
set +e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=== NPU Verification Tool ===${NC}"
echo ""

# Function to check with visual feedback
check() {
    local description="$1"
    local command="$2"
    
    printf "%-50s" "$description"
    
    if eval "$command" 2>/dev/null; then
        echo -e "${GREEN}[PASS]${NC}"
        return 0
    else
        echo -e "${RED}[FAIL]${NC}"
        return 1
    fi
}

# Track overall status
CHECKS_PASSED=0
TOTAL_CHECKS=0

# 1. Hardware checks
echo -e "${BLUE}Hardware Checks:${NC}"

((TOTAL_CHECKS++))
if check "NPU device exists (/dev/accel/accel0)" "[ -e /dev/accel/accel0 ]"; then
    ((CHECKS_PASSED++))
fi

((TOTAL_CHECKS++))
if check "NPU device readable" "[ -r /dev/accel/accel0 ]"; then
    ((CHECKS_PASSED++))
fi

((TOTAL_CHECKS++))
if check "NPU device writable" "[ -w /dev/accel/accel0 ]"; then
    ((CHECKS_PASSED++))
fi

((TOTAL_CHECKS++))
if check "User in render group" "groups | grep -q render"; then
    ((CHECKS_PASSED++))
fi

((TOTAL_CHECKS++))
if check "amdxdna kernel module loaded" "lsmod | grep -q amdxdna"; then
    ((CHECKS_PASSED++))
fi

# 2. Model checks
echo ""
echo -e "${BLUE}Model Checks:${NC}"

((TOTAL_CHECKS++))
if check "Whisper encoder model" "[ -f $BACKEND_DIR/models/whisper-base-onnx/onnx/encoder_model.onnx ]"; then
    ((CHECKS_PASSED++))
    # Check size
    size=$(stat -c%s "$BACKEND_DIR/models/whisper-base-onnx/onnx/encoder_model.onnx" 2>/dev/null || echo 0)
    echo "  └─ Size: $(( size / 1024 / 1024 )) MB"
fi

((TOTAL_CHECKS++))
if check "Whisper decoder model" "[ -f $BACKEND_DIR/models/whisper-base-onnx/onnx/decoder_model.onnx ]"; then
    ((CHECKS_PASSED++))
    # Check size
    size=$(stat -c%s "$BACKEND_DIR/models/whisper-base-onnx/onnx/decoder_model.onnx" 2>/dev/null || echo 0)
    echo "  └─ Size: $(( size / 1024 / 1024 )) MB"
fi

# 3. NPU kernel checks
echo ""
echo -e "${BLUE}NPU Kernel Checks:${NC}"

((TOTAL_CHECKS++))
if check "NPU binary (whisperx_npu.bin)" "[ -f $BACKEND_DIR/whisperx_npu.bin ]"; then
    ((CHECKS_PASSED++))
    size=$(stat -c%s "$BACKEND_DIR/whisperx_npu.bin" 2>/dev/null || echo 0)
    echo "  └─ Size: $size bytes"
fi

((TOTAL_CHECKS++))
if check "MLIR kernels" "[ -f $BACKEND_DIR/npu_optimization/mlir_aie2_kernels.mlir ]"; then
    ((CHECKS_PASSED++))
fi

((TOTAL_CHECKS++))
if check "NPU machine code generator" "[ -f $BACKEND_DIR/npu_optimization/npu_machine_code.py ]"; then
    ((CHECKS_PASSED++))
fi

((TOTAL_CHECKS++))
if check "NPU integration module" "[ -f $BACKEND_DIR/npu_optimization/whisperx_npu_integration.py ]"; then
    ((CHECKS_PASSED++))
fi

# 4. Python NPU test
echo ""
echo -e "${BLUE}Python NPU Test:${NC}"

cd "$BACKEND_DIR"

# Create test script
cat > test_npu_access.py << 'EOF'
#!/usr/bin/env python3
import os
import struct
import fcntl

try:
    # Try to open NPU device
    fd = os.open("/dev/accel/accel0", os.O_RDWR)
    
    # Try to query AIE version
    DRM_IOCTL_AMDXDNA_GET_INFO = 0xC0106447
    buffer = bytearray(8)
    import ctypes
    buffer_ptr = ctypes.addressof(ctypes.c_char.from_buffer(buffer))
    query_data = struct.pack('IIQ', 2, 8, buffer_ptr)
    
    fcntl.ioctl(fd, DRM_IOCTL_AMDXDNA_GET_INFO, query_data)
    major, minor = struct.unpack('II', buffer)
    
    os.close(fd)
    
    print(f"✅ NPU access successful - AIE version {major}.{minor}")
    exit(0)
    
except Exception as e:
    print(f"❌ NPU access failed: {e}")
    exit(1)
EOF

((TOTAL_CHECKS++))
if python3 test_npu_access.py 2>&1; then
    ((CHECKS_PASSED++))
else
    echo "  └─ Note: This may require logout/login if user was just added to render group"
fi

rm -f test_npu_access.py

# 5. Service integration check
echo ""
echo -e "${BLUE}Service Integration:${NC}"

# Check if backend is using NPU
if [ -f "$BACKEND_DIR/venv/bin/python" ]; then
    ((TOTAL_CHECKS++))
    if check "Backend venv exists" "[ -f $BACKEND_DIR/venv/bin/python ]"; then
        ((CHECKS_PASSED++))
    fi
fi

# Summary
echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Summary:${NC}"
echo -e "${BLUE}========================================${NC}"

if [ $CHECKS_PASSED -eq $TOTAL_CHECKS ]; then
    echo -e "${GREEN}✅ All checks passed! ($CHECKS_PASSED/$TOTAL_CHECKS)${NC}"
    echo -e "${GREEN}NPU is ready for hardware-accelerated transcription.${NC}"
    exit 0
else
    echo -e "${YELLOW}⚠️  Some checks failed ($CHECKS_PASSED/$TOTAL_CHECKS)${NC}"
    
    if ! groups | grep -q render; then
        echo ""
        echo -e "${YELLOW}Action Required:${NC}"
        echo "1. Add user to render group: sudo usermod -a -G render $USER"
        echo "2. Logout and login again"
        echo "3. Run this verification again"
    fi
    
    if [ ! -f "$BACKEND_DIR/whisperx_npu.bin" ]; then
        echo ""
        echo -e "${YELLOW}NPU binary missing:${NC}"
        echo "Run: cd $BACKEND_DIR && ./scripts/setup_npu.sh"
    fi
    
    exit 1
fi