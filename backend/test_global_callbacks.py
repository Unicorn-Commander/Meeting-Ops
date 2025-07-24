#!/usr/bin/env python3
"""
Test that global audio callbacks work when registered at startup
"""
import sys
import os
import logging
import time

# Add current directory to path
sys.path.insert(0, os.path.dirname(__file__))

# Set up logging
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s'
)

from services.audio_input_service import audio_input_service

def test_global_callbacks():
    """Test global callback registration approach"""
    
    logger = logging.getLogger(__name__)
    logger.info("Testing global callback registration")
    
    # Initialize audio service
    success = audio_input_service.initialize(device_id="default", sample_rate=16000, channels=1)
    if not success:
        logger.error("Failed to initialize audio input service")
        return False
    
    logger.info("Audio service initialized")
    
    # Register global callbacks (similar to server startup)
    audio_data_count = 0
    audio_level_count = 0
    
    def handle_audio_data_global(sess_id: str, audio_bytes: bytes):
        """Global audio data handler"""
        nonlocal audio_data_count
        audio_data_count += 1
        logger.info(f"GLOBAL: Audio data for {sess_id}: {len(audio_bytes)} bytes (count: {audio_data_count})")
        
    def handle_audio_level_global(level: float):
        """Global audio level handler"""
        nonlocal audio_level_count
        audio_level_count += 1
        if audio_level_count % 10 == 0:  # Log every 10th level
            logger.info(f"GLOBAL: Audio level: {level:.4f} (count: {audio_level_count})")
    
    # Register global callbacks
    audio_input_service.register_callback('audio_data', handle_audio_data_global)
    audio_input_service.register_callback('audio_level', handle_audio_level_global)
    
    logger.info("Global callbacks registered")
    
    # Test recording
    logger.info("Starting recording for 3 seconds...")
    if audio_input_service.start_recording("global_test_session"):
        logger.info("Recording started")
        time.sleep(3)
        
        logger.info("Stopping recording...")
        audio_input_service.stop_recording()
        
        logger.info(f"Recording complete:")
        logger.info(f"  - Audio data callbacks: {audio_data_count}")
        logger.info(f"  - Audio level callbacks: {audio_level_count}")
        
        if audio_data_count > 0:
            logger.info("✅ Global callbacks work!")
            return True
        else:
            logger.error("❌ No audio data received through global callbacks!")
            return False
    else:
        logger.error("❌ Failed to start recording")
        return False
    
    # Cleanup
    audio_input_service.cleanup()

if __name__ == "__main__":
    success = test_global_callbacks()
    sys.exit(0 if success else 1)