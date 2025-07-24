#!/usr/bin/env python3
"""
Debug recording pipeline with verbose logging
"""
import sys
import os
import logging
import time

# Add current directory to path
sys.path.insert(0, os.path.dirname(__file__))

# Set up logging
logging.basicConfig(
    level=logging.DEBUG, 
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

from services.audio_input_service import audio_input_service

def test_audio_input_callbacks():
    """Test if audio input callbacks are working"""
    
    logger = logging.getLogger(__name__)
    logger.info("Testing audio input with debug callbacks")
    
    # Initialize audio service
    success = audio_input_service.initialize(device_id="default", sample_rate=16000, channels=1)
    if not success:
        logger.error("Failed to initialize audio input service")
        return False
    
    logger.info("Audio service initialized")
    
    # Set up callbacks
    audio_data_count = 0
    audio_level_count = 0
    
    def debug_audio_data(session_id, audio_bytes):
        nonlocal audio_data_count
        audio_data_count += 1
        logger.info(f"Audio data callback: session={session_id}, bytes={len(audio_bytes)}, count={audio_data_count}")
        
    def debug_audio_level(level):
        nonlocal audio_level_count
        audio_level_count += 1
        if audio_level_count % 10 == 0:  # Log every 10th level
            logger.info(f"Audio level callback: level={level:.4f}, count={audio_level_count}")
    
    # Register callbacks
    audio_input_service.register_callback('audio_data', debug_audio_data)
    audio_input_service.register_callback('audio_level', debug_audio_level)
    
    # Start recording
    logger.info("Starting recording...")
    if audio_input_service.start_recording("debug_session"):
        logger.info("Recording started, collecting data for 5 seconds...")
        time.sleep(5)
        
        logger.info("Stopping recording...")
        audio_input_service.stop_recording()
        
        logger.info(f"Recording complete:")
        logger.info(f"  - Audio data callbacks: {audio_data_count}")
        logger.info(f"  - Audio level callbacks: {audio_level_count}")
        
        if audio_data_count > 0:
            logger.info("✅ Audio data callbacks working!")
            return True
        else:
            logger.error("❌ No audio data callbacks received!")
            return False
    else:
        logger.error("❌ Failed to start recording")
        return False
    
    # Cleanup
    audio_input_service.cleanup()

if __name__ == "__main__":
    success = test_audio_input_callbacks()
    sys.exit(0 if success else 1)