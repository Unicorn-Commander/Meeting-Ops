"""Per-meeting collaborator permissions API.

Implements the per-session leaf of the RBAC plan in RBAC_DESIGN.md:
explicit collaborator grants on a single recording session, on top of
the org-level and project-level membership checks that already exist.

Endpoints are mounted on /api/simple/recording-sessions/{session_id}
alongside the rest of the simple-recording API so the frontend can
hang the share modal off the same base path.

Also exposes `has_session_access(...)`, the single helper other
endpoints should call when they need to decide whether a non-org user
is allowed to see or mutate a recording session.
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr, model_validator
from sqlalchemy import or_
from sqlalchemy.orm import Session

from auth.dependencies import get_current_organization, get_current_user
from auth.models import User, UserOrganization
from auth.organization import ActiveOrganization
from database.database import get_db
from database.models import RecordingSession as DBRecordingSession
from database.models import SessionCollaborator

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/simple/recording-sessions/{session_id}",
    tags=["session-permissions"],
)

# Routes that resolve a public token (no auth) live on a separate
# router so they aren't shadowed by the path-prefixed router above.
public_router = APIRouter(
    prefix="/api/simple/recording-sessions",
    tags=["session-permissions"],
)


# ---------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------


AccessLevel = Literal["read", "comment", "edit"]
_VALID_ACCESS_LEVELS = ("read", "comment", "edit")


class CollaboratorCreate(BaseModel):
    """Body for POST /permissions/collaborators.

    Either user_id or email must be set. If both are set, user_id wins
    and the email is kept for display only.
    """
    user_id: Optional[int] = None
    email: Optional[EmailStr] = None
    access_level: AccessLevel = "read"

    @model_validator(mode="after")
    def _require_user_or_email(self) -> "CollaboratorCreate":
        if not self.user_id and not self.email:
            raise ValueError("Either user_id or email must be provided")
        return self


class CollaboratorPatch(BaseModel):
    """Body for PATCH /permissions/collaborators/{id}."""
    access_level: AccessLevel


class CollaboratorUserOut(BaseModel):
    id: int
    email: str
    username: Optional[str] = None
    full_name: Optional[str] = None


class CollaboratorOut(BaseModel):
    id: int
    user: Optional[CollaboratorUserOut] = None
    email: Optional[str] = None
    access_level: AccessLevel
    invited_by_user_id: Optional[int] = None
    token: str
    expires_at: Optional[str] = None
    accepted_at: Optional[str] = None
    revoked_at: Optional[str] = None
    created_at: Optional[str] = None
    # Convenience: did this row already get accepted (i.e. the invitee
    # opened the magic link and we resolved their user_id)?
    accepted: bool = False
    # Pre-baked magic link the frontend can show in the share modal.
    # The route resolution happens client-side; we just hand back the
    # token so the UI can build whatever URL pattern it wants.
    invite_url: Optional[str] = None


class PermissionsOut(BaseModel):
    session_id: str
    # True if any org admin/manager/member/viewer of the session's org
    # can see it. Always true today for org-scoped sessions, but exposed
    # so the frontend can render the "shared with your team" badge
    # accurately when we add per-session visibility flags later.
    org_default: bool
    # True if a project link is set and any member of that project can
    # see it. Always False today because the cross-app project member
    # lookup isn't wired yet (see TODO in has_session_access).
    project_default: bool
    collaborators: List[CollaboratorOut]


class AccessTokenOut(BaseModel):
    """Response for GET /permissions/access?token=...

    Public, no auth. The frontend uses this to verify a magic link
    before redirecting the viewer into the shared-session view.
    """
    valid: bool
    session_id: Optional[str] = None
    session_db_id: Optional[int] = None
    access_level: Optional[AccessLevel] = None
    reason: Optional[str] = None


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------


def _get_session_by_str_id(db: Session, session_id: str) -> Optional[DBRecordingSession]:
    """Resolve a session by its UUID string-id or its integer PK.

    Mirrors _get_session_for_org in simple_recording_db.py but does NOT
    scope by organization — callers do their own access check after.
    """
    session = (
        db.query(DBRecordingSession)
        .filter(DBRecordingSession.session_id == session_id)
        .first()
    )
    if session:
        return session
    try:
        int_id = int(session_id)
    except (TypeError, ValueError):
        return None
    return (
        db.query(DBRecordingSession)
        .filter(DBRecordingSession.id == int_id)
        .first()
    )


def _user_org_role(
    db: Session, user: User, organization_id: Optional[int]
) -> Optional[str]:
    """Return the user's role in `organization_id`, or None if no membership."""
    if organization_id is None:
        return None
    membership = (
        db.query(UserOrganization)
        .filter(
            UserOrganization.user_id == user.id,
            UserOrganization.organization_id == organization_id,
        )
        .first()
    )
    return membership.role if membership else None


