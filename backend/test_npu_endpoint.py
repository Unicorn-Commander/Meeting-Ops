#!/usr/bin/env python3
"""
Test NPU backend endpoints without needing microphone
"""

import asyncio
import aiohttp
import json

async def test_backend_endpoints():
    """Test key backend endpoints"""
    
    print("🧪 Testing Meeting-Ops NPU Backend Endpoints...")
    
    base_url = "http://localhost:9050"
    
    # Test status endpoint
    try:
        async with aiohttp.ClientSession() as session:
            print("\n📊 Testing system info endpoint...")
            async with session.get(f"{base_url}/api/system-info") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    print(f"✅ System info: {data.get('platform', 'Unknown')} - NPU: {data.get('npu_status', {}).get('device', 'Unknown')}")
                else:
                    print(f"❌ System info failed: {resp.status}")
            
            print("\n🤖 Testing NPU status endpoint...")
            async with session.get(f"{base_url}/api/system/npu-status") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    print(f"✅ NPU Status: {data.get('status', 'Unknown')} - Using NPU: {data.get('using_npu', False)}")
                else:
                    print(f"❌ NPU status failed: {resp.status}")
            
            print("\n🎯 Testing transcription test endpoint...")
            async with session.get(f"{base_url}/api/test-transcription") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    print(f"✅ Transcription test: {data.get('status', 'Unknown')}")
                    if data.get('result'):
                        print(f"   Result: {data.get('result', {}).get('text', 'No text')}")
                else:
                    print(f"❌ Transcription test failed: {resp.status}")
    
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        print("🔧 Make sure backend is running: ./venv/bin/python npu_main.py")
        return False
    
    print("\n✅ Backend endpoint testing completed!")
    return True

if __name__ == "__main__":
    asyncio.run(test_backend_endpoints())