import numpy as np
import asyncio
import threading
import queue
import logging
from typing import Optional, Callable, Dict, Any
import time

# Try to import sounddevice first, then fallback to pyaudio
try:
    import sounddevice as sd
    SOUNDDEVICE_AVAILABLE = True
    logger = logging.getLogger(__name__)
    logger.info("Using sounddevice for audio capture")
except (ImportError, OSError) as e:
    SOUNDDEVICE_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning(f"Sounddevice not available: {e}")

# Try to import pyaudio as fallback
try:
    import pyaudio
    PYAUDIO_AVAILABLE = True
    if not SOUNDDEVICE_AVAILABLE:
        logger = logging.getLogger(__name__)
        logger.info("Using PyAudio for audio capture")
except ImportError as e:
    logger = logging.getLogger(__name__)
    if not SOUNDDEVICE_AVAILABLE:
        logger.warning(f"Neither sounddevice nor PyAudio available: {e}. Audio input will be disabled.")
    PYAUDIO_AVAILABLE = False
    pyaudio = None

logger = logging.getLogger(__name__)

# Print to verify module loading
print(f"🎤 AudioInputService module loaded - sounddevice: {SOUNDDEVICE_AVAILABLE}, pyaudio: {PYAUDIO_AVAILABLE if 'PYAUDIO_AVAILABLE' in globals() else 'undefined'}")

