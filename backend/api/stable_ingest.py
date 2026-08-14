"""Durable, tenant-scoped transcript ingestion from Unicorn Stable."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from auth.config import auth_config
from auth.models import Organization, PersonalAccessToken, User, UserOrganization
from auth.organization import ActiveOrganization, normalize_org_slug
from auth.pat import TOKEN_PREFIX as PAT_PREFIX, resolve_pat_record
from auth.utils import check_permission
from database.database import get_db
from database.models import RecordingSession, Transcription

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/sessions", tags=["stable-ingest"])

# Must remain one of the values accepted by the PostgreSQL
# ck_recording_sessions_mode constraint. Stable provenance is carried by
# source_type/external_source rather than inventing a new lifecycle mode.
STABLE_INGEST_SESSION_MODE = "upload"

STABLE_SOURCE = "unicorn-stable"

DEFAULT_COALESCE_GRACE_MINUTES = 10


class StableTranscriptLine(BaseModel):
    participant_id: str = Field(min_length=1, max_length=256)
    name: str = Field(default="", max_length=256)
    text: str = Field(min_length=1, max_length=8000)
    ts: int = Field(ge=0, description="Unix epoch milliseconds")
    is_final: bool = True
    segment_id: Optional[str] = Field(default=None, max_length=256)
    source: Literal["local_mic", "agent_stt", "agent", "unknown"] = "unknown"
    identity_verification: Literal[
        "stable_room_member", "stable_known_agent"
    ] = "stable_room_member"
    identity_verified: Literal[True] = True
    content_verification: Literal[
        "client_caption",
        "agent_stt",
        "agent_generated_caption",
        "unverified",
    ] = "unverified"


class StableTranscriptIngest(BaseModel):
    source: str = Field(pattern=r"^unicorn-stable$")
    export_id: str = Field(min_length=1, max_length=128)
    exported_at: datetime
    room_id: str = Field(min_length=1, max_length=128)
    room_name: str = Field(min_length=1, max_length=256)
    livekit_room_name: Optional[str] = Field(default=None, max_length=256)
    call_started_at: Optional[datetime] = None
    call_ended_at: Optional[datetime] = None
    label: Optional[str] = Field(default=None, max_length=256)
    meeting_ops_session_id: Optional[str] = Field(default=None, max_length=128)
    exporter: dict[str, Any] = Field(default_factory=dict)
    line_count: int = Field(ge=0, le=2000)
    lines: list[StableTranscriptLine] = Field(min_length=1, max_length=2000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class StableTranscriptIngestResponse(BaseModel):
    ok: bool = True
    created: bool
    session_id: str
    session_url: str
    external_id: str
    line_count: int


def _utc(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _response(row: RecordingSession, *, created: bool) -> StableTranscriptIngestResponse:
    public_id = row.session_id or str(row.id)
    return StableTranscriptIngestResponse(
        created=created,
        session_id=public_id,
        session_url=f"{auth_config.APP_BASE_URL}/sessions/{public_id}",
        external_id=row.external_id or "",
        line_count=len((row.transcript_diarized or {}).get("segments", [])),
    )


def _payload_sha256(body: StableTranscriptIngest) -> str:
    canonical = json.dumps(
        body.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _stored_payload_sha256(row: RecordingSession) -> Optional[str]:
    metadata = row.processing_metadata if isinstance(row.processing_metadata, dict) else {}
    federation = metadata.get("federation")
    if not isinstance(federation, dict):
        return None
    value = federation.get("payload_sha256")
    return value if isinstance(value, str) else None


# ---------------------------------------------------------------------
# Meeting identity
#
# ``external_id`` is the identity of one EXPORT. It cannot be the identity of
# the meeting, because Stable exports per participant browser: the payload it
# hashes into export_id includes that browser's own ``call_started_at`` (when
# *they* joined) and ``call_ended_at`` (when *they* hung up), plus whatever
# transcript lines that browser happened to receive. Two people leaving one
# call one millisecond apart therefore produce two different export_ids —
# reliably, not as a race — and before this, two sessions and two summaries.
#
# What actually identifies a meeting, in preference order:
#   1. ``meeting_ops_session_id`` — an explicit upstream statement of "this is
#      that meeting". Nothing sends it today, but it is in the contract, and
#      honouring it means Stable can be fixed to send one without a second
#      change here.
#   2. The room plus the call's time window. ``room_id`` is Stable's
#      persistent room UUID, so it identifies the room and never the call;
#      the call is the room *and* when it happened. Windows from one call
#      overlap (everyone was in it at once) while windows from a later call
#      in the same room do not.
# ---------------------------------------------------------------------


def _coalesce_grace() -> timedelta:
    """Slack added to a call window before testing for overlap.

    Covers clock skew between participants' browsers and the case where one
    person's window is strictly inside another's.
    """
    raw = os.getenv("STABLE_CALL_COALESCE_GRACE_MINUTES")
    try:
        minutes = int(raw) if raw is not None and raw.strip() else (
            DEFAULT_COALESCE_GRACE_MINUTES
        )
    except (TypeError, ValueError):
        logger.warning(
            "Ignoring unparsable STABLE_CALL_COALESCE_GRACE_MINUTES=%r", raw
        )
        minutes = DEFAULT_COALESCE_GRACE_MINUTES
    return timedelta(minutes=max(0, minutes))


def _naive_utc(value: datetime) -> datetime:
    """started_at/ended_at are TIMESTAMP WITHOUT TIME ZONE; compare in the
    same shape we store so the window test means the same thing on Postgres
    and on the SQLite the test suite uses."""
    aware = _utc(value)
    return aware.replace(tzinfo=None) if aware is not None else value


def _explicit_meeting_key(body: StableTranscriptIngest) -> Optional[str]:
    value = (body.meeting_ops_session_id or "").strip()
    return f"stable:session:{value}" if value else None


def _anchor_meeting_key(room_id: str, started: datetime) -> str:
    """Identity for the first export of a call we have not seen before."""
    return f"stable:room:{room_id}:{_naive_utc(started).isoformat()}"


def _lock_room(db: Session, org_id: int, room_id: str) -> None:
    """Serialize concurrent exports of one room within this transaction.

    Two participants hanging up simultaneously would otherwise both miss the
    window lookup and both insert. The unique constraint on
    (organization_id, meeting_key) catches the explicit-key case, but the
    window case has no single key to collide on, so it needs a lock.

    No-op outside Postgres — the SQLite test database serializes writers.
    """
    bind = db.get_bind()
    if bind is None or bind.dialect.name != "postgresql":
        return
    digest = hashlib.blake2b(
        f"{org_id}:{room_id}".encode("utf-8"), digest_size=8
    ).digest()
    db.execute(
        text("SELECT pg_advisory_xact_lock(:key)"),
        {"key": int.from_bytes(digest, "big", signed=True)},
    )


def _find_meeting_by_key(
    db: Session, org_id: int, meeting_key: str
) -> Optional[RecordingSession]:
    return (
        db.query(RecordingSession)
        .filter(
            RecordingSession.organization_id == org_id,
            RecordingSession.meeting_key == meeting_key,
        )
        .first()
    )


def _find_meeting_by_window(
    db: Session,
    org_id: int,
    room_id: str,
    started: datetime,
    ended: datetime,
) -> Optional[RecordingSession]:
    """The already-ingested call in this room whose window overlaps ours.

    Overlap, not equality: participant A's window is [A joined, A left] and
    B's is [B joined, B left]; both were in the same call, so the intervals
    intersect. A different call in the same room later that day does not.
    """
    grace = _coalesce_grace()
    low = _naive_utc(started) - grace
    high = _naive_utc(ended) + grace
    return (
        db.query(RecordingSession)
        .filter(
            RecordingSession.organization_id == org_id,
            RecordingSession.external_source == STABLE_SOURCE,
            RecordingSession.external_room_id == room_id,
            RecordingSession.started_at <= high,
            RecordingSession.ended_at >= low,
        )
        .order_by(
            RecordingSession.started_at.asc(),
            RecordingSession.id.asc(),
        )
        .first()
    )


def _resolve_meeting(
    db: Session,
    org_id: int,
    body: StableTranscriptIngest,
    started: datetime,
    ended: datetime,
) -> tuple[Optional[RecordingSession], str]:
    """Return (existing session for this meeting or None, meeting_key)."""
    explicit = _explicit_meeting_key(body)
    if explicit:
        return _find_meeting_by_key(db, org_id, explicit), explicit
    existing = _find_meeting_by_window(db, org_id, body.room_id, started, ended)
    if existing is not None and existing.meeting_key:
        return existing, existing.meeting_key
    return existing, _anchor_meeting_key(body.room_id, started)


# ---------------------------------------------------------------------
# Participant identity
# ---------------------------------------------------------------------


def _resolve_exporter_participant(
    db: Session,
    org_id: int,
    exporter: dict[str, Any],
) -> Optional[dict[str, Any]]:
    """Turn Stable's exporter block into a participant, with an identity when
    one can be established.

    Stable authenticates the exporting participant against the same Keycloak
    realm this deployment provisions Meeting-Ops accounts from, and the ingest
    PAT binds the organization, so the username on this payload is a
    server-to-server assertion rather than a client claim. It is still only
    honoured when it resolves to an ACTIVE account that is already a member of
    the ingesting organization — a roster entry must never be able to reach
    across tenants.

    When no account matches, the participant is still recorded, just without
    an identity: descriptive, and granting nothing.
    """
    if not isinstance(exporter, dict):
        return None
    participant_id = str(exporter.get("participant_id") or "").strip()
    username = str(exporter.get("username") or "").strip()
    display_name = str(exporter.get("display_name") or "").strip()
    if not participant_id and not username:
        return None

    entry: dict[str, Any] = {
        "id": participant_id or f"stable-user:{username.casefold()}",
        "name": display_name or username or participant_id,
        "role": "participant",
        "kind": "human",
        "identity_source": "stable_exporter",
    }

    if not username:
        return entry
    account = (
        db.query(User)
        .filter(
            func.lower(User.username) == username.casefold(),
            User.is_active.is_(True),
        )
        .first()
    )
    if account is None:
        return entry
    membership = (
        db.query(UserOrganization)
        .filter(
            UserOrganization.user_id == account.id,
            UserOrganization.organization_id == org_id,
        )
        .first()
    )
    if membership is None:
        logger.info(
            "stable ingest: exporter %r resolved to a user outside org %s; "
            "recording them descriptively without access",
            username,
            org_id,
        )
        return entry
    entry["user_id"] = account.id
    entry["email"] = account.email
    return entry


_IDENTITY_FIELDS = ("user_id", "email")


def _fold_exporter(
    roster: list[dict[str, Any]],
    entry: Optional[dict[str, Any]],
    exporter: dict[str, Any],
) -> list[dict[str, Any]]:
    """Add the exporter to the roster without duplicating them.

    Stable sends the exporter's ``participant_id`` when it has one, and then
    the ids line up and the ordinary merge does the right thing. When it does
    not, the username or display name usually already names somebody on a
    line — appending a second entry would double-count one human and give
    them two roster identities. So match by id or name first, and only add a
    new entry when the exporter genuinely is not on the roster yet.

    When the exporter is already present and no account resolved, nothing is
    learned and the roster is left exactly as it was.
    """
    if entry is None:
        return roster
    if str(exporter.get("participant_id") or "").strip():
        return _merge_participants(roster, [entry])

    aliases = {
        value
        for value in (
            str(exporter.get("username") or "").strip().casefold(),
            str(exporter.get("display_name") or "").strip().casefold(),
        )
        if value
    }
    if not aliases:
        return _merge_participants(roster, [entry])

    for index, existing in enumerate(roster):
        known = {
            str(existing.get("id") or "").strip().casefold(),
            str(existing.get("name") or "").strip().casefold(),
        }
        if not (known & aliases):
            continue
        if not (entry.get("user_id") or entry.get("email")):
            return roster
        merged = dict(existing)
        for field in _IDENTITY_FIELDS:
            if entry.get(field) and not merged.get(field):
                merged[field] = entry[field]
        merged["identity_source"] = entry.get("identity_source")
        updated = list(roster)
        updated[index] = merged
        return updated

    return _merge_participants(roster, [entry])


def _merge_participants(
    existing: Any,
    incoming: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Union two rosters on participant id, preserving insertion order.

    An identity already proven by an earlier export is never overwritten or
    blanked by a later one that lacks it — a second exporter's payload does
    not know who the first exporter was.
    """
    merged: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    source = existing if isinstance(existing, list) else []
    for entry in list(source) + list(incoming):
        if not isinstance(entry, dict):
            continue
        key = str(entry.get("id") or "").strip()
        if not key:
            continue
        if key not in merged:
            merged[key] = dict(entry)
            order.append(key)
            continue
        target = merged[key]
        for field, value in entry.items():
            if value in (None, ""):
                continue
            if field in _IDENTITY_FIELDS and target.get(field):
                continue
            target[field] = value
    return [merged[key] for key in order]


