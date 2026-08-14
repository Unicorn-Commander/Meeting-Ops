"""Who may see a meeting.

Meeting-Ops has always answered "may this user read this session?" with a
single question: *are you a member of the organization that owns it?*  That
is broader than what a meeting actually is — being in a company is not the
same as having been in the room.

This module adds the missing half — the people who were actually in the
meeting are readers of it — without taking the old answer away from anyone.
Which rule applies is an explicit per-organization setting stored under
``organizations.settings["session_visibility"]``:

``organization``
    Every member of the owning organization may read every session in it.
    Participants additionally qualify, which only matters for a participant
    who is not otherwise a plain member.  **This is the default and is
    byte-for-byte today's behaviour.**

``participants``
    Only the session's creator, someone recorded as a participant, an
    explicit collaborator, or an org owner/admin/manager may read it.  Plain
    members and viewers who were not in the meeting are refused.

Unset means ``organization``, so enabling participant identity never
silently removes access from a live deployment.  ``MEETING_OPS_SESSION_
VISIBILITY`` sets the fleet-wide default for orgs that have not chosen.

Identity, and why an email is not automatically an identity
-----------------------------------------------------------
``recording_sessions.participants`` is a descriptive JSONB roster used for
Contact-Ops federation.  Anyone who can edit a session can type any address
into it, so an entry is a *claim*, not a credential.  Three rules keep a
claim from becoming access:

1. The account must have **verified** that address (``users.is_verified``)
   and be active.  Registering someone else's address grants nothing until
   the address is proven, and this deployment's accounts are provisioned
   through Keycloak rather than self-asserted.
2. A ``user_id`` stamped onto an entry is only ever written server-side,
   from an already-authenticated identity — never from a request body.
3. The match is consulted only for a session the caller's own organization
   owns.  A participant entry can widen access *within* a tenant; it can
   never reach across one.  Callers must keep their organization filter.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Iterable, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Setting key on organizations.settings (a JSON column that already exists).
SESSION_VISIBILITY_KEY = "session_visibility"

#: Every member of the owning org may read every session. Today's behaviour.
VISIBILITY_ORGANIZATION = "organization"
#: Only the creator, a participant, a collaborator, or an org admin may read.
VISIBILITY_PARTICIPANTS = "participants"

VALID_SESSION_VISIBILITIES = (VISIBILITY_ORGANIZATION, VISIBILITY_PARTICIPANTS)

#: Roles that keep blanket access under ``participants``. Tenant
#: administrators must still be able to administer meetings they were not
#: in (retention, deletion, support, moving a session between orgs), so
#: tightening visibility deliberately does not lock them out.
ADMIN_ROLES = frozenset({"owner", "admin", "manager"})

#: Roles that get blanket access only under ``organization``.
MEMBER_ROLES = frozenset({"member", "user"})
VIEWER_ROLES = frozenset({"viewer"})


def default_session_visibility() -> str:
    """Fleet-wide default for organizations that have not chosen one.

    Anything unrecognised falls back to ``organization`` — an unreadable
    setting must never be the reason someone loses access to their data.
    """
    raw = (os.getenv("MEETING_OPS_SESSION_VISIBILITY") or "").strip().lower()
    if not raw:
        return VISIBILITY_ORGANIZATION
    if raw in VALID_SESSION_VISIBILITIES:
        return raw
    logger.warning(
        "Ignoring unrecognised MEETING_OPS_SESSION_VISIBILITY=%r; "
        "falling back to %s",
        raw,
        VISIBILITY_ORGANIZATION,
    )
    return VISIBILITY_ORGANIZATION


def visibility_for_organization(organization: Any) -> str:
    """Read the effective visibility mode off a loaded Organization row."""
    if organization is None:
        return default_session_visibility()
    settings = getattr(organization, "settings", None)
    if isinstance(settings, dict):
        raw = settings.get(SESSION_VISIBILITY_KEY)
        if isinstance(raw, str):
            normalized = raw.strip().lower()
            if normalized in VALID_SESSION_VISIBILITIES:
                return normalized
            if normalized:
                logger.warning(
                    "Organization %s has unrecognised %s=%r; falling back to %s",
                    getattr(organization, "id", "?"),
                    SESSION_VISIBILITY_KEY,
                    raw,
                    default_session_visibility(),
                )
    return default_session_visibility()


def visibility_for_org_id(db: Session, organization_id: Optional[int]) -> str:
    """Load an organization by id and return its visibility mode.

    Uses ``Session.get`` rather than a filtered query so that a request which
    already loaded its active organization — which the auth dependency does —
    answers from the identity map instead of emitting another SELECT on the
    hottest read path. It still reflects an org mutated in this session,
    because ``get`` refreshes an expired instance.
    """
    if organization_id is None:
        return default_session_visibility()
    from auth.models import Organization

    return visibility_for_organization(db.get(Organization, organization_id))


def normalize_identity_email(value: Any) -> Optional[str]:
    """Casefold an address for comparison, or None if it is not usable.

    Empty strings collapse to None so a roster entry with no email can never
    match an account with no email.
    """
    if not isinstance(value, str):
        return None
    normalized = value.strip().casefold()
    return normalized or None


def _entries(session: Any) -> Iterable[dict]:
    raw = getattr(session, "participants", None)
    if not isinstance(raw, list):
        return ()
    return (entry for entry in raw if isinstance(entry, dict))


def participant_emails(session: Any) -> set[str]:
    """Normalized addresses claimed by the session's participant roster."""
    found: set[str] = set()
    for entry in _entries(session):
        email = normalize_identity_email(entry.get("email"))
        if email:
            found.add(email)
    return found


