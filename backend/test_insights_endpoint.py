#!/usr/bin/env python3
"""Test script for the insights endpoint."""

import requests
import json
import uuid

BASE_URL = "http://localhost:9050"

def test_insights_endpoint():
    """Test the new insights endpoint."""
    
    print("🧪 Testing Insights Endpoint\n")
    
    # Wait for backend to be ready
    import time
    print("Waiting for backend to start...")
    for i in range(10):
        try:
            response = requests.get(f"{BASE_URL}/api/status")
            if response.status_code == 200:
                print("✅ Backend is ready\n")
                break
        except:
            pass
        time.sleep(1)
    else:
        print("❌ Backend not responding after 10 seconds")
        return
    
    # Step 1: Create a session
    print("1. Creating a test session...")
    session_data = {
        "name": "Test Meeting for Insights",
        "description": "Testing the insights endpoint",
        "participants": ["Alice", "Bob"],
        "tags": ["test", "insights"]
    }
    
    response = requests.post(
        f"{BASE_URL}/api/simple/recording-sessions",
        json=session_data
    )
    
    if response.status_code != 200:
        print(f"   ❌ Failed to create session: {response.status_code}")
        print(f"   Response: {response.text}")
        return
    
    session = response.json()
    session_id = session["id"]
    print(f"   ✅ Session created: {session_id}")
    
    # Step 2: Add some mock transcription data
    print("\n2. Simulating transcription data...")
    # We'll call the insights endpoint which should handle empty transcript
    
    # Step 3: Test insights endpoint with minimal data
    print("\n3. Testing insights endpoint (minimal data)...")
    response = requests.post(
        f"{BASE_URL}/api/simple/recording-sessions/{session_id}/insights"
    )
    
    if response.status_code == 200:
        insights = response.json()
        print(f"   ✅ Insights endpoint working!")
        print(f"   Summary: {insights.get('summary', 'N/A')}")
        print(f"   Key Points: {len(insights.get('key_points', []))} points")
        print(f"   Action Items: {len(insights.get('action_items', []))} items")
        print(f"   Sentiment: {insights.get('sentiment', 'N/A')}")
    elif response.status_code == 405:
        print(f"   ❌ Method not allowed - endpoint not found")
        print(f"   The endpoint POST /api/simple/recording-sessions/{session_id}/insights does not exist")
    else:
        print(f"   ❌ Failed with status {response.status_code}")
        print(f"   Response: {response.text}")
    
    # Step 4: Start recording to generate real transcript
    print("\n4. Starting recording to generate transcript...")
    response = requests.post(
        f"{BASE_URL}/api/simple/recording-sessions/{session_id}/start"
    )
    
    if response.status_code == 200:
        print("   ✅ Recording started")
        
        # Wait a moment
        time.sleep(2)
        
        # Stop recording
        response = requests.post(
            f"{BASE_URL}/api/simple/recording-sessions/{session_id}/stop"
        )
        if response.status_code == 200:
            print("   ✅ Recording stopped")
    
    # Step 5: Test insights endpoint again
    print("\n5. Testing insights endpoint (with data)...")
    response = requests.post(
        f"{BASE_URL}/api/simple/recording-sessions/{session_id}/insights"
    )
    
    if response.status_code == 200:
        insights = response.json()
        print(f"   ✅ Insights generated successfully!")
        print("\n   Full response:")
        print(json.dumps(insights, indent=2))
    else:
        print(f"   ❌ Failed with status {response.status_code}")
        print(f"   Response: {response.text}")
    
    print("\n🎉 Testing complete!")

if __name__ == "__main__":
    test_insights_endpoint()