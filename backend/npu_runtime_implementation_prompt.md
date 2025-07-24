# Task: Implement Direct NPU Runtime for AMD Ryzen AI Whisper Acceleration

## Context
We have an AMD Ryzen 9 8945HS with RyzenAI-npu1 (16 TOPS INT8) NPU. The kernel driver `amdxdna` is loaded and `/dev/accel/accel0` is accessible. We need to bypass onnxruntime-vitisai (which only has ARM64 builds) and create our own minimal runtime to execute Whisper on the NPU.

## Current Setup
- **Working Directory**: `/home/ucadmin/Development/Unicorn-Commander-Meeting-Ops/backend/`
- **NPU Device**: `/dev/accel/accel0` (accessible, user in render group)
- **Kernel Module**: `amdxdna` (loaded, mainlined in kernel 6.14)
- **Kernel Headers**: `/usr/include/drm/amdxdna_accel.h` (contains IOCTL definitions)
- **Architecture**: x86_64 Linux (Ubuntu 25.04)

## Available Resources

### 1. Kernel Driver Interface
```c
// From /usr/include/drm/amdxdna_accel.h
DRM_IOCTL_AMDXDNA_CREATE_HWCTX  // Create hardware context
DRM_IOCTL_AMDXDNA_CREATE_BO     // Create buffer objects
DRM_IOCTL_AMDXDNA_EXEC_CMD      // Execute commands
DRM_IOCTL_AMDXDNA_SYNC_BO       // Synchronize buffer
DRM_IOCTL_AMDXDNA_GET_INFO      // Get device info
```

### 2. Existing Code
- `/home/ucadmin/Development/Unicorn-Commander-Meeting-Ops/backend/direct_npu_poc.py` - Basic device access
- `/home/ucadmin/Development/Unicorn-Commander-Meeting-Ops/backend/npu_optimization/npu_machine_code.py` - NPU instruction generator
- `/home/ucadmin/Development/xdna-driver/` - AMD XDNA driver source

### 3. NPU Specifications
- Architecture: AMD XDNA (AI Engine 2)
- Compute Units: 4
- Vector Width: 1024 bits
- INT8 Performance: 16 TOPS
- Memory: 64KB per tile

## Primary Objective
Create a minimal Python/C runtime that can:
1. Load a Whisper model (ONNX or custom format) onto the NPU
2. Execute inference directly via IOCTLs
3. Achieve real-time transcription without onnxruntime

## Specific Tasks

### 1. Reverse Engineer NPU Binary Format
- Analyze Windows Ryzen AI `.xclbin` format (if available)
- OR design custom binary format using our NPU instruction set
- Map Whisper operations to NPU instructions

### 2. Implement Device Management
```python
class NPURuntime:
    def __init__(self):
        self.device = open("/dev/accel/accel0", "rb+")
    
    def create_context(self):
        # Implement proper IOCTL calls
    
    def allocate_buffer(self, size):
        # DMA-capable buffer allocation
    
    def load_model(self, model_path):
        # Load Whisper NPU binary
    
    def execute(self, audio_data):
        # Run inference
```

### 3. Implement Whisper Operations
Map these ONNX operations to NPU:
- Conv1D/Conv2D (for feature extraction)
- MatMul (for attention)
- Softmax
- LayerNorm
- GELU activation

### 4. Memory Management
- Implement DMA buffer allocation
- Handle data transfer CPU ↔ NPU
- Manage tiling for large matrices

### 5. Create Quantization Pipeline
- Implement INT8 quantization for Whisper
- Handle scale/zero-point calibration
- Ensure numerical stability

## Performance Requirements
- Target: 30x faster than CPU (≥30x real-time)
- Latency: <100ms for 30-second audio
- Memory: Fit in NPU's limited memory via tiling

## Deliverables

### 1. Core Runtime (`npu_runtime.py`)
```python
# Minimal runtime that can:
runtime = NPURuntime()
runtime.load_model("whisper_base_int8.npubin")
transcription = runtime.transcribe(audio_data)
```

### 2. Model Converter (`onnx_to_npu.py`)
```python
# Convert ONNX Whisper to NPU binary
converter = WhisperNPUConverter()
converter.convert("whisper-base.onnx", "whisper-base.npubin")
```

### 3. Test Suite
- Unit tests for each NPU operation
- End-to-end Whisper transcription test
- Performance benchmarks

## Implementation Strategy

### Phase 1: Device Communication (Day 1)
1. Get CREATE_HWCTX working properly
2. Implement buffer allocation/mapping
3. Successfully execute a NOP command
4. Read back results

### Phase 2: Simple Operations (Day 2)
1. Implement vector add on NPU
2. Implement matrix multiply
3. Verify correctness vs CPU

### Phase 3: Whisper Operations (Day 3-4)
1. Implement Conv1D for mel spectrogram
2. Implement attention mechanism
3. Implement decoder logic

### Phase 4: Full Integration (Day 5)
1. Load real Whisper model
2. Run end-to-end inference
3. Optimize performance

## Key Challenges to Solve

1. **Binary Format**: Determine exact format NPU expects
   - Try loading simple binaries and observe behavior
   - Check dmesg/kernel logs for clues

2. **Memory Layout**: Understand NPU memory architecture
   - How are tensors laid out?
   - How to handle strided access?

3. **Synchronization**: Ensure correct CPU-NPU sync
   - When to call SYNC_BO?
   - How to poll for completion?

4. **Debugging**: Limited visibility into NPU
   - Add extensive logging
   - Compare with CPU reference

## Success Criteria
- ✅ Can open and communicate with NPU device
- ✅ Can execute simple operations (add, multiply)
- ✅ Can run Whisper encoder on NPU
- ✅ Achieves >10x speedup vs CPU
- ✅ Produces correct transcriptions

## Resources to Reference
- Linux DRM subsystem documentation
- AMD AIE (AI Engine) architecture docs
- ONNX Whisper model structure
- XRT source code (for inspiration, not copying)

## Alternative Approach (if direct IOCTL fails)
If direct hardware access proves too complex, implement a hybrid approach:
1. Use mmap() to share memory with NPU
2. Use existing XRT libraries just for device management
3. Implement our own execution logic on top

Start with the simplest possible NPU operation and build up. Remember: we don't need the full onnxruntime complexity - just enough to run Whisper!

Good luck! The NPU is waiting to be unleashed! 🚀