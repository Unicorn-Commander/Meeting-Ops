# Meeting-Ops Backend Development Guide
Part of the Unicorn Commander Suite - Backend Specific Instructions

## 🎯 Backend Overview
FastAPI + Python 3.13 backend for the Meeting-Ops AI-powered meeting recording appliance. This document is specifically for AI assistants working on the backend code only.

## 📊 Current Backend Status (January 14, 2025)
- **Overall Completion**: 95%
- **Core APIs**: 100% Complete
- **Recording System**: 90% Complete (minor fixes needed)
- **Transcription**: 95% Complete (column name issues)
- **AI Integration**: 100% Complete
- **Database**: 95% Complete (schema mismatches)
- **WebSocket**: 95% Complete (parameter issues)

## 🚀 Quick Start

### Development Server
```bash
cd backend
./start-backend.sh  # Recommended - handles all setup

# Or manually:
source venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 9050 --reload
```

### Database Setup
```bash
# PostgreSQL should be running via Docker
docker compose -f docker-compose-full-stack.yml up -d

# Database: postgresql://meetingops:REMOVED@localhost:5432/meeting_sessions
```

### Test Backend
```bash
# Check health
curl http://localhost:9050/health

# API docs
open http://localhost:9050/docs

# List sessions
curl http://localhost:9050/api/simple/recording-sessions
```

## 🔧 Key Backend Components

### Core Services
- `/services/working_audio_service.py` - Audio recording ✅ Working
- `/services/real_whisper_service.py` - NPU transcription ✅ Working
- `/services/unified_agent_service.py` - AI summaries ⚠️ Missing method
- `/services/live_recording_transcription.py` - Live transcription ⚠️ Parameter issue

### API Routers
- `/api/simple_recording_db.py` - Main recording API ✅ NEW - Database-backed
- `/api/websocket_transcription.py` - WebSocket for live transcription
- `/api/websocket_auto_summary.py` - Progressive AI summaries
- `/api/unified_agent_api.py` - AI agent configuration

### Database Models
- `/database/models.py` - SQLAlchemy models ⚠️ Column mismatches
- `/models/unified_agent.py` - Unified agent model

## ✅ What's Working

1. **Recording Pipeline**
   - Audio capture via FFmpeg
   - File saving to disk
   - Database session management
   - Status tracking (active → recording → processing → completed)

2. **Transcription**
   - NPU-accelerated Whisper (220x speedup)
   - Real-time transcription via WebSocket
   - Speaker diarization
   - Word-level timestamps

3. **AI Features**
   - Unified agent with granite3.3:8b
   - Progressive summarization
   - Auto-title generation
   - Meeting insights

4. **Database**
   - PostgreSQL integration
   - Session persistence
   - Basic CRUD operations

## ❌ Known Backend Issues

### High Priority Fixes Needed

1. **Database Column Mismatches**
```python
# Issue: Transcription model expects 'timestamp' but DB has 'created_at'
# File: /database/models.py
class Transcription(Base):
    timestamp = Column(DateTime)  # Should be created_at
    
# Also: RecordingSession model has mismatched columns:
# - start_time vs started_at
# - end_time vs ended_at  
# - audio_file_path vs audio_file
```

2. **UnifiedAgentService Missing Method**
```python
# Issue: analyze_meeting method doesn't exist
# File: /services/unified_agent_service.py
# Need to add:
async def analyze_meeting(self, session_id: str, transcript: str):
    # Implementation needed
```

3. **LiveRecordingTranscription Parameter Issue**
```python
# Issue: start_monitoring expects different parameters
# File: /services/live_recording_transcription.py
# Called with: start_monitoring(session_id, audio_file_path)
# Expects: start_monitoring(session_id) only
```

4. **Audio File Path Double Nesting**
```python
# Issue: File paths getting duplicated
# Example: "recordings/recording_xxx.wav/recording_xxx.wav"
# Should be: "recordings/recording_xxx.wav"
```

### Medium Priority

5. **Transcription Not Saving to DB**
   - Segments generated but not persisted
   - Column name issues preventing saves

6. **Summary Generation Errors**
   - Method missing in UnifiedAgentService
   - Fallback not working properly

7. **WebSocket Parameter Mismatches**
   - Live transcription start/stop issues
   - Audio levels not verified as real

## 🎯 Priority Tasks for Backend

### Immediate Database Fixes
```python
# 1. Fix Transcription model columns
class Transcription(Base):
    __tablename__ = "transcriptions"
    
    id = Column(Integer, primary_key=True)
    session_id = Column(String(100), nullable=False)
    text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)  # Not timestamp
    # ... rest of columns

# 2. Fix RecordingSession columns to match DB
class RecordingSession(Base):
    started_at = Column(DateTime)  # Not start_time
    ended_at = Column(DateTime)    # Not end_time
    audio_file = Column(String(500))  # Not audio_file_path
```

### Add Missing UnifiedAgentService Method
```python
# services/unified_agent_service.py
async def analyze_meeting(self, session_id: str, transcript: str) -> dict:
    """Analyze meeting transcript with unified agent"""
    try:
        agent = self.get_current_agent()
        
        # Call Ollama with agent prompt
        response = await self._call_ollama(
            prompt=f"{agent.system_prompt}\n\nTRANSCRIPT:\n{transcript}",
            model=agent.model_name
        )
        
        return {
            "success": True,
            "analysis": response,
            "agent_id": str(agent.id)
        }
    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        return {"success": False, "error": str(e)}
```

