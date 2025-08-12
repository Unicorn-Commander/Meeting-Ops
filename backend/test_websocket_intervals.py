#!/usr/bin/env python3
"""Test WebSocket real-time summarization at 30-second intervals"""

import asyncio
import websockets
import json
import requests
import time
from datetime import datetime

BASE_URL = "http://localhost:9050"
WS_URL = "ws://localhost:9050"

def login():
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        data={"username": "admin", "password": "admin123"}
    )
    return response.json()["access_token"]

async def test_websocket_intervals():
    token = login()
    session_id = f"ws-test-{int(time.time())}"
    
    print("🔄 TESTING WEBSOCKET 30-SECOND AI INTERVALS")
    print("="*60)
    print(f"Session ID: {session_id}")
    print(f"Expected interval: 30 seconds")
    print("-" * 60)
    
    # Sample meeting transcript chunks (simulating live transcription)
    transcript_chunks = [
        "John Smith: Good morning everyone, let's start our weekly team meeting.",
        "Sarah Chen: Thanks John. I have updates on the API integration project.",
        "Mike Johnson: And I'll cover the database optimization work.",
        "Sarah Chen: We've successfully implemented the NPU acceleration for Whisper.",
        "John Smith: That's excellent news! What's the performance improvement?",
        "Sarah Chen: We're seeing a 220x speedup compared to CPU-only processing.",
        "Mike Johnson: That's incredible. On the backend side, I've optimized our queries.",
        "John Smith: Great work team. What are our action items for this week?",
        "Sarah Chen: I need to complete the live meeting notes feature by Friday.",
        "Mike Johnson: I'll help with the backend integration and add custom vocabulary support.",
        "John Smith: Perfect. Any blockers or concerns we should address?",
        "Sarah Chen: No blockers from my side, everything is on track.",
        "Mike Johnson: All clear here, ready to support the integration work.",
        "John Smith: Excellent. Let's reconvene on Friday to review the live notes feature."
    ]
    
    try:
        # Connect to WebSocket
        ws_endpoint = f"{WS_URL}/api/meeting-intelligence/ws/live-notes/{session_id}"
        print(f"Connecting to: {ws_endpoint}")
        
        async with websockets.connect(ws_endpoint) as websocket:
            print("✅ WebSocket connected successfully")
            
            start_time = time.time()
            notes_received = 0
            last_notes_time = start_time
            
            # Send transcript chunks every 5 seconds (simulating live transcription)
            for i, chunk in enumerate(transcript_chunks):
                current_time = time.time()
                elapsed = current_time - start_time
                
                print(f"\n[{elapsed:6.1f}s] 📝 Sending chunk {i+1}/{len(transcript_chunks)}: {chunk[:50]}...")
                
                # Send transcript chunk
                message = {
                    "type": "transcript_chunk",
                    "text": f"{chunk} ",
                    "templates": ["executive-summary", "action-alerts", "key-decisions"]
                }
                
                await websocket.send(json.dumps(message))
                
                # Check for incoming notes (non-blocking)
                try:
                    # Wait up to 2 seconds for a response
                    response = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                    data = json.loads(response)
                    
                    if data.get("type") == "notes_update":
                        notes_received += 1
                        notes_time = current_time - start_time
                        interval = notes_time - (last_notes_time - start_time) if notes_received > 1 else notes_time
                        
                        print(f"🤖 [{notes_time:6.1f}s] AI Notes Update #{notes_received} (interval: {interval:.1f}s)")
                        
                        notes = data.get("notes", {})
                        if isinstance(notes, dict):
                            if "executive_summary" in notes:
                                summary = notes["executive_summary"]
                                if isinstance(summary, str):
                                    print(f"    📋 Summary: {summary[:100]}...")
                            
                            if "action_alerts" in notes:
                                actions = notes["action_alerts"]
                                if isinstance(actions, list) and actions:
                                    print(f"    ⚡ Actions: {len(actions)} items")
                                    for action in actions[:2]:
                                        if isinstance(action, str):
                                            print(f"      • {action[:60]}...")
                        
                        last_notes_time = current_time
                
                except asyncio.TimeoutError:
                    # No response within timeout, continue
                    pass
                except Exception as e:
                    print(f"    ⚠️ Error receiving: {e}")
                
                # Wait 5 seconds between chunks (simulating real conversation pace)
                await asyncio.sleep(5)
            
            # Wait a bit more to catch any final notes
            print(f"\n[{time.time() - start_time:6.1f}s] ⏳ Waiting for final notes...")
            
            for _ in range(6):  # Wait up to 30 more seconds
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                    data = json.loads(response)
                    
                    if data.get("type") == "notes_update":
                        notes_received += 1
                        notes_time = time.time() - start_time
                        interval = notes_time - (last_notes_time - start_time) if notes_received > 1 else notes_time
                        
                        print(f"🤖 [{notes_time:6.1f}s] Final AI Notes Update #{notes_received} (interval: {interval:.1f}s)")
                        break
                        
                except asyncio.TimeoutError:
                    continue
            
            # Send end session
            end_message = {
                "type": "end_session",
                "templates": ["executive-summary", "action-alerts"]
            }
            await websocket.send(json.dumps(end_message))
            
            # Wait for final notes
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                data = json.loads(response)
                
                if data.get("type") == "final_notes":
                    print(f"🏁 [{time.time() - start_time:6.1f}s] Final session notes received")
            except asyncio.TimeoutError:
                print("⏰ Timeout waiting for final notes")
            
            total_time = time.time() - start_time
            
            print("\n" + "="*60)
            print("📊 WEBSOCKET TEST RESULTS")
            print("="*60)
            print(f"✅ Total test duration: {total_time:.1f} seconds")
            print(f"✅ Transcript chunks sent: {len(transcript_chunks)}")
            print(f"✅ AI notes updates received: {notes_received}")
            print(f"✅ Expected 30-second interval: {'✓ Working' if notes_received > 0 else '❌ Not triggered'}")
            
            if notes_received > 0:
                avg_interval = total_time / notes_received
                print(f"✅ Average update interval: {avg_interval:.1f} seconds")
                print(f"✅ Interval assessment: {'Perfect!' if 25 <= avg_interval <= 35 else 'Within range' if 20 <= avg_interval <= 40 else 'Needs tuning'}")
            
            print("\n🎉 WebSocket real-time AI summarization test completed!")
    
    except Exception as e:
        print(f"❌ WebSocket test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_websocket_intervals())