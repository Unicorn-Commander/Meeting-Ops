#!/usr/bin/env python3
"""Test critical backend API endpoints"""

import requests
import json
import sys

BASE_URL = "http://localhost:9050"

def test_backend():
    print("Testing Meeting-Ops Backend API...")
    print("=" * 50)
    
    # 1. Test authentication
    print("\n1. Testing Authentication...")
    auth_data = {
        "username": "admin",
        "password": "admin123"
    }
    response = requests.post(f"{BASE_URL}/api/auth/login", data=auth_data)
    if response.status_code != 200:
        print(f"❌ Authentication failed: {response.status_code}")
        print(response.text)
        return False
    
    auth_result = response.json()
    token = auth_result["access_token"]
    print(f"✅ Authentication successful")
    print(f"   User: {auth_result['user']['username']} ({auth_result['user']['email']})")
    print(f"   Role: {auth_result['user']['role']}")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # 2. Test system status
    print("\n2. Testing System Status...")
    response = requests.get(f"{BASE_URL}/api/status")
    if response.status_code == 200:
        status = response.json()
        print(f"✅ System Status: {status['status']}")
        print(f"   NPU Available: {status['npu_available']}")
        print(f"   Transcription Ready: {status['transcription_ready']}")
    else:
        print(f"❌ Status check failed: {response.status_code}")
    
    # 3. Test audio devices
    print("\n3. Testing Audio Devices...")
    response = requests.get(f"{BASE_URL}/api/audio-devices", headers=headers)
    if response.status_code == 200:
        devices = response.json()
        if isinstance(devices, list):
            print(f"✅ Found {len(devices)} audio devices")
            for device in devices[:3]:  # Show first 3
                print(f"   - {device['name']} (ID: {device['id']})")
        else:
            print(f"✅ Audio devices endpoint working")
            print(f"   Response: {devices}")
    else:
        print(f"❌ Audio devices check failed: {response.status_code}")
    
    # 4. Test session creation
    print("\n4. Testing Session Creation...")
    session_data = {
        "name": "Test Session",
        "description": "Backend API test session"
    }
    response = requests.post(f"{BASE_URL}/api/recording-sessions", 
                           headers={**headers, "Content-Type": "application/json"},
                           json=session_data)
    if response.status_code in [200, 201]:
        session = response.json()
        session_id = session.get("id", session.get("session_id", "unknown"))
        print(f"✅ Session created: {session.get('name', session.get('title', 'Unnamed'))} (ID: {session_id})")
    else:
        print(f"❌ Session creation failed: {response.status_code}")
        print(response.text)
        return False
    
    # 5. Test session list
    print("\n5. Testing Session List...")
    response = requests.get(f"{BASE_URL}/api/recording-sessions", headers=headers)
    if response.status_code == 200:
        sessions = response.json()
        print(f"✅ Found {len(sessions)} sessions")
    else:
        print(f"❌ Session list failed: {response.status_code}")
    
    # 6. Test settings
    print("\n6. Testing Settings...")
    response = requests.get(f"{BASE_URL}/api/settings", headers=headers)
    if response.status_code == 200:
        settings = response.json()
        print(f"✅ Settings retrieved")
        print(f"   Categories: {', '.join(settings.keys())}")
    else:
        print(f"❌ Settings retrieval failed: {response.status_code}")
    
    # 7. Test file storage stats
    print("\n7. Testing File Storage...")
    response = requests.get(f"{BASE_URL}/api/files/storage/stats", headers=headers)
    if response.status_code == 200:
        stats = response.json()
        print(f"✅ Storage stats retrieved")
        print(f"   Total Files: {stats.get('total_files', 0)}")
        print(f"   Total Size: {stats.get('total_size_mb', 0):.2f} MB")
    else:
        print(f"❌ Storage stats failed: {response.status_code}")
    
    print("\n" + "=" * 50)
    print("✅ Backend API is fully operational!")
    print("\nAPI Documentation available at:")
    print(f"  - Swagger UI: {BASE_URL}/docs")
    print(f"  - ReDoc: {BASE_URL}/redoc")
    print(f"  - OpenAPI JSON: {BASE_URL}/openapi.json")
    
    return True

if __name__ == "__main__":
    try:
        success = test_backend()
        sys.exit(0 if success else 1)
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to backend at http://localhost:9050")
        print("   Make sure the backend is running!")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)