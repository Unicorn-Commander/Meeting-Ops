#!/usr/bin/env python3
"""
Test the full recording pipeline: session creation -> transcription -> database storage
"""
import sys
import os
sys.path.append('/home/ucadmin/Development/Unicorn-Commander-Meeting-Ops/backend')

import asyncio
import json
import base64
import numpy as np
import websockets
from datetime import datetime

async def test_full_pipeline():
    print("🧪 Testing full transcription pipeline...")
    
    # Create fake audio data (1 second of 16kHz audio with some content)
    sample_rate = 16000
    duration = 1.0
    t = np.linspace(0, duration, int(sample_rate * duration))
    # Generate a more complex signal (mix of frequencies)
    audio_data = (np.sin(2 * np.pi * 440 * t) * 0.3 + 
                  np.sin(2 * np.pi * 880 * t) * 0.1 + 
                  np.random.normal(0, 0.05, len(t))) * 32767
    audio_data = audio_data.astype(np.int16)
    audio_bytes = audio_data.tobytes()
    audio_b64 = base64.b64encode(audio_bytes).decode('utf-8')
    
    session_id = f"test_session_{int(datetime.now().timestamp())}"
    print(f"📝 Using session ID: {session_id}")
    print(f"🎵 Audio data size: {len(audio_bytes)} bytes")
    
    try:
        # Connect to WebSocket
        uri = f"ws://localhost:9050/ws/stream/{session_id}"
        print(f"🔌 Connecting to {uri}")
        
        async with websockets.connect(uri) as websocket:
            print("✅ WebSocket connected!")
            
            # Wait for initial status message
            response = await websocket.recv()
            status = json.loads(response)
            print(f"📡 Status: {status}")
            
            # Send audio chunk
            message = {
                "type": "audio_chunk",
                "audio_data": audio_b64,
                "timestamp": datetime.now().isoformat()
            }
            
            print("🎤 Sending audio chunk...")
            await websocket.send(json.dumps(message))
            
            # Wait for transcription response
            print("⏳ Waiting for transcription response...")
            response = await asyncio.wait_for(websocket.recv(), timeout=10.0)
            result = json.loads(response)
            print(f"📝 Transcription result: {result}")
            
            if result.get("type") == "transcription":
                print("✅ Transcription received successfully!")
                transcription_data = result.get("data", {})
                print(f"   Text: '{transcription_data.get('text', 'No text')}'")
                print(f"   Confidence: {transcription_data.get('confidence', 0)}")
            else:
                print(f"⚠️ Unexpected response type: {result.get('type')}")
                
    except Exception as e:
        print(f"❌ WebSocket test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_full_pipeline())