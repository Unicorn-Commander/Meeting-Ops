# NPU Direct Access Analysis

## Current Situation

1. **NPU Hardware**: AMD Ryzen AI NPU (RyzenAI-npu1) is present
2. **Kernel Driver**: `amdxdna` driver is loaded and working
3. **Device Node**: `/dev/accel/accel0` is accessible
4. **Firmware**: NPU firmware v1.5.2.380 is loaded

## The Problem

- XRT (Xilinx Runtime) doesn't detect the NPU device
- This is because XRT expects devices in a different format
- The `amdxdna` driver uses Linux's DRM/accel subsystem, not XRT's expected interface

## Solutions

### Option 1: Use Direct IOCTL Access (Most Direct)
```c
// Use IOCTLs from /usr/include/drm/amdxdna_accel.h
DRM_IOCTL_AMDXDNA_CREATE_HWCTX  // Create hardware context
DRM_IOCTL_AMDXDNA_CREATE_BO     // Create buffer objects
DRM_IOCTL_AMDXDNA_EXEC_CMD      // Execute commands
```

### Option 2: Write Custom Kernel Module
- Create a shim that exposes the NPU in XRT-compatible format
- Complex but would enable full XRT stack

### Option 3: Use AMD's Official Tools (When Available)
- AMD is developing official Ryzen AI software stack
- Will likely provide proper APIs for NPU access

### Option 4: Continue with Emulation
- Our current approach works functionally
- Provides all features except hardware acceleration
- Safe and portable

## Recommendation

For now, we should:
1. Continue using emulation mode (working well)
2. Monitor AMD's Ryzen AI SDK releases
3. The NPU hardware is there and ready - we just need proper userspace tools

## Why Vitis Doesn't Help

- Vitis is for FPGA/Versal devices, not Ryzen AI NPUs
- The `amdxdna` driver is a different architecture
- We need AMD's Ryzen AI specific tools, not Xilinx/Vitis tools