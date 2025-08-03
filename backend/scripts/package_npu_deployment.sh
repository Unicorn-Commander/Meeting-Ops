#!/bin/bash
# Package NPU deployment for identical hardware systems

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")"
PACKAGE_NAME="meeting-ops-npu-deployment-$(date +%Y%m%d).tar.gz"

cd "$BACKEND_DIR"

echo "📦 Creating NPU deployment package..."

# Create package with all NPU-related files
tar -czf "$PACKAGE_NAME" \
    models/whisper-base-onnx/ \
    whisperx_npu.bin \
    npu_optimization/ \
    scripts/setup_npu.sh \
    scripts/verify_npu.sh \
    scripts/package_npu_deployment.sh \
    NPU_SETUP_GUIDE.md \
    NPU_*.md \
    --exclude="*.pyc" \
    --exclude="__pycache__"

echo "✅ Created deployment package: $PACKAGE_NAME"
echo ""
echo "To deploy on identical hardware:"
echo "1. Copy $PACKAGE_NAME to target system"
echo "2. Extract: tar -xzf $PACKAGE_NAME"
echo "3. Run: ./scripts/setup_npu.sh"
echo "4. Verify: ./scripts/verify_npu.sh"