def _is_project_member(
    db: Session,
    user: User,
    project_app: Optional[str],
    project_id: Optional[str],
) -> bool:
    """Stub for the cross-app project membership lookup.

    TODO: call out to project-ops / crisis-ops (or look up a shared
    project_members table once one exists) to decide whether `user`
    is a member of the linked project. Until that's wired we treat
    "no project members visible" as the safe default — meeting will
    still be visible via org membership or an explicit collaborator
    row.
    """
    return False


def has_session_access(
    session_id: str | int,
    user: User,
    db: Session,
) -> Literal["denied", "view", "comment", "edit"]:
    """Decide what level of access `user` has to a recording session.

    Resolution order (first match wins):
      1. Org admin / manager / member of the session's org -> "edit"
      2. Org viewer of the session's org                  -> "view"
      3. Project member (via cross-app lookup, stubbed)   -> "edit"
      4. session_collaborators row for this user          -> row.access_level
      5. (else)                                           -> "denied"

    Superusers always get "edit".

    Callers should treat anything other than "denied" as "may at least
    read" and use the specific level to decide whether to allow mutations.
    """
    # Resolve session
    if isinstance(session_id, int):
        session = (
            db.query(DBRecordingSession)
            .filter(DBRecordingSession.id == session_id)
            .first()
        )
    else:
        session = _get_session_by_str_id(db, str(session_id))
    if not session:
        return "denied"

    # Superuser shortcut — global admin
    if getattr(user, "is_superuser", False):
        return "edit"

    # 1+2: org membership
    role = _user_org_role(db, user, session.organization_id)
    if role in ("admin", "manager", "member", "user"):
        # "user" is the legacy role name in user_organizations.role;
        # treat it equivalent to "member" for session access.
        return "edit"
    if role == "viewer":
        return "view"

    # 3: project membership (stubbed)
    if session.project_app and session.project_id:
        if _is_project_member(db, user, session.project_app, session.project_id):
            return "edit"

    # 4: explicit collaborator row
    collaborator = (
        db.query(SessionCollaborator)
        .filter(
            SessionCollaborator.session_id == session.id,
            SessionCollaborator.revoked_at.is_(None),
            or_(
                SessionCollaborator.user_id == user.id,
                SessionCollaborator.email == user.email,
            ),
        )
        .first()
    )
    if collaborator and _is_collaborator_active(collaborator):
        level = collaborator.access_level or "read"
        if level == "read":
            return "view"
        if level == "comment":
            return "comment"
        if level == "edit":
            return "edit"

    return "denied"


_ACCESS_RANK = {"denied": 0, "view": 1, "comment": 2, "edit": 3}


def resolve_session_for_user(
    db: Session,
    active_org_id: int,
    session_id: str | int,
    user: User,
    min_level: str = "view",
) -> Optional[DBRecordingSession]:
    """Canonical session resolver for session-scoped endpoints.

    1. Strict lookup inside the caller's ACTIVE org (uuid session_id column,
       then integer pk) — org members keep exactly the access they had.
    2. Cross-org fallback: resolve by id alone, then gate on
       has_session_access >= min_level ("view" for reads, "edit" for
       mutations). Covers personal-org sessions viewed while active in
       another org, and shared/collaborator sessions.

    Returns None when nothing accessible matches — callers raise their own
    404 so response shapes stay unchanged. This exists because the strict
    filter was copy-pasted into half a dozen files (audio download, tags,
    attachments, TTS, insights, chat, reprocess, rediarize…) and each copy
    404'd cross-org sessions the main session GET happily serves.
    """
    q = db.query(DBRecordingSession).filter(
        DBRecordingSession.organization_id == active_org_id
    )
    session = q.filter(DBRecordingSession.session_id == str(session_id)).first()
    if not session:
        try:
            pk = int(session_id)
        except (TypeError, ValueError):
            pk = None
        if pk is not None:
            session = q.filter(DBRecordingSession.id == pk).first()
    if session:
        return session

    candidate = _get_session_by_str_id(db, str(session_id))
    if not candidate:
        return None
    level = has_session_access(candidate.id, user, db)
    if _ACCESS_RANK.get(level, 0) >= _ACCESS_RANK.get(min_level, 1):
        return candidate
    return None


