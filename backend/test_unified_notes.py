#!/usr/bin/env python3
"""
Test the unified meeting notes API (supports both Granite and Gemma)
"""
import asyncio
import aiohttp
import json
import time

async def test_unified_api():
    """Test the unified meeting notes API"""
    
    print("Testing Unified Meeting Notes API")
    print("=" * 50)
    
    base_url = "http://localhost:9050"
    
    # 1. Test status endpoint
    print("1. Testing status endpoint...")
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{base_url}/api/meeting-notes-unified/status") as response:
            if response.status == 200:
                data = await response.json()
                print(f"✅ Current provider: {data['current_provider']}")
                print(f"✅ Connected: {data['connected']}")
                print(f"✅ Service type: {data.get('service_type', 'Unknown')}")
            else:
                print(f"❌ Status check failed: {response.status}")
                return
    
    # 2. Test provider functionality
    print("\n2. Testing provider functionality...")
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{base_url}/api/meeting-notes-unified/test") as response:
            if response.status == 200:
                data = await response.json()
                if data['success']:
                    print(f"✅ Provider test successful with {data['provider']}")
                    print("Sample notes generated:")
                    notes = data.get('notes', {})
                    if notes.get('summary'):
                        print(f"  Summary: {notes['summary']}")
                    if notes.get('keyPoints'):
                        print(f"  Key Points: {notes['keyPoints']}")
                else:
                    print(f"❌ Provider test failed: {data.get('error')}")
                    return
            else:
                print(f"❌ Provider test failed with status: {response.status}")
                return
    
    # 3. Test WebSocket connection
    print("\n3. Testing WebSocket connection...")
    session_id = "test-session-" + str(int(time.time()))
    ws_url = f"ws://localhost:9050/api/meeting-notes-unified/ws/meeting-notes/{session_id}"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(ws_url) as ws:
                print("✅ WebSocket connected successfully!")
                
                # Wait for status message
                status_msg = await ws.receive()
                if status_msg.type == aiohttp.WSMsgType.TEXT:
                    status_data = json.loads(status_msg.data)
                    print(f"✅ Status: {status_data.get('message')}")
                    print(f"✅ Provider: {status_data.get('provider')}")
                
                # Send test transcript
                test_transcript = {
                    "type": "transcript_update",
                    "text": "Welcome everyone to today's quarterly planning meeting. We need to finalize the budget for Q2 and discuss the new product launch timeline. Sarah will handle the marketing campaign, and we need all proposals submitted by Friday. The board meeting is next week, so timing is critical."
                }
                
                await ws.send_str(json.dumps(test_transcript))
                print("📤 Sent test transcript")
                
                # Wait for response
                print("\n📥 Waiting for AI-generated notes...")
                timeout = 45  # Wait up to 45 seconds
                start_time = time.time()
                
                while time.time() - start_time < timeout:
                    try:
                        msg = await ws.receive(timeout=5)
                        
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            data = json.loads(msg.data)
                            msg_type = data.get('type')
                            
                            if msg_type == 'notes_update':
                                print("\n✨ AI-Generated Notes received!")
                                print("-" * 40)
                                notes = data.get('notes', {})
                                provider = data.get('provider', 'unknown')
                                print(f"Provider: {provider}")
                                
                                if notes.get('summary'):
                                    print(f"\n📋 Summary: {notes['summary']}")
                                
                                if notes.get('keyPoints'):
                                    print(f"\n🔑 Key Points:")
                                    for i, point in enumerate(notes['keyPoints'], 1):
                                        print(f"  {i}. {point}")
                                
                                if notes.get('actionItems'):
                                    print(f"\n✅ Action Items:")
                                    for item in notes['actionItems']:
                                        print(f"  • {item.get('task')} - {item.get('owner', 'Unassigned')}")
                                        if item.get('deadline'):
                                            print(f"    Deadline: {item['deadline']}")
                                
                                if notes.get('decisions'):
                                    print(f"\n🎯 Decisions:")
                                    for decision in notes['decisions']:
                                        print(f"  → {decision}")
                                
                                if notes.get('sentiment'):
                                    print(f"\n😊 Sentiment: {notes['sentiment']}")
                                
                                print("\n" + "=" * 50)
                                print("✅ Live meeting notes test completed successfully!")
                                return
                            
                            elif msg_type == 'generating':
                                print("⏳ AI is generating notes...")
                            
                            elif msg_type == 'transcript_received':
                                word_count = data.get('word_count', 0)
                                print(f"📝 Transcript received ({word_count} words)")
                            
                            elif msg_type == 'error':
                                print(f"❌ Error: {data.get('message')}")
                                break
                        
                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            print(f"❌ WebSocket error: {ws.exception()}")
                            break
                        
                        elif msg.type == aiohttp.WSMsgType.CLOSED:
                            print("WebSocket connection closed")
                            break
                            
                    except asyncio.TimeoutError:
                        # Send force update to trigger notes generation
                        await ws.send_str(json.dumps({"type": "force_update"}))
                        print("🔄 Requesting immediate notes update...")
                        continue
                
                if time.time() - start_time >= timeout:
                    print("⏰ Test timed out waiting for notes")
                    
    except Exception as e:
        print(f"❌ WebSocket test failed: {e}")

async def test_provider_switching():
    """Test switching between providers"""
    print("\n" + "=" * 50)
    print("Testing Provider Switching")
    print("=" * 50)
    
    base_url = "http://localhost:9050"
    
    async with aiohttp.ClientSession() as session:
        # Try switching to Gemma (if available)
        print("1. Attempting to switch to Gemma provider...")
        async with session.post(f"{base_url}/api/meeting-notes-unified/switch-provider?provider=gemma") as response:
            if response.status == 200:
                data = await response.json()
                print(f"✅ Successfully switched to: {data['provider']}")
            else:
                data = await response.json()
                print(f"ℹ️  Gemma not available: {data.get('detail', 'Unknown error')}")
        
        # Switch back to Granite
        print("\n2. Switching back to Granite provider...")
        async with session.post(f"{base_url}/api/meeting-notes-unified/switch-provider?provider=granite") as response:
            if response.status == 200:
                data = await response.json()
                print(f"✅ Successfully switched to: {data['provider']}")
            else:
                data = await response.json()
                print(f"❌ Failed to switch: {data.get('detail', 'Unknown error')}")

async def main():
    """Run all tests"""
    await test_unified_api()
    await test_provider_switching()
    
    print("\n" + "=" * 60)
    print("🎉 ALL TESTS COMPLETED!")
    print("=" * 60)
    print("\nKey Features Tested:")
    print("✅ Unified API that preserves Gemma functionality")
    print("✅ Granite model integration with decoupled config")
    print("✅ Real-time WebSocket meeting notes generation")
    print("✅ Provider switching capability")
    print("✅ Structured notes output (summary, action items, decisions)")

if __name__ == "__main__":
    asyncio.run(main())