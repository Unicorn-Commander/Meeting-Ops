from sqlalchemy import Column, Integer, String, Text, DateTime, Float, Boolean, ForeignKey, JSON, BigInteger
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()

class Session(Base):
    __tablename__ = "sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, unique=True, index=True)  # UUID for WebSocket sessions
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    start_time = Column(DateTime, default=datetime.utcnow)
    end_time = Column(DateTime, nullable=True)
    duration_seconds = Column(Integer, default=0)
    status = Column(String, default="active")  # active, paused, completed, failed
    
    # Audio metadata
    audio_file_path = Column(String, nullable=True)
    audio_format = Column(String, default="wav")
    sample_rate = Column(Integer, default=16000)
    channels = Column(Integer, default=1)
    
    # Processing metadata
    total_transcriptions = Column(Integer, default=0)
    total_speakers = Column(Integer, default=0)
    processing_completed = Column(Boolean, default=False)
    npu_accelerated = Column(Boolean, default=False)
    
    # Summary and insights
    summary = Column(Text, nullable=True)
    key_points = Column(JSON, nullable=True)  # List of key points
    action_items = Column(JSON, nullable=True)  # List of action items
    meeting_type = Column(String, nullable=True)  # meeting, presentation, interview, etc.
    
    # Relationships
    transcriptions = relationship("Transcription", back_populates="session", cascade="all, delete-orphan")
    speakers = relationship("Speaker", back_populates="session", cascade="all, delete-orphan")
    
    def to_dict(self):
        return {
            "id": self.id,
            "session_id": self.session_id,
            "name": self.name,
            "description": self.description,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_seconds": self.duration_seconds,
            "status": self.status,
            "audio_file_path": self.audio_file_path,
            "audio_format": self.audio_format,
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "total_transcriptions": self.total_transcriptions,
            "total_speakers": self.total_speakers,
            "processing_completed": self.processing_completed,
            "npu_accelerated": self.npu_accelerated,
            "summary": self.summary,
            "key_points": self.key_points,
            "action_items": self.action_items,
            "meeting_type": self.meeting_type,
        }

class Transcription(Base):
    __tablename__ = "transcriptions"
    
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"))
    
    # Transcription content
    text = Column(Text, nullable=False)
    confidence = Column(Float, default=0.0)
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    # Audio timing
    start_time_seconds = Column(Float, default=0.0)  # Start time in audio
    end_time_seconds = Column(Float, default=0.0)    # End time in audio
    duration_seconds = Column(Float, default=0.0)
    
    # Processing metadata
    processing_time_ms = Column(Float, default=0.0)
    npu_accelerated = Column(Boolean, default=False)
    model_used = Column(String, default="whisper-base")
    
    # Speaker information
    speaker_id = Column(String, nullable=True)  # Speaker identifier
    speaker_confidence = Column(Float, default=0.0)
    
    # Relationships
    session = relationship("Session", back_populates="transcriptions")
    
    def to_dict(self):
        return {
            "id": self.id,
            "session_id": self.session_id,
            "text": self.text,
            "confidence": self.confidence,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "start_time_seconds": self.start_time_seconds,
            "end_time_seconds": self.end_time_seconds,
            "duration_seconds": self.duration_seconds,
            "processing_time_ms": self.processing_time_ms,
            "npu_accelerated": self.npu_accelerated,
            "model_used": self.model_used,
            "speaker_id": self.speaker_id,
            "speaker_confidence": self.speaker_confidence,
        }

