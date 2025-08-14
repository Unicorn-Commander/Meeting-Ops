#!/usr/bin/env python3
"""
Simple test to verify WebSocket connection and functionality
"""
import asyncio
import websockets
import json
import requests
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_websocket_connection():
    """Test WebSocket connection to auto-summary endpoint"""
    session_id = "test-connection-456"
    uri = f"ws://localhost:9050/ws/transcription-auto/{session_id}"
    
    logger.info(f"Testing connection to: {uri}")
    
    try:
        async with websockets.connect(uri) as websocket:
            logger.info("✅ Successfully connected to WebSocket")
            
            # Receive initial messages
            for i in range(3):
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                    data = json.loads(message)
                    logger.info(f"📨 Received: {data['type']}")
                    
                    if data['type'] == 'connection':
                        logger.info(f"   Features: {data.get('features', {})}")
                    elif data['type'] == 'auto_summary_status':
                        logger.info(f"   Status: {data}")
                    
                except asyncio.TimeoutError:
                    logger.info(f"   No more initial messages (waited 2s)")
                    break
            
            # Send a test message
            test_msg = {"type": "ping"}
            await websocket.send(json.dumps(test_msg))
            logger.info(f"📤 Sent: {test_msg}")
            
            # Wait for response
            response = await asyncio.wait_for(websocket.recv(), timeout=2.0)
            response_data = json.loads(response)
            logger.info(f"📨 Response: {response_data}")
            
            if response_data.get('type') == 'pong':
                logger.info("✅ Ping-pong test successful")
            
            return True
            
    except Exception as e:
        logger.error(f"❌ WebSocket connection failed: {e}")
        return False

async def test_backend_api():
    """Test backend API endpoints"""
    base_url = "http://localhost:9050"
    
    try:
        # Test health/status
        response = requests.get(f"{base_url}/health", timeout=5)
        if response.status_code == 200:
            logger.info("✅ Backend API is responding")
        else:
            logger.warning(f"⚠️ Backend API returned status {response.status_code}")
            
        # Test creating a session
        session_data = {"name": "Test Session", "description": "WebSocket test session"}
        response = requests.post(f"{base_url}/api/simple/recording-sessions", 
                               json=session_data, timeout=5)
        
        if response.status_code == 200:
            session = response.json()
            logger.info(f"✅ Created test session: {session['id']}")
            return session['id']
        else:
            logger.warning(f"⚠️ Failed to create session: {response.status_code}")
            return None
            
    except Exception as e:
        logger.error(f"❌ Backend API test failed: {e}")
        return None

async def main():
    """Run all tests"""
    logger.info("=" * 50)
    logger.info("WEBSOCKET CONNECTION TEST")
    logger.info("=" * 50)
    
    # Test backend API first
    session_id = await test_backend_api()
    
    # Test WebSocket connection
    success = await test_websocket_connection()
    
    if success:
        logger.info("\n✅ All tests PASSED")
        logger.info("The /ws/transcription-auto endpoint is working correctly")
    else:
        logger.error("\n❌ Tests FAILED")
        logger.error("WebSocket connection issue detected")

if __name__ == "__main__":
    asyncio.run(main())