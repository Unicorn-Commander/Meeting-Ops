#!/usr/bin/env python3
"""Test script for automatic summarization system"""

import asyncio
import websockets
import json
import time
from datetime import datetime
import requests

BASE_URL = "http://localhost:9050"
WS_URL = "ws://localhost:9050"

def print_message(msg_type, message):
    """Pretty print messages with timestamps"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    symbols = {
        "info": "ℹ️",
        "success": "✅",
        "error": "❌",
        "websocket": "🔌",
        "summary": "📝",
        "settings": "⚙️"
    }
    symbol = symbols.get(msg_type, "•")
    print(f"[{timestamp}] {symbol} {message}")

async def test_auto_summarization():
    """Test the automatic summarization system"""
    
    print("\n" + "="*60)
    print("🧪 TESTING AUTOMATIC SUMMARIZATION SYSTEM")
    print("="*60 + "\n")
    
    # Step 1: Check current settings
    print_message("settings", "Checking current auto-summarization settings...")
    response = requests.get(f"{BASE_URL}/api/auto-summary/settings")
    if response.status_code == 200:
        settings = response.json()
        print_message("success", f"Live Summarization: {settings['enableLiveSummarization']}")
        print_message("success", f"Update Interval: {settings['summaryUpdateInterval']} seconds")
    else:
        print_message("error", "Failed to get settings")
    
    # Step 2: Update settings to enable with short interval for testing
    print_message("settings", "\nUpdating settings for testing (15 second interval)...")
    response = requests.put(
        f"{BASE_URL}/api/auto-summary/settings",
        params={
            "enableLiveSummarization": True,
            "summaryUpdateInterval": 15  # Short interval for testing
        }
    )
    if response.status_code == 200:
        print_message("success", "Settings updated successfully")
    else:
        print_message("error", f"Failed to update settings: {response.text}")
    
    # Step 3: Create a test session
    print_message("info", "\nCreating test recording session...")
    session_data = {
        "name": "Auto-Summary Test Session",
        "description": "Testing automatic summarization",
        "participants": ["Alice", "Bob", "Charlie"]
    }
    
    response = requests.post(
        f"{BASE_URL}/api/simple/recording-sessions",
        json=session_data
    )
    
    if response.status_code != 200:
        print_message("error", f"Failed to create session: {response.text}")
        return
    
    session = response.json()
    session_id = session["id"]
    print_message("success", f"Session created: {session_id}")
    
    # Step 4: Connect to WebSocket with auto-summary
    print_message("websocket", f"\nConnecting to WebSocket with auto-summary...")
    
    try:
        async with websockets.connect(f"{WS_URL}/ws/transcription-auto/{session_id}") as websocket:
            print_message("success", "WebSocket connected!")
            
            # Track received messages
            summary_count = 0
            start_time = time.time()
            
            # Listen for messages
            async def receive_messages():
                nonlocal summary_count
                
                while True:
                    try:
                        message = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                        data = json.loads(message)
                        
                        if data["type"] == "connection":
                            print_message("websocket", f"Connection confirmed: {data['message']}")
                            if "features" in data:
                                features = data["features"]
                                print_message("info", f"  - Auto-summarization: {features.get('auto_summarization')}")
                                print_message("info", f"  - Summary interval: {features.get('summary_interval')}s")
                        
                        elif data["type"] == "auto_summary_status":
                            status = "enabled" if data["enabled"] else "disabled"
                            print_message("settings", f"Auto-summary {status}: {data.get('message', '')}")
                        
                        elif data["type"] == "auto_summary":
                            summary_count += 1
                            elapsed = int(time.time() - start_time)
                            print_message("summary", f"[{elapsed}s] Auto-summary #{summary_count} received!")
                            
                            summary = data.get("summary", {})
                            if isinstance(summary, dict):
                                print(f"    Summary: {summary.get('summary', 'N/A')}")
                                print(f"    Key Points: {len(summary.get('key_points', []))} points")
                                print(f"    Next update in: {data.get('next_update_in', 'N/A')} seconds")
                        
                        elif data["type"] == "keepalive":
                            # Don't print keepalives to reduce noise
                            pass
                        
                        else:
                            print_message("info", f"Received: {data['type']}")
                            
                    except asyncio.TimeoutError:
                        # No message received, continue
                        pass
                    except Exception as e:
                        print_message("error", f"Error receiving message: {e}")
                        break
            
            # Send test commands
            async def send_commands():
                await asyncio.sleep(2)
                
                # Request status
                print_message("info", "\nRequesting status...")
                await websocket.send(json.dumps({"type": "get_status"}))
                
                await asyncio.sleep(5)
                
                # Request manual summary
                print_message("info", "\nRequesting manual summary...")
                await websocket.send(json.dumps({"type": "request_summary"}))
                
                await asyncio.sleep(20)  # Wait for auto-summary
                
                # Toggle off
                print_message("settings", "\nDisabling auto-summary...")
                await websocket.send(json.dumps({
                    "type": "toggle_auto_summary",
                    "enabled": False
                }))
                
                await asyncio.sleep(5)
                
                # Toggle back on
                print_message("settings", "\nRe-enabling auto-summary...")
                await websocket.send(json.dumps({
                    "type": "toggle_auto_summary",
                    "enabled": True
                }))
                
                await asyncio.sleep(20)  # Wait for another auto-summary
            
            # Run both tasks concurrently
            receive_task = asyncio.create_task(receive_messages())
            send_task = asyncio.create_task(send_commands())
            
            # Wait for test duration
            await asyncio.sleep(60)  # Run test for 60 seconds
            
            # Cancel tasks
            receive_task.cancel()
            send_task.cancel()
            
            print_message("info", "\nTest duration complete, closing connection...")
            
    except Exception as e:
        print_message("error", f"WebSocket error: {e}")
    
    # Step 5: Check final status via REST API
    print_message("info", "\nChecking final status via REST API...")
    response = requests.post(
        f"{BASE_URL}/api/auto-summary/control/{session_id}",
        params={"action": "status"}
    )
    
    if response.status_code == 200:
        status = response.json()["data"]
        print_message("success", f"Final status:")
        print(f"    Enabled: {status.get('enabled')}")
        print(f"    Running: {status.get('running')}")
        print(f"    Interval: {status.get('interval')}s")
        print(f"    Has cached summary: {status.get('cached_summary')}")
    
    # Step 6: Reset settings to default
    print_message("settings", "\nResetting to default settings (60 second interval)...")
    response = requests.put(
        f"{BASE_URL}/api/auto-summary/settings",
        params={
            "enableLiveSummarization": True,
            "summaryUpdateInterval": 60
        }
    )
    
    print("\n" + "="*60)
    print_message("success", "TEST COMPLETE!")
    print(f"    Total auto-summaries received: {summary_count}")
    print("="*60 + "\n")

async def main():
    """Main test function"""
    # First check if backend is running
    try:
        response = requests.get(f"{BASE_URL}/api/status")
        if response.status_code == 200:
            print_message("success", "Backend is running")
        else:
            print_message("error", "Backend returned unexpected status")
            return
    except requests.exceptions.ConnectionError:
        print_message("error", "Backend is not running!")
        print("Please start it with: cd backend && ./start-backend.sh")
        return
    
    # Run the test
    await test_auto_summarization()

if __name__ == "__main__":
    asyncio.run(main())