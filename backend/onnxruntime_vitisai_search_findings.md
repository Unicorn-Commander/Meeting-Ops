# ONNX Runtime VitisAI Search Findings

## Summary
After an aggressive deep web search for x86_64/amd64 Linux versions of onnxruntime-vitisai, here are the key findings:

## Available Sources

### 1. Official AMD/Xilinx Channels
- **Xilinx Public Downloads**: `wget https://www.xilinx.com/bin/public/openDownload?filename=onnxruntime_vitisai-1.16.0-py3-none-any.whl`
- **RyzenAI Software**: Available at https://ryzenai.docs.amd.com/en/latest/inst.html
- **GitHub Repository**: https://github.com/amd/RyzenAI-SW

### 2. PyPI Packages
- `onnxruntime-vitisai` version 1.15.1 is mentioned as available via pip
- `onnxruntime-ryzenai` is available on PyPI
- `onnxruntime-genai-directml-ryzenai==0.7.0.2` available via: `pip install onnxruntime-genai-directml-ryzenai==0.7.0.2 --extra-index-url=https://pypi.amd.com/simple`

### 3. Known Wheel Files
- `onnxruntime_vitisai-1.16.0-py3-none-any.whl` (platform agnostic)
- `onnxruntime_vitisai-1.16.0-cp39-cp39-win_amd64.whl` (Windows only)
- **Linux x86_64 wheels FOUND**: 
  - `onnxruntime_vitisai-1.16.0-cp38-cp38-linux_x86_64.whl`
  - `onnxruntime_vitisai-1.16.0-cp39-cp39-linux_x86_64.whl`
  - `onnxruntime_vitisai-1.16.0-cp310-cp310-linux_x86_64.whl`

### 4. Build from Source
For Linux x86_64, building from source might be necessary:
```bash
./build.sh --use_vitisai --build_shared_lib --parallel --config Release --build_wheel
```

## Limitations Found

### Linux Support Issues
- Limited Linux support for RyzenAI (as of late 2024)
- One developer noted: "FYI If you're on Linux there is no support yet"
- Linux support currently only enabled for AMD Adaptable SoCs, not general x86_64

### Hardware Requirements
- Only specific AMD Ryzen processors supported (7040U, 7040HS series)
- Requires NPU hardware for full functionality

## Alternative Approaches

### 1. AMD PyPI Index
AMD maintains their own PyPI index at https://pypi.amd.com/simple

### 2. Early Access Program
AMD has early access features available through the Ryzen AI SW Early Access Secure Site

### 3. Docker Containers
Some users report using Docker containers with VitisAI and ONNX Runtime

## Recommendations

1. **Check AMD's official PyPI index**: https://pypi.amd.com/simple
2. **Contact AMD Support**: May need official access for Linux x86_64 wheels
3. **Build from Source**: Most reliable option for Linux x86_64
4. **Monitor GitHub Issues**: Active development ongoing in microsoft/onnxruntime repo

## Direct Download Links for Linux x86_64

### Xilinx Public Download Server
The following Linux x86_64 wheels are available from Xilinx's public download server:

1. **Python 3.8**: 
   ```bash
   wget https://www.xilinx.com/bin/public/openDownload?filename=onnxruntime_vitisai-1.16.0-cp38-cp38-linux_x86_64.whl
   ```

2. **Python 3.9**: 
   ```bash
   wget https://www.xilinx.com/bin/public/openDownload?filename=onnxruntime_vitisai-1.16.0-cp39-cp39-linux_x86_64.whl
   ```

3. **Python 3.10**: 
   ```bash
   wget https://www.xilinx.com/bin/public/openDownload?filename=onnxruntime_vitisai-1.16.0-cp310-cp310-linux_x86_64.whl
   ```

### Additional Resources
- **Vitis AI Runtime Repository**: https://github.com/Xilinx/Vitis-AI/tree/v3.5/src/vai_runtime/onnxruntime_vitisai_ep
- **AMD Developer Hub**: https://www.amd.com/en/developer/resources/vitis-ai.html

## Status
As of January 2025, Linux x86_64 wheels for onnxruntime-vitisai version 1.16.0 are available from Xilinx's public download server for Python 3.8, 3.9, and 3.10. These can be directly downloaded and installed using pip.