#!/usr/bin/env python3
"""
Test the WebSocket integration to ensure transcription segments are broadcast properly
"""
import asyncio
import websockets
import json
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_websocket_auto():
    """Test the /ws/transcription-auto endpoint"""
    session_id = "test-session-123"
    uri = f"ws://localhost:9050/ws/transcription-auto/{session_id}"
    
    logger.info(f"Connecting to {uri}")
    
    try:
        async with websockets.connect(uri) as websocket:
            logger.info("Connected to WebSocket")
            
            # Receive initial connection message
            message = await websocket.recv()
            data = json.loads(message)
            logger.info(f"Initial message: {data['type']}")
            logger.info(f"Features: {json.dumps(data.get('features', {}), indent=2)}")
            
            # Keep receiving messages for 10 seconds
            timeout = 10
            start_time = asyncio.get_event_loop().time()
            transcription_count = 0
            summary_count = 0
            
            while asyncio.get_event_loop().time() - start_time < timeout:
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                    data = json.loads(message)
                    
                    if data['type'] == 'transcription':
                        transcription_count += 1
                        logger.info(f"Transcription #{transcription_count}: {data['segment'].get('text', '')[:50]}...")
                        logger.info(f"  Word count: {data.get('word_count', 0)} total, {data.get('segment_word_count', 0)} in segment")
                    elif data['type'] == 'auto_summary':
                        summary_count += 1
                        logger.info(f"Auto-summary #{summary_count}: {data['summary'].get('summary', '')[:100]}...")
                        logger.info(f"  Trigger: {data.get('trigger_reason', 'unknown')}")
                    elif data['type'] == 'keepalive':
                        logger.debug("Received keepalive")
                    else:
                        logger.info(f"Received {data['type']} message")
                        
                except asyncio.TimeoutError:
                    logger.debug("No message received in 1 second")
                    continue
            
            logger.info(f"\nTest completed:")
            logger.info(f"  Transcription segments received: {transcription_count}")
            logger.info(f"  Auto-summaries received: {summary_count}")
            
            # Test manual summary request
            logger.info("\nTesting manual summary request...")
            await websocket.send(json.dumps({
                "type": "request_summary"
            }))
            
            message = await asyncio.wait_for(websocket.recv(), timeout=5.0)
            data = json.loads(message)
            logger.info(f"Manual summary response: {data['type']}")
            
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        return False
    
    return True

async def simulate_transcription():
    """Simulate transcription segments being broadcast"""
    await asyncio.sleep(1)  # Wait for WebSocket to connect
    
    from api.websocket_transcription import broadcast_transcription_update
    
    session_id = "test-session-123"
    
    # Simulate a few transcription segments
    segments = [
        {"text": "Hello, this is the first segment of our meeting.", "start": 0, "end": 3},
        {"text": "We are discussing the new project timeline today.", "start": 3, "end": 6},
        {"text": "The deadline has been moved to next quarter.", "start": 6, "end": 9},
        {"text": "This will give us more time for thorough testing.", "start": 9, "end": 12},
        {"text": "Let's review the budget implications of this change.", "start": 12, "end": 15}
    ]
    
    for i, segment in enumerate(segments):
        await broadcast_transcription_update(session_id, segment)
        logger.info(f"Broadcast segment {i+1}: {segment['text'][:30]}...")
        await asyncio.sleep(0.5)

async def main():
    """Run the test"""
    logger.info("Starting WebSocket integration test...")
    
    # Start both tasks concurrently
    tasks = [
        asyncio.create_task(test_websocket_auto()),
        asyncio.create_task(simulate_transcription())
    ]
    
    results = await asyncio.gather(*tasks)
    
    if results[0]:
        logger.info("\n✅ WebSocket integration test PASSED")
    else:
        logger.error("\n❌ WebSocket integration test FAILED")

if __name__ == "__main__":
    asyncio.run(main())