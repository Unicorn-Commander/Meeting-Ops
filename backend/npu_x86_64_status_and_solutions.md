# AMD NPU x86_64 Linux Status & Solutions

## 🎯 Current Situation

### What We Have ✅
- **Hardware**: AMD Ryzen 9 8945HS with NPU (16 TOPS INT8) - CONFIRMED WORKING
- **Kernel Driver**: `amdxdna` loaded and `/dev/accel/accel0` accessible
- **Architecture**: x86_64 Linux system
- **Downloaded**: onnxruntime-vitisai wheels (but ARM64 version)

### The Blocker ❌
- **No x86_64 Linux wheels** for onnxruntime-vitisai
- Only Windows AMD64 builds are officially available
- Linux support currently limited to ARM-based AMD Adaptable SoCs

## 📊 Solutions & Workarounds

### Option 1: Windows Virtual Machine or Dual Boot
**Pros**: Official support, guaranteed to work
**Cons**: Not native Linux
```bash
# Available wheel for Windows:
onnxruntime_vitisai-1.15.1-cp39-cp39-win_amd64.whl
```

### Option 2: Build from Source (Experimental)
Since the kernel driver works, we could try building the userspace components:

```bash
# Clone the xdna-driver (has userspace components)
git clone https://github.com/amd/xdna-driver.git
cd xdna-driver
git submodule update --init --recursive

# Install dependencies
./tools/amdxdna_deps.sh

# Build XRT plugins
# This might provide the missing userspace libraries
```

### Option 3: Docker Container Approach
Look for Vitis AI containers that might have x86_64 binaries:
```bash
# Check Docker Hub for Vitis AI containers
docker pull xilinx/vitis-ai:latest

# Run container with device passthrough
docker run --device=/dev/accel/accel0 -it xilinx/vitis-ai:latest
```

### Option 4: Contact AMD Directly
- Post on AMD Community forums
- Open issue on github.com/amd/RyzenAI-SW
- Request x86_64 Linux wheels

### Option 5: Use CPU/GPU Fallback (Temporary)
Continue using CPU emulation or switch to ROCm for GPU acceleration:
```bash
# Install ROCm ONNX Runtime for GPU acceleration
pip install onnxruntime-rocm
```

## 🔬 Technical Analysis

### Why ARM64 Wheel Won't Work
```
ERROR: onnxruntime_vitisai-1.16.0-py3-none-any.whl is not a supported wheel on this platform.
```
The wheel contains ARM64 compiled binaries that can't run on x86_64.

### What's Missing
1. **Userspace Runtime**: The VitisAI runtime libraries for x86_64
2. **ONNX EP Plugin**: The execution provider plugin compiled for x86_64
3. **XRT Libraries**: x86_64 versions of Xilinx Runtime libraries

## 🚀 Recommended Next Steps

### Immediate Actions
1. **Try the xdna-driver build** - It might provide userspace components
2. **Check Vitis AI Docker containers** - They might have x86_64 binaries
3. **Monitor AMD repositories** - Linux support is actively being developed

### Long-term Strategy
1. **Keep using CPU emulation** for now (it works!)
2. **Set up alerts** for AMD Ryzen AI Linux announcements
3. **Consider GPU acceleration** with ROCm as alternative

## 💡 The Good News

1. **Your NPU hardware is perfect** - Driver loaded, device accessible
2. **The software exists** - Just need the right architecture build
3. **AMD is working on it** - Kernel driver mainlined is huge progress
4. **Community pressure** - Many users want Linux x86_64 support

## 📝 Key Takeaway

We're at the cutting edge here! Your NPU hardware is ready and waiting. The missing piece is just the x86_64 Linux build of onnxruntime-vitisai. Given that:
- The kernel driver works perfectly
- The hardware is detected
- AMD has mainlined the driver

It's likely just a matter of time before AMD releases official x86_64 Linux support. In the meantime, CPU emulation mode is working well for development.

## 🔗 Resources to Monitor
- https://github.com/amd/xdna-driver (for userspace updates)
- https://github.com/amd/RyzenAI-SW/issues (for Linux support discussions)
- https://ryzenai.docs.amd.com/ (for official announcements)
- https://community.amd.com/t5/ai/bd-p/amd-ai (for community updates)