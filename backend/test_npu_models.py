#!/usr/bin/env python3
"""Test NPU model availability and functionality"""
import os
os.environ['LD_PRELOAD'] = '/lib/x86_64-linux-gnu/libstdc++.so.6'

import sys
sys.path.append('.')

from services.transcription_service import transcription_service

print("🧪 Testing NPU Model Integration")
print("=" * 50)

# Check available models
print("\n1️⃣ Checking available transcription models...")
models = transcription_service.get_available_models()
print(f"Found {len(models)} models:")
for model in models:
    print(f"   - {model['id']}: {model['name']}")
    if 'npu' in model['id'].lower():
        print(f"     ✅ NPU Model Found!")

# Check current model
print("\n2️⃣ Current model:")
current = transcription_service.get_current_model_info()
print(f"   ID: {current.get('model_id', 'None')}")
print(f"   Engine: {current.get('engine_type', 'None')}")
print(f"   Ready: {transcription_service.is_ready}")

# Try to switch to NPU model
print("\n3️⃣ Attempting to switch to NPU model...")
npu_models = [m for m in models if 'npu' in m['id'].lower()]
if npu_models:
    npu_model = npu_models[0]
    print(f"   Switching to: {npu_model['id']}")
    try:
        success = transcription_service.switch_model(npu_model['id'])
        if success:
            print("   ✅ Successfully switched to NPU model!")
            
            # Check if it's really using NPU
            new_info = transcription_service.get_current_model_info()
            print(f"   New engine type: {new_info.get('engine_type')}")
            print(f"   NPU available: {new_info.get('npu_available', False)}")
        else:
            print("   ❌ Failed to switch to NPU model")
    except Exception as e:
        print(f"   ❌ Error switching model: {e}")
else:
    print("   ❌ No NPU models found!")

# Check NPU engine directly
print("\n4️⃣ Checking NPU engine directly...")
try:
    from npu_optimization.whisperx_npu_engine_real import WhisperXNPUEngine
    print("   ✅ NPU engine module found!")
    
    # Try to create instance
    engine = WhisperXNPUEngine()
    print("   ✅ NPU engine instance created!")
    
    # Initialize
    if engine.initialize():
        print("   ✅ NPU engine initialized!")
        info = engine.get_system_info()
        print(f"   NPU Available: {info.get('npu_available', False)}")
        print(f"   Device: {info.get('device', 'Unknown')}")
    else:
        print("   ❌ NPU engine initialization failed")
        
except ImportError as e:
    print(f"   ❌ NPU engine module not found: {e}")
except Exception as e:
    print(f"   ❌ Error with NPU engine: {e}")

print("\n" + "=" * 50)
print("Test complete!")