def _transcript_line_count(row: RecordingSession) -> int:
    stored = row.transcript_diarized if isinstance(row.transcript_diarized, dict) else {}
    segments = stored.get("segments")
    return len(segments) if isinstance(segments, list) else 0


def _record_export(row: RecordingSession, provenance: dict[str, Any]) -> None:
    """Append this export to the session's federation provenance.

    The first export is described by the ``federation`` block itself; every
    later one is appended to ``federation.exports`` so the row remembers that
    N people delivered this meeting and who they were.
    """
    entry = {
        "export_id": provenance.get("export_id"),
        "exported_at": provenance.get("exported_at"),
        "payload_sha256": provenance.get("payload_sha256"),
        "exporter": provenance.get("exporter"),
    }
    for attr in ("processing_metadata", "extra_data"):
        blob = getattr(row, attr, None)
        blob = dict(blob) if isinstance(blob, dict) else {}
        federation = dict(blob.get("federation") or {})
        exports = [e for e in (federation.get("exports") or []) if isinstance(e, dict)]
        seen = {e.get("export_id") for e in exports}
        if federation.get("export_id"):
            seen.add(federation["export_id"])
        if entry["export_id"] not in seen:
            exports.append(entry)
        federation["exports"] = exports
        blob["federation"] = federation
        setattr(row, attr, blob)
        flag_modified(row, attr)


