#!/usr/bin/env python3
"""
Test the broadcast chain to debug why segments aren't reaching auto-summary WebSocket
"""
import asyncio
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

async def test_broadcast_chain():
    """Test the broadcast chain"""
    
    # Import modules in the right order
    from api import websocket_auto_summary
    from services.websocket_registry import websocket_registry
    from api.websocket_transcription import broadcast_transcription_update
    
    logger.info(f"Broadcasters registered: {list(websocket_registry.broadcasters.keys())}")
    
    # Test segment
    segment = {
        "text": "Test segment for broadcast chain",
        "start": 0,
        "end": 1,
        "speaker": "Speaker 1"
    }
    
    # Test direct call to auto-summary broadcaster
    logger.info("Testing direct call to auto-summary broadcaster...")
    auto_broadcaster = websocket_registry.get_broadcaster("auto_summary")
    if auto_broadcaster:
        await auto_broadcaster("test-session", segment)
        logger.info("✅ Direct call successful")
    else:
        logger.error("❌ auto_summary broadcaster not found!")
    
    # Test registry broadcast
    logger.info("Testing registry broadcast...")
    await websocket_registry.broadcast_to_all("test-session", segment)
    logger.info("✅ Registry broadcast successful")
    
    # Test full broadcast chain
    logger.info("Testing full broadcast chain via broadcast_transcription_update...")
    await broadcast_transcription_update("test-session", segment)
    logger.info("✅ Full broadcast chain successful")

if __name__ == "__main__":
    asyncio.run(test_broadcast_chain())