def _is_collaborator_active(row: SessionCollaborator) -> bool:
    if row.revoked_at is not None:
        return False
    if row.expires_at is not None:
        now = datetime.now(timezone.utc)
        # row.expires_at may come back naive on some drivers — normalize.
        exp = row.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < now:
            return False
    return True


def _can_manage_collaborators(
    db: Session,
    user: User,
    session: DBRecordingSession,
) -> bool:
    """Restricted to org admin/manager OR the session creator."""
    if getattr(user, "is_superuser", False):
        return True
    if session.user_id and session.user_id == user.id:
        return True
    role = _user_org_role(db, user, session.organization_id)
    return role in ("admin", "manager")


def _serialize_collaborator(
    db: Session, row: SessionCollaborator
) -> CollaboratorOut:
    user_out: Optional[CollaboratorUserOut] = None
    if row.user_id:
        u = db.query(User).filter(User.id == row.user_id).first()
        if u:
            user_out = CollaboratorUserOut(
                id=u.id,
                email=u.email,
                username=u.username,
                full_name=u.full_name,
            )
    return CollaboratorOut(
        id=row.id,
        user=user_out,
        email=row.email,
        access_level=row.access_level,  # type: ignore[arg-type]
        invited_by_user_id=row.invited_by_user_id,
        token=str(row.token),
        expires_at=row.expires_at.isoformat() if row.expires_at else None,
        accepted_at=row.accepted_at.isoformat() if row.accepted_at else None,
        revoked_at=row.revoked_at.isoformat() if row.revoked_at else None,
        created_at=row.created_at.isoformat() if row.created_at else None,
        accepted=row.accepted_at is not None,
        invite_url=_build_invite_url(row.token),
    )


def _build_invite_url(token: uuid.UUID) -> str:
    """Build a magic-link URL the frontend can show in the share modal.

    Reads MEETING_OPS_PUBLIC_URL (preferred) or APP_PUBLIC_URL as the
    base; falls back to a relative URL the frontend will resolve
    against window.location.
    """
    base = (
        os.getenv("MEETING_OPS_PUBLIC_URL", "").strip()
        or os.getenv("APP_PUBLIC_URL", "").strip()
        or ""
    ).rstrip("/")
    suffix = f"/shared/sessions?token={token}"
    return f"{base}{suffix}" if base else suffix


# ---------------------------------------------------------------------
# Invitation email (Postmark via existing SMTP env if available)
# ---------------------------------------------------------------------