def _adopt_export(
    db: Session,
    row: RecordingSession,
    *,
    provenance: dict[str, Any],
    roster: list[dict[str, Any]],
    segments: list[dict[str, Any]],
    speakers: list[str],
    plain_text: str,
    started: datetime,
    ended: datetime,
    source: str,
    speaker_count: int,
) -> StableTranscriptIngestResponse:
    """Fold one more export of an already-known meeting into its session.

    Deliberately conservative about content and generous about identity:

    * The roster is always unioned — that is what gives each participant
      access to the single shared session, and it can only add.
    * The call window only ever widens, so a later export of the same call
      still overlaps it.
    * The transcript is replaced only when this export carries strictly more
      lines AND nothing has been summarised yet. A summary that has already
      been generated (or approved for federation) must not silently start
      describing different text.

    Merging two sessions that already exist for one meeting is out of scope;
    this only stops new ones being created.
    """
    merged = _merge_participants(row.participants, roster)
    if merged != (row.participants if isinstance(row.participants, list) else []):
        row.participants = merged
        flag_modified(row, "participants")

    started_naive = _naive_utc(started)
    ended_naive = _naive_utc(ended)
    # Both backends hand these columns back naive, but comparing a naive to an
    # aware datetime raises TypeError, and this is a live ingest path — so
    # normalize whatever the driver returned rather than trusting it.
    stored_start = _naive_utc(row.started_at) if row.started_at else None
    stored_end = _naive_utc(row.ended_at) if row.ended_at else None
    if stored_start is not None:
        started_naive = min(stored_start, started_naive)
    if stored_end is not None:
        ended_naive = max(stored_end, ended_naive)
    row.started_at = started_naive
    row.ended_at = ended_naive
    row.duration = max(0.0, (ended_naive - started_naive).total_seconds())

    if (
        not row.summary
        and not row.final_summary
        and len(segments) > _transcript_line_count(row)
    ):
        row.transcript = plain_text
        row.transcript_simple = plain_text
        row.transcript_diarized = {
            "text": plain_text,
            "segments": segments,
            "speakers": speakers,
            "source": source,
        }
        flag_modified(row, "transcript_diarized")
        # Only a transcript swap may move the diarization cardinality; a
        # participant who exported but never spoke is not a speaker.
        row.speaker_count = speaker_count
        db.query(Transcription).filter(Transcription.session_id == row.id).delete(
            synchronize_session=False
        )
        db.add_all(
            Transcription(
                session_id=row.id,
                text=segment["text"],
                speaker=segment["speaker"],
                start_time=segment["start"],
                end_time=segment["end"],
                confidence=None,
            )
            for segment in segments
        )

    _record_export(row, provenance)
    db.commit()
    db.refresh(row)
    return _response(row, created=False)


