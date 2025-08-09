#!/usr/bin/env python3
"""
Simple audio recording fix - use ffmpeg which handles PulseAudio properly
"""

import subprocess
import threading
import queue
import time
import logging
import os

logger = logging.getLogger(__name__)

class SimpleAudioRecorder:
    """
    Simple audio recorder that works with PulseAudio
    Uses ffmpeg which handles audio subsystem conflicts properly
    """
    
    def __init__(self):
        self.recording = False
        self.process = None
        self.output_file = None
        
    def start_recording(self, session_id: str, output_dir: str = "/home/ucadmin/Meeting-Ops/backend/recordings"):
        """Start recording using ffmpeg"""
        if self.recording:
            return False, "Already recording"
            
        # Create output directory
        os.makedirs(output_dir, exist_ok=True)
        
        # Output file
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        self.output_file = f"{output_dir}/recording_{session_id}_{timestamp}.wav"
        
        # Use ffmpeg to record from PulseAudio
        cmd = [
            'ffmpeg',
            '-f', 'pulse',  # Use PulseAudio input
            '-i', 'default',  # Default mic (will use USB if it's default)
            '-ac', '1',  # Mono
            '-ar', '44100',  # Sample rate
            '-y',  # Overwrite if exists
            self.output_file
        ]
        
        # Alternative: Try using the USB device directly
        # First check if ffmpeg is available
        try:
            subprocess.run(['which', 'ffmpeg'], check=True, capture_output=True)
            use_ffmpeg = True
        except:
            use_ffmpeg = False
            
        if not use_ffmpeg:
            # Fallback to sox which is more commonly available
            cmd = [
                'sox',
                '-t', 'pulseaudio', 'default',  # Input from PulseAudio
                '-r', '44100',  # Sample rate
                '-c', '1',  # Channels
                self.output_file
            ]
            
            # Check if sox is available
            try:
                subprocess.run(['which', 'sox'], check=True, capture_output=True)
            except:
                # Last resort: Use Python's sounddevice if available
                return self._start_python_recording(session_id, output_dir)
        
        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            self.recording = True
            logger.info(f"✅ Started recording to {self.output_file}")
            return True, self.output_file
        except Exception as e:
            logger.error(f"Failed to start recording: {e}")
            return False, str(e)
            
    def _start_python_recording(self, session_id: str, output_dir: str):
        """Fallback: Use Python's sounddevice library"""
        try:
            import sounddevice as sd
            import soundfile as sf
            import numpy as np
            
            # Find USB device
            devices = sd.query_devices()
            usb_device = None
            for i, dev in enumerate(devices):
                if 'USB' in dev['name']:
                    usb_device = i
                    break
                    
            if usb_device is None:
                usb_device = sd.default.device[0]  # Use default
                
            # Start recording in a thread
            self.recording = True
            self.audio_queue = queue.Queue()
            
            def callback(indata, frames, time, status):
                if self.recording:
                    self.audio_queue.put(indata.copy())
                    
            self.stream = sd.InputStream(
                device=usb_device,
                channels=1,
                samplerate=44100,
                callback=callback
            )
            
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            self.output_file = f"{output_dir}/recording_{session_id}_{timestamp}.wav"
            
            # Start stream
            self.stream.start()
            
            # Start writer thread
            def writer():
                with sf.SoundFile(self.output_file, mode='w', 
                                 samplerate=44100, channels=1) as f:
                    while self.recording:
                        try:
                            data = self.audio_queue.get(timeout=1)
                            f.write(data)
                        except queue.Empty:
                            continue
                            
            self.writer_thread = threading.Thread(target=writer, daemon=True)
            self.writer_thread.start()
            
            logger.info(f"✅ Started Python recording to {self.output_file}")
            return True, self.output_file
            
        except ImportError:
            return False, "No audio recording method available (need ffmpeg, sox, or sounddevice)"
        except Exception as e:
            return False, str(e)
            
    def stop_recording(self):
        """Stop recording"""
        if not self.recording:
            return False, "Not recording"
            
        self.recording = False
        
        if self.process:
            self.process.terminate()
            self.process.wait(timeout=2)
            
        if hasattr(self, 'stream'):
            self.stream.stop()
            self.stream.close()
            
        # Check if file was created
        if self.output_file and os.path.exists(self.output_file):
            size = os.path.getsize(self.output_file)
            logger.info(f"✅ Recording saved: {self.output_file} ({size:,} bytes)")
            return True, self.output_file
        else:
            return False, "Recording file not created"
            
    def is_recording(self):
        """Check if currently recording"""
        return self.recording


# Global instance
simple_recorder = SimpleAudioRecorder()