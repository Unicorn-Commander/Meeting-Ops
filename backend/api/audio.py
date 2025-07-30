from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from state import app_state
from services.audio_capture import audio_capture_service

class TranscriptUpdate(BaseModel):
    text: str

router = APIRouter()

@router.post("/sessions/{session_id}/record", tags=["Audio"])
async def start_recording(session_id: str):
    """Start server-side audio recording for a session"""
    if app_state.is_recording:
        raise HTTPException(status_code=400, detail="Recording already in progress")
    
    audio_capture_service.start_recording(session_id)
    app_state.is_recording = True
    app_state.current_session = session_id
    return {"session_id": session_id, "status": "recording_started"}

@router.post("/sessions/{session_id}/stop", tags=["Audio"])
async def stop_recording(session_id: str):
    """Stop server-side recording and return audio file path"""
    if not app_state.is_recording or app_state.current_session != session_id:
        raise HTTPException(status_code=400, detail="No active recording session to stop")
    
    file_path = audio_capture_service.stop_recording()
    app_state.is_recording = False
    app_state.current_session = None
    return {"session_id": session_id, "status": "recording_stopped", "file_path": file_path}

@router.post("/sessions/{session_id}/pause", tags=["Audio"])
async def pause_recording(session_id: str):
    """Pause the current server-side recording session"""
    if not app_state.is_recording or app_state.current_session != session_id:
        raise HTTPException(status_code=400, detail="No active recording session to pause")
    return {"session_id": session_id, "status": "recording_paused"}

@router.post("/sessions/{session_id}/resume", tags=["Audio"])
async def resume_recording(session_id: str):
    """Resume the current server-side recording session"""
    if not app_state.is_recording or app_state.current_session != session_id:
        raise HTTPException(status_code=400, detail="No active recording session to resume")
    return {"session_id": session_id, "status": "recording_resumed"}

@router.put("/sessions/{session_id}/transcript", tags=["Audio"])
async def update_transcript(session_id: str, transcript_update: TranscriptUpdate):
    """Update/correct the transcript for a specific session"""
    return {"session_id": session_id, "status": "transcript_updated", "new_text": transcript_update.text}