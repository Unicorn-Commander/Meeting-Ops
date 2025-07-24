#!/usr/bin/env python3
"""
Test script to simulate audio input and verify 10-second chunk buffering works
"""
import numpy as np
import time
import sys
import os

# Add backend to path
sys.path.append('/home/ucladmin/Development/Unicorn-Commander-Meeting-Ops/backend')

from services.audio_input_service import AudioInputService
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def simulate_audio_chunks():
    """Simulate 15 seconds of audio data to test 10-second buffering"""
    
    # Create audio service instance
    audio_service = AudioInputService()
    
    # Override sounddevice/pyaudio availability for testing
    audio_service.use_sounddevice = False
    audio_service.sample_rate = 16000
    audio_service.channels = 1
    
    chunk_count = 0
    
    def mock_chunk_callback(sess_id: str, chunk_audio_bytes: bytes):
        nonlocal chunk_count
        chunk_count += 1
        logger.info(f"🎯 CHUNK CALLBACK #{chunk_count}: Session {sess_id}, {len(chunk_audio_bytes)} bytes")
        logger.info(f"📊 Expected bytes per 10s: {16000 * 1 * 2 * 10} bytes")
    
    def mock_data_callback(sess_id: str, audio_bytes: bytes):
        logger.debug(f"📝 Data callback: {len(audio_bytes)} bytes")
    
    # Register callbacks
    audio_service.register_callback('audio_chunk', mock_chunk_callback)
    audio_service.register_callback('audio_data', mock_data_callback)
    
    # Set recording state
    audio_service.is_recording = True
    
    # Start the processing thread
    import threading
    session_id = "test_session_chunk"
    processing_thread = threading.Thread(
        target=audio_service._process_audio_queue,
        args=(session_id,),
        daemon=True
    )
    processing_thread.start()
    
    # Simulate audio data over 15 seconds
    chunk_size = 1024  # Match audio service chunk size
    bytes_per_second = 16000 * 1 * 2  # 16kHz, mono, 16-bit
    chunks_per_second = bytes_per_second // chunk_size
    
    logger.info(f"🎙️ Simulating {chunks_per_second} chunks per second")
    logger.info(f"🎙️ Each chunk: {chunk_size} bytes")
    logger.info(f"🎙️ Expected chunks for 10s buffer: {chunks_per_second * 10}")
    
    start_time = time.time()
    audio_service.last_audio_time = start_time
    
    for i in range(int(chunks_per_second * 15)):  # 15 seconds of data
        # Generate fake audio data
        fake_audio = np.random.randint(-32768, 32767, chunk_size//2, dtype=np.int16).tobytes()
        
        # Add to queue
        audio_service.audio_queue.put(fake_audio)
        
        # Wait appropriate time between chunks
        time.sleep(1.0 / chunks_per_second)
        
        if i % chunks_per_second == 0:
            elapsed = time.time() - start_time
            logger.info(f"⏰ {elapsed:.1f}s elapsed, chunk {i+1}/{int(chunks_per_second * 15)}")
    
    # Stop recording and wait for processing to complete
    logger.info("🛑 Stopping simulation...")
    audio_service.is_recording = False
    processing_thread.join(timeout=5)
    
    logger.info(f"🎯 FINAL RESULT: {chunk_count} chunk callbacks triggered")
    logger.info(f"📊 Expected: 1-2 chunk callbacks for 15 seconds (10s + 5s)")
    
    if chunk_count >= 1:
        logger.info("✅ 10-second chunk buffering appears to be working!")
    else:
        logger.error("❌ No chunk callbacks triggered - buffering may not be working")

if __name__ == "__main__":
    simulate_audio_chunks()