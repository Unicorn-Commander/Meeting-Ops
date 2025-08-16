#!/usr/bin/env python3
"""
Verify GPU AI summaries are working during recording
"""
import requests
import time
import json

print("=" * 60)
print("GPU AI SUMMARIES VERIFICATION")
print("=" * 60)

# Check GPU backend
print("\n1. Checking GPU llama.cpp backend...")
try:
    response = requests.post(
        "http://localhost:11437/completion",
        json={"prompt": "Test", "n_predict": 5},
        timeout=5
    )
    if response.status_code == 200:
        print("   ✅ GPU backend ONLINE at port 11437")
    else:
        print("   ❌ GPU backend not responding properly")
        print("   Run: ./start-gpu-optimized.sh")
except:
    print("   ❌ GPU backend OFFLINE")
    print("   Run: ./start-gpu-optimized.sh")

# Check unified agent service configuration
print("\n2. Checking Unified Agent Service configuration...")
try:
    from services.unified_agent_service import unified_agent_service
    print(f"   Backend: {unified_agent_service.backend_type}")
    print(f"   URL: {unified_agent_service.base_url}")
    print(f"   Endpoint: {unified_agent_service.endpoint_path}")
    
    if unified_agent_service.backend_type == "llamacpp":
        print("   ✅ Configured for GPU acceleration!")
    else:
        print("   ⚠️ Using CPU backend (slower)")
except Exception as e:
    print(f"   ❌ Error: {e}")

# Check if config exists
print("\n3. Checking AI backend configuration...")
try:
    from config.ai_backends import AI_BACKENDS, AI_BACKEND
    print(f"   Default backend: {AI_BACKEND}")
    print(f"   Available backends: {list(AI_BACKENDS.keys())}")
    print("   ✅ Configuration loaded")
except:
    print("   ⚠️ Using fallback configuration")

print("\n" + "=" * 60)
print("EXPECTED BEHAVIOR WHEN RECORDING:")
print("=" * 60)
print("""
1. Start recording via API or frontend
2. Speak 50+ words into microphone
3. Check backend logs for:
   - "🚀 Started unified agent for progressive AI summaries"
   - "🎯 Progressive summary triggered at X words"
   - "⚡ LLAMACPP inference completed in X.Xs"
   - "📡 Broadcast progressive summary"

4. GPU usage should spike to 99% when summaries generate
   (Check with: rocm-smi or watch -n 1 rocm-smi)

5. Frontend should receive progressive summaries via WebSocket

If not seeing these:
- Ensure GPU server is running: ./start-gpu-optimized.sh
- Check that recording actually starts unified agent
- Verify word counting in live_recording_transcription
""")

print("\n✅ Verification complete. Start a recording to test!")
print("   API: POST /api/simple/recording-sessions/{id}/start")