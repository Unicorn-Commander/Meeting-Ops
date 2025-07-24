#!/usr/bin/env python3
"""
Simple test to verify sounddevice audio capture is working
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from services.audio_input_service import audio_input_service
import time
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')
logger = logging.getLogger(__name__)

def test_audio_capture():
    """Test audio capture functionality"""
    try:
        logger.info("Testing audio capture...")
        
        # Initialize the service
        success = audio_input_service.initialize(device_id="default", sample_rate=16000, channels=1)
        
        if not success:
            logger.error("Failed to initialize audio input service")
            return False
            
        logger.info("Audio service initialized successfully")
        
        # Get available devices
        devices = audio_input_service.get_available_devices()
        logger.info(f"Found {len(devices)} audio input devices:")
        for device in devices[:3]:  # Show first 3 devices
            logger.info(f"  - {device['name']} (index: {device['index']})")
        
        # Test short recording
        logger.info("Starting 3-second test recording...")
        
        audio_data_received = []
        
        def audio_data_callback(session_id, audio_bytes):
            audio_data_received.append(len(audio_bytes))
            
        audio_input_service.register_callback('audio_data', audio_data_callback)
        
        # Start recording
        if audio_input_service.start_recording("test_session"):
            logger.info("Recording started...")
            time.sleep(3)  # Record for 3 seconds
            
            # Stop recording
            audio_input_service.stop_recording()
            logger.info("Recording stopped")
            
            # Check results
            total_bytes = sum(audio_data_received)
            logger.info(f"Received {len(audio_data_received)} audio chunks, {total_bytes} total bytes")
            
            if len(audio_data_received) > 0:
                logger.info("✅ Audio capture is working!")
                return True
            else:
                logger.error("❌ No audio data received")
                return False
        else:
            logger.error("❌ Failed to start recording")
            return False
            
    except Exception as e:
        logger.error(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        # Cleanup
        audio_input_service.cleanup()

if __name__ == "__main__":
    success = test_audio_capture()
    sys.exit(0 if success else 1)