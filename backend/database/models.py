"""Database models for Meeting-Ops"""
from sqlalchemy import Column, Integer, String, DateTime, Text, Float, Boolean, JSON
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

class Settings(Base):
    """Settings model"""
    __tablename__ = "settings"
    
    id = Column(Integer, primary_key=True)
    category = Column(String(50), nullable=False)
    key = Column(String(100), nullable=False)
    value = Column(Text)
    description = Column(String(500))
    updated_at = Column(DateTime, default=datetime.utcnow)

class RecordingSession(Base):
    """Recording session model"""
    __tablename__ = "recording_sessions"
    
    id = Column(String(100), primary_key=True)  # Changed to String for UUID
    session_id = Column(String(100), unique=True, nullable=True)  # Legacy field
    name = Column(String(200))
    description = Column(Text)
    meeting_type = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)
    start_time = Column(DateTime)
    end_time = Column(DateTime)
    duration = Column(Float, default=0)
    status = Column(String(50), default="active")
    extra_data = Column(JSON)
    user_id = Column(Integer)  # Foreign key to User
    audio_file_path = Column(String(500))
    file_size = Column(Integer, default=0)
    summary = Column(Text)
    tags = Column(JSON)
    starred = Column(Boolean, default=False)
    npu_processed = Column(Boolean, default=False)
    processing_time = Column(Float)
    confidence_score = Column(Float)
    
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
    """Transcription model"""
    __tablename__ = "transcriptions"
    
    id = Column(Integer, primary_key=True)
    session_id = Column(String(100), nullable=False)  # Changed to match RecordingSession.id type
    text = Column(Text, nullable=False)
    confidence = Column(Float)
    timestamp = Column(DateTime, default=datetime.utcnow)
    start_time = Column(Float)  # Renamed for consistency
    end_time = Column(Float)    # Renamed for consistency
    duration_seconds = Column(Float)
    processing_time_ms = Column(Float)
    npu_accelerated = Column(Boolean)
    model_used = Column(String(100))
    speaker = Column(String(100))  # Added for speaker name
    speaker_id = Column(String(100))
    speaker_confidence = Column(Float)
    
    def to_dict(self):
        return {
            "id": self.id,
            "session_id": self.session_id,
            "text": self.text,
            "speaker": self.speaker_id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "confidence": self.confidence,
            "start_time_seconds": self.start_time_seconds,
            "end_time_seconds": self.end_time_seconds,
            "duration_seconds": self.duration_seconds,
            "processing_time_ms": self.processing_time_ms,
            "npu_accelerated": self.npu_accelerated,
            "model_used": self.model_used,
            "speaker_confidence": self.speaker_confidence
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
    uploaded_at = Column(DateTime, default=datetime.utcnow)