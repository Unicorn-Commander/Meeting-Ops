"""Database connection and session management"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from .models import Base

# Get database URL from environment or use PostgreSQL
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://meetingops:REMOVED@localhost:5434/meeting_sessions")

# Create engine
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {})

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_database():
    """Initialize database tables"""
    # Import models so their tables are registered on the shared metadata
    from auth import models as _auth_models  # noqa: F401
    from models import vocabulary as _vocabulary_models  # noqa: F401

    Base.metadata.create_all(bind=engine)

def get_db():
    """Get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_db_session():
    """Get database session (direct, not for dependency injection)"""
    return SessionLocal()
