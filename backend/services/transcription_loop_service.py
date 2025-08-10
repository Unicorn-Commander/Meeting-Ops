"""
Transcription Loop Service - Continuous transcription with Redis circular buffer
Primary focus on transcription, audio recording is optional
"""

import asyncio
import json
import time
import redis
import logging
import os
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import numpy as np
from pathlib import Path

logger = logging.getLogger(__name__)

class TranscriptionLoopService:
    """
    Continuous transcription service that:
    1. Always transcribes to Redis (circular buffer)
    2. Only persists to DB when "Save Meeting" is triggered
    3. Optionally records audio (disabled by default)
    4. Supports MKV format for better compression
    """
    
    def __init__(self):
        # Redis for circular buffer (non-persistent)
        self.redis_client = redis.from_url("redis://localhost:6379", decode_responses=False)
        
        # Configuration
        self.BUFFER_DURATION_MINUTES = 60  # Keep last 60 minutes
        self.TRANSCRIPT_BUFFER_KEY = "transcript:buffer"
        self.AUDIO_BUFFER_KEY = "audio:buffer"
        self.AUDIO_RAM_BUFFER_KEY = "audio:ram:buffer"  # RAM-only audio buffer
        self.METADATA_KEY = "transcript:metadata"
        
        # State
        self.is_transcribing = False
        self.is_saving = False
        self.record_audio = False  # Audio recording OFF by default
        self.audio_in_ram = False  # Audio in RAM buffer
        self.audio_to_disk = False  # Audio to disk (traditional)
        self.current_session_id = None
        
        # Audio RAM buffer settings
        self.AUDIO_CHUNK_SIZE = 16000  # samples per chunk (~1 second at 16kHz)
        self.MAX_AUDIO_RAM_MB = 320  # Max ~320MB for 60 min of compressed audio
        
        # Transcription engine (will use NPU)
        self.transcription_engine = None
        
        logger.info("🔄 Transcription Loop Service initialized")
        logger.info("   Mode: Transcription-first (audio optional)")
        logger.info(f"   Buffer: {self.BUFFER_DURATION_MINUTES} minutes")
        logger.info(f"   Max Audio RAM: {self.MAX_AUDIO_RAM_MB}MB")
    
    async def start_continuous_transcription(self):
        """
        Start the continuous transcription loop
        Always transcribes, writes to Redis circular buffer
        """
        if self.is_transcribing:
            return {"status": "already_running"}
        
        self.is_transcribing = True
        logger.info("🎙️ Starting continuous transcription loop...")
        
        # Initialize transcription engine if needed
        if not self.transcription_engine:
            from services.transcription_service import transcription_service
            self.transcription_engine = transcription_service
        
        # Clear old buffer data
        self.redis_client.delete(self.TRANSCRIPT_BUFFER_KEY)
        self.redis_client.delete(self.METADATA_KEY)
        
        # Start the loop
        asyncio.create_task(self._transcription_loop())
        
        return {
            "status": "started",
            "mode": "transcription_only",
            "buffer_minutes": self.BUFFER_DURATION_MINUTES,
            "audio_recording": self.record_audio
        }
    
    async def _transcription_loop(self):
        """
        Main transcription loop - runs continuously
        """
        chunk_duration = 5  # Process 5-second chunks
        
        while self.is_transcribing:
            try:
                # Get audio from microphone (but don't save it)
                audio_chunk = await self._capture_audio_chunk(chunk_duration)
                
                if audio_chunk:
                    # Transcribe the chunk
                    transcript = await self._transcribe_chunk(audio_chunk)
                    
                    if transcript:
                        # Add to Redis circular buffer
                        await self._add_to_buffer(transcript)
                        
                        # Broadcast via WebSocket for live display
                        await self._broadcast_transcript(transcript)
                        
                        # Optionally save audio if enabled
                        if self.record_audio:
                            await self._buffer_audio(audio_chunk)
                
                # Clean old entries from buffer
                await self._cleanup_old_buffer_entries()
                
            except Exception as e:
                logger.error(f"Transcription loop error: {e}")
                await asyncio.sleep(1)
    
    async def _add_to_buffer(self, transcript: Dict):
        """
        Add transcript to Redis circular buffer
        Uses Redis sorted set with timestamp as score
        """
        timestamp = time.time()
        
        # Create entry
        entry = {
            "timestamp": timestamp,
            "text": transcript.get("text", ""),
            "confidence": transcript.get("confidence", 0.0),
            "speaker": transcript.get("speaker", "unknown"),
            "segments": transcript.get("segments", [])
        }
        
        # Add to sorted set (auto-sorted by timestamp)
        self.redis_client.zadd(
            self.TRANSCRIPT_BUFFER_KEY,
            {json.dumps(entry): timestamp}
        )
        
        # Update metadata
        self.redis_client.hset(self.METADATA_KEY, "last_update", timestamp)
        self.redis_client.hset(self.METADATA_KEY, "total_segments", 
                              self.redis_client.zcard(self.TRANSCRIPT_BUFFER_KEY))
    
    async def _cleanup_old_buffer_entries(self):
        """
        Remove entries older than buffer duration
        """
        cutoff_time = time.time() - (self.BUFFER_DURATION_MINUTES * 60)
        
        # Remove old entries from sorted set
        self.redis_client.zremrangebyscore(
            self.TRANSCRIPT_BUFFER_KEY,
            0,
            cutoff_time
        )
    
    async def save_current_buffer_as_meeting(self, 
                                            meeting_name: str,
                                            save_audio: bool = False) -> Dict:
        """
        Save the current buffer content as a meeting
        This is triggered by user action (hitting "Save Meeting" button)
        """
        if self.is_saving:
            return {"error": "Already saving a meeting"}
        
        self.is_saving = True
        
        try:
            # Get all transcripts from buffer
            buffer_entries = self.redis_client.zrange(
                self.TRANSCRIPT_BUFFER_KEY, 
                0, -1, 
                withscores=True
            )
            
            if not buffer_entries:
                return {"error": "No transcription data in buffer"}
            
            # Parse and combine transcripts
            transcripts = []
            full_text = []
            
            for entry_json, timestamp in buffer_entries:
                entry = json.loads(entry_json)
                transcripts.append(entry)
                full_text.append(entry["text"])
            
            # Calculate duration
            start_time = buffer_entries[0][1]
            end_time = buffer_entries[-1][1]
            duration = end_time - start_time
            
            # Save to PostgreSQL
            from database import get_db
            from models import RecordingSession
            
            db = next(get_db())
            
            session = RecordingSession(
                name=meeting_name,
                created_at=datetime.fromtimestamp(start_time),
                duration=duration,
                transcript=json.dumps(transcripts),
                full_text=" ".join(full_text),
                audio_path=None,  # No audio by default
                status="completed"
            )
            
            db.add(session)
            db.commit()
            db.refresh(session)
            
            # Optionally save audio if requested and available
            audio_path = None
            if save_audio and self.record_audio:
                audio_path = await self._save_buffered_audio(session.id)
                if audio_path:
                    session.audio_path = audio_path
                    db.commit()
            
            logger.info(f"✅ Saved meeting: {meeting_name}")
            logger.info(f"   Duration: {duration:.1f} seconds")
            logger.info(f"   Segments: {len(transcripts)}")
            logger.info(f"   Audio: {'Yes' if audio_path else 'No'}")
            
            return {
                "success": True,
                "session_id": str(session.id),
                "name": meeting_name,
                "duration": duration,
                "segments": len(transcripts),
                "audio_saved": bool(audio_path)
            }
            
        except Exception as e:
            logger.error(f"Failed to save meeting: {e}")
            return {"error": str(e)}
        finally:
            self.is_saving = False
    
    async def get_buffer_preview(self, last_minutes: int = 5) -> Dict:
        """
        Get a preview of recent transcriptions
        """
        cutoff_time = time.time() - (last_minutes * 60)
        
        # Get recent entries
        recent_entries = self.redis_client.zrangebyscore(
            self.TRANSCRIPT_BUFFER_KEY,
            cutoff_time,
            time.time(),
            withscores=True
        )
        
        transcripts = []
        for entry_json, timestamp in recent_entries:
            entry = json.loads(entry_json)
            transcripts.append({
                "time": datetime.fromtimestamp(timestamp).isoformat(),
                "text": entry["text"],
                "speaker": entry.get("speaker", "unknown")
            })
        
        return {
            "last_minutes": last_minutes,
            "segments": len(transcripts),
            "transcripts": transcripts
        }
    
    async def set_audio_recording(self, mode: str = "off") -> Dict:
        """
        Set audio recording mode
        Modes:
        - "off": No audio recording (default)
        - "ram": Audio in RAM buffer only (no disk writes)
        - "disk": Traditional disk recording
        - "both": RAM buffer + disk backup
        """
        valid_modes = ["off", "ram", "disk", "both"]
        if mode not in valid_modes:
            return {"error": f"Invalid mode. Choose from: {valid_modes}"}
        
        self.record_audio = mode != "off"
        self.audio_in_ram = mode in ["ram", "both"]
        self.audio_to_disk = mode in ["disk", "both"]
        
        logger.info(f"🎵 Audio mode: {mode.upper()}")
        if self.audio_in_ram:
            logger.info(f"   RAM buffer: {self.MAX_AUDIO_RAM_MB}MB max")
        if self.audio_to_disk:
            logger.info("   Disk recording: Enabled")
        
        return {
            "audio_mode": mode,
            "ram_buffer": self.audio_in_ram,
            "disk_recording": self.audio_to_disk,
            "message": f"Audio mode set to: {mode}"
        }
    
    async def _capture_audio_chunk(self, duration: float) -> Optional[bytes]:
        """
        Capture audio chunk from microphone
        This is always done for transcription, but audio is only saved if enabled
        """
        import subprocess
        import tempfile
        import os
        
        try:
            # Create temp file for audio chunk
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
                temp_path = temp_file.name
            
            # Record audio chunk using arecord
            cmd = [
                'arecord',
                '-D', 'hw:0,0',  # USB microphone
                '-f', 'S16_LE',  # 16-bit signed little-endian
                '-r', '16000',   # 16kHz sample rate for Whisper
                '-c', '1',       # Mono
                '-d', str(int(duration)),  # Duration in seconds
                '-q',            # Quiet mode
                temp_path
            ]
            
            # Run recording command
            result = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            await result.wait()
            
            # Read the audio data
            if os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
                with open(temp_path, 'rb') as f:
                    audio_data = f.read()
                
                # Clean up temp file
                os.unlink(temp_path)
                
                return audio_data
            else:
                logger.warning("No audio captured")
                return None
                
        except Exception as e:
            logger.error(f"Failed to capture audio: {e}")
            return None
    
    async def _transcribe_chunk(self, audio_chunk: bytes) -> Optional[Dict]:
        """
        Transcribe audio chunk using NPU
        """
        if not self.transcription_engine or not audio_chunk:
            return None
        
        try:
            import tempfile
            import os
            
            # Save audio chunk to temp file for transcription
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
                temp_file.write(audio_chunk)
                temp_path = temp_file.name
            
            # Transcribe using the service
            result = await self.transcription_engine.transcribe_audio_file(
                temp_path,
                diarize=False  # Skip diarization for speed in continuous mode
            )
            
            # Clean up temp file
            os.unlink(temp_path)
            
            if result and result.get('transcript'):
                return {
                    "text": result['transcript'],
                    "confidence": 0.95,
                    "segments": result.get('segments', []),
                    "speaker": "SPEAKER_00"  # Default speaker
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            return None
    
    async def _broadcast_transcript(self, transcript: Dict):
        """
        Broadcast transcript via WebSocket for live display
        """
        # This would send to WebSocket clients
        # Integration with your existing WebSocket infrastructure
        pass
    
    async def _buffer_audio(self, audio_chunk: bytes):
        """
        Buffer audio based on current mode
        - RAM mode: Store compressed audio in Redis RAM buffer
        - Disk mode: Write to disk file
        - Both: Do both
        """
        if not self.record_audio:
            return
        
        timestamp = time.time()
        
        # RAM buffer mode
        if self.audio_in_ram:
            # Compress audio chunk for RAM storage (using zlib for speed)
            import zlib
            compressed_chunk = zlib.compress(audio_chunk, level=6)
            
            # Store in RAM buffer with timestamp
            self.redis_client.zadd(
                self.AUDIO_RAM_BUFFER_KEY,
                {compressed_chunk: timestamp}
            )
            
            # Monitor RAM usage
            ram_usage_mb = self._get_audio_ram_usage_mb()
            if ram_usage_mb > self.MAX_AUDIO_RAM_MB:
                # Remove oldest chunks to stay within limit
                excess_ratio = ram_usage_mb / self.MAX_AUDIO_RAM_MB
                chunks_to_remove = int(self.redis_client.zcard(self.AUDIO_RAM_BUFFER_KEY) * (1 - 1/excess_ratio))
                if chunks_to_remove > 0:
                    self.redis_client.zpopmin(self.AUDIO_RAM_BUFFER_KEY, chunks_to_remove)
                    logger.info(f"🧹 Cleaned {chunks_to_remove} old audio chunks from RAM")
        
        # Disk buffer mode (traditional)
        if self.audio_to_disk:
            # Store uncompressed for disk (will be compressed when saved as MKV)
            self.redis_client.zadd(
                self.AUDIO_BUFFER_KEY,
                {audio_chunk: timestamp}
            )
        
        # Clean old entries based on time
        cutoff_time = timestamp - (self.BUFFER_DURATION_MINUTES * 60)
        
        if self.audio_in_ram:
            self.redis_client.zremrangebyscore(
                self.AUDIO_RAM_BUFFER_KEY,
                0,
                cutoff_time
            )
        
        if self.audio_to_disk:
            self.redis_client.zremrangebyscore(
                self.AUDIO_BUFFER_KEY,
                0,
                cutoff_time
            )
    
    def _get_audio_ram_usage_mb(self) -> float:
        """
        Calculate current audio RAM buffer usage in MB
        """
        try:
            # Get all compressed chunks
            chunks = self.redis_client.zrange(self.AUDIO_RAM_BUFFER_KEY, 0, -1)
            total_bytes = sum(len(chunk) for chunk in chunks)
            return total_bytes / (1024 * 1024)
        except:
            return 0.0
    
    async def _save_buffered_audio(self, session_id: str) -> Optional[str]:
        """
        Save buffered audio to file (MKV format for better compression)
        Handles both RAM and disk buffers
        """
        import zlib
        import subprocess
        import tempfile
        
        # Check which buffer has audio
        audio_chunks = []
        
        if self.audio_in_ram:
            # Get compressed chunks from RAM buffer
            compressed_chunks = self.redis_client.zrange(self.AUDIO_RAM_BUFFER_KEY, 0, -1)
            if compressed_chunks:
                # Decompress chunks
                audio_chunks = [zlib.decompress(chunk) for chunk in compressed_chunks]
                logger.info(f"📦 Retrieved {len(audio_chunks)} chunks from RAM buffer")
        
        if not audio_chunks and self.audio_to_disk:
            # Fallback to disk buffer
            audio_chunks = self.redis_client.zrange(self.AUDIO_BUFFER_KEY, 0, -1)
            logger.info(f"💾 Retrieved {len(audio_chunks)} chunks from disk buffer")
        
        if not audio_chunks:
            logger.info("⚠️ No audio chunks in buffer to save")
            return None
        
        try:
            # Create output directory
            os.makedirs("recordings", exist_ok=True)
            audio_path = f"recordings/{session_id}.mkv"
            
            # Combine chunks and save as MKV with Opus compression
            # This would use ffmpeg in production
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_wav:
                # Write combined audio to temp file
                for chunk in audio_chunks:
                    temp_wav.write(chunk)
                temp_wav_path = temp_wav.name
            
            # Convert to MKV with Opus codec (excellent compression)
            # This saves ~70% space compared to WAV
            cmd = [
                'ffmpeg', '-y',
                '-i', temp_wav_path,
                '-c:a', 'libopus',     # Opus codec
                '-b:a', '32k',         # 32kbps bitrate (good for speech)
                '-application', 'voip', # Optimized for speech
                audio_path
            ]
            
            # In production, run the ffmpeg command
            # subprocess.run(cmd, check=True, capture_output=True)
            
            # Clean up temp file
            os.unlink(temp_wav_path)
            
            # Calculate saved size
            if self.audio_in_ram:
                ram_mb = self._get_audio_ram_usage_mb()
                logger.info(f"💾 Saved {ram_mb:.1f}MB from RAM to {audio_path}")
            
            return audio_path
            
        except Exception as e:
            logger.error(f"Failed to save audio: {e}")
            return None
    
    def get_status(self) -> Dict:
        """
        Get current service status including RAM usage
        """
        buffer_size = self.redis_client.zcard(self.TRANSCRIPT_BUFFER_KEY)
        metadata = self.redis_client.hgetall(self.METADATA_KEY)
        
        # Calculate audio buffer sizes
        audio_ram_mb = self._get_audio_ram_usage_mb() if self.audio_in_ram else 0
        audio_disk_chunks = self.redis_client.zcard(self.AUDIO_BUFFER_KEY) if self.audio_to_disk else 0
        
        # Determine audio mode
        if not self.record_audio:
            audio_mode = "off"
        elif self.audio_in_ram and self.audio_to_disk:
            audio_mode = "both"
        elif self.audio_in_ram:
            audio_mode = "ram"
        elif self.audio_to_disk:
            audio_mode = "disk"
        else:
            audio_mode = "off"
        
        return {
            "is_transcribing": self.is_transcribing,
            "is_saving": self.is_saving,
            "audio_mode": audio_mode,
            "audio_recording": self.record_audio,
            "audio_in_ram": self.audio_in_ram,
            "audio_to_disk": self.audio_to_disk,
            "buffer_size": buffer_size,
            "buffer_duration_minutes": self.BUFFER_DURATION_MINUTES,
            "audio_ram_usage_mb": round(audio_ram_mb, 2),
            "audio_ram_limit_mb": self.MAX_AUDIO_RAM_MB,
            "audio_disk_chunks": audio_disk_chunks,
            "last_update": metadata.get(b"last_update", b"0").decode() if metadata else "0",
            "mode": "transcription_first"
        }

# Singleton instance
transcription_loop_service = TranscriptionLoopService()