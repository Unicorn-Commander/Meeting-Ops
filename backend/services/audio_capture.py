import pyaudio
import wave
import threading
import numpy as np
from .websocket_server import websocket_server  # Import WebSocket server
import time
from datetime import datetime
import os

class AudioCaptureService:
    def __init__(self, output_dir="recordings"):
        self.websocket_server = websocket_server
        self.output_dir = output_dir
        self.is_recording = False
        self.frames = []
        self.audio = pyaudio.PyAudio()
        self.stream = None
        self.chunk = 1024
        self.format = pyaudio.paInt16
        self.channels = 1
        self.rate = 48000
        
        # Create output directory if needed
        os.makedirs(self.output_dir, exist_ok=True)

    def start_recording(self, session_id):
        if self.is_recording:
            return False
            
        self.is_recording = True
        self.frames = []
        self.session_id = session_id
        self.current_file = f"{self.output_dir}/session_{session_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
        
        self.stream = self.audio.open(
            format=self.format,
            channels=self.channels,
            rate=self.rate,
            input=True,
            frames_per_buffer=self.chunk
        )
        
        self.recording_thread = threading.Thread(target=self._record)
        self.recording_thread.start()
        return True

    def _calculate_level(self, data):
        # Convert byte data to numpy array
        audio_data = np.frombuffer(data, dtype=np.int16)
        # Calculate RMS value as audio level (0-100)
        rms = np.sqrt(np.mean(audio_data**2))
        level = min(100, int(rms / 100))  # Scale RMS to 0-100 range
        return level

    def _record(self):
        while self.is_recording:
            data = self.stream.read(self.chunk)
            self.frames.append(data)
            
            # Calculate and send audio level
            level = self._calculate_level(data)
            self.websocket_server.send_audio_level(level)
            data = self.stream.read(self.chunk)
            self.frames.append(data)

    def stop_recording(self):
        if not self.is_recording:
            return False
            
        self.is_recording = False
        self.recording_thread.join()
        
        self.stream.stop_stream()
        self.stream.close()
        
        # Save recording
        wf = wave.open(self.current_file, 'wb')
        wf.setnchannels(self.channels)
        wf.setsampwidth(self.audio.get_sample_size(self.format))
        wf.setframerate(self.rate)
        wf.writeframes(b''.join(self.frames))
        wf.close()
        
        return self.current_file

# Singleton instance
audio_capture_service = AudioCaptureService()
