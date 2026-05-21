"""POST /api/simple/recording-sessions/{session_id}/move-org

Reassign a recording session and all of its org-scoped child rows to a
different organization. Used when a user accidentally recorded under
the wrong org, or when a meeting initially recorded personally needs
to move into a work org.

Auth shape:

    - Caller must be admin OR manager in the SOURCE org (the active org),
      OR the session creator, OR a superuser.
    - Caller must be at least a member of the TARGET org.

What moves:

    - recording_sessions.organization_id
    - audio_files.organization_id  (session_id is a string here — matched on
      the legacy session.session_id field)
    - chat_history.organization_id (session_key = session.session_id)
    - action_items.organization_id
    - speaker_session_link.organization_id  (note: speaker_id still refs
      the source-org SpeakerProfile — those become "orphaned" links;
      surfaced in the response as `orphaned_speaker_links` for UI cleanup)
    - upload_jobs.organization_id
    - tts_jobs.organization_id
    - session_attachments.organization_id
    - meeting_digest is NOT updated — digests are time-window summaries
      keyed off (org, period, date); the next digest run for either org
      will regenerate as needed.
    - transcriptions has no organization_id column (inherits via session_id);
      no action needed.
    - Qdrant points: best-effort `set_payload` to update organization_id.
      A failure here is logged but does not roll back — the API call still
      succeeds and the row-level move is preserved. The reindex_all
      surface remains available if a customer needs forced repair.
    - Audit log: one row in audit_logs with action='move_session_org'.

This endpoint is intentionally NOT recursive over the SessionCollaborator
table — magic-link grants are session-scoped (not org-scoped), so the
collaborators list survives the move unchanged. Same for participants
(stored as a JSONB column on the session row).
"""

from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

from auth.dependencies import get_current_organization, get_current_user
from auth.models import (
    AuditLog,
    Organization,
    User,
    UserOrganization,
)
from auth.organization import ActiveOrganization
from database.database import get_db
from database.models import RecordingSession


logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/api/simple/recording-sessions",
    tags=["session-move-org"],
)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class MoveOrgRequest(BaseModel):
    target_organization_id: int = Field(..., gt=0)


class OrphanedSpeakerLink(BaseModel):
    link_id: int
    raw_label: str
    speaker_id: Optional[int] = None
    speaker_display: Optional[str] = None


class MoveOrgResponse(BaseModel):
    session_id: int
    source_organization_id: int
    target_organization_id: int
    moved_counts: dict[str, int]
    orphaned_speaker_links: List[OrphanedSpeakerLink] = Field(default_factory=list)
    qdrant_repointed: bool
    qdrant_error: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_session(
    db: Session, organization_id: int, session_id: str
) -> RecordingSession:
    """Same shape as api.sessions_participants:_resolve_session."""
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


def _source_role_allows_move(
    *,
    session: RecordingSession,
    user: User,
    active_org: ActiveOrganization,
) -> bool:
    """Admin/manager in source org, OR session creator, OR superuser."""
    if getattr(user, "is_superuser", False):
        return True
    role = (
        active_org.user_role or ""
    ).lower() if hasattr(active_org, "user_role") else ""
    if role in {"admin", "manager"}:
        return True
    if session.user_id and session.user_id == user.id:
        return True
    return False


def _target_membership_allows_receive(
    *, db: Session, user: User, target_org_id: int
) -> bool:
    """User must be a member (any role) of the target org. Superuser
    bypasses the check — they can drop a session into any org."""
    if getattr(user, "is_superuser", False):
        return True
    membership = (
        db.query(UserOrganization)
        .filter(
            UserOrganization.user_id == user.id,
            UserOrganization.organization_id == target_org_id,
        )
        .first()
    )
    return membership is not None


# ---------------------------------------------------------------------------
# Qdrant re-tag
# ---------------------------------------------------------------------------