def _send_invitation_email(
    *,
    to_email: str,
    invite_url: str,
    inviter: User,
    session: DBRecordingSession,
    access_level: str,
) -> None:
    """Send an external-collaborator invitation email.

    Looks for POSTMARK_SERVER_TOKEN (Postmark HTTP API) first; if not
    present, falls back to the SMTP env vars used elsewhere in the
    codebase. If neither is configured, logs the TODO and returns —
    we don't want a missing email config to break the API call.
    """
    from auth.email import _postmark_sender, _postmark_token

    postmark_token = _postmark_token()
    from_email = (
        _postmark_sender()
        if postmark_token
        else (
            os.getenv("SMTP_FROM", "").strip()
            or os.getenv("SMTP_USER", "").strip()
        )
    )
    subject = (
        f"{inviter.full_name or inviter.email} shared a meeting with you"
    )
    session_title = (
        session.title or session.name or f"Meeting {session.id}"
    )
    body_text = (
        f"{inviter.full_name or inviter.email} invited you to view a "
        f"meeting on Meeting-Ops ({access_level} access).\n\n"
        f"Meeting: {session_title}\n\n"
        f"Open it here: {invite_url}\n\n"
        "If you weren't expecting this, you can ignore this email."
    )

    if not from_email:
        logger.info(
            "TODO: send invitation email to %s (no from-address "
            "configured; would have sent: %s)",
            to_email,
            invite_url,
        )
        return

    # 1) Postmark HTTP API
    if postmark_token:
        try:
            import json as _json
            import urllib.request as _u

            req = _u.Request(
                "https://api.postmarkapp.com/email",
                data=_json.dumps(
                    {
                        "From": from_email,
                        "To": to_email,
                        "Subject": subject,
                        "TextBody": body_text,
                        "MessageStream": os.getenv(
                            "POSTMARK_MESSAGE_STREAM", "outbound"
                        ),
                    }
                ).encode(),
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "X-Postmark-Server-Token": postmark_token,
                },
                method="POST",
            )
            with _u.urlopen(req, timeout=10) as resp:
                if resp.status >= 300:
                    raise RuntimeError(f"Postmark HTTP {resp.status}")
            logger.info(
                "Sent collaborator invitation via Postmark to %s "
                "(session %s)",
                to_email,
                session.session_id or session.id,
            )
            return
        except Exception as exc:
            logger.warning(
                "Postmark send failed for %s: %s — falling back to SMTP",
                to_email,
                exc,
            )

    # 2) SMTP fallback (reuses creds the rest of the app uses)
    smtp_host = os.getenv("SMTP_HOST", "").strip()
    if not smtp_host:
        logger.info(
            "TODO: send invitation email to %s (no Postmark token, no "
            "SMTP host; would have sent: %s)",
            to_email,
            invite_url,
        )
        return

    try:
        import smtplib
        from email.mime.text import MIMEText

        smtp_port = int(os.getenv("SMTP_PORT", "587"))
        smtp_user = os.getenv("SMTP_USER", "").strip()
        smtp_password = os.getenv("SMTP_PASSWORD", "").strip()
        use_tls = os.getenv("SMTP_USE_TLS", "true").lower() == "true"

        msg = MIMEText(body_text)
        msg["Subject"] = subject
        msg["From"] = from_email
        msg["To"] = to_email

        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as smtp:
            if use_tls:
                smtp.starttls()
            if smtp_user and smtp_password:
                smtp.login(smtp_user, smtp_password)
            smtp.send_message(msg)
        logger.info(
            "Sent collaborator invitation via SMTP to %s (session %s)",
            to_email,
            session.session_id or session.id,
        )
    except Exception as exc:
        logger.warning(
            "SMTP invitation email failed for %s: %s "
            "(invite_url=%s) — frontend can still surface the link "
            "for manual sharing",
            to_email,
            exc,
            invite_url,
        )


# ---------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------


