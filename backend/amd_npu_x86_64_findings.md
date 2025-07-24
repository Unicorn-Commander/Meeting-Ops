# AMD NPU/Ryzen AI x86_64 Linux Support Findings

## Summary
As of January 2025, AMD NPU (Ryzen AI) support on Linux x86_64 is in active development but not fully available. The kernel driver is mainlined, but the complete software stack is still being developed.

## Current Status

### 1. **Official Support**
- **Windows Only**: Currently, onnxruntime-vitisai wheels are only officially available for Windows AMD64
- **Linux Support**: Limited to AMD Adaptable SoCs, not x86_64 desktop/laptop systems with Ryzen AI NPUs
- **Available Windows Wheel**: `onnxruntime_vitisai-1.15.1-cp39-cp39-win_amd64.whl`

### 2. **Linux Kernel Support**
- **Kernel Driver**: The `amdxdna` driver is mainlined starting with Linux kernel 6.14
- **Requirements**: 
  - Linux kernel 6.10+ with `CONFIG_AMD_IOMMU` and `CONFIG_DRM_ACCEL` enabled
  - IOMMU SVA support
  - Ubuntu 22.04 LTS, 24.04 LTS, and 24.10 are supported

### 3. **Hardware Architecture**
- NPU is based on AMD XDNA Architecture
- Appears as a PCIe device to the x86 host CPU
- Compatible with AMD Ryzen 7040 series processors (except Ryzen 5 7540U and Ryzen 3 7440U)

## Building from Source

### For Windows
```bash
.\build.bat --use_vitisai --build_shared_lib --parallel --config Release --build_wheel
```

### For Linux (Currently limited to AMD Adaptable SoCs)
The `--use_vitisai` flag is documented for Windows builds, but Linux x86_64 support is not fully documented or available.

## Required Components for Linux

1. **XRT Driver**: Available at https://github.com/amd/xdna-driver
2. **XRT AMD XDNA Shim**: Plugin for XRT from the xdna-driver repository
3. **LLVM-AIE (Peano)**: Fork of LLVM for AIEngine architecture
4. **Userspace Runtime**: Currently missing from official repositories

## Alternative Resources

1. **ROCm ONNX Runtime**: For AMD GPU support (not NPU)
   - Repository: `github.com/amd/onnxruntime-rocm`
   - Supports x86_64 with AMD GPUs through ROCm

2. **Community Wheels**: Some users report finding wheels at:
   - https://github.com/amd/RyzenAI-cloud-to-client-demo/tree/main/wheels
   - Xilinx public downloads

## Future Outlook

- AMD is actively working on full Linux support
- Community interest has prompted AMD to reconsider Linux support
- The kernel driver being mainlined is a positive step
- Complete software stack and optimization tools are still pending

## Recommendations

1. **For Production Use**: Stick with Windows for now if you need Ryzen AI NPU support
2. **For Development/Testing**: 
   - Ensure you have Linux kernel 6.14+
   - Monitor the xdna-driver repository for updates
   - Consider using ROCm for GPU-based inference as an alternative
3. **Building from Source**: Currently not recommended for x86_64 Linux as the full stack isn't available

## Key Limitations

- No official x86_64 Linux wheels for onnxruntime-vitisai
- Incomplete userspace software stack
- Limited documentation for Linux builds
- Full ML framework integration pending

## Contact and Updates

- Monitor AMD's official Ryzen AI Software page
- Check the Microsoft ONNX Runtime GitHub issues
- Follow the xdna-driver repository for Linux development progress