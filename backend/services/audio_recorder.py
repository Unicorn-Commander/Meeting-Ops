"""
Server-side audio recording service using sounddevice and wave
Records audio from the server's microphone and saves to WAV files
"""
import sounddevice as sd
import numpy as np
import wave
import threading
import queue
import os
from datetime import datetime
from typing import Optional, Callable
import json
import time

class AudioRecorder:
    def __init__(self, 
                 sample_rate: int = 16000,
                 channels: int = 1,
                 chunk_duration: float = 0.5,  # 500ms chunks
                 device: Optional[str] = None):
        """
        Initialize the audio recorder
        
        Args:
            sample_rate: Sample rate in Hz (16000 for Whisper)
            channels: Number of channels (1 for mono)
            chunk_duration: Duration of each audio chunk in seconds
            device: Audio device ID or name (None for default)
        """
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_size = int(sample_rate * chunk_duration)
        self.device = device
        
        # Recording state
        self.is_recording = False
        self.is_paused = False
        self.audio_queue = queue.Queue()
        self.recording_thread = None
        self.save_thread = None
        
        # Storage
        self.recordings_dir = os.path.expanduser("~/.meeting-ops/recordings")
        os.makedirs(self.recordings_dir, exist_ok=True)
        
        # Current session
        self.current_session_id = None
        self.current_file_path = None
        self.audio_buffer = []
        self.start_time = None
        
        # Callbacks
        self.on_audio_chunk: Optional[Callable] = None
        self.on_audio_level: Optional[Callable] = None
        
    def list_devices(self):
        """List available audio input devices"""
        devices = []
        for i, device in enumerate(sd.query_devices()):
            if device['max_input_channels'] > 0:
                devices.append({
                    'id': i,
                    'name': device['name'],
                    'channels': device['max_input_channels'],
                    'sample_rate': device['default_samplerate']
                })
        return devices
    
    def start_recording(self, session_id: str, session_name: str = None) -> str:
        """
        Start recording audio
        
        Args:
            session_id: Unique session identifier
            session_name: Optional session name for the file
            
        Returns:
            Path to the recording file
        """
        if self.is_recording:
            raise ValueError("Already recording")
        
        # Set up file path
        self.current_session_id = session_id
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{session_name or session_id}_{timestamp}.wav"
        # Clean filename
        filename = "".join(c for c in filename if c.isalnum() or c in (' ', '-', '_', '.')).rstrip()
        self.current_file_path = os.path.join(self.recordings_dir, filename)
        
        # Reset state
        self.audio_buffer = []
        self.is_recording = True
        self.is_paused = False
        self.start_time = time.time()
        
        # Start recording thread
        self.recording_thread = threading.Thread(target=self._record_audio)
        self.recording_thread.start()
        
        # Start save thread
        self.save_thread = threading.Thread(target=self._save_audio)
        self.save_thread.start()
        
        return self.current_file_path
    
    def stop_recording(self) -> dict:
        """
        Stop recording and save the file
        
        Returns:
            Dictionary with recording info
        """
        if not self.is_recording:
            return {"error": "Not recording"}
        
        self.is_recording = False
        
        # Wait for threads to finish
        if self.recording_thread:
            self.recording_thread.join(timeout=2)
        if self.save_thread:
            self.save_thread.join(timeout=2)
        
        # Calculate duration
        duration = time.time() - self.start_time if self.start_time else 0
        
        # Save any remaining audio
        if self.audio_buffer and self.current_file_path:
            self._write_wav_file()
        
        result = {
            "session_id": self.current_session_id,
            "file_path": self.current_file_path,
            "duration": duration,
            "sample_rate": self.sample_rate,
            "file_size": os.path.getsize(self.current_file_path) if os.path.exists(self.current_file_path) else 0
        }
        
        # Reset
        self.current_session_id = None
        self.current_file_path = None
        self.audio_buffer = []
        
        return result
    
    def pause_recording(self):
        """Pause or resume recording"""
        if self.is_recording:
            self.is_paused = not self.is_paused
            return {"paused": self.is_paused}
        return {"error": "Not recording"}
    
    def _record_audio(self):
        """Internal method to record audio from microphone"""
        try:
            with sd.InputStream(samplerate=self.sample_rate,
                               channels=self.channels,
                               device=self.device,
                               dtype='int16',
                               blocksize=self.chunk_size,
                               callback=self._audio_callback):
                
                while self.is_recording:
                    time.sleep(0.1)
                    
        except Exception as e:
            print(f"Recording error: {e}")
            self.is_recording = False
    
    def _audio_callback(self, indata, frames, time_info, status):
        """Callback for audio stream"""
        if status:
            print(f"Audio status: {status}")
        
        if not self.is_paused and self.is_recording:
            # Copy audio data
            audio_chunk = indata.copy()
            
            # Add to queue for saving
            self.audio_queue.put(audio_chunk)
            
            # Calculate audio level (RMS)
            if self.on_audio_level:
                rms = np.sqrt(np.mean(audio_chunk**2))
                # Normalize to 0-100
                level = min(100, int(rms / 32768 * 100 * 10))  # Scale up for typical mic levels
                self.on_audio_level(level)
            
            # Send chunk for transcription if callback is set
            if self.on_audio_chunk:
                self.on_audio_chunk(audio_chunk.tobytes())
    
    def _save_audio(self):
        """Internal method to save audio chunks to buffer"""
        while self.is_recording or not self.audio_queue.empty():
            try:
                chunk = self.audio_queue.get(timeout=0.5)
                self.audio_buffer.append(chunk)
                
                # Save to file periodically (every 10 seconds of audio)
                if len(self.audio_buffer) * self.chunk_size / self.sample_rate > 10:
                    self._write_wav_file(append=True)
                    
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Save error: {e}")
    
    def _write_wav_file(self, append=False):
        """Write audio buffer to WAV file"""
        if not self.audio_buffer or not self.current_file_path:
            return
        
        # Concatenate all audio chunks
        audio_data = np.concatenate(self.audio_buffer, axis=0)
        
        if append and os.path.exists(self.current_file_path):
            # Read existing file and append
            with wave.open(self.current_file_path, 'rb') as wf:
                params = wf.getparams()
                existing_frames = wf.readframes(wf.getnframes())
            
            # Write combined audio
            with wave.open(self.current_file_path, 'wb') as wf:
                wf.setnchannels(self.channels)
                wf.setsampwidth(2)  # 16-bit
                wf.setframerate(self.sample_rate)
                wf.writeframes(existing_frames)
                wf.writeframes(audio_data.tobytes())
        else:
            # Write new file
            with wave.open(self.current_file_path, 'wb') as wf:
                wf.setnchannels(self.channels)
                wf.setsampwidth(2)  # 16-bit
                wf.setframerate(self.sample_rate)
                wf.writeframes(audio_data.tobytes())
        
        # Clear buffer after writing
        self.audio_buffer = []
    
    def get_status(self) -> dict:
        """Get current recording status"""
        return {
            "is_recording": self.is_recording,
            "is_paused": self.is_paused,
            "session_id": self.current_session_id,
            "duration": time.time() - self.start_time if self.start_time and self.is_recording else 0,
            "buffer_size": len(self.audio_buffer)
        }

# Global recorder instance
audio_recorder = AudioRecorder()