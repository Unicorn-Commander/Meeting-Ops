#!/usr/bin/env python3
"""
Fix audio settings for USB microphone
"""

import sqlite3
import json

# Connect to database
conn = sqlite3.connect('meeting_sessions.db')
cursor = conn.cursor()

# Update sample rate to 48000 (supported by USB mic)
cursor.execute("""
    UPDATE settings 
    SET value = json(?)
    WHERE category = 'audio' AND key = 'audio.sample_rate'
""", (json.dumps(48000),))

# Update input source to use first device (index 0) 
cursor.execute("""
    UPDATE settings 
    SET value = json(?)
    WHERE category = 'audio' AND key = 'audio.input_source'
""", (json.dumps("0"),))  # Use device index 0

conn.commit()

# Verify the changes
cursor.execute("SELECT key, value FROM settings WHERE category = 'audio'")
for row in cursor.fetchall():
    print(f"{row[0]}: {row[1]}")

conn.close()

print("\n✅ Audio settings updated for USB microphone:")
print("   - Sample rate: 48000 Hz")
print("   - Input source: Device 0 (USB)")
print("\n⚠️  You may need to restart the backend for changes to take effect.")