"""
Always-On Recording Service
Continuous audio monitoring with automatic meeting segmentation.
When speech is detected, creates a new session and starts recording.
When silence exceeds threshold, finalizes the session.
"""

import asyncio
import logging
import os
import time
import numpy as np
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


class AlwaysOnRecorder:
    """
    State machine:
    - IDLE: Listening for speech, not recording
    - RECORDING: Speech detected, actively recording a meeting
    - SILENCE_GAP: Speech stopped, counting silence before finalizing
    - FINALIZING: Wrapping up session, processing transcript
    """

    def __init__(self):
        self.state = "IDLE"
        self.is_enabled = False
        self.monitor_task: Optional[asyncio.Task] = None
        self.device_id: Optional[str] = None

        # Configuration
        self.silence_threshold_chunks = 20  # 20 * 15s = 5 min silence to split
        self.min_meeting_chunks = 2  # 2 * 15s = 30s minimum meeting
        self.chunk_duration = 15  # seconds per chunk
        self.sample_rate = 44100
        self.speech_threshold_db = -75.0

        # State tracking
        self.current_session_id: Optional[str] = None
        self.consecutive_silent = 0
        self.speech_chunks = 0
        self.meetings_created = 0

    async def start(self, device_id: Optional[str] = None):
        """Enable always-on mode"""
        if self.is_enabled:
            return {"status": "already_running"}

        self.is_enabled = True
        self.state = "IDLE"
        self.device_id = device_id
        self.meetings_created = 0

        self.monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("Always-on recording mode ENABLED")
        return {"status": "started"}

    async def stop(self):
        """Disable always-on mode"""
        self.is_enabled = False

        # If currently recording, stop gracefully
        if self.state in ("RECORDING", "SILENCE_GAP") and self.current_session_id:
            await self._finalize_meeting()

        if self.monitor_task:
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass

        self.state = "IDLE"
        logger.info("Always-on recording mode DISABLED")
        return {"status": "stopped", "meetings_created": self.meetings_created}

    def get_status(self):
        """Get current always-on status"""
        return {
            "enabled": self.is_enabled,
            "state": self.state,
            "current_session_id": self.current_session_id,
            "consecutive_silent_chunks": self.consecutive_silent,
            "speech_chunks": self.speech_chunks,
            "meetings_created": self.meetings_created,
            "silence_threshold_minutes": (self.silence_threshold_chunks * self.chunk_duration) / 60,
            "device_id": self.device_id,
        }

    async def _monitor_loop(self):
        """Main monitoring loop - captures audio and detects speech"""
        from services.working_audio_service import audio_service

        # Find audio source
        source = self.device_id or audio_service._find_pulse_source() or "default"

        logger.info(f"Always-on monitoring started, source: {source}")

        chunk_samples = self.chunk_duration * self.sample_rate

        # Start continuous ffmpeg capture to stdout as raw PCM
        cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "pulse",
            "-i",
            source,
            "-ac",
            "1",
            "-ar",
            str(self.sample_rate),
            "-f",
            "s16le",  # Raw 16-bit PCM to stdout
            "-",
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )

        try:
            bytes_per_chunk = chunk_samples * 2  # 16-bit = 2 bytes per sample

            while self.is_enabled:
                # Read one chunk of audio
                raw_data = await process.stdout.read(bytes_per_chunk)
                if not raw_data:
                    logger.warning("Audio stream ended unexpectedly")
                    break

                # Convert to numpy
                audio = np.frombuffer(raw_data, dtype=np.int16).astype(np.float32) / 32768.0

                # Check for speech
                has_speech = self._chunk_has_speech(audio)

                if self.state == "IDLE":
                    if has_speech:
                        logger.info("Speech detected - starting new meeting")
                        await self._start_new_meeting()
                        self.state = "RECORDING"
                        self.speech_chunks = 1
                        self.consecutive_silent = 0

                elif self.state == "RECORDING":
                    if has_speech:
                        self.speech_chunks += 1
                        self.consecutive_silent = 0
                    else:
                        self.consecutive_silent += 1
                        if self.consecutive_silent >= self.silence_threshold_chunks:
                            logger.info(
                                f"Silence threshold reached ({self.silence_threshold_chunks} chunks) "
                                "- finalizing meeting"
                            )
                            if self.speech_chunks >= self.min_meeting_chunks:
                                await self._finalize_meeting()
                            else:
                                logger.info(
                                    f"Meeting too short ({self.speech_chunks} chunks), discarding"
                                )
                                await self._discard_meeting()
                            self.state = "IDLE"
                            self.speech_chunks = 0
                            self.consecutive_silent = 0

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Always-on monitor error: {e}", exc_info=True)
        finally:
            process.terminate()
            try:
                await process.wait()
            except Exception:
                pass
            logger.info("Always-on monitor loop ended")

    def _chunk_has_speech(self, audio: np.ndarray) -> bool:
        """Check if audio chunk has speech (reuse existing logic)"""
        if len(audio) == 0:
            return False
        rms = np.sqrt(np.mean(audio**2))
        if rms < 1e-10:
            return False
        db = 20 * np.log10(rms)
        return db > self.speech_threshold_db

    async def _start_new_meeting(self):
        """Create a new session and start recording"""
        import uuid
        from services.working_audio_service import audio_service

        session_id = str(uuid.uuid4())

        # Create session in database
        try:
            from database.database import SessionLocal
            from database.models import RecordingSession

            db = SessionLocal()
            try:
                new_session = RecordingSession(
                    session_id=session_id,
                    name=f"Auto-recorded meeting {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}",
                    description="Automatically detected by always-on recording",
                    status="recording",
                    created_at=datetime.now(timezone.utc),
                    started_at=datetime.now(timezone.utc),
                )
                db.add(new_session)
                db.commit()
                db.refresh(new_session)
            finally:
                db.close()

            # Start ffmpeg recording
            success, file_path = audio_service.start_recording(
                session_id, device_id=self.device_id
            )
            if success:
                self.current_session_id = session_id
                logger.info(
                    f"Auto-started recording: session={session_id}, file={file_path}"
                )

                # Start live transcription
                from services.live_recording_transcription import (
                    live_recording_transcription,
                )

                await live_recording_transcription.start_monitoring(
                    file_path, session_id
                )
            else:
                logger.error(f"Failed to start auto-recording: {file_path}")
                self.state = "IDLE"

        except Exception as e:
            logger.error(f"Error starting auto-meeting: {e}", exc_info=True)
            self.state = "IDLE"

    async def _finalize_meeting(self):
        """Stop recording and process the meeting"""
        if not self.current_session_id:
            return

        session_id = self.current_session_id
        logger.info(f"Finalizing auto-recorded meeting: {session_id}")

        try:
            # Stop live transcription
            from services.live_recording_transcription import (
                live_recording_transcription,
            )

            await live_recording_transcription.stop_monitoring()

            # Stop ffmpeg recording
            from services.working_audio_service import audio_service

            success, result = audio_service.stop_recording(session_id)

            if success:
                # Update session in DB
                from database.database import SessionLocal
                from database.models import RecordingSession

                db = SessionLocal()
                try:
                    session = (
                        db.query(RecordingSession)
                        .filter(RecordingSession.session_id == session_id)
                        .first()
                    )
                    if session:
                        session.status = "processing"
                        session.ended_at = datetime.now(timezone.utc)
                        session.audio_file = result
                        if session.started_at:
                            session.duration = (
                                datetime.now(timezone.utc) - session.started_at
                            ).total_seconds()
                        db.commit()

                        # Trigger post-processing (transcription + AI summary)
                        try:
                            from api.simple_recording_db import process_recording

                            asyncio.create_task(
                                process_recording(
                                    session_id=session.session_id,
                                    audio_file=result,
                                    db_session_id=session.id,
                                )
                            )
                            logger.info(
                                f"Post-processing scheduled for {session_id}"
                            )
                        except Exception as e:
                            logger.error(
                                f"Failed to schedule post-processing: {e}"
                            )
                finally:
                    db.close()

                self.meetings_created += 1
                logger.info(
                    f"Meeting finalized: {session_id} (total: {self.meetings_created})"
                )
            else:
                logger.error(f"Failed to stop recording: {result}")

        except Exception as e:
            logger.error(f"Error finalizing meeting: {e}", exc_info=True)
        finally:
            self.current_session_id = None

    async def _discard_meeting(self):
        """Discard a too-short meeting"""
        if not self.current_session_id:
            return

        session_id = self.current_session_id
        logger.info(f"Discarding short auto-recording: {session_id}")

        try:
            from services.live_recording_transcription import (
                live_recording_transcription,
            )

            await live_recording_transcription.stop_monitoring()

            from services.working_audio_service import audio_service

            audio_service.stop_recording(session_id)

            # Delete the session from DB
            from database.database import SessionLocal
            from database.models import RecordingSession

            db = SessionLocal()
            try:
                session = (
                    db.query(RecordingSession)
                    .filter(RecordingSession.session_id == session_id)
                    .first()
                )
                if session:
                    # Delete the audio file if it exists
                    if session.audio_file and os.path.exists(session.audio_file):
                        os.unlink(session.audio_file)
                    db.delete(session)
                    db.commit()
            finally:
                db.close()

        except Exception as e:
            logger.error(f"Error discarding meeting: {e}", exc_info=True)
        finally:
            self.current_session_id = None


# Global singleton
always_on_recorder = AlwaysOnRecorder()
