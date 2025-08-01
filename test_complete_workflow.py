#!/usr/bin/env python3
"""
Test complete workflow: create session -> transcribe -> check database
"""
import asyncio
import json
import base64
import numpy as np
import websockets
import requests
from datetime import datetime

async def test_complete_workflow():
    print("🧪 Testing complete recording workflow...")
    
    # Step 1: Create a recording session via API
    print("📝 Step 1: Creating recording session...")
    session_data = {
        "name": "Test Transcription Session",
        "description": "Testing end-to-end transcription workflow"
    }
    
    response = requests.post("http://localhost:9050/api/recording-sessions", json=session_data)
    if response.status_code != 200:
        print(f"❌ Failed to create session: {response.status_code} - {response.text}")
        return
    
    session_info = response.json()
    session_id = session_info['session']['session_id']
    print(f"✅ Created session: {session_id}")
    
    # Step 2: Test transcription via WebSocket
    print("🎤 Step 2: Testing transcription...")
    
    # Create fake audio data
    sample_rate = 16000
    duration = 1.0
    t = np.linspace(0, duration, int(sample_rate * duration))
    audio_data = (np.sin(2 * np.pi * 440 * t) * 0.3 + 
                  np.random.normal(0, 0.05, len(t))) * 32767
    audio_data = audio_data.astype(np.int16)
    audio_bytes = audio_data.tobytes()
    audio_b64 = base64.b64encode(audio_bytes).decode('utf-8')
    
    try:
        uri = f"ws://localhost:9050/ws/stream/{session_id}"
        async with websockets.connect(uri) as websocket:
            print("✅ WebSocket connected!")
            
            # Wait for status
            response = await websocket.recv()
            status = json.loads(response)
            print(f"📡 Status: transcriber_ready = {status.get('transcriber_ready', False)}")
            
            # Send audio chunk
            message = {
                "type": "audio_chunk",
                "audio_data": audio_b64,
                "timestamp": datetime.now().isoformat()
            }
            
            await websocket.send(json.dumps(message))
            print("🎤 Sent audio chunk...")
            
            # Wait for transcription
            response = await asyncio.wait_for(websocket.recv(), timeout=10.0)
            result = json.loads(response)
            
            if result.get("type") == "transcription":
                transcription_data = result.get("data", {})
                text = transcription_data.get('text', '')
                confidence = transcription_data.get('confidence', 0)
                print(f"✅ Transcription: '{text}' (confidence: {confidence})")
            else:
                print(f"⚠️ Unexpected response: {result}")
                
    except Exception as e:
        print(f"❌ WebSocket test failed: {e}")
        return
    
    # Step 3: Check database for transcription
    print("💾 Step 3: Checking database...")
    import sys
    sys.path.append('/home/ucadmin/Development/Unicorn-Commander-Meeting-Ops/backend')
    
    from database.database import SessionLocal
    from database.models import Transcription, RecordingSession
    
    db = SessionLocal()
    try:
        # Find the recording session
        recording_session = db.query(RecordingSession).filter_by(session_id=session_id).first()
        if recording_session:
            print(f"✅ Found recording session: {recording_session.name}")
            
            # Check for transcriptions
            transcriptions = db.query(Transcription).filter_by(session_id=recording_session.id).all()
            print(f"📝 Found {len(transcriptions)} transcription(s)")
            
            for trans in transcriptions:
                print(f"   Text: '{trans.text}'")
                print(f"   Confidence: {trans.confidence}")
                print(f"   Model: {trans.model_used}")
        else:
            print(f"❌ Recording session {session_id} not found in database")
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(test_complete_workflow())