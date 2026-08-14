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

from auth.models import Organization
from database.models import RecordingSession, SessionCollaborator

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


def participant_session_ids(
    db: Session,
    organization_id: Optional[int],
    user: Any,
) -> list[int]:
    """Ids of sessions in this org whose roster names ``user``.

    Evaluated in Python, over one org-scoped query, deliberately.

    The alternative is a roster predicate in SQL, which needs a table-valued
    function to expand the JSONB array (``json_each`` /
    ``jsonb_array_elements``).  Every correlated and uncorrelated form of that
    was found to leak the function into the enclosing query's FROM once the
    clause is OR'd into a larger WHERE — SQLAlchemy renders ``FROM
    recording_sessions, recording_sessions``, which silently matches EVERY row
    (a cartesian product) on Postgres and raises "ambiguous column name" on
    SQLite.  A predicate whose correctness depends on what else happens to be
    in the query is the wrong shape for an access-control check.

    Doing it here also makes divergence impossible: the list and the detail
    view call the same :func:`user_is_participant`, so a meeting can never be
    readable but unlistable (or worse, listable but unreadable).

    The cost is one scan of the organization's sessions per list request, and
    only when that organization has opted into ``participants`` visibility —
    the default returns before reaching this.  That is fine at current sizes
    and is the known ceiling: the way to raise it is to stamp ``user_id``
    onto roster entries at write time everywhere and index that, at which
    point this becomes an indexed lookup.
    """
    if organization_id is None:
        return []
    rows = (
        db.query(RecordingSession.id, RecordingSession.participants)
        .filter(RecordingSession.organization_id == organization_id)
        .all()
    )

    class _Roster:
        __slots__ = ("participants",)

        def __init__(self, participants):
            self.participants = participants

    return [
        row_id
        for row_id, participants in rows
        if user_is_participant(_Roster(participants), user)
    ]


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
    roster_ids = participant_session_ids(db, organization_id, user)
    if roster_ids:
        predicates.append(RecordingSession.id.in_(roster_ids))

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
