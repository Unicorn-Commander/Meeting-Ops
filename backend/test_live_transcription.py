#!/usr/bin/env python3
"""
Test live transcription WebSocket broadcast
"""

import asyncio
import sys
sys.path.append('/home/ucadmin/Meeting-Ops/backend')

from api.websocket_transcription import broadcast_transcription_update

async def test_broadcast():
    """Send a test transcription segment"""
    
    # Get session ID from command line or use a default
    session_id = sys.argv[1] if len(sys.argv) > 1 else "test-session"
    
    print(f"Broadcasting test transcription to session: {session_id}")
    
    test_segment = {
        "text": "This is a test transcription message from the backend.",
        "start": 0.0,
        "end": 5.0,
        "speaker": "SPEAKER_01",
        "confidence": 0.95
    }
    
    await broadcast_transcription_update(session_id, test_segment)
    print("Test message sent!")
    
    # Send another message after 2 seconds
    await asyncio.sleep(2)
    
    test_segment2 = {
        "text": "Here is another test message to verify live transcription is working.",
        "start": 5.0,
        "end": 10.0,
        "speaker": "SPEAKER_02",
        "confidence": 0.98
    }
    
    await broadcast_transcription_update(session_id, test_segment2)
    print("Second test message sent!")

if __name__ == "__main__":
    asyncio.run(test_broadcast())