#!/usr/bin/env python3
"""Simple test of recording and transcription"""
import os
os.environ['LD_PRELOAD'] = '/lib/x86_64-linux-gnu/libstdc++.so.6'

import time
from services.audio_input_service import audio_input_service
from services.audio_recording_service import audio_recording_service
from services.transcription_service import transcription_service
from database.database import SessionLocal
from database.models import RecordingSession
from datetime import datetime

print("🧪 Simple Recording and Transcription Test")
print("=" * 50)

# Create a database session
db = SessionLocal()

try:
    # 1. Create a recording session in database
    print("\n1️⃣ Creating database session...")
    session = RecordingSession(
        meeting_name="Simple Test Session",
        meeting_type="test",
        recording_mode="automatic",
        created_at=datetime.utcnow(),
        status="active"
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    session_id = session.session_id
    print(f"✅ Session created: {session_id}")
    
    # 2. Initialize audio
    print("\n2️⃣ Initializing audio service...")
    audio_input_service.initialize("default", 16000, 1)
    print("✅ Audio initialized")
    
    # 3. Set up file recording
    audio_file = f"test_session_{int(time.time())}.wav"
    print(f"\n3️⃣ Setting up file recording: {audio_file}")
    audio_recording_service.start_recording(session_id, audio_file)
    
    # 4. Track transcriptions
    transcriptions = []
    
    def handle_audio_data(sess_id, audio_bytes):
        audio_recording_service.write_audio_chunk(sess_id, audio_bytes)
    
    def handle_audio_chunk(sess_id, chunk_bytes):
        print(f"📦 Received {len(chunk_bytes)} byte chunk")
        try:
            result = transcription_service.process_audio_chunk(chunk_bytes, session_id=sess_id)
            if result:
                print(f"📝 Transcription: {result.text}")
                transcriptions.append(result.text)
                
                # Save to database
                from database.models import Transcription
                trans = Transcription(
                    session_id=sess_id,
                    text=result.text,
                    timestamp=datetime.utcnow(),
                    confidence=0.95,
                    speaker_id="speaker1"
                )
                db.add(trans)
                db.commit()
                
        except Exception as e:
            print(f"❌ Transcription error: {e}")
    
    # 5. Register callbacks
    audio_input_service.register_callback('audio_data', handle_audio_data)
    audio_input_service.register_callback('audio_chunk', handle_audio_chunk)
    print("✅ Callbacks registered")
    
    # 6. Start recording
    print(f"\n4️⃣ Starting recording...")
    audio_input_service.start_recording(session_id)
    print("🎙️ Recording for 15 seconds...")
    
    # Monitor
    for i in range(15):
        print(f"   {i+1}/15s - transcriptions: {len(transcriptions)}")
        time.sleep(1)
    
    # 7. Stop recording
    print("\n5️⃣ Stopping recording...")
    audio_input_service.stop_recording()
    stats = audio_recording_service.stop_recording(session_id)
    
    # Update session status
    session.status = "completed"
    db.commit()
    
    # Results
    print(f"\n📊 Results:")
    print(f"   Transcriptions: {len(transcriptions)}")
    print(f"   Audio file: {stats['file_path'] if stats else 'N/A'}")
    print(f"   File size: {stats['bytes_written'] if stats else 0} bytes")
    print(f"   Duration: {stats['duration_seconds'] if stats else 0:.1f} seconds")
    
    if transcriptions:
        print(f"\n📝 Full transcript:")
        for t in transcriptions:
            print(f"   - {t}")
    
except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()
finally:
    db.close()
    
print("\n" + "=" * 50)
print("✅ Test complete!")