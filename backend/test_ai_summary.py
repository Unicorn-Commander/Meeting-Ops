#!/usr/bin/env python3
"""Test AI summarization is working"""

import requests
import time

BASE_URL = "http://localhost:9050"

def login():
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        data={"username": "admin", "password": "admin123"}
    )
    return response.json()["access_token"]

def test_ai_summary():
    token = login()
    headers = {"Authorization": f"Bearer {token}"}
    
    print("🤖 Testing AI Summarization")
    print("="*50)
    
    # Test transcript
    transcript = """
    John: Good morning everyone, let's start our project status meeting.
    Sarah: Thanks John. I've completed the API integration with 220x NPU acceleration.
    Mike: Great work Sarah! The database optimization is also done.
    John: Excellent. What are our action items for this week?
    Sarah: I need to finish the live meeting notes feature by Friday.
    Mike: I'll assist with backend integration and custom vocabulary.
    John: Perfect. Any blockers?
    Sarah: No blockers from my side.
    Mike: All clear here.
    John: Great, let's meet again on Friday to review progress.
    """
    
    print("📝 Test Transcript:")
    print(transcript[:100] + "...")
    print()
    
    # Test live notes generation
    print("⚡ Generating Live Notes...")
    start = time.time()
    
    response = requests.post(
        f"{BASE_URL}/api/meeting-intelligence/live-notes",
        json={
            "transcript": transcript,
            "templates": ["executive-summary", "action-alerts", "key-decisions"],
            "session_id": "test-session"
        },
        headers=headers
    )
    
    elapsed = time.time() - start
    
    if response.status_code == 200:
        result = response.json()
        print(f"✅ Generated in {elapsed:.2f}s")
        
        if 'notes' in result:
            notes = result['notes']
            print("\n📊 AI Generated Notes:")
            print("-"*30)
            
            if isinstance(notes, dict):
                for key, value in notes.items():
                    print(f"\n{key.replace('_', ' ').title()}:")
                    if isinstance(value, str):
                        print(f"  {value[:200]}...")
                    elif isinstance(value, list):
                        for item in value[:3]:
                            print(f"  • {item}")
            else:
                print(notes)
    else:
        print(f"❌ Failed: {response.status_code}")
        print(response.text)
    
    print("\n" + "="*50)
    print("✅ AI Summarization is working!" if response.status_code == 200 else "❌ AI Summarization failed")

if __name__ == "__main__":
    test_ai_summary()