"""Database models for Meeting-Ops"""
from sqlalchemy import Column, Integer, String, DateTime, Text, Float, Boolean, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import UUID
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