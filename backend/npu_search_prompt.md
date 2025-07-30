# Search Task: Find AMD Ryzen AI NPU Whisper Implementation

## Context
We have an AMD Ryzen 9 8945HS processor with RyzenAI-npu1 (16 TOPS INT8) NPU. The kernel driver `amdxdna` is loaded and the device `/dev/accel/accel0` is accessible. We need to find a working implementation of OpenAI Whisper running on this NPU.

## Current Setup
- **Working Directory**: `/home/ucadmin/Development/Unicorn-Commander-Meeting-Ops/backend/`
- **NPU Device**: `/dev/accel/accel0` (accessible, permissions OK)
- **Kernel Module**: `amdxdna` (loaded)
- **XRT Installed**: `/opt/xilinx/xrt/` (but doesn't detect NPU)
- **Local Searxng**: Available at `http://localhost:8888`

## Primary Search Targets

### 1. Find `onnxruntime-vitisai` wheel file
Search for:
- `onnxruntime-vitisai*.whl`
- `onnxruntime_vitisai*.whl`
- "onnxruntime vitisai download"
- "onnxruntime vitis ai execution provider wheel"

Check these locations:
- AMD developer forums
- GitHub releases (AMD repos)
- PyPI mirrors
- Academic/research sites
- Chinese developer forums (they often have early access)

### 2. Find Whisper NPU Examples
Search for:
- "Ryzen AI whisper NPU working example"
- "AMD NPU whisper onnx quantized model"
- "amdxdna whisper implementation"
- "Hackster.io jchu634 ryzen ai subtitling" (full project details)
- "Ryzen AI Software 1.2 whisper example"

### 3. Find Quantized Whisper Models
Search for:
- "whisper base onnx int8 quantized AMD"
- "whisper tiny onnx ryzen ai"
- "whisper onnx vitisai quantized"
- site:huggingface.co "AMD whisper quantized"
- site:github.com "ryzen ai whisper onnx"

### 4. Alternative Package Names
Also search for:
- `vai-rt` (Vitis AI Runtime)
- `pyxir` (Python XIR library)
- `vart` (Vitis AI Runtime)
- "AMD IPU SDK" (IPU is another name for NPU)

## Search Strategies

### Use Searxng locally:
```bash
curl "http://localhost:8888/search?q=onnxruntime+vitisai+wheel+download&format=json"
curl "http://localhost:8888/search?q=AMD+Ryzen+AI+whisper+NPU+example&format=json"
```

### GitHub Code Search:
- `path:*.py "onnxruntime-vitisai" OR "VitisAIExecutionProvider"`
- `path:*.md "ryzen ai" whisper example`
- `org:amd whisper`
- `org:Xilinx "ryzen ai" whisper`

### Check these specific locations:
1. **AMD China GitHub**: Sometimes has early releases
2. **Gitee** (Chinese GitHub): Often mirrors AMD projects
3. **CSDN**: Chinese developers often share AMD tools
4. **Academic papers**: Search for "Ryzen AI NPU whisper" in Google Scholar

### File patterns to look for:
```
- install_onnxruntime_vitisai.sh
- setup_ryzen_ai_whisper.py
- whisper_*_quantized_int8.onnx
- whisper_npu_example.py
- ryzen_ai_whisper_demo.ipynb
```

## If you find onnxruntime-vitisai:
1. Download to: `/home/ucadmin/Development/Unicorn-Commander-Meeting-Ops/backend/`
2. Install with: `pip install ./onnxruntime-vitisai*.whl`
3. Test with:
```python
import onnxruntime as ort
providers = ort.get_available_providers()
print(providers)  # Should include 'VitisAIExecutionProvider'
```

## If you find example code:
Save to: `/home/ucadmin/Development/Unicorn-Commander-Meeting-Ops/backend/npu_whisper_examples/`

## Additional Context
- The NPU hardware is AMD Phoenix architecture (not Xilinx FPGA)
- We already have working emulation mode, just need hardware acceleration
- Standard `onnxruntime` doesn't have the Vitis AI provider
- The kernel driver is working, we just need the userspace runtime

## Keywords for Advanced Search
- "site:pan.baidu.com onnxruntime vitisai"
- "site:drive.google.com ryzen ai whisper"
- "inurl:releases onnxruntime vitisai"
- "intitle:index.of onnxruntime-vitisai"
- "AMD employee" + "ryzen ai" + "whisper"

Please search thoroughly and download any relevant files, examples, or documentation you find!