#!/usr/bin/env python3
"""
Test the audio level WebSocket endpoint
"""

import asyncio
import websockets
import json
import sys

async def test_audio_levels():
    """Connect to audio levels WebSocket and display levels"""
    uri = "ws://localhost:9050/ws/audio-levels"
    
    print("🎤 Testing Audio Level WebSocket")
    print(f"   Connecting to: {uri}")
    print("=" * 50)
    
    try:
        async with websockets.connect(uri) as websocket:
            print("✅ Connected to WebSocket")
            
            # Receive messages
            message_count = 0
            while True:
                try:
                    message = await websocket.recv()
                    data = json.loads(message)
                    
                    if data.get("type") == "audio_level":
                        level = data.get("level", 0)
                        db = data.get("db", -60)
                        peak = data.get("peak", 0)
                        status = data.get("status", "unknown")
                        
                        # Create visual bar
                        bar_length = int(level * 50)
                        bar = "█" * bar_length + "░" * (50 - bar_length)
                        
                        # Status icon
                        if status == "monitoring":
                            icon = "🎤"
                        elif status == "simulated":
                            icon = "🎭"
                        else:
                            icon = "❓"
                        
                        # Print update
                        print(f"\r{icon} [{bar}] {db:.1f} dB | Peak: {peak:.2f} | Status: {status}", end="", flush=True)
                        
                        message_count += 1
                        
                        # Exit after 100 messages for testing
                        if message_count >= 100:
                            print("\n\n✅ Test completed successfully!")
                            break
                    
                    elif data.get("type") == "status":
                        print(f"📊 Status: {data.get('message')}")
                    
                    elif data.get("type") == "error":
                        print(f"❌ Error: {data.get('message')}")
                        break
                        
                except websockets.exceptions.ConnectionClosed:
                    print("\n❌ WebSocket connection closed")
                    break
                except Exception as e:
                    print(f"\n❌ Error receiving message: {e}")
                    break
                    
    except websockets.exceptions.WebSocketException as e:
        print(f"❌ WebSocket error: {e}")
    except ConnectionRefusedError:
        print("❌ Could not connect to server. Make sure the backend is running on port 9050.")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")

if __name__ == "__main__":
    print("Audio Level WebSocket Test")
    print("Press Ctrl+C to stop\n")
    
    try:
        asyncio.run(test_audio_levels())
    except KeyboardInterrupt:
        print("\n\n👋 Test stopped by user")
        sys.exit(0)