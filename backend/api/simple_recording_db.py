"""
Database-backed Simple Recording API
Fixed version that persists to PostgreSQL
"""

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Query
from pydantic import BaseModel
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import desc, or_, func
import asyncio
import os
import re
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
def apply_vocabulary_replacements(text: str, db_session, organization_id: int) -> str:
    """Apply vocabulary term replacements to transcript text."""
    if not text:
        return text
    try:
        from models.vocabulary import CustomVocabulary
        terms = db_session.query(CustomVocabulary).filter(
            CustomVocabulary.organization_id == organization_id,
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


from auth.dependencies import get_current_organization, get_current_user
from auth.organization import ActiveOrganization
from auth.tier import gate_feature_for_caller
from auth.models import Organization, User, UserOrganization

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
    project_app: Optional[str] = None      # 'project-ops' | 'crisis-ops' | None
    project_id: Optional[int] = None
    project_slug: Optional[str] = None


class UpdateSessionProjectRequest(BaseModel):
    project_app: Optional[str] = None      # 'project-ops' | 'crisis-ops' | None ('' clears)
    project_id: Optional[int] = None
    project_slug: Optional[str] = None

class ParticipantSummary(BaseModel):
    id: str
    name: str
    email: Optional[str] = None
    role: Optional[str] = None


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
    participants: List[ParticipantSummary] = []
    tags: List[str] = []
    summary_preview: Optional[str] = None
    speaker_count: int = 0
    project_app: Optional[str] = None
    project_id: Optional[int] = None
    project_slug: Optional[str] = None
    organization_id: Optional[int] = None
    organization_name: Optional[str] = None
    # User-editable "when the meeting actually happened". ISO date /
    # 24h time. Backfilled from started_at / created_at by alembic 027.
    meeting_date: Optional[str] = None
    meeting_time: Optional[str] = None


def _brigade_graph_url_for_session(session: DBRecordingSession) -> Optional[str]:
    """Build the per-session Brigade graph deep-link, or None when this
    session has never been written to Brigade.

    The frontend uses the presence of this URL to decide whether to
    render the "View in Brigade graph" link on SessionDetails. We do
    the URL construction server-side so the client doesn't need to
    know the active tenancy mode (which depends on the
    BRIGADE_TENANCY_MODE env var the backend already reads)."""
    if not getattr(session, "brigade_graph_node_id", None):
        return None
    try:
        from services.brigade_writer import build_brigade_graph_url

        return build_brigade_graph_url(session)
    except Exception as exc:  # noqa: BLE001
        # Defensive — the URL builder is pure but if env parsing flips
        # an unexpected exception we'd rather show nothing than 500
        # the entire session detail.
        logger.debug("brigade graph url builder failed: %s", exc)
        return None


def _summary_preview(session: DBRecordingSession, max_chars: int = 220) -> Optional[str]:
    """Pull a short plain-text snippet of the AI summary for the list view.

    Prefers ai_insights.summary (most recent + LLM-cleaned), then
    final_summary.summary, then the legacy session.summary JSON blob.
    """
    candidates = []
    if isinstance(session.ai_insights, dict):
        candidates.append(session.ai_insights.get("summary"))
    if isinstance(session.final_summary, dict):
        candidates.append(session.final_summary.get("summary"))
        candidates.append(session.final_summary.get("text"))
    if session.summary:
        try:
            raw = json.loads(session.summary) if isinstance(session.summary, str) else session.summary
            if isinstance(raw, dict):
                candidates.append(raw.get("summary"))
                candidates.append(raw.get("text"))
            elif isinstance(raw, str):
                candidates.append(raw)
        except (json.JSONDecodeError, ValueError, TypeError):
            candidates.append(str(session.summary))
    for c in candidates:
        if c and isinstance(c, str):
            # Strip markdown decoration so a list-view snippet stays readable.
            text = c
            for marker in ("**", "##", "###", "####", "`"):
                text = text.replace(marker, "")
            # Bullet asterisks and leading dashes: turn into a separator so we
            # still get list-readable prose ("X. Y. Z" feel) without raw
            # markdown clutter.
            text = re.sub(r"(^|\n)\s*[\*\-•]\s+", r"\1", text)
            text = " ".join(text.split())
            if not text:
                continue
            if len(text) <= max_chars:
                return text
            return text[:max_chars - 1].rstrip() + "…"
    return None


def _speaker_count(session: DBRecordingSession) -> int:
    """Count distinct speakers from transcript_diarized.speakers if present."""
    td = session.transcript_diarized
    if isinstance(td, dict):
        speakers = td.get("speakers")
        if isinstance(speakers, list):
            return len([s for s in speakers if s])
    return 0


def _scoped_session_query(db: Session, organization_id: int):
    return db.query(DBRecordingSession).filter(
        DBRecordingSession.organization_id == organization_id
    )


def _participants_payload(session: DBRecordingSession) -> List[dict]:
    """Coerce the JSONB column into a clean response list. Tolerates legacy
    NULLs and stray non-list values without 500ing the caller."""
    raw = session.participants
    if not isinstance(raw, list):
        return []
    out: List[dict] = []
    for p in raw:
        if not isinstance(p, dict):
            continue
        out.append({
            "id": str(p.get("id") or ""),
            "name": str(p.get("name") or ""),
            "email": p.get("email") or None,
            "role": p.get("role") or None,
        })
    return out


def _tags_payload(session: DBRecordingSession) -> List[str]:
    """Coerce the TEXT[] column into a clean list of strings."""
    raw = session.tags
    if not isinstance(raw, list):
        return []
    return [t for t in raw if isinstance(t, str) and t]


def _action_items_payload(db: Session, session: DBRecordingSession) -> List[dict]:
    """Persisted action items for this session, ordered the way the LLM
    produced them (sort_order asc, with created_at as a stable tiebreaker
    for manual additions made after summarize).

    Falls back to an empty list on lookup error so the session detail
    response keeps working even if the action_items table is unavailable
    (very early after migration). Frontend retains a JSON-column fallback
    parser for that window."""
    try:
        from database.models import ActionItem
        rows = (
            db.query(ActionItem)
            .filter(ActionItem.session_id == session.id)
            .order_by(ActionItem.sort_order.asc(), ActionItem.created_at.asc(), ActionItem.id.asc())
            .all()
        )
    except Exception as exc:
        logger.warning(f"action_items lookup failed for session {session.id}: {exc}")
        return []

    out: List[dict] = []
    for item in rows:
        out.append({
            "id": item.id,
            "text": item.text,
            "owner": item.owner,
            "due_date": item.due_date.isoformat() if item.due_date else None,
            "status": item.status,
            "sort_order": item.sort_order,
            "source": item.source,
            "created_at": item.created_at.isoformat() if item.created_at else None,
            "completed_at": item.completed_at.isoformat() if item.completed_at else None,
        })
    return out


def _get_session_for_org(
    db: Session,
    organization_id: int,
    session_id: str,
) -> Optional[DBRecordingSession]:
    session = _scoped_session_query(db, organization_id).filter(
        DBRecordingSession.session_id == session_id
    ).first()
    if session:
        return session

    try:
        int_id = int(session_id)
    except (TypeError, ValueError):
        return None

    return _scoped_session_query(db, organization_id).filter(
        DBRecordingSession.id == int_id
    ).first()
    
@router.post("/recording-sessions")
async def create_session(
    request: CreateSessionRequest,
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
    db: Session = Depends(get_db)
) -> SessionResponse:
    """Create a new recording session in database"""
    
    session_id = str(uuid.uuid4())
    
    # Create database session
    # Validate project_app if provided
    project_app = request.project_app or None
    if project_app and project_app not in ("project-ops", "crisis-ops"):
        raise HTTPException(status_code=400, detail="project_app must be 'project-ops' or 'crisis-ops'")

    db_session = DBRecordingSession(
        session_id=session_id,
        name=request.name,
        title=request.name,  # Use name as title
        description=request.description or "",
        status="active",
        created_at=datetime.now(timezone.utc),
        duration=0.0,
        user_id=current_user.id,
        organization_id=active_org.organization.id,
        project_app=project_app,
        project_id=request.project_id if project_app else None,
        project_slug=request.project_slug if project_app else None,
    )

    db.add(db_session)
    db.commit()
    db.refresh(db_session)

    logger.info(
        f"Created DB session: {session_id} "
        f"(project_app={db_session.project_app}, project_id={db_session.project_id})"
    )

    return SessionResponse(
        id=session_id,
        name=db_session.name,
        description=db_session.description or "",
        created_at=db_session.created_at.isoformat(),
        status=db_session.status,
        duration=0.0
    )

_VALID_SORT_KEYS = {"created_at_desc", "meeting_date_desc", "meeting_date_asc"}


@router.get("/recording-sessions")
async def list_sessions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
    # Sessions.tsx now requests limit=1000 by default (no real pagination
    # yet — power users were silently losing the tail at the old 100 default).
    # le=2000 caps the payload at something an admin tool can hit without
    # being a DoS vector.
    limit: int = Query(100, ge=1, le=2000),
    tags: Optional[str] = Query(None, description="Comma-separated tags; AND filter"),
    sort: Optional[str] = Query(
        None,
        description=(
            "Sort order. One of created_at_desc (default), "
            "meeting_date_desc, meeting_date_asc. When meeting_date is "
            "null the sort falls back to started_at."
        ),
    ),
    bulk_import_job_id: Optional[str] = Query(
        None,
        description="Filter sessions created by this bulk import job (UUID)",
    ),
    include_all_my_orgs: bool = Query(
        False,
        description="Return sessions from every organization the caller belongs to.",
    ),
) -> List[SessionResponse]:
    """List all recording sessions from database"""

    org_names_by_id: dict[int, str] = {}
    if include_all_my_orgs and not getattr(current_user, "is_superuser", False):
        org_ids = [
            row.organization_id
            for row in db.query(UserOrganization.organization_id)
            .filter(UserOrganization.user_id == current_user.id)
            .all()
        ]
        if not org_ids:
            query = db.query(DBRecordingSession).filter(False)
        else:
            query = db.query(DBRecordingSession).filter(
                DBRecordingSession.organization_id.in_(org_ids)
            )
    elif include_all_my_orgs and getattr(current_user, "is_superuser", False):
        query = db.query(DBRecordingSession)
    else:
        query = _scoped_session_query(db, active_org.organization.id)
    if tags:
        wanted = [t.strip() for t in tags.split(",") if t.strip()]
        if wanted:
            query = query.filter(DBRecordingSession.tags.contains(wanted))
    # Hide empty always-on sessions: when the user clicks Start always-on
    # but never produces audio (mic blocked, browser bug, accidental click),
    # the start endpoint still creates a session row. Without filtering, the
    # dashboard fills up with "Always-on YYYY-MM-DD HH:MM" rows that have
    # no transcript and no audio. Filter them out here.
    query = query.filter(
        ~(
            (DBRecordingSession.mode == "always_on")
            & ((DBRecordingSession.transcript.is_(None)) | (DBRecordingSession.transcript == ""))
            & ((DBRecordingSession.audio_file.is_(None)) | (DBRecordingSession.audio_file == ""))
        )
    )

    if bulk_import_job_id:
        from database.models import BulkImportFile
        import uuid as _uuid
        try:
            job_uuid = _uuid.UUID(bulk_import_job_id)
            file_rows = db.query(BulkImportFile).filter(BulkImportFile.job_id == job_uuid, BulkImportFile.session_id_when_created.isnot(None)).all()
            session_ids = [str(f.session_id_when_created) for f in file_rows if f.session_id_when_created]
            if session_ids:
                query = query.filter(DBRecordingSession.session_id.in_(session_ids))
            else:
                query = query.filter(False)
        except ValueError:
            # Malformed bulk_import_job_id - silently ignore the filter
            # rather than 400'ing. The list view still returns the org's
            # sessions; the caller passed garbage and gets the unfiltered
            # view back, which is the safer fail-open shape here.
            pass
    sort_key = sort if sort in _VALID_SORT_KEYS else "created_at_desc"
    if sort_key in ("meeting_date_desc", "meeting_date_asc"):
        # Coalesce so a null meeting_date falls back to started_at and
        # finally to created_at. Keeps newly-uploaded sessions visible
        # in date-sorted views even before the user edits a date in.
        effective = func.coalesce(
            DBRecordingSession.meeting_date,
            func.date(DBRecordingSession.started_at),
            func.date(DBRecordingSession.created_at),
        )
        order_clause = desc(effective) if sort_key == "meeting_date_desc" else effective
        query = query.order_by(order_clause, desc(DBRecordingSession.id))
    else:
        query = query.order_by(desc(DBRecordingSession.created_at))

    sessions = query.limit(limit).all()
    session_org_ids = sorted({
        int(session.organization_id)
        for session in sessions
        if session.organization_id is not None
    })
    if session_org_ids:
        org_names_by_id = {
            int(org.id): org.name
            for org in db.query(Organization)
            .filter(Organization.id.in_(session_org_ids))
            .all()
        }

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
            transcription=transcription_data,
            participants=_participants_payload(session),
            tags=_tags_payload(session),
            summary_preview=_summary_preview(session),
            speaker_count=_speaker_count(session),
            project_app=session.project_app,
            project_id=session.project_id,
            project_slug=session.project_slug,
            organization_id=session.organization_id,
            organization_name=org_names_by_id.get(session.organization_id),
            meeting_date=session.meeting_date.isoformat() if session.meeting_date else None,
            meeting_time=session.meeting_time.isoformat() if session.meeting_time else None,
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
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
    db: Session = Depends(get_db)
) -> List[SearchResult]:
    """Search recording sessions across name, transcript, and transcript_simple columns.
    Returns matching sessions with a snippet of the matching text."""
    
    search_term = f"%{q}%"
    
    sessions = _scoped_session_query(db, active_org.organization.id).filter(
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


# === Semantic / Vector Search (Qdrant) ===

@router.get("/recording-sessions/semantic-search")
async def semantic_search_sessions(
    q: str = Query(..., min_length=1, description="Natural language search query"),
    limit: int = Query(10, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
):
    """Semantic search across meetings using vector similarity.
    Understands meaning, not just keywords — e.g. 'meetings about budget planning'
    will match transcripts discussing finances even without the exact words."""
    # v3.23.0 tier gate: cross-meeting semantic search is a TEXT-corpus
    # operation. Basic + higher get it; Free is browser-only.
    gate_feature_for_caller(current_user, "cross_meeting_search")
    try:
        from services.semantic_search_service import semantic_search
        results = semantic_search.search(
            query=q,
            limit=limit,
            organization_id=active_org.organization.id,
        )
        return {"query": q, "results": results, "count": len(results)}
    except Exception as e:
        logger.error(f"Semantic search error: {e}")
        raise HTTPException(status_code=500, detail=f"Semantic search failed: {str(e)}")


@router.post("/semantic-search/reindex")
async def reindex_all_sessions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
):
    """Reindex all completed sessions into the vector store.
    Run this once to backfill, then new sessions are indexed automatically."""
    try:
        from services.semantic_search_service import semantic_search
        result = semantic_search.reindex_all(
            db,
            organization_id=active_org.organization.id,
        )
        return {"status": "ok", **result}
    except Exception as e:
        logger.error(f"Reindex error: {e}")
        raise HTTPException(status_code=500, detail=f"Reindex failed: {str(e)}")


@router.get("/semantic-search/stats")
async def get_semantic_search_stats(
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
):
    """Get vector search index statistics."""
    try:
        from services.semantic_search_service import semantic_search
        return semantic_search.get_stats(organization_id=active_org.organization.id)
    except Exception as e:
        return {"initialized": False, "error": str(e)}


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
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
    db: Session = Depends(get_db)
) -> dict:
    """Get a specific recording session from database with error handling"""
    try:
        # Find by session_id (UUID string), org-scoped first.
        session = _get_session_for_org(db, active_org.organization.id, session_id)

        # Fallback: if the session isn't in the active org, the caller
        # might still be a per-meeting collaborator (or hold access via
        # a future project-membership lookup). Resolve cross-org and
        # delegate the final permission check to has_session_access so
        # external collaborators can fetch meeting detail without being
        # in the org's users table.
        if not session:
            from api.session_permissions import (
                _get_session_by_str_id,
                has_session_access,
            )
            candidate = _get_session_by_str_id(db, session_id)
            if candidate and has_session_access(candidate.id, current_user, db) != "denied":
                session = candidate

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
            # User-editable meeting date/time. ISO date / 24h time. Null
            # only if backfill (alembic 027) found no started_at / created_at
            # to pull from, or the user explicitly cleared the value.
            "meeting_date": session.meeting_date.isoformat() if session.meeting_date else None,
            "meeting_time": session.meeting_time.isoformat() if session.meeting_time else None,
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
            "updated_at": session.updated_at.isoformat() if session.updated_at else None,
            # Project linking (Phase 2)
            "project_app": session.project_app,
            "project_id": session.project_id,
            "project_slug": session.project_slug,
            "organization_id": session.organization_id,
            "organization_name": (
                db.query(Organization.name)
                .filter(Organization.id == session.organization_id)
                .scalar()
            ),
            # Conference Room linkage. `room_id` is the canonical "this is a
            # room session" signal — non-null means the live-summary UI
            # should pull slices from the server-rolled store instead of
            # rolling them client-side.
            "room_id": str(session.room_id) if session.room_id else None,
            "room_source_id": (
                str(session.room_source_id) if session.room_source_id else None
            ),
            "room_name": session.room_name,
            # Per-session participants (attendees). Editable from the
            # session detail sidebar; feeds the email-attendees default.
            "participants": _participants_payload(session),
            # Free-form per-session tags. Editable from the header chips.
            "tags": _tags_payload(session),
            # First-class action items derived from the summarizer JSON and
            # promoted by services.action_items_extractor. Status-aware so
            # the UI can flip done/doing/cancelled and have it stick.
            "action_items": _action_items_payload(db, session),
            # Brigade integration Phase 1: surfaces the per-session
            # Brigade graph deep-link to the frontend so SessionDetails
            # can render the "View in Brigade graph" affordance only
            # for sessions that have been synced. brigade_graph_node_id
            # is the canonical entity name we passed to Brigade's
            # store_entity; brigade_synced_at stamps the last
            # successful write; brigade_graph_url is pre-built so the
            # client doesn't need to know the tenancy mode.
            "brigade_graph_node_id": getattr(session, "brigade_graph_node_id", None),
            "brigade_synced_at": (
                session.brigade_synced_at.isoformat()
                if getattr(session, "brigade_synced_at", None)
                else None
            ),
            "brigade_graph_url": _brigade_graph_url_for_session(session),
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
            if success and audio_file:
                audio_file = os.path.normpath(os.path.abspath(audio_file))
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
                        started = session.started_at
                        ended = session.ended_at
                        if started.tzinfo is None:
                            started = started.replace(tzinfo=timezone.utc)
                        if ended.tzinfo is None:
                            ended = ended.replace(tzinfo=timezone.utc)
                        session.duration = (ended - started).total_seconds()
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
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
    db: Session = Depends(get_db)
):
    """Start recording for a session. Optionally specify device_id to select audio input."""

    # v3.18.1 tier gate: paid-tier server processing — starting a server
    # recording triggers STT/diarization/summary at stop, all server-side.
    # Free is browser-only and must never reach this path.
    gate_feature_for_caller(current_user, "canonical_reprocess")

    # Get session from database - handle both session_id and integer id
    session = _get_session_for_org(db, active_org.organization.id, session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Start recording with audio service (it will generate the file path)
    device_id = body.device_id if body else None
    success, file_path = audio_service.start_recording(session_id, device_id=device_id)

    if not success:
        raise HTTPException(status_code=500, detail=f"Failed to start recording: {file_path}")

    # Normalize the audio file path to prevent double-nesting
    file_path = os.path.normpath(os.path.abspath(file_path))

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
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
    db: Session = Depends(get_db)
):
    """Stop recording and trigger transcription"""
    
    # Get session from database - handle both session_id and integer id
    session = _get_session_for_org(db, active_org.organization.id, session_id)
    
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

        # Normalize the audio file path to prevent double-nesting
        if audio_file:
            audio_file = os.path.normpath(os.path.abspath(audio_file))

        # Update session in database
        session.status = "processing"
        session.ended_at = datetime.now(timezone.utc)
        if session.started_at:
            # Handle mixed naive/aware datetimes (from before timezone migration)
            started = session.started_at
            ended = session.ended_at
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            if ended.tzinfo is None:
                ended = ended.replace(tzinfo=timezone.utc)
            session.duration = (ended - started).total_seconds()

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

        # Step 1: Transcribe + diarize via the canonical provider stack so
        # per-segment embeddings get preserved end-to-end. The legacy
        # real_whisper_service.transcribe_file path returns segments
        # without embeddings, so identify_speakers below would skip every
        # SPEAKER_xx label with reason=no_embedding and never auto-link
        # enrolled voices. The canonical stack (Parakeet STT + speaker-svc
        # diarize with return_embeddings=true + word-level alignment in
        # _assign_speakers_from_diarization) keeps the 256-d ECAPA embedding
        # on each utterance so identify_speakers can match Aaron's voice
        # automatically.
        transcription_result = None
        try:
            logger.info(f"Starting canonical transcribe+diarize for {audio_file}")

            from api.uploads import _assign_speakers_from_diarization
            from services.providers.registry import get_provider_registry

            registry = get_provider_registry(db)

            # 1a. Transcribe via STT provider (default: Parakeet 1.1B on midboy2)
            stt_provider = registry.get_stt(session.organization_id)
            stt_result = await asyncio.wait_for(
                stt_provider.transcribe(audio_file, language="en"),
                timeout=600  # 10 minute timeout for long always-on sessions
            )

            if not stt_result or not stt_result.get("segments"):
                logger.warning("Canonical STT returned no segments; falling back to legacy whisper")
                transcription_result = await asyncio.wait_for(
                    asyncio.to_thread(
                        real_whisper_service.transcribe_file,
                        audio_file,
                        diarize=True
                    ),
                    timeout=300
                )
            else:
                # Build the unified transcription_result shape downstream
                # code (vocabulary, summarizer, action items, metadata)
                # expects: {"text", "segments", "language", ...}.
                transcription_result = {
                    "text": stt_result.get("text", ""),
                    "segments": stt_result.get("segments", []),
                    "language": stt_result.get("language", "en"),
                    "model": stt_result.get("model", "parakeet-tdt-1.1b"),
                    "duration": stt_result.get("duration", 0.0),
                    "audio_duration": stt_result.get("duration", 0.0),
                    "rtf": stt_result.get("rtf"),
                    "npu_accelerated": False,
                }

            if transcription_result and transcription_result.get("segments"):
                # Persist transcription FIRST so _assign_speakers_from_diarization
                # has segments to label and so the word_timestamps land in
                # processing_metadata where _build_segments_from_words can
                # find them for Path 1 (word-level alignment).
                session.transcript_diarized = transcription_result
                simple_text = " ".join([s.get("text", "") for s in transcription_result.get("segments", [])])
                session.transcript_simple = simple_text
                session.transcript = json.dumps(transcription_result)

                # Stash word timestamps from the STT call (Parakeet emits
                # these natively) so _build_segments_from_words can do
                # word-level diarization alignment downstream.
                if stt_result and stt_result.get("words"):
                    pm = dict(session.processing_metadata or {})
                    pm["word_timestamps"] = stt_result["words"]
                    pm["has_word_timestamps"] = True
                    session.processing_metadata = pm
                    from sqlalchemy.orm.attributes import flag_modified
                    flag_modified(session, "processing_metadata")

                # 1b. Diarize via speaker-svc with return_embeddings=true so
                # each turn carries a 256-d ECAPA embedding for identify_speakers.
                diar_segments = []
                try:
                    diar_provider = registry.get_diarization(session.organization_id)
                    diar_segments = await asyncio.wait_for(
                        diar_provider.diarize(audio_file),
                        timeout=600
                    )
                    logger.info(
                        f"Canonical diarize: {len(diar_segments)} turns, "
                        f"embeddings={'yes' if (diar_segments and diar_segments[0].get('embedding')) else 'no'}"
                    )
                except Exception as exc:
                    logger.warning(f"Diarization step failed (non-fatal): {exc}")
                    diar_segments = []

                if diar_segments:
                    # _assign_speakers_from_diarization writes labels + embeddings
                    # onto session.transcript_diarized.segments AND refreshes the
                    # Transcription rows. After this, identify_speakers (called in
                    # Step 6a below) can match enrolled voices automatically.
                    try:
                        _assign_speakers_from_diarization(session, diar_segments)
                    except Exception as exc:
                        logger.warning(f"Speaker merge step failed (non-fatal): {exc}")

                    # Re-read segments after merge — _assign_speakers_from_diarization
                    # rewrites the segments list (Path 1 produces utterances) and
                    # rewrites Transcription rows itself.
                    transcription_result = session.transcript_diarized or transcription_result
                else:
                    # No diarization → save segments straight to Transcription rows
                    # so list/detail views render text without speaker labels.
                    segment_count = 0
                    for segment in transcription_result.get("segments", []):
                        try:
                            trans = Transcription(
                                session_id=session.id,
                                text=segment.get("text", ""),
                                speaker=segment.get("speaker"),
                                start_time=float(segment.get("start", 0) or 0),
                                end_time=float(segment.get("end", 0) or 0),
                                confidence=float(segment.get("confidence", 0.95) or 0.95),
                            )
                            db.add(trans)
                            segment_count += 1
                        except Exception as e:
                            logger.warning(f"Failed to save segment: {e}")
                            continue
                    logger.info(f"Saved {segment_count} transcription segments (no diarization)")

                segments_after = (session.transcript_diarized or {}).get("segments", []) if isinstance(session.transcript_diarized, dict) else []
                emb_count = sum(1 for s in segments_after if s.get("embedding"))
                logger.info(
                    f"Step 1 complete: {len(segments_after)} segments, "
                    f"{emb_count} carry embeddings for identify_speakers"
                )
            else:
                logger.warning("No transcription segments generated")
                session.transcript = json.dumps({"text": "Transcription failed", "segments": []})

        except asyncio.TimeoutError:
            logger.error(f"Transcription timed out for session {session_id}")
            session.transcript = json.dumps({"text": "Transcription timed out", "segments": []})
        except Exception as e:
            logger.error(f"Transcription error: {e}", exc_info=True)
            session.transcript = json.dumps({"text": f"Transcription error: {str(e)}", "segments": []})
        
        # Step 1.5: Apply vocabulary replacements to transcript
        try:
            if session.transcript_simple:
                session.transcript_simple = apply_vocabulary_replacements(
                    session.transcript_simple,
                    db,
                    session.organization_id,
                )

            if session.transcript_diarized and isinstance(session.transcript_diarized, dict):
                segments = session.transcript_diarized.get("segments", [])
                for seg in segments:
                    if seg.get("text"):
                        seg["text"] = apply_vocabulary_replacements(
                            seg["text"],
                            db,
                            session.organization_id,
                        )
                session.transcript_diarized = session.transcript_diarized

            if transcription_result and "segments" in transcription_result:
                for seg in transcription_result["segments"]:
                    if seg.get("text"):
                        seg["text"] = apply_vocabulary_replacements(
                            seg["text"],
                            db,
                            session.organization_id,
                        )
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
        
        # Update metadata. Pull the actual STT model name + npu flag from
        # transcription_result so always-on sessions reflect whether they
        # ran through Parakeet (canonical) or the legacy NPU whisper fallback.
        metadata = session.processing_metadata or {}
        transcription_model = (
            (transcription_result or {}).get("model")
            if isinstance(transcription_result, dict)
            else None
        ) or "parakeet-tdt-1.1b"
        npu_accelerated = bool(
            (transcription_result or {}).get("npu_accelerated", False)
            if isinstance(transcription_result, dict)
            else False
        )
        metadata.update({
            "word_count": word_count,
            "speaker_count": speaker_count,
            "npu_accelerated": npu_accelerated,
            "processing_time_ms": int(processing_duration * 1000) if processing_duration > 0 else 0,
            "transcription_model": transcription_model,
            "ai_model": "granite3.3:8b",
            "processing_completed_at": datetime.now(timezone.utc).isoformat()
        })
        session.processing_metadata = metadata
        
        # Step 4: ALWAYS mark as completed (never leave in processing)
        session.status = "completed"
        session.updated_at = datetime.now(timezone.utc)

        # Promote action items into the first-class table so the dashboard
        # can render an interactive list. Best-effort; never block finalize.
        try:
            from services.action_items_extractor import persist_action_items
            persist_action_items(db, session)
        except Exception as exc:
            logger.warning(f"action_items promotion failed for session {session_id}: {exc}")

        try:
            db.commit()
            logger.info(f"✅ Successfully completed processing for session {session_id}")
            logger.info(f"   Status: {session.status}")
            logger.info(f"   Title: {session.title}")
            logger.info(f"   Has transcript: {bool(session.transcript)}")
            logger.info(f"   Has summary: {bool(session.summary)}")

            # Step 5: Index into vector store for semantic search
            try:
                from services.semantic_search_service import semantic_search
                semantic_search.index_session(
                    session_id=session.session_id or str(session.id),
                    title=session.title or session.name or "",
                    transcript=session.transcript_simple or "",
                    summary=session.summary or "",
                    created_at=session.created_at.isoformat() if session.created_at else "",
                    organization_id=session.organization_id,
                )
                logger.info(f"   Indexed in vector store for semantic search")
            except Exception as e:
                logger.warning(f"Vector indexing failed (non-fatal): {e}")

            # Step 6a: Phase 3 — identify speakers against the org speaker
            # library and rewrite transcript_diarized labels with display
            # names BEFORE embedding, so cross-meeting RAG sees real names.
            try:
                from services.speaker_service import identify_speakers
                ident_summary = identify_speakers(session, db)
                logger.info(f"   Speaker identification: {ident_summary}")
            except Exception as e:
                logger.warning(f"Speaker identification failed (non-fatal): {e}")

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

class RenameSessionRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    # ISO YYYY-MM-DD; empty string or null clears. The string form lets
    # the frontend send the native <input type="date"> value as-is.
    meeting_date: Optional[str] = None
    # 24h HH:MM[:SS]; empty string or null clears.
    meeting_time: Optional[str] = None


def _parse_meeting_date(value: Optional[str]):
    """Parse a YYYY-MM-DD into a date, or None to clear.

    Raises HTTPException(400) on malformed input so the client gets a
    helpful error instead of a 500.
    """
    if value is None or value == "":
        return None
    try:
        from datetime import date as _date
        return _date.fromisoformat(value)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=400,
            detail=f"meeting_date must be YYYY-MM-DD, got {value!r}",
        )


def _parse_meeting_time(value: Optional[str]):
    """Parse a HH:MM[:SS] into a time, or None to clear."""
    if value is None or value == "":
        return None
    try:
        from datetime import time as _time
        # Native <input type="time"> emits HH:MM; ISO accepts both.
        return _time.fromisoformat(value)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=400,
            detail=f"meeting_time must be HH:MM or HH:MM:SS, got {value!r}",
        )


@router.patch("/recording-sessions/{session_id}")
async def rename_session(
    session_id: str,
    request: RenameSessionRequest,
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
    db: Session = Depends(get_db),
):
    """Update user-editable session metadata.

    Supports title, description, meeting_date, meeting_time. Each is
    independently optional. Setting title flips title_user_set=True,
    which prevents the auto-summary step from overwriting the rename
    on the next reprocess. Setting meeting_date / meeting_time to "" or
    null clears the column back to NULL.
    """
    session = _get_session_for_org(db, active_org.organization.id, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if request.title is not None:
        title = request.title.strip()
        if title:
            session.title = title[:200]
            session.name = title[:200]
            session.title_user_set = True
        else:
            # Empty title resets so auto-titling can take over again.
            session.title_user_set = False

    if request.description is not None:
        session.description = request.description

    # meeting_date / meeting_time. The Pydantic field being present (not
    # absent) is what triggers an update; "" clears, value writes.
    fields_set = request.model_dump(exclude_unset=True)
    if "meeting_date" in fields_set:
        session.meeting_date = _parse_meeting_date(request.meeting_date)
    if "meeting_time" in fields_set:
        session.meeting_time = _parse_meeting_time(request.meeting_time)

    session.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(session)

    return {
        "status": "updated",
        "session_id": session.session_id,
        "title": session.title,
        "title_user_set": session.title_user_set,
        "meeting_date": session.meeting_date.isoformat() if session.meeting_date else None,
        "meeting_time": session.meeting_time.isoformat() if session.meeting_time else None,
    }


@router.patch("/recording-sessions/{session_id}/project-link")
async def update_session_project_link(
    session_id: str,
    request: UpdateSessionProjectRequest,
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
    db: Session = Depends(get_db),
):
    """Set or clear the project link on an existing recording session.

    Pass project_app=None (or empty string) to clear the link.
    """
    session = _get_session_for_org(db, active_org.organization.id, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Normalize: empty string means clear
    project_app = request.project_app or None
    if project_app and project_app not in ("project-ops", "crisis-ops"):
        raise HTTPException(status_code=400, detail="project_app must be 'project-ops' or 'crisis-ops'")

    if project_app:
        session.project_app = project_app
        session.project_id = request.project_id
        session.project_slug = request.project_slug
    else:
        # Clear the link
        session.project_app = None
        session.project_id = None
        session.project_slug = None

    session.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(session)

    logger.info(
        f"Updated project link for session {session_id}: "
        f"project_app={session.project_app}, project_id={session.project_id}"
    )

    return {
        "id": session.session_id or str(session.id),
        "project_app": session.project_app,
        "project_id": session.project_id,
        "project_slug": session.project_slug,
    }


@router.delete("/recording-sessions/{session_id}")
async def delete_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
    db: Session = Depends(get_db)
):
    """Delete a recording session"""
    
    session = _get_session_for_org(db, active_org.organization.id, session_id)
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Delete audio file if it exists
    if session.audio_file and os.path.exists(session.audio_file):
        try:
            os.remove(session.audio_file)
        except OSError:
            pass

    # Purge any durable copies in Garage too (the whole session prefix:
    # audio + tts + import). Makes "delete my data" actually delete it.
    try:
        from services.session_media import purge_session_media
        removed = purge_session_media(session)
        if removed:
            logger.info(f"Purged {removed} Garage object(s) for session {session_id}")
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Garage purge failed for session {session_id}: {exc}")

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
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
    db: Session = Depends(get_db)
):
    """Download audio file for a session"""
    from fastapi.responses import FileResponse, JSONResponse
    
    session = _get_session_for_org(db, active_org.organization.id, session_id)
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Resolve a local path: prefer the local working copy; if it's gone
    # (e.g. evicted), pull the durable copy back from Garage into the cache.
    # Backend proxies the bytes via FileResponse — Garage is never exposed
    # to the browser, and range requests (audio scrubbing) keep working.
    from services.session_media import resolve_local_path
    resolved = resolve_local_path(session)
    if resolved is None:
        if not session.audio_file:
            logger.warning(f"Session {session_id} has no audio file path")
            return JSONResponse(
                status_code=404,
                content={"detail": "No audio file associated with this session"}
            )
        logger.warning(f"Audio file not found locally or in Garage: {session.audio_file}")
        return JSONResponse(
            status_code=404,
            content={"detail": f"Audio file not found for session {session_id}"}
        )
    audio_path_str = str(resolved)
    # If the local working-copy path drifted, repoint it (cheap, idempotent).
    if session.audio_file != audio_path_str and resolved.exists():
        session.audio_file = audio_path_str
        try:
            db.commit()
        except Exception:
            db.rollback()

    filename = f"{(session.name or session.title or 'recording').replace(' ', '_')}_audio.wav"
    # Set headers for both streaming and download
    return FileResponse(
        audio_path_str,
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
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
    db: Session = Depends(get_db)
):
    """Download transcript with speakers for a session"""
    from fastapi.responses import Response
    
    session = _get_session_for_org(db, active_org.organization.id, session_id)
    
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
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
    db: Session = Depends(get_db)
):
    """Download meeting summary as PDF"""
    from fastapi.responses import Response

    session = _get_session_for_org(db, active_org.organization.id, session_id)

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

