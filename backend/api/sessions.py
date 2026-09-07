"""
Session management API endpoints
"""
import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from typing import List, Optional, Union
from datetime import datetime, timezone

from database.database import get_db
from database.models import RecordingSession
from auth.dependencies import get_current_organization, get_current_user
from auth.organization import ActiveOrganization
from auth.models import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/recording-sessions", tags=["sessions"])

@router.get("", response_model=List[dict])
async def list_sessions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000)
):
    """List all recording sessions"""
    sessions = (
        db.query(RecordingSession)
        .filter(RecordingSession.organization_id == active_org.organization.id)
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [
        {
            "id": str(session.id),
            "title": session.title,
            "created_at": session.created_at.isoformat() if session.created_at else None,
            "status": session.status,
            "duration": session.duration,
            "is_combined": bool(getattr(session, "is_combined", False)),
        }
        for session in sessions
    ]

@router.get("/{session_id}")
async def get_session(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
):
    """Get a specific recording session"""
    from api.session_permissions import resolve_session_for_user

    session = resolve_session_for_user(
        db, active_org.organization.id, session_id, current_user
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "id": str(session.id),
        "title": session.title,
        "created_at": session.created_at.isoformat() if session.created_at else None,
        "status": session.status,
        "duration": session.duration,
        "participants": (session.extra_data or {}).get("participants", []),
        "description": session.description,
        "is_combined": bool(getattr(session, "is_combined", False)),
    }

@router.post("")
async def create_session(
    session_data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
):
    """Create a new recording session"""
    session = RecordingSession(
        title=session_data.get("title", "Untitled Session"),
        description=session_data.get("description", ""),
        status="pending",
        created_at=datetime.now(timezone.utc),
        extra_data={"participants": session_data.get("participants", [])},
        user_id=current_user.id,
        organization_id=active_org.organization.id,
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


# ---------------------------------------------------------------------------
# Combined meetings (docs/COMBINED-MEETINGS-CONTRACT.md)
#
# Absolute-path router so the wire paths are exactly the contract's
# ``POST /api/sessions/combine`` and ``POST /api/sessions/{id}/combine/rerun``
# (the legacy ``router`` above is mounted under ``/api/recording-sessions``).
# Registered in main.py right after ``router`` so it is matched before the
# other ``/api/sessions/{session_id}/…`` routers (speakers, tts).
# ---------------------------------------------------------------------------

combine_router = APIRouter(prefix="/api/sessions", tags=["combined-meetings"])


class CombineRequest(BaseModel):
    """Body for ``POST /api/sessions/combine``.

    ``session_ids`` are WIRE ids — the UUID ``session_id`` the list endpoint
    returns, or a numeric pk (as a string or an int). Validation of the set
    (>= 2 distinct, editable, same org, no nesting) lives in
    ``services.session_combine.resolve_parts`` so the API can answer with
    the contract's 400 / 404 instead of a 422.
    """

    session_ids: List[Union[str, int]] = Field(default_factory=list)
    name: Optional[str] = Field(default=None, max_length=200)


async def _enqueue_combine_job(
    db: Session,
    combined: RecordingSession,
    *,
    current_user: User,
    background_tasks: BackgroundTasks,
    force: bool,
) -> str:
    """Enqueue ``combine_sessions_job`` on the INTERACTIVE arq lane (the same
    ``services.job_runner.enqueue_job`` path finalize uses) and stamp the row
    with the job id for the worker's drift guard.

    Without arq (dev/test, no Redis) the job runs in-process after the
    response — mirroring finalize's inline fallback — so the endpoint stays
    functional and the row never sits in ``processing`` with no job behind it.
    """
    from services.job_runner import enqueue_job

    job_id: Optional[str] = None
    try:
        job_id = await enqueue_job(
            "combine_sessions_job",
            combined.id,
            user_id=current_user.id,
            org_id=combined.organization_id,
            owner_user_id=current_user.id,
            owner_org_id=combined.organization_id,
            force=force,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "combine: arq enqueue failed session=%s: %s — running inline",
            combined.id, exc,
        )
    if not job_id:
        job_id = f"inline-{uuid.uuid4().hex[:16]}"
        from workers.combine_workers import combine_sessions_job

        background_tasks.add_task(
            combine_sessions_job,
            {"job_id": job_id},
            combined.id,
            current_user.id,
            combined.organization_id,
            None,
            force,
        )
    combined.processing_job_id = job_id
    combined.status = "processing"
    db.commit()
    db.refresh(combined)
    return job_id


@combine_router.post("/combine", status_code=202)
async def combine_sessions(
    body: CombineRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
):
    """Create a combined meeting from two or more sessions.

    The parts are NOT modified. A new summary-only session is created with
    ordered links to the parts, and the unified summary / insights / action
    items are generated in the background (202 + ``job_id``; poll the
    session's ``status`` via ``status_url``).
    """
    from services import session_combine as sc

    try:
        parts = sc.resolve_parts(
            db, active_org.organization.id, current_user, body.session_ids
        )
    except sc.CombineError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)

    combined = sc.create_combined_session(
        db, parts, name=body.name, user_id=current_user.id
    )
    job_id = await _enqueue_combine_job(
        db,
        combined,
        current_user=current_user,
        background_tasks=background_tasks,
        force=False,
    )
    logger.info(
        "combine: created combined session=%s parts=%s job=%s user=%s",
        combined.id, [p.id for p in parts], job_id, current_user.id,
    )
    return sc.combined_payload(db, combined, job_id=job_id)


@combine_router.post("/{session_id}/combine/rerun", status_code=202)
async def rerun_combined_summary(
    session_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
):
    """Regenerate the unified summary of an existing combined meeting
    (e.g. after renaming speakers in a part). Always re-runs the LLM."""
    from api.session_permissions import resolve_session_for_user
    from services import session_combine as sc

    combined = resolve_session_for_user(
        db, active_org.organization.id, session_id, current_user, min_level="edit"
    )
    if combined is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if not bool(getattr(combined, "is_combined", False)):
        raise HTTPException(status_code=400, detail="Not a combined meeting")
    if not sc.members_in_order(db, combined.id):
        raise HTTPException(
            status_code=400, detail="This combined meeting has no parts left"
        )
    job_id = await _enqueue_combine_job(
        db,
        combined,
        current_user=current_user,
        background_tasks=background_tasks,
        force=True,
    )
    logger.info(
        "combine: rerun combined session=%s job=%s user=%s",
        combined.id, job_id, current_user.id,
    )
    return sc.combined_payload(db, combined, job_id=job_id)
