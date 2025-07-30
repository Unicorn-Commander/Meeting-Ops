#!/usr/bin/env python3
"""Test recording API workflow"""

import httpx
import json
import asyncio

async def test_recording_workflow():
    base_url = "http://localhost:9050"
    
    async with httpx.AsyncClient() as client:
        # 1. Login
        print("1. Logging in...")
        login_response = await client.post(
            f"{base_url}/api/auth/login",
            data={"username": "admin", "password": "admin123"},
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        
        if login_response.status_code != 200:
            print(f"Login failed: {login_response.text}")
            return
            
        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        print("✓ Login successful")
        
        # 2. Check status
        print("\n2. Checking system status...")
        status_response = await client.get(f"{base_url}/api/status", headers=headers)
        status = status_response.json()
        print(f"✓ System status response: {json.dumps(status, indent=2)}")
        print(f"✓ Transcriber ready: {status.get('transcriber_ready', 'N/A')}, NPU: {status.get('npu_available', 'N/A')}")
        
        # 3. Create recording session
        print("\n3. Creating recording session...")
        session_response = await client.post(
            f"{base_url}/api/recording-sessions",
            json={"name": "Test Recording"},
            headers=headers
        )
        
        if session_response.status_code != 200:
            print(f"Failed to create session: {session_response.text}")
            return
            
        session_data = session_response.json()
        session_id = session_data["session"]["session_id"]
        print(f"✓ Created session: {session_id}")
        
        # 4. Start recording
        print("\n4. Starting recording...")
        start_response = await client.post(
            f"{base_url}/api/recording-sessions/{session_id}/start",
            headers=headers
        )
        
        if start_response.status_code != 200:
            print(f"Failed to start recording: {start_response.text}")
            return
            
        print("✓ Recording started")
        
        # 5. Wait a bit
        print("\n5. Recording for 5 seconds...")
        await asyncio.sleep(5)
        
        # 6. Stop recording
        print("\n6. Stopping recording...")
        stop_response = await client.post(
            f"{base_url}/api/recording-sessions/{session_id}/stop",
            headers=headers
        )
        
        if stop_response.status_code != 200:
            print(f"Failed to stop recording: {stop_response.text}")
            return
            
        print("✓ Recording stopped")
        
        # 7. Get session details
        print("\n7. Getting session details...")
        details_response = await client.get(
            f"{base_url}/api/recording-sessions/{session_id}",
            headers=headers
        )
        
        if details_response.status_code == 200:
            details = details_response.json()
            print(f"✓ Session details:")
            print(f"  - Duration: {details['session'].get('duration', 0)} seconds")
            print(f"  - Status: {details['session'].get('status', 'unknown')}")
            print(f"  - Transcriptions: {len(details.get('transcriptions', []))}")
            
            if details.get('transcriptions'):
                print("\n  Transcriptions:")
                for t in details['transcriptions'][:5]:  # Show first 5
                    print(f"    - {t['text']}")
        
        print("\n✓ Test completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_recording_workflow())