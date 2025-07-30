#!/usr/bin/env python3
"""Test WebSocket audio levels connection"""

import asyncio
import websockets
import json
import sys

async def test_audio_levels():
    # Get token from login
    import httpx
    
    # Login first
    async with httpx.AsyncClient() as client:
        login_response = await client.post(
            "http://localhost:9050/api/auth/login",
            data={"username": "admin", "password": "admin123"},
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        
        if login_response.status_code != 200:
            print(f"Login failed: {login_response.text}")
            return
            
        token = login_response.json()["access_token"]
        print(f"Login successful, got token: {token[:20]}...")
    
    # Connect to WebSocket
    uri = f"ws://localhost:9050/ws/audio-levels?token={token}"
    
    try:
        async with websockets.connect(uri) as websocket:
            print("Connected to audio levels WebSocket!")
            
            # Listen for audio level updates
            for i in range(10):  # Get 10 updates
                message = await websocket.recv()
                data = json.loads(message)
                
                if data.get("type") == "error":
                    print(f"Error: {data.get('message')}")
                    break
                    
                level = data.get("level", 0)
                db = data.get("db", -60)
                peak = data.get("peak", 0)
                
                # Create a simple level meter visualization
                bar_length = int(level * 50)
                bar = "█" * bar_length + "░" * (50 - bar_length)
                
                print(f"\rLevel: [{bar}] {level:.2%} ({db:.1f} dB) Peak: {peak:.2%}", end="")
                sys.stdout.flush()
                
            print("\n\nTest completed successfully!")
            
    except Exception as e:
        print(f"WebSocket error: {e}")

if __name__ == "__main__":
    asyncio.run(test_audio_levels())