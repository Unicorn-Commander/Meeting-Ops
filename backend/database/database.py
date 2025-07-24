from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
import os

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./meeting_sessions.db")

# Create SQLAlchemy engine
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)

# Create SessionLocal class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create Base
Base = declarative_base()

def get_db():
    """Dependency to get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_database():
    """Initialize database tables"""
    # Import all models to ensure they're registered
    from auth.models import User, Organization, UserOrganization, AuditLog
    from database.models import Session, Transcription, Speaker, AudioSegment, Settings, AudioFile
    
    # Create all tables using the shared Base
    Base.metadata.create_all(bind=engine)
    print("📊 Database tables created successfully")

def reset_database():
    """Reset all database tables (for development)"""
    from database.models import Base
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    print("🔄 Database reset completed")