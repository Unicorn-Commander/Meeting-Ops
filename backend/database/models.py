"""Database models for Meeting-Ops"""
from sqlalchemy import Column, Integer, BigInteger, String, DateTime, Text, Float, Boolean, JSON, ForeignKey, Index
from sqlalchemy.orm import declarative_base
from sqlalchemy.dialects.postgresql import UUID, JSONB
from datetime import datetime, timezone
import uuid

Base = declarative_base()

class Settings(Base):
    """Settings model"""
    __tablename__ = "settings"
    
    id = Column(Integer, primary_key=True)
    category = Column(String(50), nullable=False)
    key = Column(String(100), nullable=False)
    value = Column(Text)
    description = Column(String(500))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class RecordingSession(Base):
    """Recording session model"""
    __tablename__ = "recording_sessions"
    
    id = Column(Integer, primary_key=True)  # Keep as Integer to match existing table
    session_id = Column(String(100), unique=True, nullable=True)  # Legacy field
    name = Column(String(200))
    description = Column(Text)
    meeting_type = Column(String(100))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    started_at = Column(DateTime)  # Changed from start_time
    ended_at = Column(DateTime)    # Changed from end_time
    duration = Column(Float, default=0)
    status = Column(String(50), default="active")
    extra_data = Column(JSON)
    user_id = Column(Integer)  # Foreign key to User
    audio_file = Column(String(500))  # Changed from audio_file_path
    title = Column(String(500))  # Added title column
    transcript = Column(Text)  # Added transcript column
    transcript_simple = Column(Text)  # Simple text transcript without speakers
    transcript_diarized = Column(JSON)  # Full diarized transcript with speakers
    summary = Column(Text)
    progressive_summaries = Column(JSON)  # List of summaries during recording
    final_summary = Column(JSON)  # Comprehensive final analysis
    ai_insights = Column(JSON)  # Legacy field for compatibility
    processing_metadata = Column(JSON)  # Processing stats and metadata (renamed from metadata)
    generated_emails = Column(JSON)  # Generated follow-up emails
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    # Satellite device fields
    source_device_id = Column(String(100), nullable=True)  # Which satellite recorded this
    source_type = Column(String(50), default="local_mic")  # "local_mic", "satellite_stream", "satellite_upload", "satellite_transcript", "companion_app"
    room_name = Column(String(200), nullable=True)  # Physical room name
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    project_app = Column(String(50), nullable=True)  # 'project-ops', 'crisis-ops', or NULL
    project_id = Column(Integer, nullable=True)
    project_slug = Column(String(200), nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "session_id": self.session_id,
            "name": self.name,
            "description": self.description,
            "meeting_type": self.meeting_type,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "duration": self.duration,
            "status": self.status,
            "extra_data": self.extra_data
        }

class Transcription(Base):
    """Transcription model - matches actual database schema"""
    __tablename__ = "transcriptions"
    
    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, nullable=False)  # Foreign key to RecordingSession.id (integer)
    text = Column(Text, nullable=False)
    speaker = Column(String(100))  # Speaker name
    # Note: speaker_id column doesn't exist in actual database
    start_time = Column(Float)  # Start time in seconds
    end_time = Column(Float)    # End time in seconds
    confidence = Column(Float)  # Transcription confidence
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))  # Creation timestamp
    
    # REMOVED: These columns don't exist in actual database:
    # duration_seconds = Column(Float)  # ❌ REMOVED
    # processing_time_ms = Column(Float)  # ❌ REMOVED  
    # npu_accelerated = Column(Boolean)  # ❌ REMOVED
    # model_used = Column(String(100))  # ❌ REMOVED
    # speaker_confidence = Column(Float)  # ❌ REMOVED
    
    def to_dict(self):
        return {
            "id": self.id,
            "session_id": self.session_id,
            "text": self.text,
            "speaker": self.speaker,
            "timestamp": self.created_at.isoformat() if self.created_at else None,
            "confidence": self.confidence,
            "start_time": self.start_time,
            "end_time": self.end_time
        }

class Speaker(Base):
    """Speaker model"""
    __tablename__ = "speakers"
    
    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, nullable=False)
    speaker_id = Column(String(100), nullable=False)
    display_name = Column(String(100))
    total_speaking_time = Column(Float, default=0.0)
    total_segments = Column(Integer, default=0)
    first_appearance = Column(Float)
    last_appearance = Column(Float)
    confidence = Column(Float)
    voice_characteristics = Column(JSON)
    
    def to_dict(self):
        return {
            "id": self.id,
            "session_id": self.session_id,
            "speaker_id": self.speaker_id,
            "name": self.display_name,
            "total_speaking_time": self.total_speaking_time,
            "total_segments": self.total_segments,
            "first_heard": self.first_appearance,
            "last_heard": self.last_appearance,
            "confidence": self.confidence,
            "voice_characteristics": self.voice_characteristics
        }

