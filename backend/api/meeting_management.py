"""
Complete Meeting Management API endpoints for the frontend
"""
from fastapi import APIRouter, HTTPException, Depends, Query, UploadFile, File, BackgroundTasks
from fastapi.responses import StreamingResponse, FileResponse
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta, timezone
from pydantic import BaseModel
import json
import os
import uuid
import asyncio
from pathlib import Path
import subprocess
import tempfile

# Import dependencies
from database.database import get_db, SessionLocal
from database.models import RecordingSession, Transcription
from sqlalchemy.orm import Session
from auth.dependencies import get_current_user, get_current_organization
from auth.models import User
from auth.organization import ActiveOrganization
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["meetings"])

# Global storage for active recordings
active_recordings = {}
recording_processes = {}

class SessionCreate(BaseModel):
    name: str
    description: Optional[str] = None

class SessionUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    starred: Optional[bool] = None
    tags: Optional[List[str]] = None

class TranscriptUpdate(BaseModel):
    transcript: List[Dict[str, Any]]

class SummarizationTemplate(BaseModel):
    id: Optional[str] = None
    name: str
    category: str
    description: str
    icon: str = "FileText"
    prompt: str
    outputFormat: str = "markdown"
    extractFields: List[str] = []
    maxLength: int = 1500
    temperature: float = 0.3
    model: str = "llama3"
    isDefault: bool = False

# Recording Session Endpoints
@router.post("/recording-sessions")
async def create_session(
    session_data: SessionCreate
):
    """Create a new recording session"""
    # For now, just return a mock response since we're having DB issues
    # This will allow the recording UI to work
    session_id = str(uuid.uuid4())
    
    # Store in memory for this session
    active_recordings[session_id] = {
        "id": session_id,
        "name": session_data.name,
        "description": session_data.description,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "created",
        "start_time": None,
        "audio_chunks": []
    }
    
    return {
        "id": session_id,
        "name": session_data.name,
        "description": session_data.description,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "created"
    }

@router.get("/recording-sessions")
async def list_sessions(
    db: Session = Depends(get_db) if get_db else None,
    current_user = Depends(get_current_user) if get_current_user else None,
    skip: int = 0,
    limit: int = 100
):
    """List all recording sessions for the current user"""
    try:
        sessions = db.query(RecordingSession).filter(
            RecordingSession.user_id == current_user.id
        ).offset(skip).limit(limit).all()
        
        result = []
        for session in sessions:
            # Get transcript word count and speaker count
            transcripts = db.query(Transcription).filter(
                Transcription.session_id == session.id
            ).all()
            
            word_count = sum(len(t.text.split()) for t in transcripts if t.text)
            speakers = set(t.speaker for t in transcripts if t.speaker)
            
            result.append({
                "id": session.id,
                "name": session.name,
                "created_at": session.created_at.isoformat(),
                "duration": session.duration or 0,
                "status": session.status or "completed",
                "file_size": session.file_size or 0,
                "speaker_count": len(speakers),
                "word_count": word_count,
                "has_transcript": len(transcripts) > 0,
                "has_summary": bool(session.summary),
                "tags": session.tags or [],
                "starred": session.starred or False,
                "npu_processed": session.npu_processed or False,
                "processing_time": session.processing_time or 0,
                "confidence_score": session.confidence_score or 0.0
            })
        
        return result
    except Exception as e:
        logger.error(f"Failed to list sessions: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/recording-sessions/{session_id}")