@router.get("/permissions", response_model=PermissionsOut)
async def get_permissions(
    session_id: str,
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> PermissionsOut:
    """Return the collaborator-management view for a recording session.

    This payload includes invitee email addresses and pending magic links,
    so it is restricted to the session creator or an org admin/manager.
    Ordinary readers use the meeting endpoint and never receive the
    collaborator roster or bearer tokens.
    """
    session = _get_session_by_str_id(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if not _can_manage_collaborators(db, current_user, session):
        raise HTTPException(
            status_code=403,
            detail="Only the session creator or an org admin/manager can manage collaborators",
        )

    collaborators = (
        db.query(SessionCollaborator)
        .filter(
            SessionCollaborator.session_id == session.id,
            SessionCollaborator.revoked_at.is_(None),
        )
        .order_by(SessionCollaborator.created_at.asc())
        .all()
    )

    project_default = False  # see _is_project_member TODO

    return PermissionsOut(
        session_id=session.session_id or str(session.id),
        org_default=session.organization_id is not None,
        project_default=project_default,
        collaborators=[_serialize_collaborator(db, c) for c in collaborators],
    )


@router.post("/permissions/collaborators", response_model=CollaboratorOut)
async def add_collaborator(
    session_id: str,
    body: CollaboratorCreate,
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> CollaboratorOut:
    """Add a collaborator to a recording session.

    - If body.user_id is set, the row is created with that user.
    - If only body.email is set and matches an existing user, user_id is
      auto-resolved (the invitee already has a uchub account).
    - If only body.email is set and no user matches, the row stays
      email-only and the magic-link token gates access until they accept.

    Restricted to org admin/manager OR the session creator.
    """
    session = _get_session_by_str_id(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if not _can_manage_collaborators(db, current_user, session):
        raise HTTPException(
            status_code=403,
            detail="Only the session creator or an org admin/manager can manage collaborators",
        )

    if body.access_level not in _VALID_ACCESS_LEVELS:
        raise HTTPException(
            status_code=400,
            detail=f"access_level must be one of {_VALID_ACCESS_LEVELS}",
        )

    user_id = body.user_id
    email_value = body.email
    resolved_email = email_value

    if user_id:
        invitee = db.query(User).filter(User.id == user_id).first()
        if not invitee:
            raise HTTPException(status_code=404, detail="Invitee user not found")
        resolved_email = invitee.email
    elif email_value:
        # Resolve to an existing user if we already have one for this email.
        invitee = (
            db.query(User).filter(User.email.ilike(str(email_value))).first()
        )
        if invitee:
            user_id = invitee.id
            resolved_email = invitee.email

    # Avoid duplicate active rows for the same (session, user) pair.
    if user_id:
        existing = (
            db.query(SessionCollaborator)
            .filter(
                SessionCollaborator.session_id == session.id,
                SessionCollaborator.user_id == user_id,
                SessionCollaborator.revoked_at.is_(None),
            )
            .first()
        )
        if existing:
            existing.access_level = body.access_level
            db.commit()
            db.refresh(existing)
            return _serialize_collaborator(db, existing)

    row = SessionCollaborator(
        session_id=session.id,
        user_id=user_id,
        email=str(resolved_email) if resolved_email else None,
        access_level=body.access_level,
        invited_by_user_id=current_user.id,
        token=uuid.uuid4(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    # External-only invite -> send magic-link email
    if not user_id and resolved_email:
        try:
            _send_invitation_email(
                to_email=str(resolved_email),
                invite_url=_build_invite_url(row.token),
                inviter=current_user,
                session=session,
                access_level=body.access_level,
            )
        except Exception as exc:
            # Don't unwind the DB write — the magic link still works,
            # the user can resend manually if needed.
            logger.warning(
                "Invitation email send failed (non-fatal) for %s: %s",
                resolved_email,
                exc,
            )

    return _serialize_collaborator(db, row)


@router.patch(
    "/permissions/collaborators/{collaborator_id}",
    response_model=CollaboratorOut,
)
async def update_collaborator(
    session_id: str,
    collaborator_id: int,
    body: CollaboratorPatch,
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> CollaboratorOut:
    """Change a collaborator's access_level. Same auth as POST."""
    session = _get_session_by_str_id(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if not _can_manage_collaborators(db, current_user, session):
        raise HTTPException(
            status_code=403,
            detail="Only the session creator or an org admin/manager can manage collaborators",
        )
    if body.access_level not in _VALID_ACCESS_LEVELS:
        raise HTTPException(
            status_code=400,
            detail=f"access_level must be one of {_VALID_ACCESS_LEVELS}",
        )

    row = (
        db.query(SessionCollaborator)
        .filter(
            SessionCollaborator.id == collaborator_id,
            SessionCollaborator.session_id == session.id,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Collaborator not found")

    row.access_level = body.access_level
    db.commit()
    db.refresh(row)
    return _serialize_collaborator(db, row)


@router.delete("/permissions/collaborators/{collaborator_id}")
async def revoke_collaborator(
    session_id: str,
    collaborator_id: int,
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> dict:
    """Soft-revoke a collaborator (sets revoked_at). Same auth as POST."""
    session = _get_session_by_str_id(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if not _can_manage_collaborators(db, current_user, session):
        raise HTTPException(
            status_code=403,
            detail="Only the session creator or an org admin/manager can manage collaborators",
        )

    row = (
        db.query(SessionCollaborator)
        .filter(
            SessionCollaborator.id == collaborator_id,
            SessionCollaborator.session_id == session.id,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Collaborator not found")

    row.revoked_at = datetime.now(timezone.utc)
    db.commit()
    return {"status": "revoked", "collaborator_id": collaborator_id}


class RedeemTokenRequest(BaseModel):
    token: str


class RedeemTokenResponse(BaseModel):
    valid: bool
    session_id: Optional[str] = None
    session_db_id: Optional[int] = None
    access_level: Optional[AccessLevel] = None
    reason: Optional[str] = None
    bound_user_id: Optional[int] = None


@router.post(
    "/permissions/redeem",
    response_model=RedeemTokenResponse,
)
async def redeem_magic_link(
    payload: RedeemTokenRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Auth'd redemption of a magic-link share token. The frontend calls
    this after Keycloak login on the shared-session landing page.

    Binds the current user to the collaborator row (so subsequent
    requests authorize through user_id rather than relying on the
    token-in-URL pattern) and returns the session id + granted access
    level. Idempotent.
    """
    import uuid as _uuid

    try:
        token_uuid = _uuid.UUID(payload.token)
    except (ValueError, AttributeError):
        return RedeemTokenResponse(valid=False, reason="invalid token format")

    row = (
        db.query(SessionCollaborator)
        .filter(SessionCollaborator.token == token_uuid)
        .first()
    )
    if not row:
        return RedeemTokenResponse(valid=False, reason="token not found")
    if not _is_collaborator_active(row):
        reason = "revoked" if row.revoked_at is not None else "expired"
        return RedeemTokenResponse(valid=False, reason=reason)

    session = (
        db.query(DBRecordingSession)
        .filter(DBRecordingSession.id == row.session_id)
        .first()
    )
    if not session:
        return RedeemTokenResponse(valid=False, reason="session not found")

    # Optional email match check. If the original invite was scoped to a
    # specific email, refuse to bind a different user. Stops a leaked
    # token from being redeemed by anyone other than the invitee.
    if row.email and current_user.email and row.email.lower() != current_user.email.lower():
        return RedeemTokenResponse(
            valid=False,
            reason="this invitation was sent to a different email address",
        )

    # Bind the user, mark accepted.
    if row.user_id != current_user.id:
        row.user_id = current_user.id
    if not row.accepted_at:
        from datetime import datetime, timezone as _tz
        row.accepted_at = datetime.now(_tz.utc)
    db.commit()

    return RedeemTokenResponse(
        valid=True,
        session_id=session.session_id or str(session.id),
        session_db_id=session.id,
        access_level=row.access_level,
        bound_user_id=current_user.id,
    )


@public_router.get(
    "/permissions/access",
    response_model=AccessTokenOut,
)
async def resolve_access_token(
    token: str = Query(..., description="Magic-link share token"),
    db: Session = Depends(get_db),
) -> AccessTokenOut:
    """Resolve a magic-link share token. Public — no auth required.

    Returns whether the token is valid and, if so, the session.id so the
    share-link flow can route the viewer into the correct shared-session
    view.
    """
    try:
        token_uuid = uuid.UUID(token)
    except (ValueError, AttributeError):
        return AccessTokenOut(valid=False, reason="invalid token format")

    row = (
        db.query(SessionCollaborator)
        .filter(SessionCollaborator.token == token_uuid)
        .first()
    )
    if not row:
        return AccessTokenOut(valid=False, reason="token not found")
    if not _is_collaborator_active(row):
        reason = (
            "revoked"
            if row.revoked_at is not None
            else "expired"
        )
        return AccessTokenOut(valid=False, reason=reason)

    session = (
        db.query(DBRecordingSession)
        .filter(DBRecordingSession.id == row.session_id)
        .first()
    )
    if not session:
        return AccessTokenOut(valid=False, reason="session not found")

    return AccessTokenOut(
        valid=True,
        session_id=session.session_id or str(session.id),
        session_db_id=session.id,
        access_level=row.access_level,  # type: ignore[arg-type]
    )