def participant_user_ids(session: Any) -> set[int]:
    """Meeting-Ops user ids stamped onto the roster by a server-side writer."""
    found: set[int] = set()
    for entry in _entries(session):
        raw = entry.get("user_id")
        if isinstance(raw, bool):
            # bool is an int subclass; a stray True must not become user 1.
            continue
        if isinstance(raw, int):
            found.add(raw)
        elif isinstance(raw, str) and raw.strip().isdigit():
            found.add(int(raw.strip()))
    return found


def user_is_participant(session: Any, user: Any) -> bool:
    """Was ``user`` one of the people recorded in this meeting?

    A stamped ``user_id`` is authoritative because only server-side writers
    produce one.  An ``email`` match additionally requires the account to
    have verified that address, so an unverified signup claiming somebody
    else's address is refused.

    This never checks the organization — callers must have already
    established that the user may act in the session's tenant.
    """
    if session is None or user is None:
        return False
    if not getattr(user, "is_active", True):
        return False

    user_id = getattr(user, "id", None)
    if isinstance(user_id, int) and user_id in participant_user_ids(session):
        return True

    if not getattr(user, "is_verified", False):
        return False
    email = normalize_identity_email(getattr(user, "email", None))
    if not email:
        return False
    return email in participant_emails(session)


def _is_postgres(db: Session) -> bool:
    bind = db.get_bind() if db is not None else None
    return bind is not None and bind.dialect.name == "postgresql"


def _roster_entries(db: Session):
    """The roster expanded to one row per entry, correlated to the session.

    ``joins_implicitly`` keeps this a lateral over ``participants``; the
    ``correlate`` at each call site is what stops the planner re-adding
    recording_sessions to the subquery FROM (which would be a cartesian
    product matching every row whenever ANY row matched).
    """
    from sqlalchemy import func

    from database.models import RecordingSession

    expand = func.jsonb_array_elements if _is_postgres(db) else func.json_each
    return expand(RecordingSession.participants).table_valued(
        "value", joins_implicitly=True
    )


def _roster_user_id_clause(db: Session, user_id: int):
    """Some roster entry carries this Meeting-Ops user id.

    Postgres uses JSONB containment so the GIN index from alembic 041 does
    the work — the same index-assisted pattern ``api.federation_meetings``
    uses. This is the fast path, and the one server-stamped identities take.
    """
    from sqlalchemy import func, literal, select

    from database.models import RecordingSession

    if _is_postgres(db):
        return RecordingSession.participants.contains([{"user_id": user_id}])
    entries = _roster_entries(db)
    return (
        select(literal(1))
        .select_from(entries)
        .where(func.json_extract(entries.c.value, "$.user_id") == user_id)
        .correlate(RecordingSession)
        .exists()
    )


