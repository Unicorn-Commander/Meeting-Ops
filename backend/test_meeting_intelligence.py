#!/usr/bin/env python3
"""
Test Meeting Intelligence with configurable LLM endpoints
"""

import requests
import json
import time

BASE_URL = "http://localhost:9050"

def get_auth_token():
    """Get authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        data={"username": "admin", "password": "admin123"}
    )
    if response.status_code == 200:
        return response.json().get("access_token")
    return None

def test_llm_endpoints(token):
    """Test LLM endpoint configuration"""
    headers = {"Authorization": f"Bearer {token}"}
    
    print("\n" + "="*60)
    print("TESTING LLM ENDPOINTS")
    print("="*60)
    
    # Get current endpoints
    response = requests.get(f"{BASE_URL}/api/llm-settings/endpoints", headers=headers)
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Found {len(data['endpoints'])} endpoints")
        print(f"   Active: {data['active_endpoint']}")
        print(f"   Fallback: {'Enabled' if data['fallback_enabled'] else 'Disabled'}")
        
        # Test switching to remote endpoint
        print("\nSwitching to remote endpoint...")
        remote_endpoint = "remote_gemma2_9b"
        
        # First, update the endpoint to use correct model
        update_response = requests.put(
            f"{BASE_URL}/api/llm-settings/endpoints/{remote_endpoint}",
            json={"model": "gemma2:9b"},
            headers=headers
        )
        
        if update_response.status_code == 200:
            print(f"✅ Updated remote endpoint to use gemma2:9b")
        
        # Activate the remote endpoint
        activate_response = requests.post(
            f"{BASE_URL}/api/llm-settings/endpoints/{remote_endpoint}/activate",
            headers=headers
        )
        
        if activate_response.status_code == 200:
            print(f"✅ Activated {remote_endpoint}")
            return True
        else:
            print(f"❌ Failed to activate: {activate_response.text}")
    else:
        print(f"❌ Failed to get endpoints: {response.text}")
    
    return False

def test_meeting_intelligence(token):
    """Test Meeting Intelligence features"""
    headers = {"Authorization": f"Bearer {token}"}
    
    print("\n" + "="*60)
    print("TESTING MEETING INTELLIGENCE")
    print("="*60)
    
    # Sample transcript for testing
    sample_transcript = """
    John: Good morning everyone, let's start our project status meeting.
    
    Sarah: Thanks John. I've completed the API integration we discussed last week. 
    The endpoints are now fully functional and tested.
    
    John: Excellent work Sarah. What about the performance improvements?
    
    Sarah: We've achieved a 40% reduction in response time by implementing caching 
    and optimizing our database queries. The NPU acceleration is working perfectly.
    
    Mike: That's great news. I've been working on the UI updates. The new dashboard 
    is almost ready. I just need another day to finish the responsive design.
    
    John: Perfect. Mike, can you have that completed by Friday?
    
    Mike: Yes, definitely. I'll have it done by end of day Thursday actually.
    
    Sarah: I can help with testing once Mike is done. We should also update the 
    documentation to reflect these changes.
    
    John: Good point. Let's make sure to do that. So our action items are:
    1. Mike to complete UI updates by Thursday
    2. Sarah to test the UI once complete
    3. Update documentation for all changes
    
    Does everyone agree with this plan?
    
    Sarah: Yes, sounds good.
    
    Mike: Agreed.
    
    John: Great, let's reconvene on Friday to review everything. Thanks everyone!
    """
    
    # Test Live Notes generation
    print("\n1. Testing Live Notes Generation...")
    live_notes_response = requests.post(
        f"{BASE_URL}/api/meeting-intelligence/live-notes",
        json={
            "transcript": sample_transcript,
            "templates": ["executive-summary", "action-alerts"],
            "session_id": "test-session-001"
        },
        headers=headers
    )
    
    if live_notes_response.status_code == 200:
        notes = live_notes_response.json()
        print("✅ Live notes generated successfully!")
        print(f"   Type: {notes.get('type')}")
        print(f"   Session: {notes.get('session_id')}")
        print(f"   Templates used: {notes.get('templates_used')}")
        
        if 'notes' in notes and notes['notes']:
            print("\n   Generated Notes:")
            for key, value in notes['notes'].items():
                print(f"   - {key}: {str(value)[:100]}...")
    else:
        print(f"❌ Failed to generate live notes: {live_notes_response.status_code}")
        print(f"   Error: {live_notes_response.text}")
    
    # Test Final Report generation
    print("\n2. Testing Final Report Generation...")
    final_report_response = requests.post(
        f"{BASE_URL}/api/meeting-intelligence/final-report",
        json={
            "transcript": sample_transcript,
            "templates": ["full-report", "action-items"],
            "session_id": "test-session-001"
        },
        headers=headers
    )
    
    if final_report_response.status_code == 200:
        report = final_report_response.json()
        print("✅ Final report generated successfully!")
        print(f"   Type: {report.get('type')}")
        print(f"   Session: {report.get('session_id')}")
        print(f"   Templates used: {report.get('templates_used')}")
        print(f"   Transcript length: {report.get('transcript_length')} chars")
        print(f"   Context used: {report.get('context_used')} chars")
        
        if 'report' in report and report['report']:
            print("\n   Generated Report:")
            for key, value in report['report'].items():
                print(f"   - {key}: {str(value)[:100]}...")
    else:
        print(f"❌ Failed to generate final report: {final_report_response.status_code}")
        print(f"   Error: {final_report_response.text}")
    
    # Test Model Status
    print("\n3. Testing Model Status...")
    model_status_response = requests.get(
        f"{BASE_URL}/api/meeting-intelligence/model-status",
        headers=headers
    )
    
    if model_status_response.status_code == 200:
        status = model_status_response.json()
        print("✅ Model status retrieved!")
        print(f"   Status: {status.get('status')}")
        print(f"   Endpoint: {status.get('endpoint')}")
        print(f"   Provider: {status.get('provider')}")
        print(f"   URL: {status.get('url')}")
        print(f"   Context window: {status.get('context_window')} tokens")
        
        if 'capabilities' in status:
            print("   Capabilities:")
            for cap in status['capabilities']:
                print(f"     - {cap}")
    else:
        print(f"❌ Failed to get model status: {model_status_response.text}")

def test_endpoint_switching(token):
    """Test switching between endpoints"""
    headers = {"Authorization": f"Bearer {token}"}
    
    print("\n" + "="*60)
    print("TESTING ENDPOINT SWITCHING")
    print("="*60)
    
    endpoints_to_test = ["local_gemma3n", "remote_gemma2_9b"]
    
    for endpoint_name in endpoints_to_test:
        print(f"\nSwitching to {endpoint_name}...")
        
        # Activate endpoint
        response = requests.post(
            f"{BASE_URL}/api/llm-settings/endpoints/{endpoint_name}/activate",
            headers=headers
        )
        
        if response.status_code == 200:
            print(f"✅ Activated {endpoint_name}")
            
            # Test with a simple prompt
            test_response = requests.post(
                f"{BASE_URL}/api/meeting-intelligence/live-notes",
                json={
                    "transcript": "Quick test: The meeting is about improving performance.",
                    "templates": ["executive-summary"],
                    "session_id": f"test-{endpoint_name}"
                },
                headers=headers
            )
            
            if test_response.status_code == 200:
                print(f"✅ Successfully generated notes with {endpoint_name}")
            else:
                print(f"⚠️  Failed to generate with {endpoint_name}: {test_response.status_code}")
        else:
            print(f"❌ Failed to activate {endpoint_name}")

def main():
    print("🚀 Meeting Intelligence Test Suite")
    print("="*60)
    
    # Get auth token
    print("Authenticating...")
    token = get_auth_token()
    
    if not token:
        print("❌ Failed to authenticate")
        return
    
    print("✅ Authentication successful")
    
    # Run tests
    if test_llm_endpoints(token):
        test_meeting_intelligence(token)
        test_endpoint_switching(token)
    
    print("\n" + "="*60)
    print("✅ Test suite completed!")
    print("="*60)

if __name__ == "__main__":
    main()