def _retag_qdrant(*, session: RecordingSession, new_org_id: int) -> tuple[bool, Optional[str]]:
    """Best-effort: walk all points with payload.session_id == session.session_id
    and set their organization_id to ``new_org_id``. Uses the lower-level
    ``set_payload`` API so we don't have to re-embed.

    Returns (ok, error). ``ok=False`` does NOT roll back the move —
    the DB-side change is the source of truth; Qdrant is a derived
    index. ``reindex_all`` from the SemanticSearchService remains
    available as a manual repair path.
    """
    try:
        from services.semantic_search_service import semantic_search

        client = semantic_search._get_client()
        if client is None:
            return False, "qdrant client unavailable"

        from qdrant_client.models import (
            Filter,
            FieldCondition,
            MatchValue,
            PayloadSelectorInclude,  # noqa: F401  (used for type hint clarity)
        )

        # Match the writer's id convention — session.session_id (string)
        # is the canonical payload field for the legacy session id; the
        # collection schema in services.semantic_search_service uses
        # ``session_id`` as the payload key, regardless of whether the
        # actual value is the legacy string or the int pk.
        match_value = session.session_id or str(session.id)

        # ``set_payload`` with a points selector that filters by
        # session_id only updates the matching points. No-op when
        # nothing matches (newly-created session with no indexed
        # content yet).
        try:
            # collection name is read off the service module so we
            # follow whatever the service does today.
            from services.semantic_search_service import COLLECTION_NAME
        except Exception:
            COLLECTION_NAME = "meet_chunks"  # legacy fallback

        client.set_payload(
            collection_name=COLLECTION_NAME,
            payload={"organization_id": new_org_id},
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="session_id",
                        match=MatchValue(value=match_value),
                    )
                ],
            ),
        )
        return True, None
    except Exception as e:
        logger.warning(
            "move-org: qdrant retag failed for session=%s: %s",
            session.id,
            e,
        )
        return False, str(e)


# ---------------------------------------------------------------------------
# DB-side cascade
# ---------------------------------------------------------------------------


def _cascade_update(
    *,
    db: Session,
    session: RecordingSession,
    new_org_id: int,
) -> dict[str, int]:
    """Bulk-update organization_id on every org-scoped child row tied
    to this session. Returns a count-per-table dict for the response.

    We use raw SQL with parameter binding for the child tables because:
      1. SQLAlchemy bulk ORM updates trigger N selects on relationship
         backrefs, which we don't need here;
      2. The audio_files table uses a STRING session_id (not int pk),
         which requires a different match key than the rest.

    The ``recording_sessions.organization_id`` flip happens last so a
    failure midway leaves the parent matching its still-correct children
    (the next manual repair can find them via session.session_id).
    """
    counts: dict[str, int] = {}

    # IMPORTANT: order matters — children first, parent last. If we flip
    # the parent's org_id and then a child update fails, the parent is
    # "in" the new org but a child is still "in" the old org, which leaks
    # data to the old org members on any join that goes
    # child -> session -> org.
    pk = session.id
    legacy_sid = session.session_id  # string, used by audio_files/chat_history

    # action_items (integer session_id)
    res = db.execute(
        sa_text(
            "UPDATE action_items SET organization_id = :new_org "
            "WHERE session_id = :sid"
        ),
        {"new_org": new_org_id, "sid": pk},
    )
    counts["action_items"] = res.rowcount or 0

    # audio_files (string session_id — column is String(100))
    if legacy_sid:
        res = db.execute(
            sa_text(
                "UPDATE audio_files SET organization_id = :new_org "
                "WHERE session_id = :sid"
            ),
            {"new_org": new_org_id, "sid": legacy_sid},
        )
        counts["audio_files"] = res.rowcount or 0
    else:
        counts["audio_files"] = 0

    # chat_history (string session_key — same legacy id)
    if legacy_sid:
        res = db.execute(
            sa_text(
                "UPDATE chat_history SET organization_id = :new_org "
                "WHERE session_key = :sid"
            ),
            {"new_org": new_org_id, "sid": legacy_sid},
        )
        counts["chat_history"] = res.rowcount or 0
    else:
        counts["chat_history"] = 0

    # speaker_session_link
    res = db.execute(
        sa_text(
            "UPDATE speaker_session_link SET organization_id = :new_org "
            "WHERE session_id = :sid"
        ),
        {"new_org": new_org_id, "sid": pk},
    )
    counts["speaker_session_link"] = res.rowcount or 0

    # upload_jobs
    res = db.execute(
        sa_text(
            "UPDATE upload_jobs SET organization_id = :new_org "
            "WHERE session_id = :sid"
        ),
        {"new_org": new_org_id, "sid": pk},
    )
    counts["upload_jobs"] = res.rowcount or 0

    # tts_jobs
    res = db.execute(
        sa_text(
            "UPDATE tts_jobs SET organization_id = :new_org "
            "WHERE session_id = :sid"
        ),
        {"new_org": new_org_id, "sid": pk},
    )
    counts["tts_jobs"] = res.rowcount or 0

    # session_attachments
    res = db.execute(
        sa_text(
            "UPDATE session_attachments SET organization_id = :new_org "
            "WHERE session_id = :sid"
        ),
        {"new_org": new_org_id, "sid": pk},
    )
    counts["session_attachments"] = res.rowcount or 0

    # Parent last.
    session.organization_id = new_org_id
    counts["recording_sessions"] = 1

    return counts


