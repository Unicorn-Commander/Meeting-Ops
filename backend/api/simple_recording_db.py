"""
Database-backed Simple Recording API
Fixed version that persists to PostgreSQL
"""

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Query
from pydantic import BaseModel
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import desc, or_
import asyncio
import os
import json
import logging
import uuid
import time

# Database imports
from database.database import get_db
from database.models import RecordingSession as DBRecordingSession, Transcription

# Import the working audio service
from services.working_audio_service import audio_service
from services.transcription_service import transcription_service
from services.real_whisper_service import real_whisper_service
from services.unified_agent_service import unified_agent_service


# Vocabulary replacement helper
def apply_vocabulary_replacements(text: str, db_session) -> str:
    """Apply vocabulary term replacements to transcript text."""
    if not text:
        return text
    try:
        from models.vocabulary import CustomVocabulary
        terms = db_session.query(CustomVocabulary).filter(
            CustomVocabulary.is_active == True
        ).order_by(CustomVocabulary.priority.desc()).all()

        if not terms:
            return text

        import re
        replaced_count = 0
        for term in terms:
            if term.regex_pattern:
                try:
                    flags = 0 if term.case_sensitive else re.IGNORECASE
                    new_text = re.sub(term.regex_pattern, term.expansion, text, flags=flags)
                    if new_text != text:
                        replaced_count += 1
                        text = new_text
                except re.error as e:
                    logger.warning(f"Invalid regex pattern for term '{term.term}': {e}")
            else:
                if term.case_sensitive:
                    if term.term in text:
                        text = text.replace(term.term, term.expansion)
                        replaced_count += 1
                else:
                    pattern = re.compile(re.escape(term.term), re.IGNORECASE)
                    new_text = pattern.sub(term.expansion, text)
                    if new_text != text:
                        replaced_count += 1
                        text = new_text

        if replaced_count > 0:
            logger.info(f"Applied {replaced_count} vocabulary replacements")
        return text
    except Exception as e:
        logger.warning(f"Vocabulary replacement failed (non-fatal): {e}")
        return text


from auth.dependencies import get_current_user
from auth.models import User

import redis.asyncio as aioredis

router = APIRouter(prefix="/api/simple", tags=["simple-recording-db"])
logger = logging.getLogger(__name__)

# Redis URL (matches docker-compose port)
_REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6381")

# Track auto-stop monitor tasks so they can be cancelled on manual stop
_auto_stop_tasks: Dict[str, asyncio.Task] = {}

class CreateSessionRequest(BaseModel):
    name: str
    description: Optional[str] = ""

class SessionResponse(BaseModel):
    id: str
    name: str
    title: Optional[str] = None
    description: str
    created_at: str
    status: str
    duration: float
    audio_file: Optional[str] = None
    transcription: Optional[dict] = None
    
@router.post("/recording-sessions")
async def create_session(
    request: CreateSessionRequest, 
    db: Session = Depends(get_db)
) -> SessionResponse:
    """Create a new recording session in database"""
    
    session_id = str(uuid.uuid4())
    
    # Create database session
    db_session = DBRecordingSession(
        session_id=session_id,
        name=request.name,
        title=request.name,  # Use name as title
        description=request.description or "",
        status="active",
        created_at=datetime.now(timezone.utc),
        duration=0.0
    )
    
    db.add(db_session)
    db.commit()
    db.refresh(db_session)
    
    logger.info(f"Created DB session: {session_id}")
    
    return SessionResponse(
        id=session_id,
        name=db_session.name,
        description=db_session.description or "",
        created_at=db_session.created_at.isoformat(),
        status=db_session.status,
        duration=0.0
    )

@router.get("/recording-sessions")
async def list_sessions(
    db: Session = Depends(get_db),
    limit: int = 100
) -> List[SessionResponse]:
    """List all recording sessions from database"""
    
    sessions = db.query(DBRecordingSession)\
        .order_by(desc(DBRecordingSession.created_at))\
        .limit(limit)\
        .all()
    
    result = []
    for session in sessions:
        # Parse transcription if it exists
        transcription_data = None
        if session.transcript:
            try:
                transcription_data = json.loads(session.transcript) if isinstance(session.transcript, str) else session.transcript
            except (json.JSONDecodeError, ValueError, TypeError):
                transcription_data = {"text": session.transcript} if session.transcript else None
        
        result.append(SessionResponse(
            id=session.session_id or str(session.id),
            name=session.name or session.title or f"Session {session.id}",
            title=session.title,
            description=session.description or "",
            created_at=session.created_at.isoformat() if session.created_at else datetime.now(timezone.utc).isoformat(),
            status=session.status or "completed",
            duration=session.duration or 0.0,
            audio_file=session.audio_file,
            transcription=transcription_data
        ))
    
    return result


class SearchResult(BaseModel):
    id: str
    name: str
    description: str
    created_at: str
    status: str
    duration: float
    snippet: Optional[str] = None
    match_field: Optional[str] = None