class AudioInputService:
    """Service for capturing audio from hardware devices"""
    
    def __init__(self):
        import random
        self.instance_id = random.randint(1000, 9999)
        self.pyaudio = None
        self.stream = None
        self.sd_stream = None
        self.use_sounddevice = SOUNDDEVICE_AVAILABLE
        print(f"🔍 AudioInputService.__init__ [{self.instance_id}]: use_sounddevice = {self.use_sounddevice} (SOUNDDEVICE_AVAILABLE = {SOUNDDEVICE_AVAILABLE})")
        self.is_recording = False
        self.audio_queue = queue.Queue()
        self.recording_thread = None
        self.callbacks: Dict[str, Callable] = {}
        
        # Audio parameters (will be loaded from settings)
        self.device_index = None
        self.sample_rate = 16000
        self.channels = 1
        self.chunk_size = 1024  # Number of frames per buffer
        self.format = pyaudio.paInt16 if PYAUDIO_AVAILABLE else None
        
        # Audio level monitoring
        self.current_audio_level = 0.0
        self.last_audio_time = time.time()
        
    def initialize(self, device_id: str = "default", sample_rate: int = 16000, channels: int = 1):
        """Initialize audio input with specified device"""
        print(f"🎤 INITIALIZE called: device={device_id}, rate={sample_rate}, channels={channels}")
        try:
            self.sample_rate = sample_rate
            self.channels = channels
            
            # Get device index
            if device_id == "default":
                self.device_index = None  # Use system default
            else:
                # Extract device index from device_id (e.g., "device_1" -> 1)
                try:
                    self.device_index = int(device_id.split('_')[1])
                except:
                    logger.warning(f"Invalid device_id format: {device_id}, using default")
                    self.device_index = None
            
            if self.use_sounddevice:
                # Initialize sounddevice
                try:
                    # Test the device by querying
                    if self.device_index is None:
                        device_info = sd.query_devices(kind='input')
                    else:
                        device_info = sd.query_devices(self.device_index)
                    
                    logger.info(f"🎤 Audio input initialized with sounddevice: {device_info.get('name', 'Unknown')}")
                    logger.info(f"   Sample rate: {self.sample_rate}Hz, Channels: {self.channels}")
                    return True
                except Exception as e:
                    logger.error(f"Sounddevice initialization failed: {e}")
                    # Fall back to PyAudio if available
                    if PYAUDIO_AVAILABLE:
                        logger.info("Falling back to PyAudio")
                        self.use_sounddevice = False
                    else:
                        return False
            
            if not self.use_sounddevice and PYAUDIO_AVAILABLE:
                # Initialize PyAudio
                self.pyaudio = pyaudio.PyAudio()
                
                # Test the device
                device_info = self._get_device_info()
                if device_info:
                    logger.info(f"🎤 Audio input initialized with PyAudio: {device_info['name']}")
                    logger.info(f"   Sample rate: {self.sample_rate}Hz, Channels: {self.channels}")
                    return True
                else:
                    logger.error("Failed to get device info")
                    return False
            
            if not self.use_sounddevice and not PYAUDIO_AVAILABLE:
                logger.error("No audio libraries available")
                return False
                
        except Exception as e:
            logger.error(f"Failed to initialize audio input: {e}")
            return False
    
    def _get_device_info(self) -> Optional[Dict[str, Any]]:
        """Get information about the current audio device"""
        if not self.pyaudio:
            return None
            
        try:
            if self.device_index is None:
                # Get default input device
                return self.pyaudio.get_default_input_device_info()
            else:
                return self.pyaudio.get_device_info_by_index(self.device_index)
        except Exception as e:
            logger.error(f"Error getting device info: {e}")
            return None
    
    def start_recording(self, session_id: str):
        """Start recording audio from the device"""
        logger.info(f"🎙️ START_RECORDING called for session: {session_id}")
        logger.info(f"   sounddevice available: {self.use_sounddevice}")
        logger.info(f"   pyaudio available: {PYAUDIO_AVAILABLE}")
        print(f"🎙️ START_RECORDING called for session: {session_id}")
        print(f"   sounddevice available: {self.use_sounddevice}")
        print(f"   pyaudio available: {PYAUDIO_AVAILABLE}")
        
        if self.is_recording:
            logger.warning("Already recording")
            return False
            
        try:
            self.is_recording = True
            
            if self.use_sounddevice:
                # Use sounddevice for recording
                def sounddevice_callback(indata, frames, time_info, status):
                    if status:
                        logger.warning(f"Sounddevice callback status: {status}")
                    
                    if self.is_recording:
                        # Convert float32 to int16
                        audio_int16 = (indata * 32767).astype(np.int16)
                        audio_bytes = audio_int16.tobytes()
                        
                        # Add audio data to queue
                        self.audio_queue.put(audio_bytes)
                        
                        # Calculate audio level
                        self.current_audio_level = np.sqrt(np.mean(indata**2))
                        self.last_audio_time = time.time()
                        
                        # Trigger level callback if registered
                        if 'audio_level' in self.callbacks:
                            self.callbacks['audio_level'](self.current_audio_level)
                
                self.sd_stream = sd.InputStream(
                    device=self.device_index,
                    channels=self.channels,
                    samplerate=self.sample_rate,
                    blocksize=self.chunk_size,
                    dtype=np.float32,
                    callback=sounddevice_callback
                )
                self.sd_stream.start()
                
            elif PYAUDIO_AVAILABLE:
                # Use PyAudio for recording
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
            
            else:
                logger.error("No audio library available for recording")
                return False
            
            # Start processing thread
            self.recording_thread = threading.Thread(
                target=self._process_audio_queue,
                args=(session_id,),
                daemon=True
            )
            self.recording_thread.start()
            
            logger.info(f"🔴 Started recording for session: {session_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start recording: {e}")
            self.is_recording = False
            return False
    
    def stop_recording(self):
        """Stop recording audio"""
        if not self.is_recording:
            return
            
        self.is_recording = False
        
        try:
            if self.use_sounddevice and self.sd_stream:
                self.sd_stream.stop()
                self.sd_stream.close()
                self.sd_stream = None
            elif self.stream:
                self.stream.stop_stream()
                self.stream.close()
                self.stream = None
            
            # Clear the queue
            while not self.audio_queue.empty():
                try:
                    self.audio_queue.get_nowait()
                except:
                    pass
            
            logger.info("⏹️ Stopped recording")
            
        except Exception as e:
            logger.error(f"Error stopping recording: {e}")
    
    def _audio_callback(self, in_data, frame_count, time_info, status):
        """Callback function for audio stream"""
        if status:
            logger.warning(f"Audio callback status: {status}")
        
        if self.is_recording:
            # Add audio data to queue
            self.audio_queue.put(in_data)
            
            # Calculate audio level
            audio_array = np.frombuffer(in_data, dtype=np.int16)
            self.current_audio_level = np.sqrt(np.mean(audio_array**2)) / 32768.0
            self.last_audio_time = time.time()
            
            # Trigger level callback if registered
            if 'audio_level' in self.callbacks:
                self.callbacks['audio_level'](self.current_audio_level)
        
        return (in_data, pyaudio.paContinue)
    
    def _process_audio_queue(self, session_id: str):
        """Process audio data from the queue with 10-second buffering"""
        logger.info(f"Started audio processing thread for session: {session_id}")
        
        # Buffer for accumulating 10 seconds of audio
        audio_buffer = []
        buffer_start_time = time.time()
        bytes_per_second = self.sample_rate * self.channels * 2  # 16-bit = 2 bytes
        target_buffer_size = bytes_per_second * 10  # 10 seconds
        
        logger.info(f"🎙️ Audio buffering: {target_buffer_size} bytes for 10-second chunks")
        
        while self.is_recording:
            try:
                # Get audio data from queue (wait up to 1 second)
                audio_data = self.audio_queue.get(timeout=1.0)
                
                # Add to buffer
                audio_buffer.append(audio_data)
                current_buffer_size = sum(len(chunk) for chunk in audio_buffer)
                
                # Check if we have enough data or timeout (10 seconds)
                elapsed_time = time.time() - buffer_start_time
                
                if current_buffer_size >= target_buffer_size or elapsed_time >= 10.0:
                    if audio_buffer:  # Only process if we have data
                        # Combine all chunks into one buffer
                        combined_audio = b''.join(audio_buffer)
                        
                        # Trigger transcription callback for the chunk
                        if 'audio_chunk' in self.callbacks:
                            self.callbacks['audio_chunk'](session_id, combined_audio)
                        
                        # Also trigger individual chunk callback for real-time processing if needed
                        if 'audio_data' in self.callbacks:
                            self.callbacks['audio_data'](session_id, combined_audio)
                        
                        logger.info(f"📝 Processed {len(combined_audio)} bytes ({elapsed_time:.1f}s) for transcription")
                        
                        # Reset buffer
                        audio_buffer = []
                        buffer_start_time = time.time()
                
            except queue.Empty:
                # No audio data available, check if we should continue
                if time.time() - self.last_audio_time > 5.0:
                    logger.warning("No audio data received for 5 seconds")
            except Exception as e:
                logger.error(f"Error processing audio: {e}")
        
        # Process any remaining buffer when recording stops
        if audio_buffer:
            combined_audio = b''.join(audio_buffer)
            if 'audio_chunk' in self.callbacks:
                self.callbacks['audio_chunk'](session_id, combined_audio)
            logger.info(f"📝 Processed final buffer: {len(combined_audio)} bytes")
        
        logger.info("Audio processing thread stopped")
    
    def register_callback(self, event_type: str, callback: Callable):
        """Register a callback for audio events
        
        Event types:
        - 'audio_data': Called with (session_id, audio_bytes)
        - 'audio_level': Called with (level: float)
        """
        self.callbacks[event_type] = callback
        logger.info(f"Registered callback for event: {event_type}")
    
    def get_audio_level(self) -> float:
        """Get current audio level (0.0 to 1.0)"""
        return self.current_audio_level
    
    def get_available_devices(self) -> list:
        """Get list of available audio input devices"""
        devices = []
        
        try:
            if self.use_sounddevice:
                # Use sounddevice to get devices
                device_list = sd.query_devices()
                
                # Handle both single device and device list
                if hasattr(device_list, '__len__') and not isinstance(device_list, dict):
                    # It's a list of devices
                    for i, info in enumerate(device_list):
                        if info['max_input_channels'] > 0:
                            devices.append({
                                'index': i,
                                'name': info['name'],
                                'channels': info['max_input_channels'],
                                'sample_rate': int(info['default_samplerate'])
                            })
                else:
                    # It's a single device
                    if device_list['max_input_channels'] > 0:
                        devices.append({
                            'index': 0,
                            'name': device_list['name'],
                            'channels': device_list['max_input_channels'],
                            'sample_rate': int(device_list['default_samplerate'])
                        })
                        
            elif PYAUDIO_AVAILABLE:
                # Use PyAudio to get devices
                if not self.pyaudio:
                    self.pyaudio = pyaudio.PyAudio()
                
                for i in range(self.pyaudio.get_device_count()):
                    info = self.pyaudio.get_device_info_by_index(i)
                    if info['maxInputChannels'] > 0:
                        devices.append({
                            'index': i,
                            'name': info['name'],
                            'channels': info['maxInputChannels'],
                            'sample_rate': int(info['defaultSampleRate'])
                        })
            
        except Exception as e:
            logger.error(f"Error getting audio devices: {e}")
        
        return devices
    
    def cleanup(self):
        """Clean up audio resources"""
        self.stop_recording()
        
        if self.use_sounddevice and self.sd_stream:
            try:
                self.sd_stream.close()
            except:
                pass
            self.sd_stream = None
            
        if self.pyaudio:
            self.pyaudio.terminate()
            self.pyaudio = None
        
        logger.info("Audio input service cleaned up")

# Global audio input service instance
audio_input_service = AudioInputService()