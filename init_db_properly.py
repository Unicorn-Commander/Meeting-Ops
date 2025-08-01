#!/usr/bin/env python3
"""
Initialize database properly with all required tables
"""
import sys
import os
sys.path.append('/home/ucadmin/Development/Unicorn-Commander-Meeting-Ops/backend')

from database.database import init_database, engine
from database.models import Base
from sqlalchemy import text

print("Initializing database...")

# Initialize all tables
init_database()

# Check what tables were created
with engine.connect() as conn:
    result = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
    tables = [row[0] for row in result]
    print(f"Tables created: {tables}")
    
    # Check if settings table has data
    if 'settings' in tables:
        result = conn.execute(text("SELECT COUNT(*) FROM settings"))
        count = result.scalar()
        print(f"Settings table has {count} rows")
        
        if count == 0:
            print("Adding default settings...")
            # Add some basic settings
            conn.execute(text("""
                INSERT INTO settings (category, key, value, description) VALUES 
                ('ai', 'whisper_model', 'whisper-base', 'Default Whisper model'),
                ('audio', 'sample_rate', '16000', 'Audio sample rate'),
                ('audio', 'input_source', 'usb', 'Default audio input source')
            """))
            conn.commit()
            print("✅ Default settings added")

print("✅ Database initialization complete")