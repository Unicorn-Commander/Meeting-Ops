#!/usr/bin/env python3
"""Add test audio file to database for FileManager testing"""

import sys
sys.path.insert(0, '.')

from database.database import SessionLocal
from database.models import AudioFile
from datetime import datetime
import uuid
import os

db = SessionLocal()

try:
    # Create test audio file entry
    test_file = AudioFile(
        file_id=str(uuid.uuid4()),
        session_id="test-session-001",
        user_id=1,  # Assuming admin user
        filename="meeting-2025-07-25.wav",
        file_path="/recordings/test/meeting-2025-07-25.wav",
        file_size=15728640,  # 15MB
        file_format="wav",
        mime_type="audio/wav",
        duration_seconds=1800,  # 30 minutes
        sample_rate=16000,
        channels=1,
        bit_depth=16,
        is_processed=True,
        transcription_ready=True,
        tags=["important", "quarterly-review", "team-meeting"],
        metadata={
            "recording_device": "USB Microphone",
            "room": "Conference Room A",
            "attendees": 8
        },
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    
    db.add(test_file)
    
    # Add another file
    test_file2 = AudioFile(
        file_id=str(uuid.uuid4()),
        session_id="test-session-002",
        user_id=1,
        filename="standup-2025-07-24.wav",
        file_path="/recordings/test/standup-2025-07-24.wav",
        file_size=5242880,  # 5MB
        file_format="wav",
        mime_type="audio/wav",
        duration_seconds=600,  # 10 minutes
        sample_rate=16000,
        channels=1,
        bit_depth=16,
        is_processed=True,
        transcription_ready=False,
        tags=["daily-standup", "engineering"],
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    
    db.add(test_file2)
    
    # Add a third file
    test_file3 = AudioFile(
        file_id=str(uuid.uuid4()),
        session_id="test-session-003",
        user_id=1,
        filename="client-demo-2025-07-23.wav",
        file_path="/recordings/test/client-demo-2025-07-23.wav",
        file_size=31457280,  # 30MB
        file_format="wav",
        mime_type="audio/wav",
        duration_seconds=3600,  # 1 hour
        sample_rate=44100,
        channels=2,
        bit_depth=24,
        is_processed=False,
        transcription_ready=False,
        tags=["client", "demo", "sales"],
        metadata={
            "client_name": "Acme Corp",
            "presenter": "John Doe",
            "product_version": "2.5.0"
        },
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    
    db.add(test_file3)
    
    db.commit()
    print("Successfully added 3 test audio files!")
    
    # List all files
    files = db.query(AudioFile).all()
    print(f"\nTotal files in database: {len(files)}")
    for f in files:
        print(f"- {f.filename} ({f.file_format}, {f.file_size/1024/1024:.1f}MB)")
        
except Exception as e:
    print(f"Error: {e}")
    db.rollback()
finally:
    db.close()