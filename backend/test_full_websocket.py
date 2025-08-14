#!/usr/bin/env python3
"""
Full test of the WebSocket auto-summary with transcription segments
"""
import asyncio
import websockets
import json
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def websocket_client(session_id: str):
    """WebSocket client that connects and listens for messages"""
    uri = f"ws://localhost:9050/ws/transcription-auto/{session_id}"
    
    transcription_count = 0
    summary_count = 0
    
    try:
        async with websockets.connect(uri) as websocket:
            logger.info(f"Connected to {uri}")
            
            # Receive messages for 15 seconds
            timeout = 15
            start_time = asyncio.get_event_loop().time()
            
            while asyncio.get_event_loop().time() - start_time < timeout:
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                    data = json.loads(message)
                    
                    if data['type'] == 'connection':
                        logger.info(f"Connection established. Features: {data.get('features', {})}")
                    elif data['type'] == 'transcription':
                        transcription_count += 1
                        segment = data['segment']
                        logger.info(f"📝 Transcription #{transcription_count}: \"{segment.get('text', '')[:50]}...\"")
                        logger.info(f"   Word count: {data.get('word_count', 0)} total, {data.get('segment_word_count', 0)} in segment")
                    elif data['type'] == 'auto_summary':
                        summary_count += 1
                        logger.info(f"📊 Auto-summary #{summary_count}: {data.get('trigger_reason', 'unknown')}")
                        logger.info(f"   Summary: {data['summary'].get('summary', '')[:100]}...")
                    elif data['type'] == 'auto_summary_status':
                        logger.info(f"Summary status: {data}")
                        
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logger.error(f"Error receiving message: {e}")
                    break
            
            logger.info(f"\n✅ Test Results:")
            logger.info(f"   Transcription segments received: {transcription_count}")
            logger.info(f"   Auto-summaries received: {summary_count}")
            
    except Exception as e:
        logger.error(f"WebSocket error: {e}")

async def simulate_recording_with_transcription(session_id: str):
    """Simulate a recording session with transcription"""
    await asyncio.sleep(2)  # Wait for WebSocket to connect
    
    # Create a session first
    from api.simple_recording_fixed import sessions
    sessions[session_id] = {
        "id": session_id,
        "name": "Test Recording",
        "status": "recording",
        "transcription_segments": [],
        "transcript": ""
    }
    
    # Import the broadcast function
    from api.websocket_transcription import broadcast_transcription_update
    
    # Simulate transcription segments being generated
    test_segments = [
        {"text": "Welcome everyone to today's meeting about the new project timeline.", "start": 0, "end": 4},
        {"text": "As you all know, we've been working on this initiative for three months.", "start": 4, "end": 8},
        {"text": "The original deadline was set for the end of this quarter.", "start": 8, "end": 12},
        {"text": "However, after reviewing our progress and the remaining tasks,", "start": 12, "end": 16},
        {"text": "we've decided to extend the deadline to next quarter.", "start": 16, "end": 20},
        {"text": "This extension will allow us to properly test all features.", "start": 20, "end": 24},
        {"text": "Quality is our top priority, and we don't want to rush.", "start": 24, "end": 28},
        {"text": "The additional time will also help with documentation.", "start": 28, "end": 32},
        {"text": "We'll use this time to create comprehensive user guides.", "start": 32, "end": 36},
        {"text": "The development team will focus on optimization and bug fixes.", "start": 36, "end": 40},
    ]
    
    logger.info(f"\n🎤 Starting to broadcast {len(test_segments)} transcription segments...")
    
    for i, segment in enumerate(test_segments):
        await broadcast_transcription_update(session_id, segment)
        logger.info(f"   Sent segment {i+1}/{len(test_segments)}: \"{segment['text'][:30]}...\"")
        await asyncio.sleep(0.5)  # Small delay between segments
    
    logger.info("✅ All segments broadcast")
    
    # Wait a bit for any auto-summaries to trigger
    await asyncio.sleep(5)

async def main():
    """Run the full test"""
    session_id = "test-full-websocket-123"
    
    logger.info("=" * 60)
    logger.info("FULL WEBSOCKET AUTO-SUMMARY TEST")
    logger.info("=" * 60)
    
    # Ensure the auto-summary module is loaded
    from api import websocket_auto_summary
    from services.websocket_registry import websocket_registry
    logger.info(f"Registry has broadcasters: {list(websocket_registry.broadcasters.keys())}")
    
    # Run client and simulation concurrently
    await asyncio.gather(
        websocket_client(session_id),
        simulate_recording_with_transcription(session_id)
    )
    
    logger.info("\n" + "=" * 60)
    logger.info("TEST COMPLETE")
    logger.info("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())