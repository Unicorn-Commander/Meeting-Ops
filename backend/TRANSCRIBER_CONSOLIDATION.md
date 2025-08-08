# Transcriber Backend Consolidation

## Current Status (August 7, 2025)

### ✅ ACTIVE TRANSCRIBER
- **`services/fast_npu_transcriber.py`** - PRODUCTION TRANSCRIBER
  - Used by `npu_main.py` (main backend)
  - Supports NPU hardware acceleration AND CPU fallback
  - Uses faster-whisper backend
  - Configurable via `npu_config.json`
  - Features: word timestamps, VAD, language detection

### 🔄 DEPRECATED TRANSCRIBERS (Should be removed or archived)
- `basic_whisper_transcriber.py` - Basic implementation
- `cpu_onnx_transcriber.py` - CPU-only ONNX implementation  
- `hybrid_transcriber.py` - Hybrid CPU/NPU approach
- `npu_whisper_transcriber_old.py` - Old NPU implementation
- `npu_whisper_transcriber.py` - Previous NPU implementation
- `real_whisper_transcriber.py` - OpenAI whisper implementation
- `whisper_onnx_transcriber.py` - ONNX-based implementation
- `whisperx_transcriber.py` - WhisperX implementation
- `services/npu_enforced_transcriber.py` - NPU-only (no fallback)
- `stt_engine/whisper_npu_transcriber.py` - Engine-specific implementation

### 📋 CONSOLIDATION ACTIONS

#### Phase 1: Immediate (Completed)
- ✅ Standardized on `services/fast_npu_transcriber.py`
- ✅ Added CPU fallback strategy
- ✅ Configured via `npu_config.json`

#### Phase 2: Cleanup (Optional)
- Move deprecated transcribers to `deprecated/` directory
- Update any remaining imports to use standardized transcriber
- Remove unused transcriber references from imports

#### Phase 3: Optimization (Future)
- Add support for additional models (tiny, small, medium)
- Implement model caching and switching
- Add performance benchmarking between models

### 🎯 CONFIGURATION

The active transcriber is configured via `npu_config.json`:
- `default_model`: Model for NPU (large-v3)  
- `cpu_model`: Fallback model for CPU (base)
- `compute_type`: Quantization (int8 for NPU, float32 for CPU)
- Hardware detection automatic

### 🚀 USAGE

```python
from services.fast_npu_transcriber import get_fast_npu_transcriber

# Get singleton transcriber instance
transcriber = get_fast_npu_transcriber()

# Check status
status = transcriber.get_status()
print(f"Using: {status['device']}")

# Transcribe audio
result = transcriber.transcribe(audio_data, sample_rate=16000)
```

## Decision: Keep Only Active Transcriber

The `services/fast_npu_transcriber.py` is the only transcriber needed. All others are deprecated and can be removed to reduce codebase complexity.