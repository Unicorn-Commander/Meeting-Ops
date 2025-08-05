"""
Session management API endpoints
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from database.database import get_db
from database.models import RecordingSession
from auth.dependencies import get_current_user
from auth.models import User

router = APIRouter(prefix="/recording-sessions", tags=["sessions"])

@router.get("", response_model=List[dict])
async def list_sessions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000)
):
    """List all recording sessions"""
    sessions = db.query(RecordingSession).offset(skip).limit(limit).all()
    return [
        {
            "id": str(session.id),
            "title": session.title,
            "created_at": session.created_at.isoformat() if session.created_at else None,
            "status": session.status,
            "duration": session.duration
        }
        for session in sessions
    ]

@router.get("/{session_id}")
async def get_session(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific recording session"""
    session = db.query(RecordingSession).filter(RecordingSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return {
        "id": str(session.id),
        "title": session.title,
        "created_at": session.created_at.isoformat() if session.created_at else None,
        "status": session.status,
        "duration": session.duration,
        "participants": session.participants,
        "description": session.description
    }

@router.post("")
async def create_session(
    session_data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new recording session"""
    session = RecordingSession(
        title=session_data.get("title", "Untitled Session"),
        description=session_data.get("description", ""),
        participants=session_data.get("participants", []),
        status="pending",
        created_at=datetime.utcnow()
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    
    return {
        "id": str(session.id),
        "title": session.title,
        "created_at": session.created_at.isoformat(),
        "status": session.status
    }