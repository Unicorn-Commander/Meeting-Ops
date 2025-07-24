# Gemini Task Assignments

## Project Context
Working directory: `/home/ucadmin/Development/Unicorn-Commander-Meeting-Ops/`
Backend directory: `/home/ucadmin/Development/Unicorn-Commander-Meeting-Ops/backend/`
Frontend directory: `/home/ucadmin/Development/Unicorn-Commander-Meeting-Ops/frontend/`

Admin credentials: `admin` / `Changeme123!`
Backend URL: `http://localhost:9050`
Frontend URL: `http://localhost:5173`

---

## Task #205: Frontend UI Testing & Integration (HIGH PRIORITY)

### Prompt:
Test the model switching functionality in the frontend UI and verify integration with the new backend APIs. The backend has been updated with new AI model management endpoints including download/uninstall simulation, model testing, and detailed availability checking. Your job is to test the frontend integration and fix any issues.

### Key Files to Work With:
- `/home/ucadmin/Development/Unicorn-Commander-Meeting-Ops/frontend/src/components/NPUModelSettings.tsx`
- `/home/ucadmin/Development/Unicorn-Commander-Meeting-Ops/frontend/src/pages/Settings.tsx`
- `/home/ucadmin/Development/Unicorn-Commander-Meeting-Ops/frontend/src/services/api.ts`

### Backend Endpoints to Test:
- `GET /api/ai/stt/models` (list models)
- `PUT /api/ai/stt/model` (switch models) 
- `POST /api/ai/stt/test` (test current model)
- `POST /api/ai/stt/models/{id}/download` (download simulation)
- `DELETE /api/ai/stt/models/{id}` (uninstall)
- `GET /api/ai/stt/models/{id}/availability` (detailed diagnostics)

### Checklist:
- [ ] Start frontend dev server: `cd /home/ucadmin/Development/Unicorn-Commander-Meeting-Ops/frontend && npm run dev`
- [ ] Verify backend is running: `curl http://localhost:9050/api/ai/stt/models`
- [ ] Login with admin credentials in browser at `http://localhost:5173`
- [ ] Navigate to Settings → AI Models section
- [ ] Verify 8 models are displayed (whisperx-npu-unified, whisperx-npu, whisper-onnx-npu, etc.)
- [ ] Test model switching - select different model and verify API call works
- [ ] Test download buttons - verify they show progress/completion
- [ ] Test uninstall buttons - verify they work and show confirmation
- [ ] Test model testing - click test button and verify results display
- [ ] Check availability diagnostics - verify error messages show helpful info
- [ ] Verify current model is highlighted properly
- [ ] Test error handling - what happens when API calls fail?
- [ ] Check responsive design on different screen sizes
- [ ] Verify loading states and spinners work
- [ ] Test permission handling - try with non-admin user if possible
- [ ] Fix any frontend bugs or integration issues found

---

## Task #206: Recording v2 API Fixes (HIGH PRIORITY)

### Prompt:
Fix the import issues in the recording v2 API and re-enable the enhanced recording service. The recording v2 API was disabled due to import errors but it contains important session management and error handling improvements. Fix the imports and test the recording functionality.

### Key Files to Work With:
- `/home/ucadmin/Development/Unicorn-Commander-Meeting-Ops/backend/api/recording_v2.py`
- `/home/ucadmin/Development/Unicorn-Commander-Meeting-Ops/backend/services/audio_session_manager.py`
- `/home/ucadmin/Development/Unicorn-Commander-Meeting-Ops/backend/services/audio_input_service_v2.py`
- `/home/ucadmin/Development/Unicorn-Commander-Meeting-Ops/backend/main.py` (recording v2 commented out)

### Checklist:
- [ ] Examine `/home/ucadmin/Development/Unicorn-Commander-Meeting-Ops/backend/api/recording_v2.py` for import errors
- [ ] Fix any missing module imports in recording_v2.py
- [ ] Check `/home/ucadmin/Development/Unicorn-Commander-Meeting-Ops/backend/services/audio_session_manager.py` imports
- [ ] Fix `/home/ucadmin/Development/Unicorn-Commander-Meeting-Ops/backend/services/audio_input_service_v2.py` imports
- [ ] Verify all dependencies exist and are properly imported
- [ ] Test the imports: `cd /home/ucadmin/Development/Unicorn-Commander-Meeting-Ops/backend && python -c "from api.recording_v2 import router"`
- [ ] Re-enable recording v2 in `/home/ucadmin/Development/Unicorn-Commander-Meeting-Ops/backend/main.py` (uncomment the include_router line)
- [ ] Restart the backend server
- [ ] Test `POST /api/recording/v2/start` endpoint
- [ ] Test `POST /api/recording/v2/stop` endpoint  
- [ ] Test session management endpoints
- [ ] Verify WebSocket connections work: `ws://localhost:9050/ws/stream/{session_id}`
- [ ] Test error handling and recovery
- [ ] Check audio device integration
- [ ] Verify session cleanup works properly