class Speaker(Base):
    __tablename__ = "speakers"
    
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"))
    
    # Speaker identification
    speaker_id = Column(String, nullable=False)  # e.g., "SPEAKER_00", "SPEAKER_01"
    display_name = Column(String, nullable=True)  # Optional human-readable name
    
    # Speaker statistics
    total_speaking_time = Column(Float, default=0.0)  # Total seconds spoken
    total_segments = Column(Integer, default=0)       # Number of speaking segments
    first_appearance = Column(Float, default=0.0)     # First time speaker appears
    last_appearance = Column(Float, default=0.0)      # Last time speaker appears
    
    # Speaker characteristics (from diarization model)
    confidence = Column(Float, default=0.0)
    voice_characteristics = Column(JSON, nullable=True)  # Model-specific features
    
    # Relationships
    session = relationship("Session", back_populates="speakers")
    
    def to_dict(self):
        return {
            "id": self.id,
            "session_id": self.session_id,
            "speaker_id": self.speaker_id,
            "display_name": self.display_name,
            "total_speaking_time": self.total_speaking_time,
            "total_segments": self.total_segments,
            "first_appearance": self.first_appearance,
            "last_appearance": self.last_appearance,
            "confidence": self.confidence,
            "voice_characteristics": self.voice_characteristics,
        }

class AudioSegment(Base):
    __tablename__ = "audio_segments"
    
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"))
    transcription_id = Column(Integer, ForeignKey("transcriptions.id"), nullable=True)
    
    # Audio segment metadata
    start_time = Column(Float, nullable=False)  # Start time in seconds
    end_time = Column(Float, nullable=False)    # End time in seconds
    duration = Column(Float, nullable=False)
    
    # Audio file information
    audio_file_path = Column(String, nullable=True)  # Path to segment audio file
    audio_format = Column(String, default="wav")
    
    # Quality metrics
    signal_level = Column(Float, default=0.0)     # Average signal level
    noise_level = Column(Float, default=0.0)      # Background noise level
    clarity_score = Column(Float, default=0.0)    # Audio clarity assessment
    
    def to_dict(self):
        return {
            "id": self.id,
            "session_id": self.session_id,
            "transcription_id": self.transcription_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration": self.duration,
            "audio_file_path": self.audio_file_path,
            "audio_format": self.audio_format,
            "signal_level": self.signal_level,
            "noise_level": self.noise_level,
            "clarity_score": self.clarity_score,
        }

class Settings(Base):
    __tablename__ = "settings"
    
    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, index=True, nullable=False)
    value = Column(JSON, nullable=False)
    category = Column(String, nullable=False)  # audio, ai, storage, network, etc.
    description = Column(String, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        return {
            "id": self.id,
            "key": self.key,
            "value": self.value,
            "category": self.category,
            "description": self.description,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

class AudioFile(Base):
    __tablename__ = "audio_files"
    
    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(String, unique=True, index=True, nullable=False)  # Unique file identifier
    session_id = Column(String, ForeignKey("sessions.session_id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # User who created the file
    
    # File information
    filename = Column(String, nullable=False)
    file_path = Column(String, unique=True, nullable=False)
    file_size = Column(BigInteger, nullable=False)  # Size in bytes
    file_format = Column(String, nullable=False)  # wav, mp3, etc.
    mime_type = Column(String, nullable=False)
    
    # Audio metadata
    duration_seconds = Column(Float, nullable=True)
    sample_rate = Column(Integer, nullable=True)
    channels = Column(Integer, nullable=True)
    bit_depth = Column(Integer, nullable=True)
    
    # Status and timestamps
    status = Column(String, default="ready")  # ready, processing, error, deleted
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at = Column(DateTime, nullable=True)  # Soft delete
    
    # Access control
    is_public = Column(Boolean, default=False)
    access_count = Column(Integer, default=0)
    last_accessed = Column(DateTime, nullable=True)
    
    # Metadata
    tags = Column(JSON, nullable=True)  # List of tags
    extra_metadata = Column(JSON, nullable=True)  # Additional metadata
    
    def to_dict(self):
        return {
            "id": self.id,
            "file_id": self.file_id,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "filename": self.filename,
            "file_path": self.file_path,
            "file_size": self.file_size,
            "file_format": self.file_format,
            "mime_type": self.mime_type,
            "duration_seconds": self.duration_seconds,
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "bit_depth": self.bit_depth,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "deleted_at": self.deleted_at.isoformat() if self.deleted_at else None,
            "is_public": self.is_public,
            "access_count": self.access_count,
            "last_accessed": self.last_accessed.isoformat() if self.last_accessed else None,
            "tags": self.tags,
            "metadata": self.extra_metadata,
        }