class AudioFile(Base):
    """Audio file model"""
    __tablename__ = "audio_files"
    
    id = Column(Integer, primary_key=True)
    file_id = Column(String(100), unique=True, nullable=False)
    session_id = Column(String(100), nullable=False)
    user_id = Column(Integer)
    filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_size = Column(Integer)
    file_format = Column(String(10))
    mime_type = Column(String(50))
    duration_seconds = Column(Float)
    sample_rate = Column(Integer)
    channels = Column(Integer)
    uploaded_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)


class ChatHistory(Base):
    """Persisted AI chat history for per-meeting and cross-meeting RAG conversations."""
    __tablename__ = "chat_history"

    id = Column(Integer, primary_key=True)
    # session_id for per-meeting chat, or "__rag__" for cross-meeting RAG chat
    session_key = Column(String(200), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # "user" or "assistant"
    content = Column(Text, nullable=False)
    metadata_json = Column(Text, nullable=True)  # JSON string for extra metadata
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)


class SatelliteDevice(Base):
    """Satellite recording device (ESP32-S3, Raspberry Pi, companion app)"""
    __tablename__ = "satellite_devices"

    id = Column(Integer, primary_key=True)
    device_id = Column(String(100), unique=True, nullable=False)
    name = Column(String(200))
    room_name = Column(String(200))
    device_type = Column(String(50))  # "esp32", "esp32-s3", "rpi4", "rpi5", "companion-app"
    capabilities = Column(Text)  # JSON string: {"audio": true, "local_stt": false, "vad": false, "sd_card": true}
    ip_address = Column(String(50))
    last_heartbeat = Column(DateTime)
    status = Column(String(50), default="offline")  # "online", "offline", "recording", "uploading", "error"
    firmware_version = Column(String(50))
    config = Column(Text)  # JSON string: {"sample_rate": 16000, "bit_depth": 16, "channels": 1, "stream_mode": "websocket"}
    api_key = Column(String(200))  # Hashed API key for device authentication
    current_session_id = Column(String(100), nullable=True)  # Active recording session
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, onupdate=lambda: datetime.now(timezone.utc))
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)


class OrgProviderSettings(Base):
    """Per-organization provider configuration for pluggable AI services."""
    __tablename__ = "org_provider_settings"
    __table_args__ = (
        Index("ix_org_provider_settings_org_kind", "organization_id", "service_kind", unique=True),
    )

    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    service_kind = Column(String(50), nullable=False)  # llm, stt, tts, embeddings, reranking, diarization
    provider_name = Column(String(50), nullable=False)  # litellm, openai, infinity, kokoro, etc.
    endpoint_url = Column(String(500), nullable=True)
    api_key_encrypted = Column(Text, nullable=True)  # Fernet-encrypted
    model_name = Column(String(200), nullable=True)
    overrides = Column(JSON, nullable=True)  # {"fast": {"model": "x"}, "quality": {"model": "y"}}
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class MeetingChunkEmbedding(Base):
    """Tracks chunk embeddings for meeting transcripts in Qdrant."""
    __tablename__ = "meeting_chunk_embedding"

    id = Column(Integer, primary_key=True)
    meeting_id = Column(Integer, ForeignKey("recording_sessions.id"), nullable=False, index=True)
    chunk_idx = Column(Integer, nullable=False)
    qdrant_point_id = Column(String(100), nullable=False)
    text_snippet = Column(String(200), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class MeetingDigest(Base):
    """Cached time-window meeting digests."""
    __tablename__ = "meeting_digest"
    __table_args__ = (
        Index("ix_meeting_digest_org_period", "organization_id", "period", "date"),
    )

    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    period = Column(String(20), nullable=False)  # day, week, month, quarter, year
    date = Column(String(10), nullable=False)  # YYYY-MM-DD
    project_id = Column(Integer, nullable=True)
    content = Column(Text, nullable=False)
    meeting_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class UploadJob(Base):
    """Chunked media upload state and processing pipeline progress."""
    __tablename__ = "upload_jobs"
    __table_args__ = (
        Index("ix_upload_jobs_org_upload_id", "organization_id", "upload_id", unique=True),
        Index("ix_upload_jobs_stage", "stage"),
    )

    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    upload_id = Column(UUID(as_uuid=True), unique=True, nullable=False, default=uuid.uuid4, index=True)
    filename = Column(Text, nullable=False)
    content_type = Column(Text, nullable=True)
    action = Column(String(20), nullable=False, default="transcribe")
    total_size = Column(BigInteger, nullable=False)
    bytes_received = Column(BigInteger, nullable=False, default=0)
    chunks_received = Column(Integer, nullable=False, default=0)
    total_chunks = Column(Integer, nullable=False, default=0)
    stage = Column(String(30), nullable=False, default="queued")
    last_completed_stage = Column(String(30), nullable=True)
    progress_pct = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)
    session_id = Column(Integer, ForeignKey("recording_sessions.id"), nullable=True)
    job_started_at = Column(DateTime, nullable=True)
    job_completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