@dataclass
class StableIngestPrincipal:
    user: User
    token: PersonalAccessToken
    active_org: ActiveOrganization


def require_stable_ingest_principal(
    request: Request,
    db: Session = Depends(get_db),
) -> StableIngestPrincipal:
    """Authenticate one org-bound Stable integration PAT.

    JWTs, browser cookies, forward-auth identity, and legacy API keys are
    intentionally not considered by this machine-to-machine endpoint.
    """
    authorization = request.headers.get("Authorization") or ""
    scheme, _, plaintext = authorization.partition(" ")
    plaintext = plaintext.strip()
    if (
        scheme.lower() != "bearer"
        or not plaintext
        or not plaintext.startswith(PAT_PREFIX)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A Stable integration PAT is required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = resolve_pat_record(db, plaintext=plaintext)
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid, expired, or revoked integration PAT",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if token.scope != "stable.transcript.ingest" or token.organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="PAT is not authorized for Stable transcript ingestion",
        )

    raw_slug = request.headers.get("X-MeetingOps-Org")
    if not raw_slug or not raw_slug.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-MeetingOps-Org header is required",
        )
    try:
        slug = normalize_org_slug(raw_slug)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-MeetingOps-Org header is invalid",
        )

    organization = (
        db.query(Organization)
        .filter(
            Organization.slug == slug,
            Organization.is_active.is_(True),
        )
        .first()
    )
    if organization is None:
        # Do not reveal inactive organizations or any additional tenant facts.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )
    if token.organization_id != organization.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="PAT is not authorized for this organization",
        )

    current_user = token.user
    membership = (
        db.query(UserOrganization)
        .filter(
            UserOrganization.user_id == current_user.id,
            UserOrganization.organization_id == organization.id,
        )
        .first()
    )
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized for this organization",
        )

    role = "superuser" if current_user.is_superuser else membership.role
    if not check_permission(role, "session.create"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to create sessions in this organization",
        )
    return StableIngestPrincipal(
        user=current_user,
        token=token,
        active_org=ActiveOrganization(
            organization=organization,
            membership=membership,
            role=role,
        ),
    )