---

## Task #208: WhisperX NPU Engine Stub (MEDIUM PRIORITY)

### Prompt:
Create stub implementations for the NPU optimization modules to eliminate import errors and make NPU models show as "available" in the UI. The system currently shows import errors for WhisperX NPU modules. Create minimal stub classes that implement the expected interfaces.

### Files to Create:
- `/home/ucladmin/Development/Unicorn-Commander-Meeting-Ops/backend/npu_optimization/__init__.py`
- `/home/ucadmin/Development/Unicorn-Commander-Meeting-Ops/backend/npu_optimization/whisperx_npu_engine.py`

### Referenced in:
- `/home/ucadmin/Development/Unicorn-Commander-Meeting-Ops/backend/services/stt_model_manager.py` (lines 145, 153)
- `/home/ucadmin/Development/Unicorn-Commander-Meeting-Ops/backend/api/stt_models.py` (line 423)

### Checklist:
- [ ] Create directory: `mkdir -p /home/ucadmin/Development/Unicorn-Commander-Meeting-Ops/backend/npu_optimization/`
- [ ] Create `/home/ucadmin/Development/Unicorn-Commander-Meeting-Ops/backend/npu_optimization/__init__.py`
- [ ] Create `/home/ucadmin/Development/Unicorn-Commander-Meeting-Ops/backend/npu_optimization/whisperx_npu_engine.py` with WhisperXNPUEngine class
- [ ] Implement basic methods: `__init__`, `transcribe`, `get_info`, `is_ready`
- [ ] Create stub methods that return realistic placeholder data
- [ ] Test imports: `cd /home/ucadmin/Development/Unicorn-Commander-Meeting-Ops/backend && python -c "from npu_optimization.whisperx_npu_engine import WhisperXNPUEngine"`
- [ ] Verify models show as "available" in API: `curl http://localhost:9050/api/ai/stt/models`
- [ ] Test model switching to NPU models works without errors
- [ ] Check that model testing works with stubs: `curl -X POST http://localhost:9050/api/ai/stt/test`
- [ ] Verify frontend shows NPU models as installable
- [ ] Add logging to stub methods for debugging
- [ ] Document the stub implementation for future replacement

---

## Task #207: WebSocket Testing (MEDIUM PRIORITY)

### Prompt:
Test the WebSocket real-time transcription functionality with the new unified transcription service. The system has WebSocket endpoints for real-time audio streaming and transcription. Test the connections, data flow, and real-time features.

### Key Files:
- `/home/ucadmin/Development/Unicorn-Commander-Meeting-Ops/backend/api/websocket.py`
- `/home/ucadmin/Development/Unicorn-Commander-Meeting-Ops/backend/services/transcription_service.py`
- `/home/ucadmin/Development/Unicorn-Commander-Meeting-Ops/frontend/src/hooks/useWebSocket.ts` (if exists)

### WebSocket Endpoint: 
`ws://localhost:9050/ws/stream/{session_id}`

### Related APIs: 
- `/api/recording-sessions`
- `/api/audio-level`

### Checklist:
- [ ] Start a new recording session: `curl -X POST http://localhost:9050/api/recording-sessions -H "Content-Type: application/json" -d '{"title":"test"}'`
- [ ] Connect to WebSocket: `ws://localhost:9050/ws/stream/{session_id}` (use wscat or browser dev tools)
- [ ] Verify WebSocket connection establishes successfully
- [ ] Test sending audio data through WebSocket
- [ ] Verify real-time transcription responses
- [ ] Test audio level monitoring: `curl http://localhost:9050/api/audio-level`
- [ ] Check session state management during streaming
- [ ] Test multiple concurrent WebSocket connections
- [ ] Verify proper connection cleanup on disconnect
- [ ] Test error handling for invalid session IDs
- [ ] Check authentication for WebSocket connections
- [ ] Test pause/resume functionality via WebSocket
- [ ] Verify real-time updates in frontend during recording
- [ ] Test WebSocket reconnection on network issues