@router.get("/recording-sessions/search")
async def search_sessions(
    q: str = Query(..., min_length=1, description="Search query string"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
) -> List[SearchResult]:
    """Search recording sessions across name, transcript, and transcript_simple columns.
    Returns matching sessions with a snippet of the matching text."""
    
    search_term = f"%{q}%"
    
    sessions = db.query(DBRecordingSession).filter(
        or_(
            DBRecordingSession.name.ilike(search_term),
            DBRecordingSession.title.ilike(search_term),
            DBRecordingSession.description.ilike(search_term),
            DBRecordingSession.transcript.ilike(search_term),
            DBRecordingSession.transcript_simple.ilike(search_term),
        )
    ).order_by(desc(DBRecordingSession.created_at)).limit(limit).all()
    
    results = []
    for session in sessions:
        snippet = None
        match_field = None
        q_lower = q.lower()
        
        # Determine which field matched and extract a snippet
        if session.name and q_lower in session.name.lower():
            snippet = session.name
            match_field = "name"
        elif session.title and q_lower in session.title.lower():
            snippet = session.title
            match_field = "title"
        elif session.description and q_lower in session.description.lower():
            snippet = _extract_snippet(session.description, q)
            match_field = "description"
        elif session.transcript_simple and q_lower in session.transcript_simple.lower():
            snippet = _extract_snippet(session.transcript_simple, q)
            match_field = "transcript"
        elif session.transcript and q_lower in str(session.transcript).lower():
            # transcript may be JSON, extract text for snippet
            try:
                trans_data = json.loads(session.transcript) if isinstance(session.transcript, str) else session.transcript
                if isinstance(trans_data, dict) and "text" in trans_data:
                    text = trans_data["text"]
                elif isinstance(trans_data, dict) and "segments" in trans_data:
                    text = " ".join(seg.get("text", "") for seg in trans_data["segments"])
                else:
                    text = str(session.transcript)
                snippet = _extract_snippet(text, q)
            except Exception:
                snippet = _extract_snippet(str(session.transcript), q)
            match_field = "transcript"
        
        results.append(SearchResult(
            id=session.session_id or str(session.id),
            name=session.name or session.title or f"Session {session.id}",
            description=session.description or "",
            created_at=session.created_at.isoformat() if session.created_at else "",
            status=session.status or "completed",
            duration=session.duration or 0.0,
            snippet=snippet,
            match_field=match_field,
        ))
    
    return results


def _extract_snippet(text: str, query: str, context_chars: int = 80) -> str:
    """Extract a snippet of text around the first occurrence of the query string."""
    if not text:
        return ""
    idx = text.lower().find(query.lower())
    if idx == -1:
        return text[:160] + ("..." if len(text) > 160 else "")
    
    start = max(0, idx - context_chars)
    end = min(len(text), idx + len(query) + context_chars)
    
    snippet = text[start:end]
    if start > 0:
        snippet = "..." + snippet
    if end < len(text):
        snippet = snippet + "..."
    
    return snippet

@router.get("/recording-sessions/{session_id}")
async def get_session(
    session_id: str,
    db: Session = Depends(get_db)
) -> dict:
    """Get a specific recording session from database with error handling"""
    try:
        # Find by session_id (UUID string)
        session = db.query(DBRecordingSession).filter(
            DBRecordingSession.session_id == session_id
        ).first()
        
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Parse transcription if it exists - with safe error handling
        transcription_data = None
        if session.transcript:
            try:
                if isinstance(session.transcript, str):
                    transcription_data = json.loads(session.transcript)
                else:
                    transcription_data = session.transcript
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(f"Failed to parse transcript JSON for session {session_id}: {e}")
                transcription_data = {"text": str(session.transcript)} if session.transcript else None
        
        # Get transcription segments with error handling
        segments = []
        try:
            transcriptions = db.query(Transcription).filter(
                Transcription.session_id == session.id
            ).order_by(Transcription.start_time).all()
            
            for trans in transcriptions:
                try:
                    segments.append({
                        "text": trans.text or "",
                        "speaker": trans.speaker or "Unknown",
                        "start": trans.start_time or 0,
                        "end": trans.end_time or 0,
                        "confidence": trans.confidence or 0
                    })
                except Exception as e:
                    logger.warning(f"Error processing transcription segment: {e}")
                    continue
                    
        except Exception as e:
            logger.warning(f"Error loading transcription segments for session {session_id}: {e}")
            segments = []
        
        # Build transcription data
        if segments and not transcription_data:
            transcription_data = {"segments": segments}
        elif transcription_data and segments:
            transcription_data["segments"] = segments
        elif not transcription_data:
            transcription_data = {"text": "", "segments": []}
        
        # Parse summary with error handling
        summary_data = None
        if session.summary:
            try:
                if session.summary != "null":
                    if isinstance(session.summary, str):
                        summary_data = json.loads(session.summary)
                    else:
                        summary_data = session.summary
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(f"Failed to parse summary JSON for session {session_id}: {e}")
                summary_data = {"text": str(session.summary)} if session.summary else None
        
        # Return session data with all new fields
        return {
            "id": session.session_id or str(session.id),
            "session_id": session.session_id or str(session.id),
            "name": session.name or session.title or f"Session {session.id}",
            "title": session.title or session.name or f"Session {session.id}",
            "description": session.description or "",
            "created_at": session.created_at.isoformat() if session.created_at else None,
            "started_at": session.started_at.isoformat() if session.started_at else None,
            "ended_at": session.ended_at.isoformat() if session.ended_at else None,
            "status": session.status or "unknown",
            "duration": float(session.duration) if session.duration else 0.0,
            "audio_file": session.audio_file or "",
            # Old fields for backward compatibility
            "transcription": transcription_data,
            "transcription_segments": segments,
            "summary": summary_data,
            "transcript": session.transcript or "",
            # New enhanced fields
            "transcript_simple": session.transcript_simple or "",
            "transcript_diarized": session.transcript_diarized or transcription_data,
            "progressive_summaries": session.progressive_summaries or [],
            "final_summary": session.final_summary or summary_data,
            "ai_insights": session.ai_insights or summary_data,
            "metadata": session.processing_metadata or {},
            "generated_emails": session.generated_emails or [],
            # Legacy fields
            "user_id": session.user_id,
            "meeting_type": session.meeting_type,
            "updated_at": session.updated_at.isoformat() if session.updated_at else None
        }
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Error retrieving session {session_id}: {e}")
        logger.error(f"Exception type: {type(e)}")
        logger.error(f"Exception details: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail=f"Internal server error retrieving session: {str(e)}"
        )

class StartRecordingRequest(BaseModel):
    device_id: Optional[str] = None


async def _monitor_auto_stop(session_id: str, db_session_id: int):
    """Background task that listens for an auto-stop Redis event from the
    LiveRecordingTranscriptionService and finalizes the recording when
    prolonged silence is detected.

    Subscribes to ``recording:{session_id}:auto-stop`` and, on receipt,
    stops the audio capture, updates the DB session, and schedules
    background transcription processing.
    """
    redis_client = None
    pubsub = None
    try:
        redis_client = await aioredis.from_url(_REDIS_URL, decode_responses=True)
        pubsub = redis_client.pubsub()
        channel = f"recording:{session_id}:auto-stop"
        await pubsub.subscribe(channel)
        logger.info(f"Auto-stop monitor subscribed to {channel}")

        async for message in pubsub.listen():
            if message["type"] != "message":
                continue

            logger.warning(f"Auto-stop event received for session {session_id}")

            try:
                event_data = json.loads(message["data"])
                silence_secs = event_data.get("silence_duration_seconds", "unknown")
                logger.info(f"  Reason: prolonged silence ({silence_secs}s)")
            except (json.JSONDecodeError, TypeError):
                pass

            # 1. Stop ffmpeg recording (graceful SIGINT -> WAV header)
            from services.working_audio_service import audio_service as _audio_svc
            success, audio_file = _audio_svc.stop_recording(session_id)
            if not success:
                logger.error(f"Auto-stop: failed to stop audio capture: {audio_file}")

            # 2. Stop live transcription monitoring (already set is_active=False,
            #    but cancel the task explicitly for clean shutdown)
            try:
                from services.live_recording_transcription import live_recording_transcription
                await live_recording_transcription.stop_monitoring()
                logger.info(f"Auto-stop: stopped live transcription for {session_id}")
            except Exception as e:
                logger.error(f"Auto-stop: error stopping live transcription: {e}")

            # 3. Update the DB session
            from database.database import SessionLocal
            db = SessionLocal()
            try:
                session = db.query(DBRecordingSession).filter(
                    DBRecordingSession.session_id == session_id
                ).first()
                if session:
                    session.status = "processing"
                    session.ended_at = datetime.now(timezone.utc)
                    if session.started_at:
                        session.duration = (session.ended_at - session.started_at).total_seconds()
                    if not session.audio_file and audio_file:
                        session.audio_file = audio_file
                    db.commit()
                    logger.info(f"Auto-stop: session {session_id} marked as processing")

                    # 4. Schedule background transcription + AI processing
                    asyncio.create_task(
                        process_recording(
                            session_id=session.session_id,
                            audio_file=audio_file if success else (session.audio_file or ""),
                            db_session_id=session.id,
                        )
                    )
                    logger.info(f"Auto-stop: scheduled background processing for {session_id}")
                else:
                    logger.error(f"Auto-stop: session {session_id} not found in DB")
            except Exception as e:
                logger.error(f"Auto-stop: DB error finalizing session: {e}")
                db.rollback()
            finally:
                db.close()

            # Clean up our task reference and exit the listener
            _auto_stop_tasks.pop(session_id, None)
            break

    except asyncio.CancelledError:
        logger.info(f"Auto-stop monitor cancelled for session {session_id}")
    except Exception as e:
        logger.error(f"Auto-stop monitor error for session {session_id}: {e}")
    finally:
        if pubsub:
            try:
                await pubsub.unsubscribe()
                await pubsub.close()
            except Exception:
                pass
        if redis_client:
            try:
                await redis_client.close()
            except Exception:
                pass


@router.post("/recording-sessions/{session_id}/start")
async def start_recording(
    session_id: str,
    body: Optional[StartRecordingRequest] = None,
    db: Session = Depends(get_db)
):
    """Start recording for a session. Optionally specify device_id to select audio input."""

    # Get session from database - handle both session_id and integer id
    session = db.query(DBRecordingSession).filter(
        DBRecordingSession.session_id == session_id
    ).first()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Start recording with audio service (it will generate the file path)
    device_id = body.device_id if body else None
    success, file_path = audio_service.start_recording(session_id, device_id=device_id)
    
    if not success:
        raise HTTPException(status_code=500, detail=f"Failed to start recording: {file_path}")
    
    # Update database with correct column names
    session.status = "recording"
    session.started_at = datetime.now(timezone.utc)
    session.audio_file = file_path  # Note: column is audio_file, not audio_file_path
    db.commit()
    
    logger.info(f"Started recording for session {session_id}")
    
    # Start live transcription monitoring (will wait for file internally)
    try:
        from services.live_recording_transcription import live_recording_transcription
        
        # Start monitoring task - it will handle waiting for the file
        asyncio.create_task(live_recording_transcription.start_monitoring(
            file_path,   # audio_file parameter
            session_id   # session_id parameter
        ))
        logger.info(f"Started live transcription monitoring for session {session_id}")
        logger.info(f"  Will monitor file: {file_path}")
        logger.info(f"  Transcription every 15 seconds, summaries every 500 words")
            
    except Exception as e:
        logger.error(f"Failed to start live transcription: {e}")
    
    # Start unified agent for progressive AI summaries with GPU acceleration
    try:
        asyncio.create_task(
            unified_agent_service.start_meeting_analysis(session_id)
        )
        logger.info(f"🚀 Started unified agent for progressive AI summaries on session {session_id}")
        logger.info(f"   Using GPU-accelerated llama.cpp on port 11437")
    except Exception as e:
        logger.error(f"Failed to start unified agent: {e}")
    
    # Start auto-stop monitor (listens for prolonged silence event from live transcription)
    try:
        task = asyncio.create_task(
            _monitor_auto_stop(session_id, session.id)
        )
        _auto_stop_tasks[session_id] = task
        logger.info(f"Started auto-stop monitor for session {session_id} "
                     f"(silence threshold: {20 * 15}s)")
    except Exception as e:
        logger.error(f"Failed to start auto-stop monitor: {e}")

    return {
        "status": "recording",
        "session_id": session_id,
        "message": "Recording started successfully"
    }

@router.post("/recording-sessions/{session_id}/stop")
async def stop_recording(
    session_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Stop recording and trigger transcription"""
    
    # Get session from database - handle both session_id and integer id
    session = db.query(DBRecordingSession).filter(
        DBRecordingSession.session_id == session_id
    ).first()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Cancel the auto-stop monitor if it's running (manual stop takes priority)
    auto_stop_task = _auto_stop_tasks.pop(session_id, None)
    if auto_stop_task and not auto_stop_task.done():
        auto_stop_task.cancel()
        logger.info(f"Cancelled auto-stop monitor for session {session_id} (manual stop)")

    try:
        # Stop recording
        success, audio_file = audio_service.stop_recording(session_id)

        if not success:
            raise HTTPException(status_code=500, detail=f"Failed to stop recording: {audio_file}")

        # Update session in database
        session.status = "processing"
        session.ended_at = datetime.now(timezone.utc)
        if session.started_at:
            session.duration = (session.ended_at - session.started_at).total_seconds()
        
        # Save the audio file path if not already set
        if not session.audio_file and audio_file:
            session.audio_file = audio_file
            
        db.commit()
        
        # Stop live transcription monitoring
        try:
            from services.live_recording_transcription import live_recording_transcription
            asyncio.create_task(live_recording_transcription.stop_monitoring())
            logger.info(f"Stopped live transcription for session {session_id}")
        except Exception as e:
            logger.error(f"Error stopping live transcription: {e}")
        
        # Schedule background transcription and processing
        background_tasks.add_task(
            process_recording,
            session_id=session.id if isinstance(session.id, int) else session.session_id,
            audio_file=audio_file,
            db_session_id=session.id
        )
        
        return {
            "status": "processing",
            "session_id": session_id,
            "duration": session.duration,
            "audio_file": audio_file,
            "message": "Recording stopped, processing transcription..."
        }
        
    except Exception as e:
        logger.error(f"Error stopping recording: {e}")
        session.status = "error"
        db.commit()
        raise HTTPException(status_code=500, detail=str(e))

async def process_recording(session_id: str, audio_file: str, db_session_id: int):
    """Background task to process recording - with guaranteed completion"""
    from database.database import SessionLocal
    
    processing_start_time = time.time()  # Track processing start time
    
    db = SessionLocal()
    try:
        # Get fresh session from database
        session = db.query(DBRecordingSession).filter(
            DBRecordingSession.id == db_session_id
        ).first()
        
        if not session:
            logger.error(f"Session {db_session_id} not found in database")
            return
        
        logger.info(f"Starting guaranteed processing for session {session_id}")
        
        # Step 1: Transcribe with timeout protection
        transcription_result = None
        try:
            logger.info(f"Starting transcription for {audio_file}")
            
            # Add timeout to prevent hanging
            transcription_result = await asyncio.wait_for(
                asyncio.to_thread(
                    real_whisper_service.transcribe_file,
                    audio_file,
                    diarize=True
                ),
                timeout=300  # 5 minute timeout
            )
            
            if transcription_result and "segments" in transcription_result:
                # Save full diarized transcript
                session.transcript_diarized = transcription_result
                
                # Save simple text transcript (just the text without speakers)
                simple_text = " ".join([s.get("text", "") for s in transcription_result.get("segments", [])])
                session.transcript_simple = simple_text
                
                # Legacy field for backward compatibility
                session.transcript = json.dumps(transcription_result)
                
                # Save individual segments with error handling
                segment_count = 0
                for segment in transcription_result.get("segments", []):
                    try:
                        # Convert NumPy types to Python native types to avoid database errors
                        start_time = segment.get("start", 0)
                        end_time = segment.get("end", 0)
                        confidence = segment.get("confidence", 0.95)
                        
                        # Convert NumPy float64 to Python float
                        if hasattr(start_time, 'item'):  # NumPy type
                            start_time = float(start_time.item())
                        else:
                            start_time = float(start_time)
                            
                        if hasattr(end_time, 'item'):  # NumPy type
                            end_time = float(end_time.item())
                        else:
                            end_time = float(end_time)
                            
                        if hasattr(confidence, 'item'):  # NumPy type
                            confidence = float(confidence.item())
                        else:
                            confidence = float(confidence)
                        
                        trans = Transcription(
                            session_id=session.id,  # Use integer to match database schema
                            text=segment.get("text", ""),
                            speaker=segment.get("speaker"),
                            start_time=start_time,
                            end_time=end_time,
                            confidence=confidence
                        )
                        db.add(trans)
                        segment_count += 1
                    except Exception as e:
                        logger.warning(f"Failed to save segment: {e}")
                        continue
                
                logger.info(f"Saved {segment_count} transcription segments")
            else:
                logger.warning("No transcription segments generated")
                session.transcript = json.dumps({"text": "Transcription failed", "segments": []})
                
        except asyncio.TimeoutError:
            logger.error(f"Transcription timed out for session {session_id}")
            session.transcript = json.dumps({"text": "Transcription timed out", "segments": []})
        except Exception as e:
            logger.error(f"Transcription error: {e}")
            session.transcript = json.dumps({"text": f"Transcription error: {str(e)}", "segments": []})
        
        # Step 1.5: Apply vocabulary replacements to transcript
        try:
            if session.transcript_simple:
                session.transcript_simple = apply_vocabulary_replacements(session.transcript_simple, db)

            if session.transcript_diarized and isinstance(session.transcript_diarized, dict):
                segments = session.transcript_diarized.get("segments", [])
                for seg in segments:
                    if seg.get("text"):
                        seg["text"] = apply_vocabulary_replacements(seg["text"], db)
                session.transcript_diarized = session.transcript_diarized

            if transcription_result and "segments" in transcription_result:
                for seg in transcription_result["segments"]:
                    if seg.get("text"):
                        seg["text"] = apply_vocabulary_replacements(seg["text"], db)
                session.transcript = json.dumps(transcription_result)

            db.flush()
            logger.info(f"Vocabulary replacements applied for session {session_id}")
        except Exception as e:
            logger.warning(f"Vocabulary replacement step failed (non-fatal): {e}")

        # Step 2: Generate AI summary with timeout protection
        try:
            if transcription_result and "segments" in transcription_result:
                full_text = " ".join([s.get("text", "") for s in transcription_result["segments"]])
                
                if full_text.strip():
                    logger.info(f"Starting AI analysis for session {session_id}")
                    
                    # Use the new dual-model approach: Granite for final comprehensive analysis
                    logger.info(f"Starting final comprehensive analysis with Granite 3.3 8B")
                    summary_result = await asyncio.wait_for(
                        unified_agent_service.analyze_meeting(
                            session_id=str(session.id),
                            transcript=full_text
                        ),
                        timeout=180  # 3 minute timeout
                    )
                    
                    if summary_result and summary_result.get("success"):
                        analysis = summary_result.get("analysis", {})
                        
                        # Save comprehensive final summary
                        final_summary = {
                            "executive": analysis.get("executive", ""),
                            "bullets": analysis.get("bullets", []),
                            "actions": analysis.get("actions", []),
                            "decisions": analysis.get("decisions", []),
                            "title": analysis.get("title", ""),
                            "minutes": analysis.get("minutes", ""),  # Meeting minutes
                            "tasks": analysis.get("tasks", []),  # Task list
                            "generated_at": datetime.now(timezone.utc).isoformat()
                        }
                        session.final_summary = final_summary
                        
                        # Legacy summary field for backward compatibility
                        session.summary = json.dumps(analysis)
                        
                        # Also save as ai_insights for legacy frontend support
                        session.ai_insights = analysis
                        
                        # Auto-generate title if available
                        if isinstance(analysis, dict) and "title" in analysis:
                            new_title = analysis["title"]
                            if new_title and isinstance(new_title, str) and new_title != session.name:
                                session.title = new_title[:200]  # Limit title length
                                logger.info(f"Auto-generated title: {new_title}")
                    else:
                        logger.warning("AI analysis failed, using fallback summary")
                        session.summary = json.dumps({
                            "executive": f"Meeting recorded with {len(full_text.split())} words transcribed.",
                            "bullets": ["Meeting content captured successfully", "AI analysis unavailable"],
                            "title": f"Meeting {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}"
                        })
                else:
                    logger.warning("No transcript text available for AI analysis")
                    session.summary = json.dumps({
                        "executive": "Meeting recorded but no transcription available.",
                        "bullets": ["Audio file captured", "Transcription failed"],
                        "title": f"Meeting {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}"
                    })
            else:
                logger.warning("No transcription available for AI analysis")
                session.summary = json.dumps({
                    "executive": "Meeting recorded but transcription failed.",
                    "bullets": ["Audio file saved", "Transcription processing failed"],
                    "title": f"Meeting {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}"
                })
                
        except asyncio.TimeoutError:
            logger.error(f"AI analysis timed out for session {session_id}")
            session.summary = json.dumps({
                "executive": "Meeting recorded successfully. AI analysis timed out.",
                "bullets": ["Audio and transcript captured", "AI processing unavailable"],
                "title": f"Meeting {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}"
            })
        except Exception as e:
            logger.error(f"AI analysis error: {e}")
            session.summary = json.dumps({
                "executive": "Meeting recorded successfully. AI analysis failed.",
                "bullets": ["Audio and transcript captured", f"AI error: {str(e)[:100]}"],
                "title": f"Meeting {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}"
            })
        
        # Step 3: Update metadata with processing stats
        processing_end_time = time.time()
        processing_duration = processing_end_time - processing_start_time  # Calculate actual duration
        
        # Calculate word count and speaker count
        word_count = 0
        speaker_count = 0
        if session.transcript_simple:
            word_count = len(session.transcript_simple.split())
        if session.transcript_diarized and isinstance(session.transcript_diarized, dict):
            speakers = set()
            for segment in session.transcript_diarized.get("segments", []):
                if segment.get("speaker"):
                    speakers.add(segment["speaker"])
            speaker_count = len(speakers)
        
        # Update metadata
        metadata = session.processing_metadata or {}
        metadata.update({
            "word_count": word_count,
            "speaker_count": speaker_count,
            "npu_accelerated": True,  # We always use NPU for transcription
            "processing_time_ms": int(processing_duration * 1000) if processing_duration > 0 else 0,
            "transcription_model": "whisper-large-v3",
            "ai_model": "granite3.3:8b",
            "processing_completed_at": datetime.now(timezone.utc).isoformat()
        })
        session.processing_metadata = metadata
        
        # Step 4: ALWAYS mark as completed (never leave in processing)
        session.status = "completed"
        session.updated_at = datetime.now(timezone.utc)
        
        try:
            db.commit()
            logger.info(f"✅ Successfully completed processing for session {session_id}")
            logger.info(f"   Status: {session.status}")
            logger.info(f"   Title: {session.title}")
            logger.info(f"   Has transcript: {bool(session.transcript)}")
            logger.info(f"   Has summary: {bool(session.summary)}")
        except Exception as e:
            logger.error(f"Failed to commit session updates: {e}")
            db.rollback()
        
    except Exception as e:
        logger.error(f"Critical error in background processing: {e}")
        
        # Even on critical error, try to mark as completed
        try:
            if session:
                session.status = "completed"  # Not "error" - frontend expects "completed"
                session.summary = json.dumps({
                    "executive": "Meeting recorded but processing failed.",
                    "bullets": ["Audio file captured", f"Processing error: {str(e)[:100]}"],
                    "title": f"Meeting {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}"
                })
                session.updated_at = datetime.now(timezone.utc)
                db.commit()
                logger.info(f"Marked session {session_id} as completed despite errors")
        except Exception as commit_error:
            logger.error(f"Failed to mark session as completed: {commit_error}")
            
    finally:
        db.close()

@router.delete("/recording-sessions/{session_id}")
async def delete_session(
    session_id: str,
    db: Session = Depends(get_db)
):
    """Delete a recording session"""
    
    session = db.query(DBRecordingSession).filter(
        DBRecordingSession.session_id == session_id
    ).first()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Delete audio file if it exists
    if session.audio_file and os.path.exists(session.audio_file):
        try:
            os.remove(session.audio_file)
        except OSError:
            pass
    
    # Delete transcriptions
    db.query(Transcription).filter(
        Transcription.session_id == session.id
    ).delete()
    
    # Delete session
    db.delete(session)
    db.commit()
    
    return {"message": "Session deleted successfully"}

# Export endpoints for audio download and transcript download
@router.get("/recording-sessions/{session_id}/download/audio")
async def download_audio(
    session_id: str,
    db: Session = Depends(get_db)
):
    """Download audio file for a session"""
    from fastapi.responses import FileResponse, JSONResponse
    
    session = db.query(DBRecordingSession).filter(
        DBRecordingSession.session_id == session_id
    ).first()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if not session.audio_file:
        logger.warning(f"Session {session_id} has no audio file path")
        return JSONResponse(
            status_code=404,
            content={"detail": "No audio file associated with this session"}
        )
    
    if not os.path.exists(session.audio_file):
        logger.warning(f"Audio file not found: {session.audio_file}")
        # Check if file exists without full path (relative to recordings dir)
        recordings_dir = "/home/ucadmin/Meeting-Ops/backend/recordings"
        filename_only = os.path.basename(session.audio_file)
        alt_path = os.path.join(recordings_dir, filename_only)
        
        if os.path.exists(alt_path):
            logger.info(f"Found audio file at alternate path: {alt_path}")
            session.audio_file = alt_path
            db.commit()
        else:
            return JSONResponse(
                status_code=404,
                content={"detail": f"Audio file not found at {session.audio_file}"}
            )
    
    filename = f"{(session.name or session.title or 'recording').replace(' ', '_')}_audio.wav"
    # Set headers for both streaming and download
    return FileResponse(
        session.audio_file, 
        filename=filename, 
        media_type="audio/wav",
        headers={
            "Accept-Ranges": "bytes",  # Support range requests for audio streaming
            "Cache-Control": "no-cache"
        }
    )

@router.get("/recording-sessions/{session_id}/download/transcript")
async def download_transcript(
    session_id: str,
    db: Session = Depends(get_db)
):
    """Download transcript with speakers for a session"""
    from fastapi.responses import Response
    
    session = db.query(DBRecordingSession).filter(
        DBRecordingSession.session_id == session_id
    ).first()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Build transcript text with speaker diarization
    transcript = f"Recording: {session.name or session.title or 'Untitled'}\n"
    transcript += f"Date: {session.created_at}\n"
    transcript += f"Duration: {session.duration or 0} seconds\n"
    
    # Add metadata if available
    if session.processing_metadata:
        transcript += f"Word Count: {session.processing_metadata.get('word_count', 'N/A')}\n"
        transcript += f"Speakers: {session.processing_metadata.get('speaker_count', 'N/A')}\n"
    
    transcript += "\n--- TRANSCRIPT WITH SPEAKERS ---\n\n"
    
    # Use diarized transcript if available
    if session.transcript_diarized and isinstance(session.transcript_diarized, dict):
        for segment in session.transcript_diarized.get("segments", []):
            speaker = segment.get("speaker", "Unknown Speaker")
            text = segment.get("text", "")
            timestamp = segment.get("start", 0)
            minutes = int(timestamp // 60)
            seconds = int(timestamp % 60)
            transcript += f"[{minutes:02d}:{seconds:02d} - {speaker}]: {text}\n\n"
    else:
        # Fallback to segments from Transcription table
        segments = db.query(Transcription).filter(
            Transcription.session_id == session.id
        ).order_by(Transcription.start_time).all()
        
        if segments:
            for segment in segments:
                speaker = segment.speaker or "Unknown Speaker"
                transcript += f"[{speaker}]: {segment.text}\n\n"
        elif session.transcript:
            try:
                trans_data = json.loads(session.transcript) if isinstance(session.transcript, str) else session.transcript
                if isinstance(trans_data, dict) and "segments" in trans_data:
                    for seg in trans_data["segments"]:
                        speaker = seg.get("speaker", "Unknown Speaker")
                        text = seg.get("text", "")
                        transcript += f"[{speaker}]: {text}\n\n"
                else:
                    transcript += str(session.transcript)
            except (json.JSONDecodeError, TypeError, ValueError):
                transcript += str(session.transcript) if session.transcript else "No transcription available."
        else:
            transcript += "No transcription available."

    filename = f"{(session.name or session.title or 'recording').replace(' ', '_')}_transcript_with_speakers.txt"
    return Response(
        content=transcript,
        media_type="text/plain",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )

@router.get("/recording-sessions/{session_id}/download/summary/pdf")
async def download_summary_pdf(
    session_id: str,
    db: Session = Depends(get_db)
):
    """Download meeting summary as PDF"""
    from fastapi.responses import Response

    session = db.query(DBRecordingSession).filter(
        DBRecordingSession.session_id == session_id
    ).first()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        from api.batch_export import export_to_pdf, ExportOptions
        options = ExportOptions()
        pdf_bytes = export_to_pdf(session, options)
        filename = f"{(session.name or session.title or 'meeting').replace(' ', '_')}_summary.pdf"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except ImportError as e:
        raise HTTPException(status_code=501, detail=f"PDF generation not available: {e}")
    except Exception as e:
        logger.error(f"PDF generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {str(e)}")

@router.get("/recording-sessions/{session_id}/download/summary/docx")
async def download_summary_docx(
    session_id: str,
    db: Session = Depends(get_db)
):
    """Download meeting summary as DOCX"""
    from fastapi.responses import Response

    session = db.query(DBRecordingSession).filter(
        DBRecordingSession.session_id == session_id
    ).first()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        from api.batch_export import export_to_docx, ExportOptions
        options = ExportOptions()
        docx_bytes = export_to_docx(session, options)
        filename = f"{(session.name or session.title or 'meeting').replace(' ', '_')}_summary.docx"
        return Response(
            content=docx_bytes,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except ImportError as e:
        raise HTTPException(status_code=501, detail=f"DOCX generation not available: {e}")
    except Exception as e:
        logger.error(f"DOCX generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"DOCX generation failed: {str(e)}")

@router.get("/recording-sessions/{session_id}/download/transcript/simple")
async def download_transcript_simple(
    session_id: str,
    db: Session = Depends(get_db)
):
    """Download simple transcript without speakers"""
    from fastapi.responses import Response
    
    session = db.query(DBRecordingSession).filter(
        DBRecordingSession.session_id == session_id
    ).first()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Build simple transcript text
    transcript = f"Recording: {session.name or session.title or 'Untitled'}\n"
    transcript += f"Date: {session.created_at}\n"
    transcript += f"Duration: {session.duration or 0} seconds\n"
    
    if session.processing_metadata:
        transcript += f"Word Count: {session.processing_metadata.get('word_count', 'N/A')}\n"
    
    transcript += "\n--- TRANSCRIPT ---\n\n"
    
    # Use simple transcript if available
    if session.transcript_simple:
        transcript += session.transcript_simple
    else:
        # Fallback to extracting text from diarized transcript
        if session.transcript_diarized and isinstance(session.transcript_diarized, dict):
            texts = [seg.get("text", "") for seg in session.transcript_diarized.get("segments", [])]
            transcript += " ".join(texts)
        elif session.transcript:
            try:
                trans_data = json.loads(session.transcript) if isinstance(session.transcript, str) else session.transcript
                if isinstance(trans_data, dict) and "segments" in trans_data:
                    texts = [seg.get("text", "") for seg in trans_data["segments"]]
                    transcript += " ".join(texts)
                elif isinstance(trans_data, dict) and "text" in trans_data:
                    transcript += trans_data["text"]
                else:
                    transcript += str(session.transcript)
            except (json.JSONDecodeError, TypeError, ValueError):
                transcript += str(session.transcript) if session.transcript else "No transcription available."
        else:
            transcript += "No transcription available."

    filename = f"{(session.name or session.title or 'recording').replace(' ', '_')}_transcript_simple.txt"
    return Response(
        content=transcript,
        media_type="text/plain",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )


# === Always-On Recording Mode ===

@router.post("/always-on/start")
async def start_always_on(
    body: Optional[StartRecordingRequest] = None,
    current_user: User = Depends(get_current_user),
):
    """Enable always-on recording mode. The system will listen continuously
    and automatically create meeting sessions when speech is detected."""
    from services.always_on_recorder import always_on_recorder

    device_id = body.device_id if body else None
    result = await always_on_recorder.start(device_id=device_id)
    return result


@router.post("/always-on/stop")
async def stop_always_on(
    current_user: User = Depends(get_current_user),
):
    """Disable always-on recording mode"""
    from services.always_on_recorder import always_on_recorder

    result = await always_on_recorder.stop()
    return result


@router.get("/always-on/status")
async def get_always_on_status(
    current_user: User = Depends(get_current_user),
):
    """Get always-on recording status"""
    from services.always_on_recorder import always_on_recorder

    return always_on_recorder.get_status()