@router.post(
    "/ingest",
    response_model=StableTranscriptIngestResponse,
    status_code=status.HTTP_200_OK,
)
async def ingest_stable_transcript(
    body: StableTranscriptIngest,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    principal: StableIngestPrincipal = Depends(require_stable_ingest_principal),
) -> StableTranscriptIngestResponse:
    """Land one Stable export onto the one Meeting-Ops session for its call.

    A call is exported once per participant browser, so this endpoint is
    called N times for an N-person meeting, each time with a different
    ``export_id`` and slightly different content. All N land on the same
    session: the first creates it, the rest are recorded as additional
    exports and additional participants. One meeting, one transcript, one
    summary, readable by everyone who was in it.

    Authentication accepts only an unexpired ``stable.transcript.ingest`` PAT
    bound to the exact organization in ``X-MeetingOps-Org``. Browser identity,
    generic user PATs, JWTs, cookies, and legacy API keys are not accepted.
    """
    if idempotency_key and idempotency_key != body.export_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Idempotency-Key must match export_id",
        )
    if body.line_count != len(body.lines):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="line_count does not match lines",
        )

    current_user = principal.user
    org_id = principal.active_org.organization.id
    payload_sha256 = _payload_sha256(body)
    existing = (
        db.query(RecordingSession)
        .filter(
            RecordingSession.organization_id == org_id,
            RecordingSession.external_source == body.source,
            RecordingSession.external_id == body.export_id,
        )
        .first()
    )
    if existing is not None:
        if _stored_payload_sha256(existing) != payload_sha256:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="export_id was already used for different transcript content",
            )
        return _response(existing, created=False)

    lines = sorted(body.lines, key=lambda line: (line.ts, line.name, line.participant_id))
    first_ms = lines[0].ts
    started = _utc(body.call_started_at) or datetime.fromtimestamp(
        first_ms / 1000, tz=timezone.utc
    )
    ended = _utc(body.call_ended_at) or datetime.fromtimestamp(
        lines[-1].ts / 1000, tz=timezone.utc
    )
    if ended < started:
        ended = started

    speakers: list[str] = []
    participants_by_id: dict[str, dict[str, str]] = {}
    segments: list[dict[str, Any]] = []
    transcript_rows: list[Transcription] = []
    for line in lines:
        speaker = (line.name or line.participant_id).strip()
        if speaker not in speakers:
            speakers.append(speaker)
        participant = participants_by_id.setdefault(
            line.participant_id,
            {
                "id": line.participant_id,
                "name": speaker,
                "role": "agent" if line.source == "agent" else "participant",
                "kind": "agent" if line.source == "agent" else "human",
            },
        )
        if line.source == "agent":
            participant["role"] = "agent"
            participant["kind"] = "agent"
        relative_start = max(0.0, (line.ts - int(started.timestamp() * 1000)) / 1000)
        segment = {
            "start": relative_start,
            "end": relative_start,
            "text": line.text.strip(),
            "speaker": speaker,
            "participant_id": line.participant_id,
            "source": line.source,
            "confidence": None,
            "identity_verification": line.identity_verification,
            "identity_verified": line.identity_verified,
            "content_verification": line.content_verification,
            **({"segment_id": line.segment_id} if line.segment_id else {}),
        }
        segments.append(segment)

    plain_text = "\n\n".join(line.text.strip() for line in lines)
    session_uuid = str(uuid.uuid4())
    provenance = {
        "source": body.source,
        "export_id": body.export_id,
        "exported_at": _utc(body.exported_at).isoformat(),
        "stable_room_id": body.room_id,
        "stable_livekit_room_name": body.livekit_room_name,
        "exporter": body.exporter,
        "metadata": body.metadata,
        "payload_sha256": payload_sha256,
        "ingest_principal": {
            "user_id": current_user.id,
            "pat_id": principal.token.id,
            "scope": principal.token.scope,
            "organization_id": principal.token.organization_id,
        },
        "verification": {
            "speaker_identity": "stable_server_authorized",
            "transcript_text": "unverified",
            "acoustic_confidence": "not_provided",
        },
    }

    # The roster this export can prove: everyone it carries a line for, plus
    # the person whose browser sent it (who is often not in their own lines,
    # and who is the only participant this payload can identify).
    roster = _fold_exporter(
        list(participants_by_id.values()),
        _resolve_exporter_participant(db, org_id, body.exporter),
        body.exporter,
    )

    # Everything from here decides WHICH meeting this export belongs to, so
    # serialize concurrent exports of the same room around it.
    _lock_room(db, org_id, body.room_id)

    # Re-check the export fast path under the lock: a duplicate delivery of
    # the very same export may have committed while we were building.
    existing = (
        db.query(RecordingSession)
        .filter(
            RecordingSession.organization_id == org_id,
            RecordingSession.external_source == body.source,
            RecordingSession.external_id == body.export_id,
        )
        .first()
    )
    if existing is not None:
        if _stored_payload_sha256(existing) != payload_sha256:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="export_id was already used for different transcript content",
            )
        return _response(existing, created=False)

    existing_meeting, meeting_key = _resolve_meeting(
        db, org_id, body, started, ended
    )
    if existing_meeting is not None:
        logger.info(
            "stable ingest: export %s folded into existing meeting %s "
            "(room=%s, org=%s)",
            body.export_id,
            existing_meeting.session_id or existing_meeting.id,
            body.room_id,
            org_id,
        )
        return _adopt_export(
            db,
            existing_meeting,
            provenance=provenance,
            roster=roster,
            segments=segments,
            speakers=speakers,
            plain_text=plain_text,
            started=started,
            ended=ended,
            source=body.source,
            speaker_count=len(participants_by_id),
        )

    row = RecordingSession(
        session_id=session_uuid,
        name=body.label or f"Stable call · {body.room_name}",
        title=body.label or f"Stable call · {body.room_name}",
        description=f"Transcript imported from Unicorn Stable room {body.room_name}.",
        status="completed",
        # Imported transcripts use the existing upload pipeline mode. Stable
        # provenance remains explicit in source_type/external_source; using a
        # new ad-hoc mode would violate ck_recording_sessions_mode in Postgres.
        mode=STABLE_INGEST_SESSION_MODE,
        created_at=_utc(body.exported_at),
        started_at=_naive_utc(started),
        ended_at=_naive_utc(ended),
        meeting_date=started.date(),
        meeting_time=started.timetz().replace(tzinfo=None),
        duration=max(0.0, (ended - started).total_seconds()),
        transcript=plain_text,
        transcript_simple=plain_text,
        transcript_diarized={
            "text": plain_text,
            "segments": segments,
            "speakers": speakers,
            "source": body.source,
        },
        # Display names are not identities: two people may share one. Tenant
        # analytics and diarization cardinality therefore count stable,
        # server-authorized participant IDs.
        speaker_count=len(participants_by_id),
        user_id=current_user.id,
        organization_id=org_id,
        participants=roster,
        source_type="stable",
        external_source=body.source,
        external_id=body.export_id,
        meeting_key=meeting_key,
        external_room_id=body.room_id,
        room_name=body.room_name,
        extra_data={"federation": provenance},
        processing_metadata={"federation": provenance, "processing_complete": True},
    )
    db.add(row)
    try:
        db.flush()
        for segment in segments:
            transcript_rows.append(
                Transcription(
                    session_id=row.id,
                    text=segment["text"],
                    speaker=segment["speaker"],
                    start_time=segment["start"],
                    end_time=segment["end"],
                    confidence=None,
                )
            )
        db.add_all(transcript_rows)
        db.commit()
        db.refresh(row)
    except IntegrityError:
        db.rollback()
        # Either the same export raced us (uq …_external_source_id) or another
        # participant's export claimed the same meeting first
        # (uq …_org_meeting_key). Both mean "the session already exists"; the
        # second additionally means this export still needs to be folded in.
        existing = (
            db.query(RecordingSession)
            .filter(
                RecordingSession.organization_id == org_id,
                RecordingSession.external_source == body.source,
                RecordingSession.external_id == body.export_id,
            )
            .first()
        )
        if existing is not None:
            if _stored_payload_sha256(existing) != payload_sha256:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "export_id was already used for different transcript "
                        "content"
                    ),
                )
            return _response(existing, created=False)

        existing = _find_meeting_by_key(db, org_id, meeting_key)
        if existing is None:
            raise
        return _adopt_export(
            db,
            existing,
            provenance=provenance,
            roster=roster,
            segments=segments,
            speakers=speakers,
            plain_text=plain_text,
            started=started,
            ended=ended,
            source=body.source,
            speaker_count=len(participants_by_id),
        )

    return _response(row, created=True)
