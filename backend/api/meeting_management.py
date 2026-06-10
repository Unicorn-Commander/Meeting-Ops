"""
Meeting Management API endpoints.

HONESTY AUDIT (2026-06-10): this router was historically a grab-bag and
several endpoints returned FAKE/static data. The frontend calls NONE of the
routes this module uniquely owns (verified by grepping frontend/src — the
only non-/api/simple call, GET /api/recording-sessions/{id} in roomsApi.ts,
is served by api/sessions.py which main.py loads first and therefore wins
routing). The fake endpoints now return an honest HTTP 501 instead of
fabricated data:

  - POST /api/recording-sessions            — was an in-memory mock ("DB
    issues" workaround), unauthenticated, and shadowed by api/sessions.py
    anyway. Real creation lives at POST /api/simple/recording-sessions.
  - POST /api/recording-sessions/{id}/reprocess — pretended to reprocess via
    a background task that just stamped npu_processed=True / 1500ms / 0.95
    confidence without doing any work. Real reprocess lives at
    POST /api/uploads/sessions/{id}/reprocess (Arq queue).
  - GET  /api/system/npu-status             — fabricated "250x real-time"
    NPU metrics (same family as the fake NPU banner removed in the
    pre-onboarding sweep).
  - /api/summarization-templates CRUD       — "persisted" to a process-local
    list that evaporated on restart.
  - GET  /api/analytics/meetings            — written against a pre-multi-org
    model schema: it reads RecordingSession.npu_processed / file_size, which
    DO NOT EXIST on the live model, so it 500'd the moment any session fell
    in range (and returned zeros computed from nothing otherwise). It cannot
    serve real data; 501 until rebuilt (analytics_simple.py is the real
    analytics surface).

Still REAL and intentionally kept:
  - GET /api/recording-sessions/{id}/export — org-scoped, delegates to
    batch_export renderers, covered by tests/test_export.py.
  - DELETE/PATCH /api/recording-sessions/{id}, PUT .../transcript — real
    (legacy user_id-scoped) DB operations. KNOWN DEFECTS, uncalled by the
    frontend, left for the wave-3 backlog: DELETE reads the nonexistent
    ``audio_file_path`` column (500s before commit, rollback keeps data
    safe); PATCH silently drops ``starred`` (not a model column).
  - GET /api/recording-sessions[/{id}] — real DB reads, but shadowed by
    api/sessions.py (loaded first), so effectively dead code (also reads
    the nonexistent legacy columns above).

The router itself MUST keep loading so /health's routers_loaded count stays
stable.
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import StreamingResponse
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
import json
import os

# Import dependencies
from database.database import get_db
from database.models import RecordingSession, Transcription
from sqlalchemy.orm import Session
from auth.dependencies import get_current_user, get_current_organization
from auth.models import User
from auth.organization import ActiveOrganization
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["meetings"])

_NOT_IMPLEMENTED = HTTPException(status_code=501, detail="Not implemented")

class SessionUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    starred: Optional[bool] = None
    tags: Optional[List[str]] = None

class TranscriptUpdate(BaseModel):
    transcript: List[Dict[str, Any]]

# Recording Session Endpoints
@router.post("/recording-sessions")
async def create_session():
    """NOT IMPLEMENTED — was an unauthenticated in-memory mock.

    This route is shadowed by api/sessions.py's POST (loaded first) in the
    live app; real session creation is POST /api/simple/recording-sessions.
    """
    raise _NOT_IMPLEMENTED

@router.get("/recording-sessions")
async def list_sessions(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
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
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
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
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
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
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
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
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
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
    current_user: User = Depends(get_current_user),
):
    """NOT IMPLEMENTED — previously FAKED reprocessing (a background task
    stamped npu_processed=True, processing_time=1500, confidence=0.95 without
    doing any work). Real reprocess: POST /api/uploads/sessions/{id}/reprocess.
    """
    raise _NOT_IMPLEMENTED

# NPU Status Endpoint
@router.get("/system/npu-status")
async def get_npu_status():
    """NOT IMPLEMENTED — previously returned fabricated NPU metrics
    ("250x real-time"). There is no NPU in the live inference stack."""
    raise _NOT_IMPLEMENTED

# Analytics Endpoints
@router.get("/analytics/meetings")
async def get_meeting_analytics(
    range: str = Query(default="week", pattern="^(week|month|quarter|year|all)$"),
    current_user: User = Depends(get_current_user),
):
    """NOT IMPLEMENTED — was written against a pre-multi-org schema and read
    RecordingSession.npu_processed / file_size, which do not exist on the
    live model: it 500'd whenever any session fell in the range. The real
    analytics surface is api/analytics_simple.py (/api/analytics/*)."""
    raise _NOT_IMPLEMENTED

# Summarization Templates — NOT IMPLEMENTED. The old handlers "persisted"
# templates to a process-local list (lost on every restart) and the frontend
# never calls these routes. 501 until a real DB-backed implementation lands.

@router.get("/summarization-templates")
async def get_templates(current_user: User = Depends(get_current_user)):
    """NOT IMPLEMENTED — no template storage exists."""
    raise _NOT_IMPLEMENTED

@router.post("/summarization-templates")
async def create_template(current_user: User = Depends(get_current_user)):
    """NOT IMPLEMENTED — previously wrote to a process-local list."""
    raise _NOT_IMPLEMENTED

@router.put("/summarization-templates/{template_id}")
async def update_template(
    template_id: str,
    current_user: User = Depends(get_current_user),
):
    """NOT IMPLEMENTED — previously wrote to a process-local list."""
    raise _NOT_IMPLEMENTED

@router.delete("/summarization-templates/{template_id}")
async def delete_template(
    template_id: str,
    current_user: User = Depends(get_current_user),
):
    """NOT IMPLEMENTED — previously wrote to a process-local list."""
    raise _NOT_IMPLEMENTED

# Helper Functions
def format_srt_time(seconds: float) -> str:
    """Format seconds to SRT timestamp"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"