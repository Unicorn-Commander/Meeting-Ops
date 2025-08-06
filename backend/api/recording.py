"""
Recording API endpoints that use the audio recorder service
"""
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime
import uuid
import os
import json

from database.database import get_db
from database.models import RecordingSession, User
from auth.auth import get_current_user
from services.audio_recorder import audio_recorder

router = APIRouter(prefix="/api", tags=["recording"])

# In-memory active sessions (supplement to database)
active_sessions = {}

@router.post("/recording-sessions")
async def create_recording_session(
    name: str,
    description: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new recording session"""
    
    # Create database entry
    session = RecordingSession(
        name=name,
        description=description,
        user_id=current_user.id,
        created_at=datetime.utcnow(),
        status="created"
    )
    
    db.add(session)
    db.commit()
    db.refresh(session)
    
    # Store in memory for quick access
    active_sessions[str(session.id)] = {
        "db_id": session.id,
        "name": name,
        "user_id": current_user.id,
        "status": "created",
        "audio_file": None
    }
    
    return {
        "id": str(session.id),
        "name": session.name,
        "description": session.description,
        "created_at": session.created_at.isoformat(),
        "status": session.status
    }

@router.post("/recording-sessions/{session_id}/start")
async def start_recording(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Start recording audio for a session"""
    
    # Get session from database
    session = db.query(RecordingSession).filter(
        RecordingSession.id == session_id
    ).first()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if session.user_id != current_user.id and current_user.role not in ["admin", "superuser"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    try:
        # Start actual audio recording
        audio_file = audio_recorder.start_recording(
            session_id=session_id,
            session_name=session.name
        )
        
        # Update database
        session.status = "recording"
        session.started_at = datetime.utcnow()
        session.audio_file_path = audio_file
        db.commit()
        
        # Update memory cache
        if session_id in active_sessions:
            active_sessions[session_id]["status"] = "recording"
            active_sessions[session_id]["audio_file"] = audio_file
        
        return {
            "status": "recording",
            "session_id": session_id,
            "audio_file": audio_file,
            "message": "Recording started successfully"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start recording: {str(e)}")

@router.post("/recording-sessions/{session_id}/stop")
async def stop_recording(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """Stop recording and save the audio file"""
    
    # Get session from database
    session = db.query(RecordingSession).filter(
        RecordingSession.id == session_id
    ).first()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if session.user_id != current_user.id and current_user.role not in ["admin", "superuser"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    try:
        # Stop actual audio recording
        result = audio_recorder.stop_recording()
        
        # Update database
        session.status = "completed"
        session.ended_at = datetime.utcnow()
        session.duration = result.get("duration", 0)
        session.file_size = result.get("file_size", 0)
        db.commit()
        
        # Update memory cache
        if session_id in active_sessions:
            active_sessions[session_id]["status"] = "completed"
        
        # TODO: Trigger transcription in background
        # background_tasks.add_task(transcribe_audio, session_id, result["file_path"])
        
        return {
            "status": "completed",
            "session_id": session_id,
            "duration": result.get("duration", 0),
            "file_path": result.get("file_path"),
            "file_size": result.get("file_size", 0),
            "message": "Recording stopped successfully"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to stop recording: {str(e)}")

@router.post("/recording-sessions/{session_id}/pause")
async def pause_recording(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Pause or resume recording"""
    
    # Get session from database
    session = db.query(RecordingSession).filter(
        RecordingSession.id == session_id
    ).first()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if session.user_id != current_user.id and current_user.role not in ["admin", "superuser"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    try:
        # Pause/resume actual recording
        result = audio_recorder.pause_recording()
        
        # Update status
        new_status = "paused" if result.get("paused") else "recording"
        session.status = new_status
        db.commit()
        
        # Update memory cache
        if session_id in active_sessions:
            active_sessions[session_id]["status"] = new_status
        
        return {
            "status": new_status,
            "session_id": session_id,
            "paused": result.get("paused", False)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to pause recording: {str(e)}")

@router.get("/recording-sessions")
async def list_recording_sessions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all recording sessions for the current user"""
    
    # Admins can see all sessions
    if current_user.role in ["admin", "superuser"]:
        sessions = db.query(RecordingSession).order_by(
            RecordingSession.created_at.desc()
        ).all()
    else:
        sessions = db.query(RecordingSession).filter(
            RecordingSession.user_id == current_user.id
        ).order_by(
            RecordingSession.created_at.desc()
        ).all()
    
    return [
        {
            "id": str(s.id),
            "name": s.name,
            "description": s.description,
            "status": s.status,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "started_at": s.started_at.isoformat() if s.started_at else None,
            "ended_at": s.ended_at.isoformat() if s.ended_at else None,
            "duration": s.duration,
            "file_size": s.file_size
        }
        for s in sessions
    ]

@router.get("/recording-sessions/{session_id}")
async def get_recording_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get details of a specific recording session"""
    
    session = db.query(RecordingSession).filter(
        RecordingSession.id == session_id
    ).first()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if session.user_id != current_user.id and current_user.role not in ["admin", "superuser"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    return {
        "id": str(session.id),
        "name": session.name,
        "description": session.description,
        "status": session.status,
        "created_at": session.created_at.isoformat() if session.created_at else None,
        "started_at": session.started_at.isoformat() if session.started_at else None,
        "ended_at": session.ended_at.isoformat() if session.ended_at else None,
        "duration": session.duration,
        "file_size": session.file_size,
        "audio_file_path": session.audio_file_path
    }

@router.post("/recording-sessions/{session_id}/auto-rename")
async def auto_rename_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Auto-rename session based on transcription content using LLM"""
    
    session = db.query(RecordingSession).filter(
        RecordingSession.id == session_id
    ).first()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if session.user_id != current_user.id and current_user.role not in ["admin", "superuser"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # TODO: Implement actual LLM-based renaming using transcription
    # For now, use a simple mock
    
    original_name = session.name
    
    # Mock intelligent renaming
    import random
    topics = [
        "Team Standup",
        "Project Planning",
        "Client Meeting",
        "Design Review",
        "Sprint Retrospective",
        "Architecture Discussion",
        "Budget Review",
        "Product Demo"
    ]
    
    new_name = f"{random.choice(topics)} - {datetime.now().strftime('%B %d, %Y')}"
    
    session.name = new_name
    db.commit()
    
    return {
        "originalName": original_name,
        "newName": new_name,
        "session_id": session_id
    }

@router.get("/audio-devices")
async def list_audio_devices(
    current_user: User = Depends(get_current_user)
):
    """List available audio input devices on the server"""
    try:
        devices = audio_recorder.list_devices()
        return {"devices": devices}
    except Exception as e:
        return {"devices": [], "error": str(e)}

@router.get("/recording-status")
async def get_recording_status(
    current_user: User = Depends(get_current_user)
):
    """Get current recording status"""
    return audio_recorder.get_status()