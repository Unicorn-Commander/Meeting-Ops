#!/usr/bin/env python3
"""
Test script for new API endpoints from API Delta Document
"""
import requests
import json
import sys
from datetime import datetime

# Configuration
BASE_URL = "http://localhost:9050"
TEST_SESSION_ID = "test-session-123"

def test_endpoint(method, url, data=None, expected_status=200):
    """Test an API endpoint"""
    try:
        print(f"\n🧪 Testing {method} {url}")
        
        if method == "GET":
            response = requests.get(url)
        elif method == "POST":
            response = requests.post(url, json=data)
        elif method == "PUT":
            response = requests.put(url, json=data)
        elif method == "DELETE":
            response = requests.delete(url)
        else:
            raise ValueError(f"Unsupported method: {method}")
        
        print(f"   Status: {response.status_code}")
        
        if response.status_code == expected_status:
            print(f"   ✅ Success")
            try:
                response_data = response.json()
                print(f"   Response: {json.dumps(response_data, indent=2)[:200]}...")
                return response_data
            except:
                print(f"   Response: {response.text[:200]}...")
                return response.text
        else:
            print(f"   ❌ Failed - Expected {expected_status}, got {response.status_code}")
            print(f"   Error: {response.text}")
            return None
            
    except Exception as e:
        print(f"   ❌ Exception: {e}")
        return None

def main():
    """Run API tests"""
    print("🚀 Testing New API Endpoints (API Delta Document)")
    print("=" * 50)
    
    # Test application settings
    print("\n📋 Application Settings Tests")
    
    # Get application settings
    settings = test_endpoint("GET", f"{BASE_URL}/api/settings/application")
    
    if settings:
        # Update application settings
        settings["transcriptionModel"] = "large-v2"
        settings["enableNPUAcceleration"] = True
        test_endpoint("PUT", f"{BASE_URL}/api/settings/application", settings)
    
    # Test agent settings
    print("\n🤖 Agent Settings Tests")
    
    # Get agent settings
    agent_settings = test_endpoint("GET", f"{BASE_URL}/api/settings/agents")
    
    # Create prompt template
    new_prompt = {
        "id": "test-prompt-1",
        "name": "Test Prompt",
        "description": "A test prompt for validation",
        "prompt": "Test prompt content: {transcript}",
        "category": "test",
        "isActive": True
    }
    test_endpoint("POST", f"{BASE_URL}/api/settings/agents/prompts", new_prompt)
    
    # Test vocabulary management
    print("\n📚 Vocabulary Management Tests")
    
    # Get vocabulary
    vocab = test_endpoint("GET", f"{BASE_URL}/api/vocabulary")
    
    # Add vocabulary term
    new_term = {
        "term": "API",
        "expansion": "Application Programming Interface", 
        "category": "technology",
        "priority": 10,
        "contextHints": ["software", "programming"],
        "isActive": True
    }
    test_endpoint("POST", f"{BASE_URL}/api/vocabulary/terms", new_term)
    
    # Test live meeting intelligence
    print("\n🧠 Live Meeting Intelligence Tests")
    
    # Get live templates (may fail if session doesn't exist)
    test_endpoint("GET", f"{BASE_URL}/api/meeting-intelligence-real/live-templates/{TEST_SESSION_ID}", expected_status=404)
    
    # Generate template
    generate_request = {
        "session_id": TEST_SESSION_ID,
        "template_id": "executive-summary"
    }
    test_endpoint("POST", f"{BASE_URL}/api/meeting-intelligence-real/generate-template", generate_request, expected_status=404)
    
    # Test session templates
    print("\n📄 Session Templates Tests")
    
    # Get session templates
    test_endpoint("GET", f"{BASE_URL}/api/sessions/{TEST_SESSION_ID}/templates")
    
    # Save template content
    template_content = {
        "content": "This is test template content for session templates."
    }
    test_endpoint("PUT", f"{BASE_URL}/api/sessions/{TEST_SESSION_ID}/templates/test-template", template_content)
    
    # Test summarization templates fix
    print("\n📝 Summarization Templates Tests")
    
    # Get summarization templates (should return proper array)
    templates = test_endpoint("GET", f"{BASE_URL}/api/summarization-templates")
    
    if templates and isinstance(templates, list):
        print(f"   ✅ Templates returned as array with {len(templates)} items")
    else:
        print(f"   ❌ Templates not returned as expected array")
    
    print("\n🎉 API Testing Complete!")
    print("Note: Some tests may fail if sessions don't exist - this is expected")


if __name__ == "__main__":
    main()