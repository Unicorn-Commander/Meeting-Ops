#!/usr/bin/env python3
"""
Simple WebSocket test for live transcription
"""

import asyncio
import json
import numpy as np
from fastapi.testclient import TestClient
from main_docker import app

def test_websocket_endpoint():
    """Test WebSocket with TestClient"""
    client = TestClient(app)
    
    with client.websocket_connect("/ws/transcription") as websocket:
        # Send initial config
        websocket.send_json({"session_id": "test_123"})
        
        # Receive acknowledgment
        data = websocket.receive_json()
        print(f"Connected: {data}")
        
        # Generate test audio (2+ seconds needed)
        sample_rate = 16000
        duration = 3.0
        frequency = 440.0
        
        t = np.linspace(0, duration, int(sample_rate * duration))
        audio = np.sin(2 * np.pi * frequency * t)
        audio_int16 = (audio * 32767).astype(np.int16)
        audio_bytes = audio_int16.tobytes()
        
        print(f"Sending {len(audio_bytes)} bytes of audio...")
        
        # Send audio data
        websocket.send_bytes(audio_bytes)
        
        # Wait for response
        print("Waiting for transcription...")
        timeout = 10
        start_time = asyncio.get_event_loop().time()
        
        while asyncio.get_event_loop().time() - start_time < timeout:
            try:
                data = websocket.receive_json(timeout=1)
                if data.get("type") == "transcription":
                    print(f"\nTranscription received:")
                    print(f"  Text: {data.get('text', 'N/A')}")
                    print(f"  NPU: {data.get('npu_accelerated', False)}")
                    print(f"  Time: {data.get('processing_time', 0):.3f}s")
                    break
                elif data.get("type") == "keepalive":
                    print(".", end="", flush=True)
                else:
                    print(f"\nReceived: {data}")
            except:
                print(".", end="", flush=True)
                
        print("\nTest complete!")

if __name__ == "__main__":
    print("Testing WebSocket Live Transcription")
    print("=" * 50)
    test_websocket_endpoint()