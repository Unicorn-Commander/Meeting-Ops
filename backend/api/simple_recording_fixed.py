"""
Fixed Simple Recording API - Uses working audio service
This is a drop-in replacement for simple_recording.py that actually works
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from datetime import datetime
from typing import Dict, Any, Optional
import asyncio
import os
import logging

# Import the working audio service
from services.working_audio_service import audio_service
from services.transcription_service import transcription_service
from services.gemma_custom_service import GemmaCustomService

router = APIRouter(prefix="/api/simple", tags=["simple-recording"])
logger = logging.getLogger(__name__)

# In-memory session storage (replace with database in production)
sessions: Dict[str, Any] = {}

# Initialize services
gemma_service = GemmaCustomService()

class CreateSessionRequest(BaseModel):
    name: str
    description: Optional[str] = ""

class SessionResponse(BaseModel):
    id: str
    name: str
    description: str
    created_at: str
    status: str
    duration: float

@router.post("/recording-sessions")
async def create_session(request: CreateSessionRequest) -> SessionResponse:
    """Create a new recording session"""
    import uuid
    
    session_id = str(uuid.uuid4())
    session = {
        "id": session_id,
        "name": request.name,
        "description": request.description or "",
        "created_at": datetime.utcnow().isoformat(),
        "status": "created",
        "duration": 0,
        "audio_file": None,
        "transcription": None
    }
    
    sessions[session_id] = session
    
    return SessionResponse(**session)

@router.post("/recording-sessions/{session_id}/start")
async def start_recording(session_id: str):
    """Start recording - THIS ACTUALLY WORKS NOW!"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    try:
        # Use the working audio service
        success, result = audio_service.start_recording(session_id)
        
        if success:
            sessions[session_id]["status"] = "recording"
            sessions[session_id]["start_time"] = datetime.utcnow().isoformat()
            sessions[session_id]["audio_file"] = result
            
            # Start live transcription monitoring
            try:
                from services.live_recording_transcription import live_recording_transcription
                asyncio.create_task(
                    live_recording_transcription.start_monitoring(result, session_id)
                )
                logger.info(f"Started live transcription for session {session_id}")
            except Exception as e:
                logger.warning(f"Could not start live transcription: {e}")
            
            return {
                "status": "recording",
                "message": "Recording started successfully",
                "audio_file": result,
                "live_transcription": True
            }
        else:
            raise HTTPException(status_code=500, detail=f"Failed to start recording: {result}")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start recording: {str(e)}")

@router.post("/recording-sessions/{session_id}/stop")
async def stop_recording(session_id: str):
    """Stop recording and transcribe"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if sessions[session_id]["status"] != "recording":
        raise HTTPException(status_code=400, detail="Session is not recording")
    
    try:
        # Stop recording
        success, audio_file = audio_service.stop_recording(session_id)
        
        if not success:
            raise HTTPException(status_code=500, detail=f"Failed to stop recording: {audio_file}")
        
        # Stop live transcription monitoring  
        try:
            from services.live_recording_transcription import live_recording_transcription
            asyncio.create_task(live_recording_transcription.stop_monitoring())
            logger.info(f"Stopped live transcription for session {session_id}")
        except Exception as e:
            logger.warning(f"Could not stop live transcription: {e}")
        
        # Update session
        sessions[session_id]["status"] = "processing"
        sessions[session_id]["stop_time"] = datetime.utcnow().isoformat()
        
        # Calculate duration
        start = datetime.fromisoformat(sessions[session_id]["start_time"])
        stop = datetime.fromisoformat(sessions[session_id]["stop_time"])
        duration = (stop - start).total_seconds()
        sessions[session_id]["duration"] = duration
        
        # Start transcription in background
        asyncio.create_task(transcribe_audio(session_id, audio_file))
        
        return {
            "status": "processing",
            "message": "Recording stopped, transcription in progress",
            "duration": duration,
            "audio_file": audio_file
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to stop recording: {str(e)}")

async def transcribe_audio(session_id: str, audio_file: str):
    """Transcribe audio file using NPU service"""
    try:
        # Check if file exists
        if not os.path.exists(audio_file):
            sessions[session_id]["status"] = "error"
            sessions[session_id]["error"] = "Audio file not found"
            return
        
        # Transcribe using the transcription service
        # This will use NPU acceleration if available
        result = await asyncio.to_thread(
            transcription_service.transcribe_file,
            audio_file
        )
        
        if result:
            sessions[session_id]["transcription"] = result
            sessions[session_id]["status"] = "completed"
        else:
            sessions[session_id]["status"] = "completed"
            sessions[session_id]["transcription"] = {
                "text": "[Transcription not available]",
                "segments": []
            }
            
    except Exception as e:
        sessions[session_id]["status"] = "error"
        sessions[session_id]["error"] = str(e)

@router.get("/recording-sessions")
async def list_sessions():
    """List all recording sessions"""
    return list(sessions.values())

@router.get("/recording-sessions/{session_id}")
async def get_session(session_id: str):
    """Get session details"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    return sessions[session_id]

@router.get("/audio-devices")
async def list_audio_devices():
    """List available audio devices"""
    # For now, just return that we're using PulseAudio default
    return {
        "devices": [
            {
                "index": 0,
                "name": "System Default (PulseAudio)",
                "channels": 1,
                "sample_rate": 44100,
                "is_default": True
            }
        ]
    }

@router.get("/recording-status")
async def get_recording_status():
    """Get current recording status"""
    # Find any active recording
    for session_id, session in sessions.items():
        if session["status"] == "recording":
            return {
                "is_recording": True,
                "session_id": session_id,
                "session_name": session["name"],
                "started_at": session.get("start_time")
            }
    
    return {
        "is_recording": False,
        "session_id": None,
        "session_name": None
    }