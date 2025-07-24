#!/usr/bin/env python3
"""
Test server integration manually without full FastAPI startup
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
    format='%(levelname)s:%(name)s:%(message)s'
)

logger = logging.getLogger(__name__)

def test_server_style_integration():
    """Test the server integration approach"""
    
    try:
        # Import the services the same way the server does
        from services.audio_input_service import audio_input_service
        from services.audio_recording_service import audio_recording_service
        from services.transcription_service import transcription_service
        from services.session_manager import session_manager
        from services.settings_manager import settings_manager
        
        logger.info("✅ All services imported successfully")
        
        # Initialize services like the server does
        logger.info("🔧 Initializing services...")
        
        # Initialize audio input service with settings
        audio_settings = settings_manager.get_all_settings().get('audio', {})
        audio_device = audio_settings.get('input_source', {}).get('value', 'default')
        sample_rate = audio_settings.get('sample_rate', {}).get('value', 16000)
        channels = audio_settings.get('channels', {}).get('value', 1)
        
        logger.info(f"Audio settings: device={audio_device}, rate={sample_rate}, channels={channels}")
        
        if not audio_input_service.initialize(audio_device, sample_rate, channels):
            logger.error("❌ Failed to initialize audio input service")
            return False
        
        logger.info("✅ Audio input service initialized")
        
        # Set up global callbacks
        def handle_audio_data_global(sess_id: str, audio_bytes: bytes):
            logger.info(f"📥 Received {len(audio_bytes)} bytes for session {sess_id}")
            try:
                # Save audio to file (simplified)
                # audio_recording_service.write_audio_chunk(sess_id, audio_bytes)
                
                # Process with transcription service (simplified test)
                logger.info(f"📝 Processing audio chunk for transcription...")
                
            except Exception as e:
                logger.error(f"Error in audio data handler: {e}")
        
        def handle_audio_level_global(level: float):
            logger.info(f"🎵 Audio level: {level:.4f}")
        
        # Register the global callbacks
        audio_input_service.register_callback('audio_data', handle_audio_data_global)
        audio_input_service.register_callback('audio_level', handle_audio_level_global)
        
        logger.info("✅ Global callbacks registered")
        
        # Create a test session
        session = session_manager.create_session(
            name="Integration Test Session",
            description="Testing server-style integration"
        )
        session_id = session.session_id
        logger.info(f"✅ Created test session: {session_id}")
        
        # Test recording
        logger.info("🎙️ Starting recording...")
        if audio_input_service.start_recording(session_id):
            logger.info("✅ Recording started successfully")
            
            # Record for 3 seconds
            logger.info("⏰ Recording for 3 seconds...")
            time.sleep(3)
            
            # Stop recording
            logger.info("⏹️ Stopping recording...")
            audio_input_service.stop_recording()
            
            logger.info("✅ Integration test completed successfully!")
            return True
            
        else:
            logger.error("❌ Failed to start recording")
            return False
            
    except Exception as e:
        logger.error(f"❌ Integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        # Cleanup
        if 'audio_input_service' in locals():
            audio_input_service.cleanup()

if __name__ == "__main__":
    success = test_server_style_integration()
    sys.exit(0 if success else 1)