"""Resolve an unambiguous session-id prefix for MCP tools.

Meeting notes name a recording by the first 8 hex characters of
``RecordingSession.session_id`` (``str(uuid.uuid4())``, lowercase, hyphenated).
The exact API path matches that column in full, or the integer primary key,
and filters with ``organization_id == <caller's active org>`` — the same
predicate as ``api.simple_recording_db._scoped_session_query``. A prefix is
resolved with that predicate and a bound ``LIKE 'prefix%'``, fetching at most
two ``session_id`` values so a transcript row is never loaded just to see
whether the prefix is unique.

Full UUIDs and integer ids are not prefixes. Callers leave those on the
existing exact path, including the API's cross-org access check.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from database.models import RecordingSession


# Two rows are enough to tell unique from ambiguous. The match count in the
# error is a separate scalar, so "n matches" stays exact when n > 2.
PREFIX_ROW_CAP = 2

_HEX_AND_DASHES = re.compile(r"^[0-9a-fA-F-]+$")
_UUID_GROUPS = (8, 4, 4, 4, 12)


@dataclass(frozen=True)
class SessionPrefixResolution:
    """Id to place on the existing API path, plus an ambiguous-prefix error."""

    session_id: str
    error: str | None = None


def _hex_digits(token: str) -> str:
    return re.sub(r"[^0-9a-fA-F]", "", token).lower()


def _is_complete_uuid(token: str) -> bool:
    """True for a 32-hex UUID, with or without the canonical dashes."""
    if not _HEX_AND_DASHES.fullmatch(token):
        return False
    hex_digits = _hex_digits(token)
    if len(hex_digits) != 32:
        return False
    try:
        return uuid.UUID(hex_digits).hex == hex_digits
    except ValueError:
        return False


def is_session_id_prefix(session_id: str) -> bool:
    """True for an 8–31 hex-character prefix, dashes ignored.

    A complete UUID and an all-digit integer id are exact-path ids, not
    prefixes. ``12345678`` stays an integer even though it is 8 hex digits.
    """
    if not isinstance(session_id, str):
        return False
    token = session_id.strip()
    if not token or not _HEX_AND_DASHES.fullmatch(token):
        return False
    if _is_complete_uuid(token) or token.isdigit():
        return False
    hex_len = len(_hex_digits(token))
    return 8 <= hex_len <= 31


def session_id_like_pattern(session_id: str) -> str:
    """Bound ``LIKE`` pattern in the stored ``8-4-4-4-12`` shape.

    ``abcdef12abcd`` becomes ``abcdef12-abcd%`` so it matches
    ``str(uuid.uuid4())``. The hex itself contains no LIKE wildcards; ``%``
    and ``_`` are escaped anyway.
    """
    grouped = _group_uuid_prefix(_hex_digits(session_id.strip()))
    escaped = grouped.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return escaped + "%"


def _group_uuid_prefix(hex_digits: str) -> str:
    parts: list[str] = []
    index = 0
    for size in _UUID_GROUPS:
        if index >= len(hex_digits):
            break
        parts.append(hex_digits[index:index + size])
        index += size
    return "-".join(parts)


def prefix_lookup_query(db: Session, organization_id: int, like_pattern: str):
    """``organization_id = :org AND session_id LIKE :prefix`` capped at 2 rows."""
    return (
        db.query(RecordingSession.session_id)
        .filter(
            RecordingSession.organization_id == organization_id,
            RecordingSession.session_id.like(like_pattern, escape="\\"),
        )
        .limit(PREFIX_ROW_CAP)
    )


def _prefix_match_count(db: Session, organization_id: int, like_pattern: str) -> int:
    counted = (
        db.query(func.count(RecordingSession.id))
        .filter(
            RecordingSession.organization_id == organization_id,
            RecordingSession.session_id.like(like_pattern, escape="\\"),
        )
        .scalar()
    )
    return int(counted or 0)


def ambiguous_prefix_message(prefix: str, matches: int) -> str:
    return (
        f"ambiguous session id prefix '{prefix}': {matches} matches, "
        "pass the full id"
    )


def resolve_session_id_prefix(
    db: Session,
    organization_id: int,
    session_id: str,
) -> SessionPrefixResolution:
    """Resolve ``session_id`` inside one organization.

    * Not a prefix (full UUID, integer, anything else) — returned unchanged,
      and ``db`` is not queried.
    * 0 matches — original id unchanged, so the caller keeps the API's
      existing not-found text.
    * 1 match — that row's ``session_id``.
    * More than one — ``error`` is the ambiguous-prefix message. The original
      id is left in place and must not be sent to the API.
    """
    if not is_session_id_prefix(session_id):
        return SessionPrefixResolution(session_id=session_id)

    pattern = session_id_like_pattern(session_id)
    rows = prefix_lookup_query(db, organization_id, pattern).all()
    if len(rows) == 0:
        return SessionPrefixResolution(session_id=session_id)
    if len(rows) == 1:
        found = rows[0][0]
        if not found:
            return SessionPrefixResolution(session_id=session_id)
        return SessionPrefixResolution(session_id=str(found))

    shown = session_id.strip()
    return SessionPrefixResolution(
        session_id=session_id,
        error=ambiguous_prefix_message(shown, _prefix_match_count(db, organization_id, pattern)),
    )