def _find_orphaned_speaker_links(
    *,
    db: Session,
    session_pk: int,
    new_org_id: int,
) -> List[OrphanedSpeakerLink]:
    """After the move, any speaker_session_link row whose speaker_id
    points at a SpeakerProfile in the OLD org becomes 'orphaned' — the
    link is still readable from the new org (because we just updated
    speaker_session_link.organization_id), but the SpeakerProfile it
    references belongs to a different org and won't appear in the new
    org's speaker library.

    We DON'T auto-null these (data loss risk) — instead we surface them
    so the UI can show a "needs cleanup" indicator and let the user
    manually re-link or clear them.
    """
    rows = db.execute(
        sa_text(
            """
            SELECT
                ssl.id AS link_id,
                ssl.raw_label,
                ssl.speaker_id,
                sp.display_name AS speaker_display
            FROM speaker_session_link ssl
            LEFT JOIN speaker sp ON sp.id = ssl.speaker_id
            WHERE ssl.session_id = :sid
              AND ssl.speaker_id IS NOT NULL
              AND (sp.organization_id IS NULL OR sp.organization_id != :new_org)
            """
        ),
        {"sid": session_pk, "new_org": new_org_id},
    ).fetchall()

    out: List[OrphanedSpeakerLink] = []
    for r in rows:
        out.append(
            OrphanedSpeakerLink(
                link_id=int(r[0]),
                raw_label=str(r[1]),
                speaker_id=(int(r[2]) if r[2] is not None else None),
                speaker_display=(str(r[3]) if r[3] is not None else None),
            )
        )
    return out


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post(
    "/{session_id}/move-org",
    response_model=MoveOrgResponse,
)
async def move_session_to_org(
    session_id: str,
    payload: MoveOrgRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
):
    source_org_id = active_org.organization.id
    target_org_id = payload.target_organization_id

    if source_org_id == target_org_id:
        raise HTTPException(
            status_code=400,
            detail="Source and target organizations are the same",
        )

    session = _resolve_session(db, source_org_id, session_id)

    if not _source_role_allows_move(
        session=session, user=current_user, active_org=active_org
    ):
        raise HTTPException(
            status_code=403,
            detail=(
                "Must be admin/manager in the source org, the session "
                "creator, or a superuser to move this session"
            ),
        )

    # Target org must exist + be active + caller must be a member.
    target_org = (
        db.query(Organization).filter(Organization.id == target_org_id).first()
    )
    if not target_org:
        raise HTTPException(status_code=404, detail="Target organization not found")
    if not target_org.is_active:
        raise HTTPException(status_code=400, detail="Target organization is not active")
    if not _target_membership_allows_receive(
        db=db, user=current_user, target_org_id=target_org_id
    ):
        raise HTTPException(
            status_code=403,
            detail="You are not a member of the target organization",
        )

    # Cascade move in a single transaction so a child failure rolls back
    # the parent flip too. Bind happens inside _cascade_update.
    try:
        counts = _cascade_update(
            db=db, session=session, new_org_id=target_org_id
        )
        # Audit log row BEFORE commit so it shares the same txn boundary.
        db.add(
            AuditLog(
                user_id=current_user.id,
                organization_id=source_org_id,
                action="move_session_org",
                resource_type="recording_session",
                resource_id=str(session.id),
                ip_address=_client_ip(request),
                user_agent=request.headers.get("user-agent"),
                details={
                    "source_organization_id": source_org_id,
                    "target_organization_id": target_org_id,
                    "session_legacy_id": session.session_id,
                    "moved_counts": counts,
                },
            )
        )
        db.commit()
    except Exception as e:
        db.rollback()
        logger.exception(
            "move-org: cascade failed session=%s source=%s target=%s",
            session.id,
            source_org_id,
            target_org_id,
        )
        raise HTTPException(
            status_code=500, detail=f"Move failed: {e}"
        )

    db.refresh(session)

    orphans = _find_orphaned_speaker_links(
        db=db, session_pk=session.id, new_org_id=target_org_id
    )

    # Qdrant retag — best-effort, post-commit. A failure here is logged
    # and surfaced in the response but does not roll back the SQL move.
    qdrant_ok, qdrant_err = _retag_qdrant(
        session=session, new_org_id=target_org_id
    )

    logger.info(
        "move-org: session=%s moved from org=%s to org=%s by user=%s "
        "qdrant_ok=%s orphans=%d counts=%s",
        session.id,
        source_org_id,
        target_org_id,
        current_user.id,
        qdrant_ok,
        len(orphans),
        counts,
    )

    return MoveOrgResponse(
        session_id=session.id,
        source_organization_id=source_org_id,
        target_organization_id=target_org_id,
        moved_counts=counts,
        orphaned_speaker_links=orphans,
        qdrant_repointed=qdrant_ok,
        qdrant_error=qdrant_err,
    )


def _client_ip(request: Request) -> Optional[str]:
    """Best-effort client IP — same shape used in other auth routes."""
    # Behind oauth2-proxy/Traefik the user-visible IP is in X-Forwarded-For.
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None