---

## Task #210: Performance Metrics Collection (MEDIUM PRIORITY)

### Prompt:
Implement proper metrics collection for model switching and transcription performance. Add timing, resource usage tracking, and performance analytics to help users understand model performance differences.

### Files to Create:
- `/home/ucadmin/Development/Unicorn-Commander-Meeting-Ops/backend/services/metrics_collector.py`
- Update `/home/ucadmin/Development/Unicorn-Commander-Meeting-Ops/backend/api/stt_models.py` to include metrics

### Add metrics to:
- Model switching operations
- Transcription processing times  
- Memory usage during transcription
- Real-time performance factors

### Checklist:
- [ ] Create `/home/ucadmin/Development/Unicorn-Commander-Meeting-Ops/backend/services/metrics_collector.py`
- [ ] Implement timing decorators for transcription methods
- [ ] Add memory usage tracking using psutil
- [ ] Collect model loading/switching times
- [ ] Track real-time processing factors (how fast vs real-time)
- [ ] Add CPU/GPU utilization monitoring
- [ ] Create metrics storage (in-memory or database)
- [ ] Add `GET /api/metrics` endpoint for retrieving performance data
- [ ] Implement metrics aggregation (averages, percentiles)
- [ ] Add metrics to model test endpoint results in `/home/ucadmin/Development/Unicorn-Commander-Meeting-Ops/backend/api/stt_models.py`
- [ ] Create performance comparison features
- [ ] Add metrics visualization data for frontend
- [ ] Test metrics collection with different models
- [ ] Verify metrics persistence across server restarts

---

## Task #211: Model Benchmarking (MEDIUM PRIORITY)

### Prompt:
Implement comprehensive model benchmarking with real audio samples. Create a system to test different models with the same audio files and compare their performance, accuracy, and resource usage.

### Files to Create:
- `/home/ucadmin/Development/Unicorn-Commander-Meeting-Ops/backend/services/model_benchmarker.py`
- `/home/ucadmin/Development/Unicorn-Commander-Meeting-Ops/backend/benchmark_audio/` (directory for test files)

### Features to implement:
- Audio sample management
- Automated benchmarking across all models
- Performance comparison reports
- Accuracy metrics (if ground truth available)

### Checklist:
- [ ] Create `/home/ucadmin/Development/Unicorn-Commander-Meeting-Ops/backend/services/model_benchmarker.py`
- [ ] Create sample audio files directory: `mkdir -p /home/ucadmin/Development/Unicorn-Commander-Meeting-Ops/backend/benchmark_audio/`
- [ ] Implement audio file preprocessing (format standardization)
- [ ] Create benchmark test suite runner
- [ ] Add timing measurements for each model
- [ ] Implement memory usage tracking during benchmarks
- [ ] Create accuracy comparison (if ground truth transcripts available)
- [ ] Add `POST /api/ai/benchmark` endpoint to `/home/ucadmin/Development/Unicorn-Commander-Meeting-Ops/backend/api/stt_models.py`
- [ ] Implement benchmark result storage
- [ ] Create benchmark report generation
- [ ] Add comparison charts/data for frontend
- [ ] Test with different audio types (clear speech, noisy, accented)
- [ ] Implement benchmark scheduling (automated runs)
- [ ] Add benchmark history tracking
- [ ] Create benchmark result export (JSON/CSV)

---

## Recommended Order:
1. **Task #205** (Frontend Testing) - Most user-visible, validates backend work
2. **Task #206** (Recording v2 Fixes) - Critical functionality that's currently broken  
3. **Task #208** (NPU Stubs) - Would make the UI much cleaner
4. **Task #207** (WebSocket Testing) - Real-time features are important
5. **Task #210** (Metrics) - Good for optimization insights
6. **Task #211** (Benchmarking) - Nice to have for analysis

## Getting Started:
1. `cd /home/ucadmin/Development/Unicorn-Commander-Meeting-Ops/`
2. Ensure backend is running: `cd backend && python -m uvicorn main:app --host 0.0.0.0 --port 9050 --reload`
3. Test backend: `curl http://localhost:9050/api/ai/stt/models`
4. Choose a task and follow the checklist

Each task has clear success criteria and can be worked on independently.