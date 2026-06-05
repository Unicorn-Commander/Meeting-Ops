"""Per-session participants CRUD.

Participants are stored as a JSONB list on `recording_sessions.participants`.
Each entry is {"id": str (uuid4), "name": str, "email": str|null, "role": str|null}.

The `id` is generated server-side at insert and used for PATCH/DELETE addressing
so the frontend never has to reason about list indices (which shift under
concurrent edits). Order of the list is preserved as insertion order.
"""
from __future__ import annotations

import logging
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from auth.dependencies import get_current_organization, get_current_user
from auth.models import User
from auth.organization import ActiveOrganization
from database.database import get_db
from database.models import RecordingSession


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/simple/recording-sessions/{session_id}/participants",
    tags=["session-participants"],
)


class ParticipantIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    email: Optional[EmailStr] = None
    role: Optional[str] = Field(default=None, max_length=100)
    # Contact-Ops person id (federation join key). Stamped when known
    # so the inbound Customer-Ops reads can find meetings by contact.
    contact_id: Optional[str] = Field(default=None, max_length=64)


class ParticipantPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    email: Optional[EmailStr] = None
    role: Optional[str] = Field(default=None, max_length=100)
    contact_id: Optional[str] = Field(default=None, max_length=64)


class ParticipantOut(BaseModel):
    id: str
    name: str
    email: Optional[str] = None
    role: Optional[str] = None
    contact_id: Optional[str] = None


def _resolve_session(
    db: Session, organization_id: int, session_id: str
) -> RecordingSession:
    """UUID-or-integer-pk lookup scoped to the active org. Mirrors
    api.uploads:reprocess_session so callers can pass whichever id they
    have on hand."""
    rec = (
        db.query(RecordingSession)
        .filter(
            RecordingSession.session_id == session_id,
            RecordingSession.organization_id == organization_id,
        )
        .first()
    )
    if rec:
        return rec
    try:
        pk = int(session_id)
    except (TypeError, ValueError):
        pk = None
    if pk is not None:
        rec = (
            db.query(RecordingSession)
            .filter(
                RecordingSession.id == pk,
                RecordingSession.organization_id == organization_id,
            )
            .first()
        )
    if not rec:
        raise HTTPException(status_code=404, detail="Session not found")
    return rec


def _can_edit(
    session: RecordingSession,
    user: User,
    active_org: ActiveOrganization,
) -> bool:
    """Org admin/manager, session creator, or superuser may mutate participants.
    Mirrors the auth check in api.session_emails.email_attendees so the two
    write surfaces stay in lockstep."""
    if getattr(user, "is_superuser", False):
        return True
    role = (active_org.user_role or "").lower() if hasattr(active_org, "user_role") else ""
    if role in {"admin", "manager"}:
        return True
    if session.user_id and session.user_id == user.id:
        return True
    return False


def _normalize(participants: object) -> List[dict]:
    """Defensive load — JSONB column should always be a list but a stray
    None or dict shouldn't 500 the endpoint."""
    if not participants:
        return []
    if isinstance(participants, list):
        return [p for p in participants if isinstance(p, dict)]
    return []


def _to_out(p: dict) -> ParticipantOut:
    return ParticipantOut(
        id=str(p.get("id") or ""),
        name=str(p.get("name") or ""),
        email=p.get("email") or None,
        role=p.get("role") or None,
        contact_id=p.get("contact_id") or None,
    )


@router.get("", response_model=List[ParticipantOut])
async def list_participants(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
):
    session = _resolve_session(db, active_org.organization.id, session_id)
    return [_to_out(p) for p in _normalize(session.participants)]


@router.post("", response_model=ParticipantOut, status_code=201)
async def add_participant(
    session_id: str,
    payload: ParticipantIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
):
    session = _resolve_session(db, active_org.organization.id, session_id)
    if not _can_edit(session, current_user, active_org):
        raise HTTPException(status_code=403, detail="Not permitted to edit participants")

    new = {
        "id": str(uuid.uuid4()),
        "name": payload.name.strip(),
        "email": (str(payload.email) if payload.email else None),
        "role": (payload.role.strip() if payload.role else None) or None,
        "contact_id": (payload.contact_id.strip() if payload.contact_id else None) or None,
    }
    current = _normalize(session.participants)
    current.append(new)
    session.participants = current
    flag_modified(session, "participants")
    db.commit()
    logger.info("participants: add session=%s name=%s", session.id, new["name"])
    return _to_out(new)


@router.patch("/{participant_id}", response_model=ParticipantOut)
async def update_participant(
    session_id: str,
    participant_id: str,
    payload: ParticipantPatch,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
):
    session = _resolve_session(db, active_org.organization.id, session_id)
    if not _can_edit(session, current_user, active_org):
        raise HTTPException(status_code=403, detail="Not permitted to edit participants")

    current = _normalize(session.participants)
    updated = None
    for p in current:
        if str(p.get("id")) == participant_id:
            if payload.name is not None:
                p["name"] = payload.name.strip()
            # Distinguish "not provided" from "explicitly cleared" via model_fields_set
            if "email" in payload.model_fields_set:
                p["email"] = str(payload.email) if payload.email else None
            if "role" in payload.model_fields_set:
                p["role"] = (payload.role.strip() if payload.role else None) or None
            if "contact_id" in payload.model_fields_set:
                p["contact_id"] = (payload.contact_id.strip() if payload.contact_id else None) or None
            updated = p
            break

    if updated is None:
        raise HTTPException(status_code=404, detail="Participant not found")

    session.participants = current
    flag_modified(session, "participants")
    db.commit()
    return _to_out(updated)


@router.delete("/{participant_id}", status_code=204)
async def delete_participant(
    session_id: str,
    participant_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
):
    session = _resolve_session(db, active_org.organization.id, session_id)
    if not _can_edit(session, current_user, active_org):
        raise HTTPException(status_code=403, detail="Not permitted to edit participants")

    current = _normalize(session.participants)
    remaining = [p for p in current if str(p.get("id")) != participant_id]
    if len(remaining) == len(current):
        raise HTTPException(status_code=404, detail="Participant not found")

    session.participants = remaining
    flag_modified(session, "participants")
    db.commit()
    return None
