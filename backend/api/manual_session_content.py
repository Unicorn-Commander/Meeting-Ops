"""Explicitly authored text content; no audio, model or federation shortcut."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import DBAPIError

from auth.dependencies import get_current_user, get_current_organization
from auth.models import User
from auth.organization import ActiveOrganization
from database.database import get_db
from database.models import RecordingSession
from api.session_permissions import has_session_access
from services.manual_session_content import ManualContentRequest, state, replace, lock_transcription_writes

router = APIRouter(prefix="/api/simple/recording-sessions", tags=["manual-content"])


def _editable(db, session_id, user, active_org, *, lock=True):
    # Deliberately do not use the legacy resolver's cross-org fallback or its
    # org-wide read shortcut, which does not enforce min_level='edit'.
    query = db.query(RecordingSession).filter(RecordingSession.organization_id == active_org.organization.id)
    if lock:
        query = query.populate_existing().with_for_update()
    row = query.filter(RecordingSession.session_id == session_id).first()
    if row is None and session_id.isdecimal():
        row = query.filter(RecordingSession.id == int(session_id)).first()
    if row is None:
        raise HTTPException(404, "Session not found")
    if active_org.role_name not in {"owner", "admin", "manager"} and has_session_access(row.id, user, db) != "edit":
        raise HTTPException(403, "Session edit permission required")
    return row


@router.get("/{session_id}/manual-content")
def get_manual_content_state(session_id: str, db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization)):
    row = _editable(db, session_id, current_user, active_org)
    return state(db, row)


@router.put("/{session_id}/manual-content")
def replace_manual_content(session_id: str, body: ManualContentRequest,
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization)):
    try:
        _editable(db, session_id, current_user, active_org, lock=False)
        lock_transcription_writes(db)
        row = _editable(db, session_id, current_user, active_org)
        result = replace(db, row, body, current_user)
        db.commit()
        return {"session_id": row.session_id or str(row.id), **result}
    except DBAPIError as exc:
        db.rollback()
        if getattr(exc.orig, "pgcode", None) in {"55P03", "40P01"}:
            raise HTTPException(409, "Content is being edited; retry after reviewing the current revision") from exc
        raise
    except Exception:
        db.rollback()
        raise
