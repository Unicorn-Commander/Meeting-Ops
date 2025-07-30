#!/usr/bin/env python3
"""
Test WebSocket live transcription
"""

import asyncio
import websockets
import json
import numpy as np
import struct
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_websocket_transcription():
    """Test the WebSocket transcription endpoint"""
    uri = "ws://localhost:9050/ws/transcription"
    
    try:
        async with websockets.connect(uri) as websocket:
            logger.info("Connected to WebSocket")
            
            # Send initial configuration
            config = {
                "session_id": f"test_session_{int(datetime.now().timestamp())}"
            }
            await websocket.send(json.dumps(config))
            
            # Wait for connection acknowledgment
            response = await websocket.recv()
            ack = json.loads(response)
            logger.info(f"Connection acknowledged: {ack}")
            
            # Generate test audio (2 seconds of 440Hz tone)
            sample_rate = 16000
            duration = 2.0
            frequency = 440.0
            
            t = np.linspace(0, duration, int(sample_rate * duration))
            audio = np.sin(2 * np.pi * frequency * t)
            audio_int16 = (audio * 32767).astype(np.int16)
            audio_bytes = audio_int16.tobytes()
            
            logger.info(f"Sending {len(audio_bytes)} bytes of audio...")
            
            # Send audio in chunks (need to send 2+ seconds for processing)
            chunk_size = 8000  # 0.5 seconds
            for i in range(0, len(audio_bytes), chunk_size):
                chunk = audio_bytes[i:i + chunk_size]
                await websocket.send(chunk)
                await asyncio.sleep(0.1)  # Small delay between chunks
            
            # Send more data to trigger processing (need 2+ seconds)
            await websocket.send(audio_bytes)  # Send all data again to reach threshold
            
            # Wait for transcription results
            logger.info("Waiting for transcription results...")
            while True:
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                    result = json.loads(response)
                    
                    if result.get("type") == "transcription":
                        logger.info(f"Transcription received:")
                        logger.info(f"  Text: {result.get('text', 'N/A')}")
                        logger.info(f"  NPU Accelerated: {result.get('npu_accelerated', False)}")
                        logger.info(f"  Processing Time: {result.get('processing_time', 0):.3f}s")
                        logger.info(f"  Confidence: {result.get('confidence', 0):.2f}")
                    elif result.get("type") == "keepalive":
                        logger.info("Received keepalive")
                    else:
                        logger.info(f"Received: {result}")
                        
                except asyncio.TimeoutError:
                    logger.info("No more results, closing connection")
                    break
                    
    except Exception as e:
        logger.error(f"WebSocket error: {e}")

async def test_real_audio_file():
    """Test with a real audio file"""
    uri = "ws://localhost:9050/ws/transcription"
    audio_file = "/tmp/recordings/session_1753333393/recording.wav"
    
    try:
        # Load audio file
        import wave
        with wave.open(audio_file, 'rb') as wav:
            frames = wav.readframes(wav.getnframes())
            logger.info(f"Loaded audio file: {len(frames)} bytes")
        
        async with websockets.connect(uri) as websocket:
            logger.info("Connected to WebSocket")
            
            # Send initial configuration
            config = {
                "session_id": f"test_file_{int(datetime.now().timestamp())}"
            }
            await websocket.send(json.dumps(config))
            
            # Wait for connection acknowledgment
            response = await websocket.recv()
            ack = json.loads(response)
            logger.info(f"Connection acknowledged: {ack}")
            
            # Send audio in chunks
            chunk_size = 32000  # 1 second of 16kHz stereo
            total_sent = 0
            
            for i in range(0, len(frames), chunk_size):
                chunk = frames[i:i + chunk_size]
                await websocket.send(chunk)
                total_sent += len(chunk)
                logger.info(f"Sent {total_sent}/{len(frames)} bytes ({total_sent/len(frames)*100:.1f}%)")
                await asyncio.sleep(0.5)  # Simulate real-time streaming
            
            # Wait for final results
            logger.info("Waiting for transcription results...")
            transcriptions = []
            
            while True:
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                    result = json.loads(response)
                    
                    if result.get("type") == "transcription":
                        text = result.get('text', '')
                        if text:
                            transcriptions.append(text)
                            logger.info(f"Transcription: {text}")
                            logger.info(f"  NPU: {result.get('npu_accelerated', False)}")
                            logger.info(f"  Time: {result.get('processing_time', 0):.3f}s")
                    elif result.get("type") == "error":
                        logger.error(f"Error: {result.get('message')}")
                        break
                        
                except asyncio.TimeoutError:
                    logger.info("No more results")
                    break
            
            # Show full transcript
            if transcriptions:
                full_text = " ".join(transcriptions)
                logger.info(f"\nFull transcript:\n{full_text}")
            else:
                logger.warning("No transcriptions received")
                    
    except Exception as e:
        logger.error(f"Test failed: {e}")

if __name__ == "__main__":
    logger.info("Testing WebSocket Live Transcription")
    logger.info("=" * 50)
    
    # Test with generated audio
    logger.info("\n1. Testing with generated audio...")
    asyncio.run(test_websocket_transcription())
    
    # Test with real audio file
    logger.info("\n2. Testing with real audio file...")
    asyncio.run(test_real_audio_file())
    
    logger.info("\nTest complete!")