@router.get("/recording-sessions/{session_id}/download/summary/md")
async def download_summary_md(
    session_id: str,
    include_transcript: bool = False,
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
    db: Session = Depends(get_db)
):
    """Download meeting summary as GitHub-flavored markdown.

    Set ?include_transcript=true to append the full diarized transcript
    after the summary sections.
    """
    from fastapi.responses import Response

    session = _get_session_for_org(db, active_org.organization.id, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        from api.batch_export import export_to_markdown, ExportOptions
        options = ExportOptions(includeTranscript=include_transcript)
        md = export_to_markdown(session, options)
        filename = f"{(session.title or session.name or 'meeting').replace(' ', '_')}_summary.md"
        return Response(
            content=md,
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    except Exception as e:
        logger.error(f"Markdown generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Markdown generation failed: {e}")


@router.get("/recording-sessions/{session_id}/download/summary/docx")
async def download_summary_docx(
    session_id: str,
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
    db: Session = Depends(get_db)
):
    """Download meeting summary as DOCX"""
    from fastapi.responses import Response

    session = _get_session_for_org(db, active_org.organization.id, session_id)

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
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
    db: Session = Depends(get_db)
):
    """Download simple transcript without speakers"""
    from fastapi.responses import Response
    
    session = _get_session_for_org(db, active_org.organization.id, session_id)
    
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


# === Storage Management ===

@router.get("/storage/stats")
async def get_storage_stats(
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
    db: Session = Depends(get_db)
):
    """Get storage usage statistics"""
    import glob
    from services.working_audio_service import audio_service as _as
    recordings_dir = _as.RECORDINGS_DIR

    # Count files and total size
    wav_files = glob.glob(os.path.join(recordings_dir, "**", "*.wav"), recursive=True)
    total_size = sum(os.path.getsize(f) for f in wav_files if os.path.exists(f))

    # Get session counts
    total_sessions = _scoped_session_query(db, active_org.organization.id).count()
    sessions_with_audio = _scoped_session_query(db, active_org.organization.id).filter(
        DBRecordingSession.audio_file.isnot(None)
    ).count()

    return {
        "recordings_dir": recordings_dir,
        "total_files": len(wav_files),
        "total_size_bytes": total_size,
        "total_size_mb": round(total_size / (1024 * 1024), 1),
        "total_sessions": total_sessions,
        "sessions_with_audio": sessions_with_audio
    }


@router.post("/storage/cleanup")
async def cleanup_old_recordings(
    days: int = Query(default=90, ge=1, le=365, description="Delete recordings older than N days"),
    dry_run: bool = Query(default=True, description="If true, only report what would be deleted"),
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
    db: Session = Depends(get_db)
):
    """Delete WAV files older than N days. Keeps transcripts and summaries."""

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # Find old sessions with audio files
    old_sessions = _scoped_session_query(db, active_org.organization.id).filter(
        DBRecordingSession.created_at < cutoff,
        DBRecordingSession.audio_file.isnot(None),
        DBRecordingSession.status.in_(["completed", "failed"])
    ).all()

    results = []
    freed_bytes = 0

    for session in old_sessions:
        audio_path = session.audio_file
        file_size = 0
        if audio_path and os.path.exists(audio_path):
            file_size = os.path.getsize(audio_path)
            freed_bytes += file_size

            if not dry_run:
                os.unlink(audio_path)
                session.audio_file = None
                # Keep everything else (transcript, summary, title, etc.)

        results.append({
            "session_id": session.session_id,
            "name": session.name,
            "created_at": session.created_at.isoformat() if session.created_at else None,
            "file_size_mb": round(file_size / (1024 * 1024), 1),
            "action": "deleted" if not dry_run else "would_delete"
        })

    if not dry_run:
        db.commit()

    return {
        "dry_run": dry_run,
        "cutoff_date": cutoff.isoformat(),
        "sessions_affected": len(results),
        "space_freed_mb": round(freed_bytes / (1024 * 1024), 1),
        "details": results
    }


# === Always-On Recording Mode ===

@router.post("/always-on/start")
async def start_always_on(
    body: Optional[StartRecordingRequest] = None,
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
):
    """Enable always-on recording mode. The system will listen continuously
    and automatically create meeting sessions when speech is detected."""
    from services.always_on_recorder import always_on_recorder

    device_id = body.device_id if body else None
    result = await always_on_recorder.start(device_id=device_id)
    # Scope every auto-detected meeting to the requesting user's org. Without
    # this the recorder refuses to create sessions (organization_id is NOT
    # NULL) — see AlwaysOnRecorder.attach_owner / _start_new_meeting.
    always_on_recorder.attach_owner(active_org.organization.id, current_user.id)
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