# ---------- Phase 3: Speaker Library ----------
# These are *org-level* speakers (a person across many meetings), distinct
# from the existing per-session `Speaker` model above which holds raw
# diarized labels for a single recording.
#
# Embeddings are stored as raw bytes + a dim column so we can swap models
# (ECAPA 192-d -> ECAPA-XL 256-d -> WavLM 768-d) without a schema change.
# Encode/decode helpers live in services/speaker_service.py.

from sqlalchemy import LargeBinary  # noqa: E402


class SpeakerProfile(Base):
    """Org-level speaker identity. One row per real person you want to
    recognise across meetings."""
    __tablename__ = "speaker"
    __table_args__ = (
        Index("ix_speaker_org", "organization_id"),
        Index("ix_speaker_org_name", "organization_id", "display_name", unique=True),
    )

    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    display_name = Column(String(200), nullable=False)
    email = Column(String(320), nullable=True)
    notes = Column(Text, nullable=True)
    centroid_embedding = Column(LargeBinary, nullable=True)
    embedding_dim = Column(Integer, nullable=True)
    embedding_model = Column(String(100), nullable=True)
    sample_count = Column(Integer, nullable=False, default=0)
    created_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class SpeakerVoiceSample(Base):
    """A single embedding + (optionally) the audio bytes that produced it.
    Created by enrollment uploads and by post-meeting auto-identification."""
    __tablename__ = "speaker_voice_sample"
    __table_args__ = (
        Index("ix_speaker_voice_sample_speaker", "speaker_id"),
        Index("ix_speaker_voice_sample_org", "organization_id"),
        Index("ix_speaker_voice_sample_session", "source_session_id"),
    )

    id = Column(Integer, primary_key=True)
    speaker_id = Column(Integer, ForeignKey("speaker.id", ondelete="CASCADE"), nullable=False)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    source = Column(String(50), nullable=False)  # "enrollment" | "session"
    source_session_id = Column(Integer, ForeignKey("recording_sessions.id", ondelete="SET NULL"), nullable=True)
    source_segment_idx = Column(Integer, nullable=True)
    embedding = Column(LargeBinary, nullable=False)
    embedding_dim = Column(Integer, nullable=False)
    embedding_model = Column(String(100), nullable=False)
    audio_path = Column(String(500), nullable=True)  # only set when STORE_SPEAKER_AUDIO=true
    duration_seconds = Column(Float, nullable=True)
    similarity_to_centroid = Column(Float, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class SpeakerSessionLink(Base):
    """Maps a recording_session's raw diarized label (e.g. "SPEAKER_00")
    to an org-level SpeakerProfile. One row per unique (session, raw_label)."""
    __tablename__ = "speaker_session_link"
    __table_args__ = (
        Index("ix_speaker_session_link_session", "session_id"),
        Index("ix_speaker_session_link_org", "organization_id"),
        Index("ix_speaker_session_link_speaker", "speaker_id"),
        Index("uq_speaker_session_link_label", "session_id", "raw_label", unique=True),
    )

    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("recording_sessions.id", ondelete="CASCADE"), nullable=False)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    raw_label = Column(String(100), nullable=False)
    speaker_id = Column(Integer, ForeignKey("speaker.id", ondelete="SET NULL"), nullable=True)
    similarity = Column(Float, nullable=True)
    source = Column(String(20), nullable=False, default="auto")  # "auto" | "manual"
    confirmed = Column(Boolean, nullable=False, default=False)
    confirmed_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
