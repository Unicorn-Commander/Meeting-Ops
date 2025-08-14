#!/usr/bin/env python3
"""
Test WebSocket connection for live transcription
"""
import asyncio
import websockets
import json
import sys

async def test_websocket():
    # Get the most recent session ID
    import requests
    sessions = requests.get("http://localhost:9050/api/simple/recording-sessions").json()
    if not sessions:
        print("No sessions found")
        return
    
    session_id = sessions[0]["id"]
    print(f"Testing WebSocket for session: {session_id}")
    
    # Connect to WebSocket
    uri = f"ws://localhost:9050/ws/transcription/{session_id}"
    print(f"Connecting to: {uri}")
    
    try:
        async with websockets.connect(uri) as websocket:
            print("Connected! Waiting for messages...")
            
            # Send a test message to trigger any response
            await websocket.send(json.dumps({"type": "ping"}))
            
            # Listen for messages for 10 seconds
            timeout = 10
            start = asyncio.get_event_loop().time()
            
            while asyncio.get_event_loop().time() - start < timeout:
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                    data = json.loads(message)
                    print(f"Received: {data}")
                except asyncio.TimeoutError:
                    print(".", end="", flush=True)
                except Exception as e:
                    print(f"Error receiving: {e}")
                    
            print(f"\nTest completed after {timeout} seconds")
            
    except Exception as e:
        print(f"WebSocket connection failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_websocket())