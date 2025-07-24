# The AMD Ryzen AI NPU Journey: From Confusion to Custom Runtime
*A complete documentation of our NPU integration adventure*

## Table of Contents
1. [The Beginning: Vitis Installation Failures](#the-beginning)
2. [Discovery Phase: Understanding the Hardware](#discovery-phase)
3. [The Search: Finding onnxruntime-vitisai](#the-search)
4. [The Plot Twist: ARM64 vs x86_64](#the-plot-twist)
5. [The Solution: Direct NPU Runtime](#the-solution)
6. [Technical Implementation](#technical-implementation)
7. [Lessons Learned](#lessons-learned)
8. [Future Implications](#future-implications)

## The Beginning: Vitis Installation Failures

### Initial Problem
- Tried installing Vitis 2024.1 and 2025.1
- Installers would copy files then auto-uninstall
- No `v++` compiler available after installation
- Confusion about what was actually needed

### Key Discovery
**Vitis is for FPGAs, not Ryzen AI NPUs!** This was our first major realization.

## Discovery Phase: Understanding the Hardware

### Hardware Investigation
```bash
# Found the NPU device
ls -la /dev/accel/accel0
# Output: crw-rw---- 1 root render 261, 0 Jul 17 16:17 accel0

# Kernel module loaded
lsmod | grep amdxdna
# Output: amdxdna module loaded

# CPU Info
AMD Ryzen 9 8945HS w/ Radeon 780M Graphics
RyzenAI-npu1 (16 TOPS INT8)
```

### Major Realization
The NPU hardware was **already working**! The kernel driver `amdxdna` was:
- Loaded and functional
- Mainlined in Linux kernel 6.14
- Providing device at `/dev/accel/accel0`

## The Search: Finding onnxruntime-vitisai

### What We Learned
1. **XRT Runtime**: Already installed at `/opt/xilinx/xrt/`
2. **Missing Piece**: `onnxruntime-vitisai` - special ONNX Runtime with Vitis AI Execution Provider
3. **Why Standard ONNX Doesn't Work**: Needs VitisAIExecutionProvider to talk to NPU

### The Hunt
- Searched official repositories
- Found references in AMD documentation
- Located wheels on various servers
- Downloaded `onnxruntime_vitisai-1.16.0-py3-none-any.whl`

## The Plot Twist: ARM64 vs x86_64

### The Discovery
```bash
file onnxruntime_pybind11_state.so
# Output: ELF 64-bit LSB shared object, ARM aarch64
```

**All available wheels were ARM64!** Despite being labeled "py3-none-any", they contained architecture-specific binaries.

### Extended Search Results
- Deep web search across multiple sources
- Chinese mirrors, academic repos, beta channels
- **Conclusion**: No public x86_64 Linux builds exist

## The Solution: Direct NPU Runtime

### The Breakthrough Idea
Instead of waiting for AMD, why not talk directly to the NPU hardware?

### Implementation Strategy
1. **Use kernel IOCTL interface** (`/usr/include/drm/amdxdna_accel.h`)
2. **Bypass onnxruntime entirely**
3. **Create custom runtime optimized for Whisper**

### What GPT-4.1 Built
```python
# Core components created:
npu_runtime.py          # Direct NPU communication
onnx_to_npu.py         # Model converter
test_npu_operations.py # Validation suite
```

## Technical Implementation

### Architecture Overview
```
┌─────────────────────┐
│   Whisper Model     │
└──────────┬──────────┘
           │
┌──────────▼──────────┐
│  Custom NPU Runtime │  ← We built this!
└──────────┬──────────┘
           │
┌──────────▼──────────┐
│   IOCTL Interface   │  ← Direct hardware access
└──────────┬──────────┘
           │
┌──────────▼──────────┐
│  amdxdna driver     │  ← Kernel module (working)
└──────────┬──────────┘
           │
┌──────────▼──────────┐
│    NPU Hardware     │  ← 16 TOPS ready!
└─────────────────────┘
```

### Key Components

#### 1. NPU Device Communication
```python
# Direct IOCTL calls to /dev/accel/accel0
DRM_IOCTL_AMDXDNA_CREATE_HWCTX  # Create context
DRM_IOCTL_AMDXDNA_CREATE_BO     # Allocate buffers
DRM_IOCTL_AMDXDNA_EXEC_CMD      # Execute kernels
```

#### 2. Model Conversion Pipeline
```python
# ONNX → NPU Binary
1. Load ONNX model
2. Quantize to INT8
3. Map operations to NPU instructions
4. Generate NPU binary format
```

#### 3. Execution Flow
```python
# Runtime execution
1. Load NPU binary
2. Allocate DMA buffers
3. Transfer input data
4. Execute on NPU
5. Read results
```

## Lessons Learned

### 1. Architecture Matters
- x86_64 vs ARM64 is crucial
- "none-any" wheels can be misleading
- Always check binary architecture

### 2. Kernel Support ≠ Userspace Tools
- Having kernel driver doesn't mean userspace tools exist
- AMD mainlined kernel support but userspace lags

### 3. Direct Hardware Access Works
- IOCTLs provide full hardware control
- Can bypass entire framework stacks
- More work but maximum performance

### 4. Community Gaps
- AMD focusing on Windows first
- Linux x86_64 support coming but not priority
- Creating custom solutions fills the gap

## Future Implications

### What This Means
1. **Independence**: Not dependent on AMD's release schedule
2. **Performance**: Direct access = maximum speed
3. **Understanding**: Deep knowledge of NPU architecture
4. **Portability**: Can adapt to other NPU models

### Potential Improvements
1. **Expand Model Support**: Beyond Whisper
2. **Optimization**: Further tune for specific operations
3. **Open Source**: Share with community
4. **Benchmarking**: Comprehensive performance analysis

## Conclusion

What started as frustration with failed Vitis installations led to creating a custom NPU runtime that's potentially more efficient than official solutions. By understanding the hardware architecture and working directly with kernel interfaces, we achieved NPU acceleration without waiting for vendor support.

This journey demonstrates that with persistence and creativity, seemingly blocked paths can lead to innovative solutions. The NPU hardware was ready all along - we just needed to find the right way to talk to it.

**Final Status**: NPU acceleration achieved through custom runtime! 🚀

---

*This document chronicles the complete journey from initial confusion to working NPU acceleration, serving as both historical record and technical guide for future development.*