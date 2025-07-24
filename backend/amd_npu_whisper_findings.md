# AMD Ryzen AI NPU Whisper Support - Research Findings

## Current Situation

1. **Hardware**: You have AMD Ryzen 9 8945HS with RyzenAI-npu1 (16 TOPS INT8)
2. **Kernel Driver**: `amdxdna` driver is loaded and working
3. **Device**: `/dev/accel/accel0` is accessible
4. **XRT**: Installed but doesn't detect the NPU device

## Key Findings from Research

### 1. Official AMD Support
- AMD **has plans** to add Whisper support but it's not available yet (as of April 2025)
- Early Access examples exist but require special access from AMD
- The AMD RyzenAI-SW repository doesn't contain public Whisper examples

### 2. Community Projects
- **Hackster.io Ryzen AI Subtitling** project exists - someone got Whisper working
- They initially ran it without NPU, then optimized for NPU
- Used existing Whisper codebase as starting point

### 3. Technical Requirements
For NPU acceleration, you need:
- **onnxruntime-vitisai**: Special ONNX Runtime with Vitis AI Execution Provider
- **Quantized models**: INT8/INT4 quantized Whisper models
- **Proper environment setup**: Specific environment variables and configuration

### 4. Why XRT Doesn't Work
- The `amdxdna` kernel driver uses Linux DRM/accel framework
- XRT expects devices in a different format (like /dev/xrt*)
- This is a known issue - Ryzen AI NPUs need different tools than Xilinx FPGAs

## Possible Solutions

### Option 1: Get onnxruntime-vitisai (Recommended)
```bash
# This is what's needed (but not publicly available)
pip install onnxruntime-vitisai
```
This special version has the Vitis AI Execution Provider that can talk to the NPU.

### Option 2: Direct Kernel Access
Use the IOCTLs from `/usr/include/drm/amdxdna_accel.h` to:
1. Create hardware context
2. Allocate buffers
3. Load and execute kernels

### Option 3: Wait for Official Support
AMD is actively developing Ryzen AI SDK. The Early Access program has Whisper examples.

## Why Vitis Installer Failed
- Vitis 2024.x/2025.x are for Xilinx FPGAs, not Ryzen AI NPUs
- The NPU uses a different architecture (XDNA vs FPGA)
- You need AMD's Ryzen AI specific tools, not generic Vitis

## What Actually Works
People have successfully run Whisper on Ryzen AI NPUs using:
1. Ryzen AI Software 1.2 (older version)
2. onnxruntime-vitisai (special build)
3. Quantized Whisper models
4. Proper environment setup

## Next Steps
1. Try to get access to AMD's Early Access program
2. Look for onnxruntime-vitisai wheel files
3. Contact AMD developer support for NPU examples
4. Check if someone has shared the Hackster.io project code

The hardware is there and capable - we just need the right software stack!