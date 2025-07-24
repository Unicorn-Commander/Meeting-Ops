"""
Improved Audio Input Service with better error handling and session support
"""
import numpy as np
import threading
import logging
from typing import Optional, Dict, Any
import time
from services.audio_session_manager import AudioSessionManager

# Try to import pyaudio, but handle gracefully if not available
try:
    import pyaudio
    PYAUDIO_AVAILABLE = True
except ImportError as e:
    logger = logging.getLogger(__name__)
    logger.warning(f"PyAudio not available: {e}. Audio input will be disabled.")
    PYAUDIO_AVAILABLE = False
    pyaudio = None

logger = logging.getLogger(__name__)

class AudioInputServiceV2:
    """Improved service for capturing audio from hardware devices"""
    
    def __init__(self):
        self.pyaudio = None
        self.stream = None
        self.is_initialized = False
        self.recording_lock = threading.Lock()
        self.session_manager = AudioSessionManager()
        
        # Audio parameters
        self.device_index = None
        self.sample_rate = 16000
        self.channels = 1
        self.chunk_size = 1024
        self.format = pyaudio.paInt16 if PYAUDIO_AVAILABLE else None
        
        # Monitoring
        self.current_audio_level = 0.0
        self.last_error = None
        self.error_count = 0
        
    def initialize(self, device_id: str = "default", sample_rate: int = 16000, channels: int = 1) -> bool:
        """Initialize audio input with specified device"""
        if not PYAUDIO_AVAILABLE:
            logger.error("PyAudio not available - cannot initialize audio input")
            return False
            
        try:
            if self.pyaudio:
                self.cleanup()
                
            self.pyaudio = pyaudio.PyAudio()
            
            # Get device index
            if device_id == "default":
                self.device_index = None
            else:
                try:
                    self.device_index = int(device_id.split('_')[1])
                except:
                    logger.warning(f"Invalid device_id format: {device_id}, using default")
                    self.device_index = None
            
            self.sample_rate = sample_rate
            self.channels = channels
            
            # Test device
            try:
                test_stream = self.pyaudio.open(
                    format=self.format,
                    channels=self.channels,
                    rate=self.sample_rate,
                    input=True,
                    input_device_index=self.device_index,
                    frames_per_buffer=self.chunk_size
                )
                test_stream.close()
                self.is_initialized = True
                logger.info(f"Audio input initialized with device: {device_id}")
                return True
            except Exception as e:
                logger.error(f"Failed to test audio device: {e}")
                self.last_error = str(e)
                return False
                
        except Exception as e:
            logger.error(f"Failed to initialize PyAudio: {e}")
            self.last_error = str(e)
            return False
    
    def start_recording(self, session_id: str) -> bool:
        """Start recording audio for a specific session"""
        with self.recording_lock:
            if not self.is_initialized:
                logger.error("Audio input not initialized")
                return False
                
            try:
                # Create session in manager
                session = self.session_manager.create_session(session_id)
                
                # Start stream if not already running
                if not self.stream:
                    self.stream = self.pyaudio.open(
                        format=self.format,
                        channels=self.channels,
                        rate=self.sample_rate,
                        input=True,
                        input_device_index=self.device_index,
                        frames_per_buffer=self.chunk_size,
                        stream_callback=self._audio_callback
                    )
                    self.stream.start_stream()
                    logger.info(f"Started audio stream")
                
                logger.info(f"Started recording for session: {session_id}")
                return True
                
            except Exception as e:
                logger.error(f"Failed to start recording: {e}")
                self.last_error = str(e)
                self.error_count += 1
                return False
    
    def stop_recording(self, session_id: str) -> bool:
        """Stop recording for a specific session"""
        with self.recording_lock:
            try:
                # Stop session in manager
                success = self.session_manager.stop_session(session_id)
                
                # Check if we should stop the stream
                if self.stream and len(self.session_manager.get_active_sessions()) == 0:
                    self.stream.stop_stream()
                    self.stream.close()
                    self.stream = None
                    logger.info("Stopped audio stream")
                
                return success
                
            except Exception as e:
                logger.error(f"Error stopping recording: {e}")
                self.last_error = str(e)
                return False
    
    def _audio_callback(self, in_data, frame_count, time_info, status):
        """Callback function for audio stream"""
        if status:
            logger.warning(f"Audio callback status: {status}")
        
        try:
            # Calculate audio level
            audio_array = np.frombuffer(in_data, dtype=np.int16)
            self.current_audio_level = np.sqrt(np.mean(audio_array**2)) / 32768.0
            
            # Distribute to all active sessions
            for session_id in self.session_manager.get_active_sessions():
                self.session_manager.add_audio_data(session_id, in_data)
                
                # Trigger level callbacks
                self.session_manager._process_session_audio
                
        except Exception as e:
            logger.error(f"Error in audio callback: {e}")
            self.error_count += 1
        
        return (in_data, pyaudio.paContinue if PYAUDIO_AVAILABLE else None)
    
    def register_callback(self, event_type: str, callback, session_id: Optional[str] = None):
        """Register a callback for audio events"""
        if session_id:
            self.session_manager.register_session_callback(session_id, event_type, callback)
        else:
            self.session_manager.register_global_callback(event_type, callback)
    
    def get_audio_level(self) -> float:
        """Get current audio level (0.0 to 1.0)"""
        return self.current_audio_level
    
    def get_device_list(self) -> list:
        """Get list of available audio devices"""
        devices = []
        if not PYAUDIO_AVAILABLE:
            return []
            
        if not self.pyaudio:
            self.pyaudio = pyaudio.PyAudio()
            
        try:
            for i in range(self.pyaudio.get_device_count()):
                info = self.pyaudio.get_device_info_by_index(i)
                if info['maxInputChannels'] > 0:
                    devices.append({
                        'id': f"device_{i}",
                        'name': info['name'],
                        'channels': info['maxInputChannels'],
                        'sample_rate': int(info['defaultSampleRate'])
                    })
        except Exception as e:
            logger.error(f"Error getting device list: {e}")
            
        return devices
    
    def get_status(self) -> dict:
        """Get service status"""
        return {
            'initialized': self.is_initialized,
            'recording': self.stream is not None and self.stream.is_active() if self.stream else False,
            'active_sessions': self.session_manager.get_active_sessions(),
            'audio_level': self.current_audio_level,
            'error_count': self.error_count,
            'last_error': self.last_error,
            'device': {
                'index': self.device_index,
                'sample_rate': self.sample_rate,
                'channels': self.channels
            }
        }
    
    def cleanup(self):
        """Clean up resources"""
        try:
            # Stop all sessions
            self.session_manager.stop_all_sessions()
            
            # Close stream
            if self.stream:
                if self.stream.is_active():
                    self.stream.stop_stream()
                self.stream.close()
                self.stream = None
                
            # Terminate PyAudio
            if self.pyaudio:
                self.pyaudio.terminate()
                self.pyaudio = None
                
            self.is_initialized = False
            logger.info("Audio input service cleaned up")
            
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
    
    def __del__(self):
        """Destructor"""
        self.cleanup()