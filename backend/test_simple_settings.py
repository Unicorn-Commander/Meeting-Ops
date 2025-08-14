#!/usr/bin/env python3
"""Test script for simple settings endpoints."""

import requests
import json
import sys

BASE_URL = "http://localhost:9050"

def test_endpoints():
    """Test all simple settings endpoints."""
    
    print("🧪 Testing Simple Settings Endpoints\n")
    
    # Test 1: Get all settings
    print("1. Testing GET /api/simple/settings...")
    try:
        response = requests.get(f"{BASE_URL}/api/simple/settings")
        if response.status_code == 200:
            print("   ✅ Success - Settings loaded")
            settings = response.json()
            print(f"   Current model: {settings.get('transcriptionModel', 'N/A')}")
        else:
            print(f"   ❌ Failed with status {response.status_code}")
            print(f"   Response: {response.text}")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # Test 2: Get audio devices
    print("\n2. Testing GET /api/simple/audio-devices...")
    try:
        response = requests.get(f"{BASE_URL}/api/simple/audio-devices")
        if response.status_code == 200:
            devices = response.json()
            print(f"   ✅ Success - Found {len(devices)} audio device(s)")
            if isinstance(devices, list) and len(devices) > 0:
                for device in devices:
                    if isinstance(device, dict):
                        print(f"      - {device.get('label', 'Unknown')} ({device.get('id', 'Unknown')})")
                    else:
                        print(f"      Device data format issue: {device}")
        else:
            print(f"   ❌ Failed with status {response.status_code}")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # Test 3: Get network info
    print("\n3. Testing GET /api/simple/system/network...")
    try:
        response = requests.get(f"{BASE_URL}/api/simple/system/network")
        if response.status_code == 200:
            network = response.json()
            print(f"   ✅ Success - Network info retrieved")
            print(f"      Hostname: {network.get('hostname', 'N/A')}")
            print(f"      IP: {network.get('ipAddress', 'N/A')}")
            print(f"      Interface: {network.get('interface', 'N/A')}")
        else:
            print(f"   ❌ Failed with status {response.status_code}")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # Test 4: Get system info
    print("\n4. Testing GET /api/simple/system/info...")
    try:
        response = requests.get(f"{BASE_URL}/api/simple/system/info")
        if response.status_code == 200:
            info = response.json()
            print(f"   ✅ Success - System info retrieved")
            print(f"      Platform: {info.get('platform', 'N/A')}")
            print(f"      CPU Count: {info.get('cpu_count', 'N/A')}")
            print(f"      Memory: {info.get('memory_total_gb', 'N/A')} GB")
        else:
            print(f"   ❌ Failed with status {response.status_code}")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # Test 5: Save settings
    print("\n5. Testing POST /api/simple/settings...")
    try:
        # Get current settings first
        current = requests.get(f"{BASE_URL}/api/simple/settings").json()
        # Modify one setting
        current['transcriptionLanguage'] = 'en'
        
        response = requests.post(
            f"{BASE_URL}/api/simple/settings",
            json=current,
            headers={'Content-Type': 'application/json'}
        )
        if response.status_code == 200:
            print("   ✅ Success - Settings saved")
        else:
            print(f"   ❌ Failed with status {response.status_code}")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # Test 6: Test audio volume
    print("\n6. Testing GET /api/simple/audio/volume/hw_0-0...")
    try:
        response = requests.get(f"{BASE_URL}/api/simple/audio/volume/hw_0-0")
        if response.status_code == 200:
            volume = response.json()
            print(f"   ✅ Success - Current volume: {volume.get('volume', 'N/A')}%")
        else:
            print(f"   ❌ Failed with status {response.status_code}")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    print("\n🎉 Testing complete!")

if __name__ == "__main__":
    # Check if backend is running
    try:
        response = requests.get(f"{BASE_URL}/api/status")
        if response.status_code == 200:
            print("✅ Backend is running\n")
            test_endpoints()
        else:
            print("❌ Backend returned unexpected status")
    except requests.exceptions.ConnectionError:
        print("❌ Backend is not running!")
        print("Please start it with: cd backend && ./start-backend.sh")
        sys.exit(1)