### Fix Live Transcription Parameters
```python
# api/simple_recording_db.py - Fix the call
# Change from:
asyncio.create_task(live_recording_transcription.start_monitoring(
    session_id=session_id,
    audio_file_path=file_path  # Remove this parameter
))

# To:
asyncio.create_task(live_recording_transcription.start_monitoring(
    session_id=session_id
))
```

## 🔌 Database Schema

### Current Tables
```sql
-- recording_sessions table (actual columns)
id INTEGER PRIMARY KEY
title VARCHAR
status VARCHAR
created_at TIMESTAMP
started_at TIMESTAMP  -- Note: not start_time
ended_at TIMESTAMP    -- Note: not end_time
audio_file VARCHAR    -- Note: not audio_file_path
transcript TEXT
summary TEXT
user_id INTEGER
updated_at TIMESTAMP
session_id VARCHAR
name VARCHAR
meeting_type VARCHAR
extra_data JSON
description TEXT
duration FLOAT

-- transcriptions table
id INTEGER PRIMARY KEY
session_id VARCHAR
text TEXT
speaker VARCHAR
speaker_id VARCHAR
start_time FLOAT
end_time FLOAT
confidence FLOAT
created_at TIMESTAMP  -- Note: not timestamp
```

## 🐛 Debugging Tips

### Check Database Connection
```python
from database.database import engine
from sqlalchemy import text

with engine.connect() as conn:
    result = conn.execute(text("SELECT 1"))
    print("DB connected:", result.scalar() == 1)
```

### Test Recording Flow
```bash
# 1. Create session
SESSION_ID=$(curl -s -X POST http://localhost:9050/api/simple/recording-sessions \
  -H "Content-Type: application/json" \
  -d '{"name": "Test"}' | jq -r .id)

# 2. Start recording
curl -X POST http://localhost:9050/api/simple/recording-sessions/$SESSION_ID/start

# 3. Stop after few seconds
sleep 10
curl -X POST http://localhost:9050/api/simple/recording-sessions/$SESSION_ID/stop

# 4. Check session
curl http://localhost:9050/api/simple/recording-sessions/$SESSION_ID
```

### Monitor Logs
```bash
# Backend logs
tail -f backend.log

# Check specific service
grep -E "unified_agent|transcription" backend.log

# Database queries
grep "SQL" backend.log
```

## 📁 Backend File Structure
```
backend/
├── api/                  # API endpoints
│   ├── simple_recording_db.py  # NEW - Main recording API
│   ├── websocket_transcription.py
│   └── unified_agent_api.py
├── services/            # Business logic
│   ├── working_audio_service.py
│   ├── real_whisper_service.py
│   └── unified_agent_service.py
├── database/            # Database config
│   ├── database.py     # Connection setup
│   └── models.py       # SQLAlchemy models
├── models/             # Additional models
│   └── unified_agent.py
└── main.py             # FastAPI app
```

## 🔧 Service Architecture

### Audio Recording Flow
```
USB Mic → FFmpeg → WAV File → Database Record
                ↓
         Whisper NPU → Transcription
                ↓
         Unified Agent → Summary
```

### WebSocket Flow
```
Frontend ←→ WebSocket ←→ Backend Service
         ↓           ↓
    Live Updates   Redis Pub/Sub
```

## 📝 Notes for AI Backend Developers

### DO:
- Fix database column mismatches first
- Test with actual database queries
- Handle exceptions properly
- Log errors with context
- Use async/await for I/O operations

### DON'T:
- Change API endpoints without updating frontend
- Modify working NPU code
- Break existing WebSocket connections
- Use in-memory storage (use database)
- Ignore database transaction management

### Testing Checklist:
- [ ] Recording creates database session
- [ ] Audio file saves to correct path
- [ ] Transcription saves to database
- [ ] Summary generates properly
- [ ] WebSocket sends updates
- [ ] Session retrieval works
- [ ] Export endpoints function

## 🔄 Recent Changes (January 14, 2025)

### Major Fixes Applied:
1. **Created simple_recording_db.py** - Database-backed recording API
2. **Fixed model column names** - Partial fix, more needed
3. **Sessions persist** - No longer lost on restart
4. **Duration tracking** - Properly calculated and saved

### Still Broken:
1. **Transcription segments** - Not saving due to column issues
2. **Summaries** - UnifiedAgentService method missing
3. **Live transcription** - Parameter mismatch
4. **Some column names** - Need complete alignment

## 🎯 Next Steps for Backend

1. **Fix all column mismatches** in models.py
2. **Add analyze_meeting method** to UnifiedAgentService
3. **Fix live transcription parameters**
4. **Test complete recording → transcription → summary flow**
5. **Verify WebSocket data is real** (not mock)
6. **Clean up duplicate file path issue**

## 🚀 Performance Notes

### NPU Acceleration
- Whisper Large-v3: 220x speedup
- 1 hour audio: 16.2 seconds processing
- Real-time factor: 0.0045 RTF
- Throughput: 4,789 tokens/second

### Database Performance
- Use connection pooling
- Batch insert transcription segments
- Index on session_id, created_at
- Vacuum regularly

### Memory Management
- Stream large audio files
- Chunk transcription processing
- Clear WebSocket buffers
- Limit concurrent sessions

---

**For frontend-specific work, refer to /frontend/CLAUDE.md**
**For project overview, refer to the main /CLAUDE.md**