#!/usr/bin/env python3
"""
Test the meeting notes API endpoint
"""
import asyncio
import aiohttp
import json
import time

async def test_meeting_notes_websocket():
    """Test the WebSocket connection for meeting notes"""
    
    # First, create a test session
    session_id = "test-session-" + str(int(time.time()))
    
    print(f"Testing Meeting Notes WebSocket API")
    print("=" * 50)
    print(f"Session ID: {session_id}")
    
    # Connect to WebSocket
    ws_url = f"ws://localhost:9050/ws/meeting-notes/{session_id}"
    print(f"Connecting to: {ws_url}")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(ws_url) as ws:
                print("✅ WebSocket connected successfully!")
                
                # Send a test transcript
                test_transcript = {
                    "type": "transcript_update",
                    "text": "Welcome everyone to today's meeting. We need to discuss the Q1 budget allocation and the new product launch timeline. Sarah will be leading the marketing campaign, and we need to finalize the budget by Friday."
                }
                
                await ws.send_str(json.dumps(test_transcript))
                print(f"📤 Sent test transcript")
                
                # Listen for responses
                print("\n📥 Waiting for AI-generated notes...")
                timeout = 30  # Wait up to 30 seconds
                start_time = time.time()
                
                while time.time() - start_time < timeout:
                    msg = await ws.receive(timeout=1)
                    
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        data = json.loads(msg.data)
                        print(f"\nReceived message type: {data.get('type')}")
                        
                        if data.get('type') == 'notes_update':
                            print("\n✨ AI-Generated Notes:")
                            print("-" * 40)
                            notes = data.get('notes', {})
                            
                            if notes.get('summary'):
                                print(f"Summary: {notes['summary']}")
                            
                            if notes.get('keyPoints'):
                                print("\nKey Points:")
                                for point in notes['keyPoints']:
                                    print(f"  • {point}")
                            
                            if notes.get('actionItems'):
                                print("\nAction Items:")
                                for item in notes['actionItems']:
                                    print(f"  ✓ {item.get('task')} - {item.get('owner', 'Unassigned')}")
                            
                            if notes.get('decisions'):
                                print("\nDecisions:")
                                for decision in notes['decisions']:
                                    print(f"  → {decision}")
                            
                            break
                        
                        elif data.get('type') == 'generating':
                            print("⏳ AI is generating notes...")
                        
                        elif data.get('type') == 'error':
                            print(f"❌ Error: {data.get('message')}")
                            break
                    
                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        print(f"❌ WebSocket error: {ws.exception()}")
                        break
                    
                    elif msg.type == aiohttp.WSMsgType.CLOSED:
                        print("WebSocket connection closed")
                        break
                
                print("\n" + "=" * 50)
                print("Test completed!")
                
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        print("\nMake sure:")
        print("1. Backend is running on port 9050")
        print("2. The meeting-notes API endpoint is loaded")
        print("3. Ollama is running with a model available")

if __name__ == "__main__":
    asyncio.run(test_meeting_notes_websocket())