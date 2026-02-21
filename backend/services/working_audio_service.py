"""
Working Audio Service - Audio capture using ffmpeg through PipeWire
Provides shared mic access (no exclusive ALSA locking)
"""

import subprocess
import threading
import queue
import logging
import os
import time
import json
import signal
import redis
from typing import Optional, Callable
from datetime import datetime

logger = logging.getLogger(__name__)

class WorkingAudioService:
    """
    Audio service using ffmpeg with PipeWire/PulseAudio backend.
    - Shared mic access (other apps can use the mic simultaneously)
    - Hot-plug USB mic support via PipeWire device routing
    - Feeds audio to transcription
    - Monitors audio levels
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, 'initialized'):
            return

        self.initialized = True
        self.recording_process = None
        self.current_session_id = None
        self.is_recording = False

        # Redis for audio levels
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6381")
        try:
            self.redis_client = redis.from_url(redis_url)
            self.redis_client.ping()
        except redis.ConnectionError:
            # Fallback: try common Redis ports
            for port in [6379, 6380, 6381]:
                try:
                    self.redis_client = redis.from_url(f"redis://localhost:{port}")
                    self.redis_client.ping()
                    logger.info(f"Connected to Redis on port {port}")
                    break
                except redis.ConnectionError:
                    continue
            else:
                logger.warning("Redis not available - recording status tracking disabled")
                self.redis_client = None

        # For live transcription
        self.transcription_callback = None
        self.audio_buffer = bytearray()

        logger.info("Working Audio Service initialized (PipeWire/ffmpeg backend)")

    def _find_pulse_source(self) -> Optional[str]:
        """
        Find the best PulseAudio/PipeWire source for recording.
        Prefers USB mic, falls back to built-in.
        Returns the PulseAudio source name or None for default.
        """
        try:
            # List PulseAudio sources via pactl
            result = subprocess.run(
                ['pactl', 'list', 'sources', 'short'],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                sources = result.stdout.strip().splitlines()
                # Prefer USB source
                for line in sources:
                    if 'usb' in line.lower() and 'monitor' not in line.lower():
                        source_name = line.split('\t')[1] if '\t' in line else line.split()[1]
                        logger.info(f"Found USB audio source: {source_name}")
                        return source_name
                # Fall back to any non-monitor input
                for line in sources:
                    if 'input' in line.lower() and 'monitor' not in line.lower():
                        source_name = line.split('\t')[1] if '\t' in line else line.split()[1]
                        logger.info(f"Found audio source: {source_name}")
                        return source_name
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
            logger.warning(f"pactl source detection failed: {e}")

        # Try to construct the PipeWire ALSA source name from arecord
        try:
            result = subprocess.run(
                ['arecord', '-l'], capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if line.startswith('card ') and 'USB' in line:
                        card_num = line.split(':')[0].replace('card ', '').strip()
                        return f"hw:{card_num},0"
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        return None

    def start_recording(self, session_id: str, output_dir: Optional[str] = None) -> tuple[bool, str]:
        """
        Start recording audio using ffmpeg through PipeWire/PulseAudio.
        Returns: (success, filepath_or_error)
        """
        if self.is_recording:
            return False, "Already recording another session"

        # Default output directory
        if output_dir is None:
            output_dir = "/home/ucadmin/UC-Meeting-Ops/backend/recordings"

        os.makedirs(output_dir, exist_ok=True)

        # Generate filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = os.path.join(output_dir, f"recording_{session_id}_{timestamp}.wav")

        # Find the best audio source
        source = self._find_pulse_source()

        # Build ffmpeg command using PulseAudio input (goes through PipeWire)
        cmd = [
            'ffmpeg',
            '-y',                    # Overwrite output
            '-f', 'pulse',           # PulseAudio input (PipeWire-compatible)
            '-i', source or 'default',  # Source device
            '-ac', '1',              # Mono
            '-ar', '44100',          # 44.1kHz sample rate
            '-sample_fmt', 's16',    # 16-bit
            '-t', '7200',            # Max 2 hours safety limit
            output_file
        ]

        logger.info(f"Recording command: {' '.join(cmd)}")

        try:
            self.recording_process = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE
            )

            # Check if process started successfully
            time.sleep(0.3)
            if self.recording_process.poll() is not None:
                stderr_output = self.recording_process.stderr.read().decode() if self.recording_process.stderr else "No error output"
                logger.error(f"ffmpeg process failed to start: {stderr_output}")
                raise Exception(f"ffmpeg recording failed: {stderr_output}")

            self.is_recording = True
            self.current_session_id = session_id
            self.current_output_file = output_file

            # Start monitoring thread
            monitor_thread = threading.Thread(
                target=self._monitor_recording,
                args=(session_id,),
                daemon=True
            )
            monitor_thread.start()

            logger.info(f"Started recording session {session_id}")
            logger.info(f"   Output: {output_file}")
            logger.info(f"   Source: {source or 'default'}")
            logger.info(f"   PID: {self.recording_process.pid}")

            # Update Redis status
            if self.redis_client:
                try:
                    self.redis_client.hset(f"recording:{session_id}", mapping={
                        "status": "recording",
                        "started_at": datetime.now().isoformat(),
                        "output_file": output_file
                    })
                    self.redis_client.set("recording:active", session_id)
                except redis.ConnectionError:
                    pass

            return True, output_file

        except Exception as e:
            logger.error(f"Failed to start recording: {e}")
            self.is_recording = False
            return False, str(e)

    def stop_recording(self, session_id: str) -> tuple[bool, str]:
        """
        Stop recording.
        Returns: (success, filepath_or_error)
        """
        if not self.is_recording or self.current_session_id != session_id:
            return False, "Not recording this session"

        try:
            if self.recording_process:
                # Send SIGINT for graceful ffmpeg shutdown (writes WAV header)
                self.recording_process.send_signal(signal.SIGINT)

                try:
                    self.recording_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.recording_process.terminate()
                    try:
                        self.recording_process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        self.recording_process.kill()
                        self.recording_process.wait(timeout=1)

            self.is_recording = False
            output_file = self.current_output_file

            if os.path.exists(output_file):
                size = os.path.getsize(output_file)
                duration = size / (44100 * 2)  # Approximate duration (mono 16-bit)

                logger.info(f"Stopped recording session {session_id}")
                logger.info(f"   File: {output_file}")
                logger.info(f"   Size: {size:,} bytes")
                logger.info(f"   Duration: ~{duration:.1f} seconds")

                if self.redis_client:
                    try:
                        self.redis_client.hset(f"recording:{session_id}", mapping={
                            "status": "completed",
                            "stopped_at": datetime.now().isoformat(),
                            "file_size": size,
                            "duration": duration
                        })
                        self.redis_client.delete("recording:active")
                    except redis.ConnectionError:
                        pass

                return True, output_file
            else:
                return False, "Recording file not found"

        except Exception as e:
            logger.error(f"Failed to stop recording: {e}")
            return False, str(e)
        finally:
            self.current_session_id = None
            self.recording_process = None

    def _monitor_recording(self, session_id: str):
        """Monitor recording process"""
        while self.is_recording and self.current_session_id == session_id:
            if self.recording_process and self.recording_process.poll() is not None:
                logger.warning(f"Recording process ended unexpectedly for session {session_id}")
                self.is_recording = False
                break
            time.sleep(1)

    def get_recording_status(self, session_id: str) -> dict:
        """Get current recording status"""
        if self.is_recording and self.current_session_id == session_id:
            return {
                'recording': True,
                'session_id': session_id,
                'output_file': self.current_output_file
            }

        if self.redis_client:
            try:
                data = self.redis_client.hgetall(f"recording:{session_id}")
                if data:
                    return {k.decode(): v.decode() for k, v in data.items()}
            except redis.ConnectionError:
                pass

        return {'recording': False, 'session_id': session_id}

    def get_audio_devices(self) -> list:
        """Get list of available audio devices via PipeWire/PulseAudio"""
        devices = []

        try:
            # Try pactl first (PipeWire PulseAudio compat)
            result = subprocess.run(
                ['pactl', 'list', 'sources'],
                capture_output=True, text=True, timeout=5
            )

            if result.returncode == 0:
                current = {}
                for line in result.stdout.splitlines():
                    line = line.strip()
                    if line.startswith('Source #'):
                        if current and current.get('name') and 'monitor' not in current.get('name', '').lower():
                            devices.append(current)
                        current = {}
                    elif line.startswith('Name:'):
                        current['id'] = line.split(':', 1)[1].strip()
                        current['name'] = current['id']
                    elif line.startswith('Description:'):
                        current['name'] = line.split(':', 1)[1].strip()
                    elif 'alsa.card_name' in line:
                        pass  # already have description

                # Don't forget the last one
                if current and current.get('name') and 'monitor' not in current.get('name', '').lower():
                    devices.append(current)

            # Enrich with type info
            for d in devices:
                d['type'] = 'USB' if 'usb' in d.get('id', '').lower() else 'Built-in'
                d['available'] = True

        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        # Fallback: use arecord -l
        if not devices:
            try:
                result = subprocess.run(['arecord', '-l'], capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    for line in result.stdout.splitlines():
                        if line.startswith('card '):
                            parts = line.split(':')
                            if len(parts) >= 2:
                                card_num = parts[0].replace('card ', '').strip()
                                device_info = ':'.join(parts[1:]).strip()
                                if '[' in device_info and ']' in device_info:
                                    device_name = device_info[device_info.find('[')+1:device_info.find(']')]
                                else:
                                    device_name = device_info.split(',')[0].strip()
                                devices.append({
                                    'id': f'hw:{card_num},0',
                                    'name': device_name,
                                    'type': 'USB' if 'USB' in device_info else 'Built-in',
                                    'available': True
                                })
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass

        if not devices:
            devices.append({
                'id': 'default',
                'name': 'Default Audio Device',
                'type': 'System',
                'available': True
            })

        return devices

    def start_live_capture(self, callback: Optional[Callable] = None):
        """
        Start capturing audio for live transcription.
        Runs continuously and feeds audio to a callback.
        """
        if callback:
            self.transcription_callback = callback

        source = self._find_pulse_source()

        cmd = [
            'ffmpeg',
            '-f', 'pulse',
            '-i', source or 'default',
            '-ac', '1',
            '-ar', '44100',
            '-f', 's16le',  # Raw PCM output
            '-'  # Output to stdout
        ]

        def capture_thread():
            try:
                process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

                while True:
                    chunk_size = 44100 * 2 * 2  # 2 seconds of mono 16-bit audio
                    audio_chunk = process.stdout.read(chunk_size)

                    if not audio_chunk:
                        break

                    if self.transcription_callback:
                        self.transcription_callback(audio_chunk)

                    if self.redis_client:
                        try:
                            self.redis_client.publish('audio:raw', audio_chunk)
                        except redis.ConnectionError:
                            pass

            except Exception as e:
                logger.error(f"Live capture error: {e}")

        thread = threading.Thread(target=capture_thread, daemon=True)
        thread.start()
        logger.info("Started live audio capture for transcription")

    def cleanup(self):
        """Clean up resources"""
        if self.is_recording:
            self.stop_recording(self.current_session_id)
        if self.redis_client:
            try:
                self.redis_client.close()
            except Exception:
                pass

# Global singleton instance
audio_service = WorkingAudioService()
