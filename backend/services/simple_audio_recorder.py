"""
Simple audio recording service using subprocess and arecord
This version uses arecord command which is available on most Linux systems
"""
import subprocess
import threading
import os
import time
import json
import wave
from datetime import datetime
from typing import Optional, Dict
import signal

class SimpleAudioRecorder:
    def __init__(self):
        """Initialize the simple audio recorder"""
        self.recordings_dir = os.path.expanduser("~/.meeting-ops/recordings")
        os.makedirs(self.recordings_dir, exist_ok=True)
        
        # Recording state
        self.current_process = None
        self.current_session_id = None
        self.current_file_path = None
        self.is_recording = False
        self.is_paused = False
        self.start_time = None
        
    def list_devices(self):
        """List available audio devices using arecord -l"""
        try:
            result = subprocess.run(
                ["arecord", "-l"],
                capture_output=True,
                text=True
            )
            
            devices = []
            lines = result.stdout.split('\n')
            for line in lines:
                if 'card' in line.lower():
                    # Parse card info
                    devices.append({
                        'name': line.strip(),
                        'available': True
                    })
            
            # Always add default device
            devices.insert(0, {
                'name': 'Default System Microphone',
                'id': 'default',
                'available': True
            })
            
            return devices
            
        except FileNotFoundError:
            # arecord not found, return mock device
            return [{
                'name': 'Default Microphone (arecord not available)',
                'id': 'default',
                'available': False
            }]
    
    def start_recording(self, session_id: str, session_name: str = None) -> str:
        """
        Start recording audio using arecord
        
        Args:
            session_id: Unique session identifier
            session_name: Optional session name for the file
            
        Returns:
            Path to the recording file
        """
        if self.is_recording:
            # Clean up any stuck recording
            print(f"Warning: Recording already in progress. Stopping previous recording.")
            self.stop_recording()
            # Small delay to ensure cleanup
            time.sleep(0.5)
        
        # Set up file path
        self.current_session_id = session_id
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{session_name or session_id}_{timestamp}.wav"
        # Clean filename
        filename = "".join(c for c in filename if c.isalnum() or c in (' ', '-', '_', '.')).rstrip()
        filename = filename.replace(' ', '_')
        self.current_file_path = os.path.join(self.recordings_dir, filename)
        
        # Start recording with arecord
        try:
            # Use the USB audio device (hw:2,0)
            self.current_process = subprocess.Popen([
                "arecord",
                "-D", "hw:2,0",   # Use USB PnP Sound Device
                "-f", "S16_LE",   # 16-bit signed little-endian
                "-r", "16000",    # 16kHz sample rate (good for speech)
                "-c", "1",        # Mono
                "-t", "wav",      # WAV format
                self.current_file_path
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            self.is_recording = True
            self.start_time = time.time()
            
            return self.current_file_path
            
        except FileNotFoundError:
            # arecord not available, create a dummy file
            self.is_recording = True
            self.start_time = time.time()
            
            # Create empty WAV file as placeholder
            with wave.open(self.current_file_path, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(b'')
            
            return self.current_file_path
    
    def stop_recording(self) -> dict:
        """
        Stop recording and save the file
        
        Returns:
            Dictionary with recording info
        """
        if not self.is_recording:
            return {"error": "Not recording"}
        
        # Calculate duration
        duration = time.time() - self.start_time if self.start_time else 0
        
        # Stop the recording process
        if self.current_process:
            try:
                # Send SIGINT to gracefully stop arecord
                self.current_process.send_signal(signal.SIGINT)
                # Wait for process to finish
                self.current_process.wait(timeout=2)
            except:
                # Force kill if needed
                try:
                    self.current_process.kill()
                except:
                    pass
            
            self.current_process = None
        
        # Get file size
        file_size = 0
        if os.path.exists(self.current_file_path):
            file_size = os.path.getsize(self.current_file_path)
        
        result = {
            "session_id": self.current_session_id,
            "file_path": self.current_file_path,
            "duration": duration,
            "sample_rate": 16000,
            "file_size": file_size
        }
        
        # Reset state
        self.is_recording = False
        self.current_session_id = None
        self.current_file_path = None
        self.start_time = None
        
        return result
    
    def pause_recording(self):
        """Pause or resume recording"""
        if self.is_recording:
            if self.current_process:
                if not self.is_paused:
                    # Send SIGSTOP to pause
                    try:
                        self.current_process.send_signal(signal.SIGSTOP)
                        self.is_paused = True
                    except:
                        pass
                else:
                    # Send SIGCONT to resume
                    try:
                        self.current_process.send_signal(signal.SIGCONT)
                        self.is_paused = False
                    except:
                        pass
            
            return {"paused": self.is_paused}
        return {"error": "Not recording"}
    
    def get_status(self) -> dict:
        """Get current recording status"""
        return {
            "is_recording": self.is_recording,
            "is_paused": self.is_paused,
            "session_id": self.current_session_id,
            "duration": time.time() - self.start_time if self.start_time and self.is_recording else 0,
            "file_path": self.current_file_path
        }
    
    def get_audio_level(self) -> int:
        """Get current audio level (0-100)"""
        # For now, return a mock value when recording
        if self.is_recording and not self.is_paused:
            # Simulate varying audio levels
            import random
            base_level = 30
            variation = random.randint(-20, 40)
            level = max(0, min(100, base_level + variation))
            return level
        return 0

# Global recorder instance
simple_audio_recorder = SimpleAudioRecorder()