async def get_session(
    session_id: str,
    db: Session = Depends(get_db) if get_db else None,
    current_user = Depends(get_current_user) if get_current_user else None
):
    """Get detailed information about a recording session"""
    try:
        session = db.query(RecordingSession).filter(
            RecordingSession.id == session_id,
            RecordingSession.user_id == current_user.id
        ).first()
        
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Get transcripts
        transcripts = db.query(Transcription).filter(
            Transcription.session_id == session_id
        ).order_by(Transcription.start_time).all()
        
        # Format transcript segments
        transcript_data = []
        speakers_data = {}
        
        for t in transcripts:
            segment = {
                "id": str(t.id),
                "speaker": t.speaker or f"Speaker {t.speaker_id or 1}",
                "text": t.text,
                "start_time": t.start_time,
                "end_time": t.end_time,
                "confidence": t.confidence or 0.95,
                "is_final": True,
                "words": []  # Would need word-level timestamps from NPU
            }
            transcript_data.append(segment)
            
            # Track speaker stats
            speaker = segment["speaker"]
            if speaker not in speakers_data:
                speakers_data[speaker] = {
                    "id": speaker,
                    "name": speaker,
                    "color": f"text-blue-400",  # Would assign different colors
                    "segments": 0,
                    "totalTime": 0
                }
            speakers_data[speaker]["segments"] += 1
            speakers_data[speaker]["totalTime"] += (t.end_time - t.start_time)
        
        # Get audio file URL
        audio_url = f"/api/files/{session_id}/stream" if session.audio_file_path else None
        
        return {
            "id": session.id,
            "name": session.name,
            "created_at": session.created_at.isoformat(),
            "duration": session.duration or 0,
            "audio_url": audio_url,
            "transcript": transcript_data,
            "speakers": list(speakers_data.values()),
            "npu_processed": session.npu_processed or False,
            "processing_time": session.processing_time or 0,
            "summary": session.summary
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get session: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/recording-sessions/{session_id}")
async def delete_session(
    session_id: str,
    db: Session = Depends(get_db) if get_db else None,
    current_user = Depends(get_current_user) if get_current_user else None
):
    """Delete a recording session"""
    try:
        session = db.query(RecordingSession).filter(
            RecordingSession.id == session_id,
            RecordingSession.user_id == current_user.id
        ).first()
        
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Delete associated transcripts
        db.query(Transcription).filter(
            Transcription.session_id == session_id
        ).delete()
        
        # Delete audio file if exists
        if session.audio_file_path and os.path.exists(session.audio_file_path):
            os.remove(session.audio_file_path)
        
        # Delete session
        db.delete(session)
        db.commit()
        
        return {"status": "deleted", "session_id": session_id}
    except Exception as e:
        logger.error(f"Failed to delete session: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/recording-sessions/{session_id}")
async def update_session(
    session_id: str,
    update_data: SessionUpdate,
    db: Session = Depends(get_db) if get_db else None,
    current_user = Depends(get_current_user) if get_current_user else None
):
    """Update session metadata"""
    try:
        session = db.query(RecordingSession).filter(
            RecordingSession.id == session_id,
            RecordingSession.user_id == current_user.id
        ).first()
        
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        if update_data.name is not None:
            session.name = update_data.name
        if update_data.description is not None:
            session.description = update_data.description
        if update_data.starred is not None:
            session.starred = update_data.starred
        if update_data.tags is not None:
            session.tags = update_data.tags
        
        db.commit()
        return {"status": "updated", "session_id": session_id}
    except Exception as e:
        logger.error(f"Failed to update session: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/recording-sessions/{session_id}/transcript")
async def update_transcript(
    session_id: str,
    transcript_data: TranscriptUpdate,
    db: Session = Depends(get_db) if get_db else None,
    current_user = Depends(get_current_user) if get_current_user else None
):
    """Update the transcript for a session"""
    try:
        session = db.query(RecordingSession).filter(
            RecordingSession.id == session_id,
            RecordingSession.user_id == current_user.id
        ).first()
        
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Delete existing transcripts
        db.query(Transcription).filter(
            Transcription.session_id == session_id
        ).delete()
        
        # Add new transcripts
        for segment in transcript_data.transcript:
            transcript = Transcription(
                session_id=session_id,
                speaker=segment.get("speaker"),
                speaker_id=segment.get("speaker_id"),
                text=segment.get("text", ""),
                start_time=segment.get("start_time", 0),
                end_time=segment.get("end_time", 0),
                confidence=segment.get("confidence", 0.95)
            )
            db.add(transcript)
        
        db.commit()
        return {"status": "updated", "session_id": session_id}
    except Exception as e:
        logger.error(f"Failed to update transcript: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/recording-sessions/{session_id}/export")
async def export_session(
    session_id: str,
    format: str = Query(default="txt", pattern="^(txt|md|markdown|json|pdf|docx|srt)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
):
    """Export session in various formats.

    Org-scoped via ``_get_session_for_export``: the caller's active
    organization must own the session row. Per-user filtering was the legacy
    pre-multi-org behavior and 404'd every valid session once the
    ``organization_id`` column became canonical.

    Supported formats:
      - ``txt``       — plain transcript
      - ``md`` / ``markdown`` — GitHub-flavored markdown summary
      - ``json``      — structured session + transcript payload
      - ``srt``       — subtitle file
      - ``pdf``       — PDF summary (delegated to batch_export)
      - ``docx``      — DOCX summary (delegated to batch_export)
    """
    try:
        # Org-scoped lookup. Accepts either int PK or UUID string session_id.
        from api.batch_export import _get_session_for_export
        session = _get_session_for_export(db, active_org.organization.id, session_id)

        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        # Get transcripts (legacy Transcription rows — many sessions instead
        # carry diarized JSON on the session row itself; both paths are
        # tolerated below).
        transcripts = db.query(Transcription).filter(
            Transcription.session_id == session.id
        ).order_by(Transcription.start_time).all()

        if format == "txt":
            content = f"Meeting: {session.name}\n"
            content += f"Date: {session.created_at}\n"
            content += f"Duration: {session.duration} seconds\n\n"
            content += "Transcript:\n"
            content += "-" * 50 + "\n"

            for t in transcripts:
                speaker = t.speaker or f"Speaker {t.speaker_id or 1}"
                content += f"\n[{speaker}]: {t.text}\n"

            return StreamingResponse(
                iter([content.encode()]),
                media_type="text/plain",
                headers={"Content-Disposition": f"attachment; filename=transcript-{session_id}.txt"}
            )

        elif format in ("md", "markdown"):
            # Delegate to batch_export.export_to_markdown so we share the
            # GitHub-flavored renderer used everywhere else. ExportOptions
            # defaults already match the summary-only behavior expected by
            # the SessionDetails markdown button.
            from api.batch_export import export_to_markdown, ExportOptions
            options = ExportOptions(includeTranscript=False)
            content = export_to_markdown(session, options)
            return StreamingResponse(
                iter([content.encode("utf-8")]),
                media_type="text/markdown; charset=utf-8",
                headers={"Content-Disposition": f"attachment; filename=transcript-{session_id}.md"}
            )

        elif format == "json":
            data = {
                "session": {
                    "id": session.id,
                    "name": session.name,
                    "date": session.created_at.isoformat() if session.created_at else None,
                    "duration": session.duration
                },
                "transcript": [
                    {
                        "speaker": t.speaker or f"Speaker {t.speaker_id or 1}",
                        "text": t.text,
                        "start_time": t.start_time,
                        "end_time": t.end_time,
                        "confidence": t.confidence
                    }
                    for t in transcripts
                ]
            }

            return StreamingResponse(
                iter([json.dumps(data, indent=2).encode()]),
                media_type="application/json",
                headers={"Content-Disposition": f"attachment; filename=transcript-{session_id}.json"}
            )

        elif format == "srt":
            content = ""
            for i, t in enumerate(transcripts, 1):
                start = format_srt_time(t.start_time)
                end = format_srt_time(t.end_time)
                speaker = t.speaker or f"Speaker {t.speaker_id or 1}"
                content += f"{i}\n"
                content += f"{start} --> {end}\n"
                content += f"[{speaker}] {t.text}\n\n"

            return StreamingResponse(
                iter([content.encode()]),
                media_type="text/plain",
                headers={"Content-Disposition": f"attachment; filename=transcript-{session_id}.srt"}
            )

        elif format == "pdf":
            from api.batch_export import export_to_pdf, ExportOptions
            pdf_bytes = export_to_pdf(session, ExportOptions())
            return StreamingResponse(
                iter([pdf_bytes]),
                media_type="application/pdf",
                headers={"Content-Disposition": f"attachment; filename=transcript-{session_id}.pdf"}
            )

        elif format == "docx":
            from api.batch_export import export_to_docx, ExportOptions
            docx_bytes = export_to_docx(session, ExportOptions())
            return StreamingResponse(
                iter([docx_bytes]),
                media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                headers={"Content-Disposition": f"attachment; filename=transcript-{session_id}.docx"}
            )

        else:  # pragma: no cover — regex above pins the allowed values
            raise HTTPException(status_code=501, detail=f"Export format {format} not yet implemented")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to export session: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/recording-sessions/{session_id}/reprocess")
async def reprocess_session(
    session_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db) if get_db else None,
    current_user = Depends(get_current_user) if get_current_user else None
):
    """Reprocess a session with NPU"""
    try:
        session = db.query(RecordingSession).filter(
            RecordingSession.id == session_id,
            RecordingSession.user_id == current_user.id
        ).first()
        
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        session.status = "processing"
        db.commit()
        
        # Trigger NPU reprocessing
        background_tasks.add_task(process_with_npu, session_id, db)
        
        return {"status": "processing", "session_id": session_id}
    except Exception as e:
        logger.error(f"Failed to reprocess session: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# NPU Status Endpoint
@router.get("/system/npu-status")
async def get_npu_status():
    """Get NPU status and performance metrics"""
    try:
        npu_status = {
            "status": "idle",
            "processingSpeed": 0,
            "device": "/dev/accel/accel0",
            "available": False
        }
        
        # Check if NPU device exists
        if os.path.exists("/dev/accel/accel0"):
            npu_status["available"] = True
            npu_status["status"] = "active"
            
            # Check if any processing is happening
            if len(active_recordings) > 0:
                npu_status["status"] = "processing"
                npu_status["processingSpeed"] = 250  # Example: 250x real-time
        
        return npu_status
    except Exception as e:
        logger.error(f"Failed to get NPU status: {e}")
        return {"status": "error", "available": False}

# Analytics Endpoints
@router.get("/analytics/meetings")
async def get_meeting_analytics(
    range: str = Query(default="week", pattern="^(week|month|quarter|year|all)$"),
    db: Session = Depends(get_db) if get_db else None,
    current_user = Depends(get_current_user) if get_current_user else None
):
    """Get meeting analytics for a time range"""
    try:
        # Calculate date range
        end_date = datetime.now(timezone.utc)
        if range == "week":
            start_date = end_date - timedelta(days=7)
        elif range == "month":
            start_date = end_date - timedelta(days=30)
        elif range == "quarter":
            start_date = end_date - timedelta(days=90)
        elif range == "year":
            start_date = end_date - timedelta(days=365)
        else:
            start_date = datetime(2020, 1, 1)  # All time
        
        # Query sessions
        sessions = db.query(RecordingSession).filter(
            RecordingSession.user_id == current_user.id,
            RecordingSession.created_at >= start_date
        ).all()
        
        # Calculate stats
        total_duration = sum(s.duration or 0 for s in sessions)
        total_words = 0
        npu_count = sum(1 for s in sessions if s.npu_processed)
        
        for session in sessions:
            transcripts = db.query(Transcription).filter(
                Transcription.session_id == session.id
            ).all()
            total_words += sum(len(t.text.split()) for t in transcripts if t.text)
        
        return {
            "total_meetings": len(sessions),
            "total_duration": total_duration,
            "total_words": total_words,
            "average_duration": total_duration / len(sessions) if sessions else 0,
            "npu_processed_count": npu_count,
            "storage_used": sum(s.file_size or 0 for s in sessions)
        }
    except Exception as e:
        logger.error(f"Failed to get analytics: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Summarization Templates
templates_storage = []  # In production, this would be in database

@router.get("/summarization-templates")
async def get_templates(current_user: User = Depends(get_current_user)):
    """Get all summarization templates"""
    if not templates_storage:
        # Return default templates
        return []
    return templates_storage

@router.post("/summarization-templates")
async def create_template(
    template: SummarizationTemplate,
    current_user: User = Depends(get_current_user)
):
    """Create a new summarization template"""
    template.id = str(uuid.uuid4())
    templates_storage.append(template.dict())
    return template

@router.put("/summarization-templates/{template_id}")
async def update_template(
    template_id: str,
    template: SummarizationTemplate,
    current_user: User = Depends(get_current_user)
):
    """Update a summarization template"""
    for i, t in enumerate(templates_storage):
        if t["id"] == template_id:
            template.id = template_id
            templates_storage[i] = template.dict()
            return template
    raise HTTPException(status_code=404, detail="Template not found")

@router.delete("/summarization-templates/{template_id}")
async def delete_template(
    template_id: str,
    current_user: User = Depends(get_current_user)
):
    """Delete a summarization template"""
    global templates_storage
    templates_storage = [t for t in templates_storage if t["id"] != template_id]
    return {"status": "deleted"}

# Helper Functions
def format_srt_time(seconds: float) -> str:
    """Format seconds to SRT timestamp"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

async def process_with_npu(session_id: str, db: Session):
    """Process audio with NPU (placeholder for real NPU processing)"""
    try:
        # In real implementation, this would:
        # 1. Load audio file
        # 2. Send to NPU for transcription
        # 3. Get speaker diarization
        # 4. Save results to database
        
        session = db.query(RecordingSession).filter(
            RecordingSession.id == session_id
        ).first()
        
        if session:
            session.status = "completed"
            session.npu_processed = True
            session.processing_time = 1500  # Example: 1.5 seconds
            session.confidence_score = 0.95
            db.commit()
            
    except Exception as e:
        logger.error(f"NPU processing failed: {e}")
        session = db.query(RecordingSession).filter(
            RecordingSession.id == session_id
        ).first()
        if session:
            session.status = "failed"
            db.commit()