def _roster_email_clause(db: Session, email: str):
    """Some roster entry names this address, compared case-insensitively.

    Addresses are stored exactly as whoever typed them, so this cannot be
    JSONB containment: ``@>`` is an exact match, and it would silently miss
    ``Bob@Example.com`` for ``bob@example.com``.  Matching the raw and folded
    spellings instead would still miss every other casing, and the detail
    check in :func:`user_is_participant` folds — so the list would quietly
    hide a meeting the session page happily opens.  Correctness wins over the
    index here; the indexed path is the ``user_id`` stamp above.
    """
    from sqlalchemy import func, literal, select

    from database.models import RecordingSession

    entries = _roster_entries(db)
    if _is_postgres(db):
        stored = entries.c.value.op("->>")(literal("email"))
    else:
        stored = func.json_extract(entries.c.value, "$.email")
    return (
        select(literal(1))
        .select_from(entries)
        .where(func.lower(stored) == email)
        .correlate(RecordingSession)
        .exists()
    )


def participant_match_clause(db: Session, user: Any):
    """A SQL predicate selecting sessions whose roster names ``user``.

    Mirrors :func:`user_is_participant` for list queries.  Returns None when
    the user has no usable identity at all.
    """
    predicates = []
    user_id = getattr(user, "id", None)
    if isinstance(user_id, int):
        predicates.append(_roster_user_id_clause(db, user_id))
    if getattr(user, "is_verified", False):
        email = normalize_identity_email(getattr(user, "email", None))
        if email:
            predicates.append(_roster_email_clause(db, email))
    if not predicates:
        return None
    return or_(*predicates)


def visible_session_clause(
    db: Session,
    organization_id: Optional[int],
    user: Any,
    role: Optional[str] = None,
):
    """Extra predicate restricting a list query to what ``user`` may read.

    Returns None when no restriction applies — under the default
    ``organization`` mode, for superusers, and for org owners/admins/managers
    — so callers add nothing to their query and behaviour is unchanged.

    Callers must still apply their own ``organization_id`` filter; this only
    narrows within a tenant.
    """
    from database.models import RecordingSession

    if getattr(user, "is_superuser", False):
        return None
    if visibility_for_org_id(db, organization_id) != VISIBILITY_PARTICIPANTS:
        return None
    if role and role.strip().lower() in ADMIN_ROLES:
        return None

    predicates = []
    user_id = getattr(user, "id", None)
    if isinstance(user_id, int):
        predicates.append(RecordingSession.user_id == user_id)
    participant_clause = participant_match_clause(db, user)
    if participant_clause is not None:
        predicates.append(participant_clause)

    collaborator_clause = _collaborator_clause(user)
    if collaborator_clause is not None:
        predicates.append(collaborator_clause)

    if not predicates:
        # A user with no identity at all sees nothing rather than everything.
        return RecordingSession.id == -1
    return or_(*predicates)


def _collaborator_clause(user: Any):
    """Sessions this user holds an active explicit collaborator grant on.

    Mirrors ``api.session_permissions._is_collaborator_active`` so the list
    and the detail view agree about which grants are still live.
    """
    from datetime import datetime, timezone

    from sqlalchemy import select

    from database.models import RecordingSession, SessionCollaborator

    user_id = getattr(user, "id", None)
    if not isinstance(user_id, int):
        return None
    now = datetime.now(timezone.utc)
    grants = (
        select(SessionCollaborator.session_id)
        .where(SessionCollaborator.user_id == user_id)
        .where(SessionCollaborator.revoked_at.is_(None))
        .where(
            or_(
                SessionCollaborator.expires_at.is_(None),
                SessionCollaborator.expires_at > now,
            )
        )
    )
    return RecordingSession.id.in_(grants)
