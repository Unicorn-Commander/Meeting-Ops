import wave
import numpy as np
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple
import logging
import io

logger = logging.getLogger(__name__)

class AudioRecordingService:
    """Service for managing audio recording to files"""
    
    def __init__(self):
        self.active_recordings = {}  # session_id -> wave writer
    
    def start_recording(
        self, 
        session_id: str,  # Now takes explicit session ID
        file_path: str,
        sample_rate: int = 16000,
        channels: int = 1,
        sample_width: int = 2  # 16-bit
    ) -> bool:
        """Start recording audio to a file"""
        try:
            # Create directory if needed
            Path(file_path).parent.mkdir(parents=True, exist_ok=True)
            
            # Open wave file for writing
            wave_writer = wave.open(file_path, 'wb')
            wave_writer.setnchannels(channels)
            wave_writer.setsampwidth(sample_width)
            wave_writer.setframerate(sample_rate)
            
            # Store the writer using provided session ID
            self.active_recordings[session_id] = {
                'writer': wave_writer,
                'path': file_path,
                'start_time': datetime.utcnow(),
                'bytes_written': 0,
                'duration': 0.0
            }
            
            logger.info(f"Started recording to: {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error starting recording: {e}")
            return False
    
    def write_audio_chunk(self, session_id: str, audio_data: bytes) -> bool:
        """Write audio chunk to the recording file"""
        if session_id not in self.active_recordings:
            logger.warning(f"No active recording for session: {session_id}")
            return False
        
        try:
            recording = self.active_recordings[session_id]
            wave_writer = recording['writer']
            
            # Write audio data
            wave_writer.writeframes(audio_data)
            
            # Update statistics
            recording['bytes_written'] += len(audio_data)
            
            # Calculate duration (assuming 16-bit mono at 16kHz)
            sample_rate = wave_writer.getframerate()
            channels = wave_writer.getnchannels()
            sample_width = wave_writer.getsampwidth()
            
            total_samples = recording['bytes_written'] / (channels * sample_width)
            recording['duration'] = total_samples / sample_rate
            
            return True
            
        except Exception as e:
            logger.error(f"Error writing audio chunk: {e}")
            return False
    
    def stop_recording(self, session_id: str) -> Optional[dict]:
        """Stop recording and close the file"""
        if session_id not in self.active_recordings:
            logger.warning(f"No active recording for session: {session_id}")
            return None
        
        try:
            recording = self.active_recordings[session_id]
            wave_writer = recording['writer']
            
            # Close the wave file
            wave_writer.close()
            
            # Update WAV header with final size
            try:
                self.update_wav_header(recording['path'])
            except Exception as e:
                logger.error(f"Error updating WAV header: {e}")
            
            # Get final statistics
            end_time = datetime.utcnow()
            duration = (end_time - recording['start_time']).total_seconds()
            
            result = {
                'file_path': recording['path'],
                'bytes_written': recording['bytes_written'],
                'duration_seconds': recording['duration'],
                'actual_duration_seconds': duration,
                'start_time': recording['start_time'],
                'end_time': end_time
            }
            
            # Remove from active recordings
            del self.active_recordings[session_id]
            
            logger.info(f"Stopped recording: {recording['path']} ({recording['duration']:.2f}s)")
            return result
            
        except Exception as e:
            logger.error(f"Error stopping recording: {e}")
            return None
    
    def is_recording(self, session_id: str) -> bool:
        """Check if a session is currently recording"""
        return session_id in self.active_recordings
    
    def get_recording_status(self, session_id: str) -> Optional[dict]:
        """Get status of an active recording"""
        if session_id not in self.active_recordings:
            return None
        
        recording = self.active_recordings[session_id]
        current_time = datetime.utcnow()
        elapsed = (current_time - recording['start_time']).total_seconds()
        
        return {
            'session_id': session_id,
            'file_path': recording['path'],
            'bytes_written': recording['bytes_written'],
            'duration_seconds': recording['duration'],
            'elapsed_seconds': elapsed,
            'is_active': True
        }
    
    def stop_all_recordings(self):
        """Stop all active recordings"""
        session_ids = list(self.active_recordings.keys())
        for session_id in session_ids:
            self.stop_recording(session_id)
        
        logger.info(f"Stopped {len(session_ids)} active recordings")
    
    @staticmethod
    def create_wav_header(
        sample_rate: int = 16000,
        channels: int = 1,
        sample_width: int = 2
    ) -> bytes:
        """Create a WAV file header"""
        # This is useful for streaming scenarios where we need to send
        # a valid WAV header before the actual audio data
        
        # WAV header is 44 bytes
        header = io.BytesIO()
        
        # RIFF chunk descriptor
        header.write(b'RIFF')
        header.write(b'\x00\x00\x00\x00')  # File size - 8 (will be updated later)
        header.write(b'WAVE')
        
        # fmt sub-chunk
        header.write(b'fmt ')
        header.write((16).to_bytes(4, 'little'))  # Subchunk size
        header.write((1).to_bytes(2, 'little'))   # Audio format (1 = PCM)
        header.write(channels.to_bytes(2, 'little'))
        header.write(sample_rate.to_bytes(4, 'little'))
        
        byte_rate = sample_rate * channels * sample_width
        header.write(byte_rate.to_bytes(4, 'little'))
        
        block_align = channels * sample_width
        header.write(block_align.to_bytes(2, 'little'))
        header.write((sample_width * 8).to_bytes(2, 'little'))  # Bits per sample
        
        # data sub-chunk
        header.write(b'data')
        header.write(b'\x00\x00\x00\x00')  # Data size (will be updated later)
        
        return header.getvalue()
    
    @staticmethod
    def update_wav_header(file_path: str):
        """Update WAV header with correct file size"""
        try:
            with open(file_path, 'r+b') as f:
                # Get file size
                f.seek(0, 2)  # Seek to end
                file_size = f.tell()
                
                # Update RIFF chunk size
                f.seek(4)
                f.write((file_size - 8).to_bytes(4, 'little'))
                
                # Update data chunk size
                f.seek(40)
                f.write((file_size - 44).to_bytes(4, 'little'))
                
            logger.info(f"Updated WAV header for: {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating WAV header: {e}")
            return False

# Global instance
audio_recording_service = AudioRecordingService()