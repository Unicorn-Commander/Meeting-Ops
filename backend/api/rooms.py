"""Conference Room API — Phase 1.

Endpoints for creating and managing physical conference rooms, attaching
audio sources, issuing pairing codes, starting/stopping recordings, and
granting per-room access.

Every endpoint is org-scoped — the active organization comes from
``get_current_organization`` and EVERY query filters by it. ACL checks
augment org membership with per-room grants (admin/member/viewer). The
``can_access_room`` helper is the single authoritative authn/authz call.
"""
from __future__ import annotations

import logging
import re
import secrets
import subprocess
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, desc
from sqlalchemy.orm import Session

from auth.dependencies import get_current_organization, get_current_user
from auth.models import User
from auth.organization import ActiveOrganization
from database.database import get_db
from database.models import RecordingSession
from database.models_rooms import (
    ROOM_HARDWARE_TYPES,
    ROOM_ROLES,
    ROOM_STATUSES,
    ConferenceRoom,
    RoomAcl,
    RoomAudioSource,
    RoomPairingCode,
)


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/rooms", tags=["rooms"])
# Separate router for /api/system/audio-devices so it doesn't collide with
# the rooms prefix routing. Loaded alongside in main.py via router_attr.
system_router = APIRouter(prefix="/api/system", tags=["system"])


# === Pydantic models ====================================================


class RoomCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    location: Optional[str] = Field(default=None, max_length=500)
    default_retention_days: int = Field(default=90, ge=1, le=3650)
    schedule_json: Optional[dict[str, Any]] = None
    legal_hold: bool = False


class RoomUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    location: Optional[str] = Field(default=None, max_length=500)
    status: Optional[str] = None
    default_retention_days: Optional[int] = Field(default=None, ge=1, le=3650)
    schedule_json: Optional[dict[str, Any]] = None
    legal_hold: Optional[bool] = None


class RoomResponse(BaseModel):
    id: str
    organization_id: int
    name: str
    location: Optional[str]
    status: str
    default_retention_days: int
    schedule_json: Optional[dict[str, Any]]
    legal_hold: bool
    created_at: str
    updated_at: str


class AudioSourceCreateRequest(BaseModel):
    hardware_type: str
    device_path: Optional[str] = Field(default=None, max_length=255)
    device_id: Optional[int] = None  # satellite_devices.id
    label: Optional[str] = Field(default=None, max_length=255)
    config_json: Optional[dict[str, Any]] = None


class AudioSourceResponse(BaseModel):
    id: str
    room_id: str
    hardware_type: str
    device_path: Optional[str]
    device_id: Optional[int]
    label: Optional[str]
    status: str
    config_json: Optional[dict[str, Any]]
    created_at: str


class PairingCodeResponse(BaseModel):
    id: str
    room_id: str
    code: str
    expires_at: str
    created_at: str


class PairingRedeemRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6)
    device_id: Optional[int] = None  # satellite_devices.id once Phase 3 wires it


class PairingRedeemResponse(BaseModel):
    room_id: str
    redeemed_at: str


class AclGrantRequest(BaseModel):
    user_id: int
    role: str


class AclResponse(BaseModel):
    id: str
    room_id: str
    user_id: int
    role: str
    created_at: str


class RecordingStartResponse(BaseModel):
    session_id: str
    session_pk: int
    room_id: str
    source_id: Optional[str]
    started_at: str


class RecordingStopResponse(BaseModel):
    session_id: str
    session_pk: int
    stopped_at: str


class AudioDeviceInfo(BaseModel):
    card: int
    device: int
    card_name: str
    card_label: str
    device_name: str
    device_label: str
    device_path: str  # hw:X,Y
    is_usb: bool


# === Conversion helpers =================================================


def _room_to_response(room: ConferenceRoom) -> RoomResponse:
    return RoomResponse(
        id=str(room.id),
        organization_id=room.organization_id,
        name=room.name,
        location=room.location,
        status=room.status,
        default_retention_days=room.default_retention_days,
        schedule_json=room.schedule_json,
        legal_hold=bool(room.legal_hold),
        created_at=room.created_at.isoformat() if room.created_at else "",
        updated_at=room.updated_at.isoformat() if room.updated_at else "",
    )


def _source_to_response(source: RoomAudioSource) -> AudioSourceResponse:
    return AudioSourceResponse(
        id=str(source.id),
        room_id=str(source.room_id),
        hardware_type=source.hardware_type,
        device_path=source.device_path,
        device_id=source.device_id,
        label=source.label,
        status=source.status,
        config_json=source.config_json,
        created_at=source.created_at.isoformat() if source.created_at else "",
    )


def _pairing_to_response(pairing: RoomPairingCode) -> PairingCodeResponse:
    return PairingCodeResponse(
        id=str(pairing.id),
        room_id=str(pairing.room_id),
        code=pairing.code,
        expires_at=pairing.expires_at.isoformat() if pairing.expires_at else "",
        created_at=pairing.created_at.isoformat() if pairing.created_at else "",
    )


def _acl_to_response(acl: RoomAcl) -> AclResponse:
    return AclResponse(
        id=str(acl.id),
        room_id=str(acl.room_id),
        user_id=acl.user_id,
        role=acl.role,
        created_at=acl.created_at.isoformat() if acl.created_at else "",
    )


# === Org + ACL helpers ==================================================


def _is_org_admin(active_org: ActiveOrganization) -> bool:
    """Org admin / superuser bypass for room-level admin operations."""
    return active_org.role in {"admin", "superuser"}


def _get_room_or_404(
    db: Session,
    room_id: str,
    organization_id: int,
) -> ConferenceRoom:
    """Look up a room within the caller's org. Cross-org reads are
    indistinguishable from non-existent rooms — never reveal existence."""
    try:
        room_uuid = uuid.UUID(room_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=404, detail="Room not found")
    room = (
        db.query(ConferenceRoom)
        .filter(
            ConferenceRoom.id == room_uuid,
            ConferenceRoom.organization_id == organization_id,
        )
        .first()
    )
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    return room


def can_access_room(
    db: Session,
    user: User,
    room: ConferenceRoom,
    active_org: ActiveOrganization,
    required_role: str = "viewer",
) -> bool:
    """Return True if `user` can access `room` at >= `required_role`.

    * Superusers and org admins always pass.
    * Otherwise the user must have a row in `room_acl` for this room
      whose role is >= required_role.

    Role precedence: admin > member > viewer. Unknown role strings (e.g. a
    future `legal_officer`) are treated as equivalent to "member" for
    access-tier purposes; the API enforces specific role names at write
    time.
    """
    if user.is_superuser or _is_org_admin(active_org):
        return True

    # Cross-org safety: room must belong to caller's active org.
    if room.organization_id != active_org.organization.id:
        return False

    acl = (
        db.query(RoomAcl)
        .filter(
            RoomAcl.room_id == room.id,
            RoomAcl.user_id == user.id,
        )
        .first()
    )
    if not acl:
        return False

    precedence = {"viewer": 0, "member": 1, "admin": 2}
    return precedence.get(acl.role, precedence["member"]) >= precedence.get(
        required_role, 0
    )


def _require_org_admin(active_org: ActiveOrganization) -> None:
    if not _is_org_admin(active_org):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Org admin required",
        )


def _require_room_role(
    db: Session,
    user: User,
    room: ConferenceRoom,
    active_org: ActiveOrganization,
    required_role: str,
) -> None:
    if not can_access_room(db, user, room, active_org, required_role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Insufficient access to room (required: {required_role})",
        )


# === Room CRUD ==========================================================


@router.post("", response_model=RoomResponse)
async def create_room(
    request: RoomCreateRequest,
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
    db: Session = Depends(get_db),
):
    """Create a conference room. Admin-only."""
    _require_org_admin(active_org)

    room = ConferenceRoom(
        organization_id=active_org.organization.id,
        name=request.name,
        location=request.location,
        default_retention_days=request.default_retention_days,
        schedule_json=request.schedule_json,
        legal_hold=request.legal_hold,
    )
    db.add(room)
    try:
        db.commit()
    except Exception:
        db.rollback()
        # Most likely a unique-constraint violation on (org_id, name).
        raise HTTPException(
            status_code=409,
            detail=f"Room name '{request.name}' is already in use in this organization",
        )
    db.refresh(room)
    logger.info(
        "Created conference room %s (org=%s, name=%r)",
        room.id,
        room.organization_id,
        room.name,
    )
    return _room_to_response(room)


@router.get("", response_model=list[RoomResponse])
async def list_rooms(
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
    db: Session = Depends(get_db),
):
    """List rooms in the caller's active organization."""
    rooms = (
        db.query(ConferenceRoom)
        .filter(ConferenceRoom.organization_id == active_org.organization.id)
        .order_by(desc(ConferenceRoom.created_at))
        .all()
    )
    return [_room_to_response(r) for r in rooms]


@router.get("/{room_id}", response_model=RoomResponse)
async def get_room(
    room_id: str,
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
    db: Session = Depends(get_db),
):
    """Get a room's detail. Requires viewer-or-better access."""
    room = _get_room_or_404(db, room_id, active_org.organization.id)
    _require_room_role(db, current_user, room, active_org, "viewer")
    return _room_to_response(room)


@router.put("/{room_id}", response_model=RoomResponse)
async def update_room(
    room_id: str,
    request: RoomUpdateRequest,
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
    db: Session = Depends(get_db),
):
    """Update room metadata. Admin-only."""
    _require_org_admin(active_org)
    room = _get_room_or_404(db, room_id, active_org.organization.id)

    if request.name is not None:
        room.name = request.name
    if request.location is not None:
        room.location = request.location
    if request.status is not None:
        if request.status not in ROOM_STATUSES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status. Allowed: {sorted(ROOM_STATUSES)}",
            )
        room.status = request.status
    if request.default_retention_days is not None:
        room.default_retention_days = request.default_retention_days
    if request.schedule_json is not None:
        room.schedule_json = request.schedule_json
    if request.legal_hold is not None:
        room.legal_hold = request.legal_hold

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Update failed (likely a duplicate name in this organization)",
        )
    db.refresh(room)
    return _room_to_response(room)


@router.delete("/{room_id}")
async def delete_room(
    room_id: str,
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
    db: Session = Depends(get_db),
):
    """Delete a room. Admin-only. Cascades to audio sources, pairing codes,
    and ACL rows; sets room_id NULL on historical recording sessions."""
    _require_org_admin(active_org)
    room = _get_room_or_404(db, room_id, active_org.organization.id)
    db.delete(room)
    db.commit()
    return {"deleted": True, "room_id": room_id}


# === Audio sources ======================================================


@router.post("/{room_id}/sources", response_model=AudioSourceResponse)
async def add_audio_source(
    room_id: str,
    request: AudioSourceCreateRequest,
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
    db: Session = Depends(get_db),
):
    """Attach an audio source to a room. Admin-only.

    Validates hardware_type against the known set. For ``server_usb_mic``
    sources `device_path` must look like an ALSA hw spec (`hw:X,Y` or
    `plughw:X,Y`). Other types defer validation to the recorder.
    """
    _require_org_admin(active_org)
    room = _get_room_or_404(db, room_id, active_org.organization.id)

    if request.hardware_type not in ROOM_HARDWARE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid hardware_type. Allowed: {sorted(ROOM_HARDWARE_TYPES)}",
        )

    if request.hardware_type == "server_usb_mic":
        if not request.device_path:
            raise HTTPException(
                status_code=400,
                detail="server_usb_mic requires device_path (e.g. hw:2,0)",
            )
        # Loose validation — allow hw:X,Y / plughw:X,Y / sysdefault and the
        # `default` alias. The recorder fails loudly if it can't open the
        # device, which is the real source of truth.
        if not re.match(r"^(plug)?hw:\d+(,\d+)?$|^default$|^sysdefault$", request.device_path):
            raise HTTPException(
                status_code=400,
                detail="device_path must be hw:X[,Y], plughw:X[,Y], default, or sysdefault",
            )

    source = RoomAudioSource(
        room_id=room.id,
        hardware_type=request.hardware_type,
        device_path=request.device_path,
        device_id=request.device_id,
        label=request.label,
        config_json=request.config_json,
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    return _source_to_response(source)


@router.get("/{room_id}/sources", response_model=list[AudioSourceResponse])
async def list_audio_sources(
    room_id: str,
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
    db: Session = Depends(get_db),
):
    """List audio sources for a room. Viewer-or-better."""
    room = _get_room_or_404(db, room_id, active_org.organization.id)
    _require_room_role(db, current_user, room, active_org, "viewer")
    sources = (
        db.query(RoomAudioSource)
        .filter(RoomAudioSource.room_id == room.id)
        .order_by(RoomAudioSource.created_at)
        .all()
    )
    return [_source_to_response(s) for s in sources]


@router.delete("/{room_id}/sources/{source_id}")
async def remove_audio_source(
    room_id: str,
    source_id: str,
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
    db: Session = Depends(get_db),
):
    """Remove a source from a room. Admin-only."""
    _require_org_admin(active_org)
    room = _get_room_or_404(db, room_id, active_org.organization.id)
    try:
        source_uuid = uuid.UUID(source_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=404, detail="Source not found")
    source = (
        db.query(RoomAudioSource)
        .filter(
            RoomAudioSource.id == source_uuid,
            RoomAudioSource.room_id == room.id,
        )
        .first()
    )
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    db.delete(source)
    db.commit()
    return {"deleted": True, "source_id": source_id}


# === Pairing codes ======================================================


PAIRING_TTL = timedelta(minutes=10)
PAIRING_MAX_GENERATION_ATTEMPTS = 20


def _generate_unique_pairing_code(db: Session) -> str:
    """Cryptographically random 6-digit numeric code. Unique across all
    currently-active (not redeemed, not expired) pairing codes — once
    redeemed/expired, the value is free to be reused for a different room.
    Retries up to PAIRING_MAX_GENERATION_ATTEMPTS times before giving up
    (with 10**6 code space and short TTL collisions are vanishingly rare).
    """
    now = datetime.now(timezone.utc)
    for _ in range(PAIRING_MAX_GENERATION_ATTEMPTS):
        # secrets.randbelow is cryptographically strong; zero-pad to width 6.
        candidate = f"{secrets.randbelow(1_000_000):06d}"
        active_collision = (
            db.query(RoomPairingCode)
            .filter(
                RoomPairingCode.code == candidate,
                RoomPairingCode.redeemed_at.is_(None),
                RoomPairingCode.expires_at > now,
            )
            .first()
        )
        if not active_collision:
            return candidate
    raise HTTPException(
        status_code=503,
        detail="Could not generate a unique pairing code; try again",
    )


@router.post("/{room_id}/pairing-codes", response_model=PairingCodeResponse)
async def generate_pairing_code(
    room_id: str,
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
    db: Session = Depends(get_db),
):
    """Generate a 6-digit pairing code with 10-min TTL. Admin-only.

    Codes are unique across all currently-active codes (system-wide); once
    redeemed or expired, the value can be reissued for a different room.
    """
    _require_org_admin(active_org)
    room = _get_room_or_404(db, room_id, active_org.organization.id)

    now = datetime.now(timezone.utc)
    code = _generate_unique_pairing_code(db)
    pairing = RoomPairingCode(
        room_id=room.id,
        code=code,
        created_at=now,
        expires_at=now + PAIRING_TTL,
    )
    db.add(pairing)
    db.commit()
    db.refresh(pairing)
    logger.info(
        "Generated pairing code for room %s (org=%s, ttl=%ss)",
        room.id,
        room.organization_id,
        int(PAIRING_TTL.total_seconds()),
    )
    return _pairing_to_response(pairing)


@router.post("/pairing-codes/redeem", response_model=PairingRedeemResponse)
async def redeem_pairing_code(
    request: PairingRedeemRequest,
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
    db: Session = Depends(get_db),
):
    """Redeem a pairing code, marking it consumed.

    In Phase 1, redemption is server-side — admins use this to enrol a
    USB mic (or any host process) into a room. In Phase 3 satellite
    devices will redeem via their own API key flow. The redemption is
    scoped to the caller's org for safety: a code generated in org A
    cannot be redeemed from org B's session.
    """
    code = request.code.strip()
    if not code.isdigit() or len(code) != 6:
        raise HTTPException(status_code=400, detail="code must be 6 digits")

    now = datetime.now(timezone.utc)
    # Join through the room to enforce org scoping. A leaked code from
    # another org's admin will not redeem from this org's API session.
    pairing = (
        db.query(RoomPairingCode)
        .join(ConferenceRoom, ConferenceRoom.id == RoomPairingCode.room_id)
        .filter(
            RoomPairingCode.code == code,
            RoomPairingCode.redeemed_at.is_(None),
            RoomPairingCode.expires_at > now,
            ConferenceRoom.organization_id == active_org.organization.id,
        )
        .first()
    )
    if not pairing:
        # Don't tell the caller which case it is — a generic 404 prevents
        # brute-force discovery of valid codes from other orgs.
        raise HTTPException(status_code=404, detail="Code is invalid or expired")

    pairing.redeemed_at = now
    if request.device_id is not None:
        pairing.redeemed_by_device_id = request.device_id
    db.commit()
    db.refresh(pairing)
    return PairingRedeemResponse(
        room_id=str(pairing.room_id),
        redeemed_at=pairing.redeemed_at.isoformat(),
    )


# === Recording lifecycle ================================================


@router.post("/{room_id}/recordings/start", response_model=RecordingStartResponse)
async def start_recording(
    room_id: str,
    source_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
    db: Session = Depends(get_db),
):
    """Start a recording on this room. Requires member-or-better.

    Creates a RecordingSession row pinned to this room (and optionally a
    specific source). If `source_id` is omitted the room's first
    configured source is used. The RoomRecorder is started in the
    background — the response returns immediately with the new session id.
    """
    room = _get_room_or_404(db, room_id, active_org.organization.id)
    _require_room_role(db, current_user, room, active_org, "member")

    if room.status == "recording":
        raise HTTPException(
            status_code=409,
            detail="Room is already recording",
        )

    # Resolve source.
    source: Optional[RoomAudioSource] = None
    if source_id is not None:
        try:
            source_uuid = uuid.UUID(source_id)
        except (TypeError, ValueError):
            raise HTTPException(status_code=404, detail="Source not found")
        source = (
            db.query(RoomAudioSource)
            .filter(
                RoomAudioSource.id == source_uuid,
                RoomAudioSource.room_id == room.id,
            )
            .first()
        )
        if not source:
            raise HTTPException(status_code=404, detail="Source not found")
    else:
        source = (
            db.query(RoomAudioSource)
            .filter(RoomAudioSource.room_id == room.id)
            .order_by(RoomAudioSource.created_at)
            .first()
        )
        if not source:
            raise HTTPException(
                status_code=400,
                detail="Room has no audio sources; add one before starting a recording",
            )

    started_at = datetime.now(timezone.utc)
    title = f"{room.name} - {started_at.strftime('%Y-%m-%d %H:%M')}"
    session = RecordingSession(
        session_id=str(uuid.uuid4()),
        name=title,
        title=title,
        description=f"Conference room recording: {room.name}",
        meeting_type="conference_room",
        mode="always_on",  # uses the always-on chunk pipeline
        created_at=started_at,
        started_at=started_at,
        status="recording",
        duration=0.0,
        user_id=current_user.id,
        organization_id=active_org.organization.id,
        source_type="room-server-usb-mic"
        if source.hardware_type == "server_usb_mic"
        else "room-other",
        room_name=room.name,
        room_id=room.id,
        room_source_id=source.id,
        processing_metadata={
            "source_label": source.label or source.device_path or source.hardware_type,
            "created_by": "conference_room",
            "room_id": str(room.id),
            "source_id": str(source.id),
            "hardware_type": source.hardware_type,
        },
    )
    db.add(session)

    room.status = "recording"
    source.status = "recording"
    db.commit()
    db.refresh(session)

    # Kick off the recorder. Import locally so test fixtures can patch the
    # module without affecting the API import graph.
    try:
        from services.room_recorder import start_room_recorder

        await start_room_recorder(room=room, source=source, session=session)
    except Exception as exc:
        # Recorder failed to start — roll the room/source back to error so
        # the UI shows it and the admin can investigate.
        logger.exception(
            "Failed to start RoomRecorder for room %s source %s: %s",
            room.id,
            source.id,
            exc,
        )
        room.status = "error"
        source.status = "error"
        session.status = "error"
        db.commit()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start recorder: {exc}",
        )

    return RecordingStartResponse(
        session_id=session.session_id or str(session.id),
        session_pk=session.id,
        room_id=str(room.id),
        source_id=str(source.id),
        started_at=started_at.isoformat(),
    )


@router.post("/{room_id}/recordings/stop", response_model=RecordingStopResponse)
async def stop_recording(
    room_id: str,
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
    db: Session = Depends(get_db),
):
    """Stop the current recording on this room. Member-or-better.

    Finds the active RecordingSession for this room, terminates the
    RoomRecorder subprocess, and marks the session/room/source idle.
    """
    room = _get_room_or_404(db, room_id, active_org.organization.id)
    _require_room_role(db, current_user, room, active_org, "member")

    session = (
        db.query(RecordingSession)
        .filter(
            RecordingSession.room_id == room.id,
            RecordingSession.organization_id == active_org.organization.id,
            RecordingSession.status.in_(("recording", "processing", "paused")),
        )
        .order_by(desc(RecordingSession.created_at))
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="No active recording on this room")

    stopped_at = datetime.now(timezone.utc)

    try:
        from services.room_recorder import stop_room_recorder

        await stop_room_recorder(room_id=room.id)
    except Exception:
        # Best-effort stop. We still flip the DB to a sane state so the UI
        # isn't stuck on "recording" forever.
        logger.exception("RoomRecorder stop failed for room %s", room.id)

    session.status = "completed"
    session.ended_at = stopped_at
    if session.started_at:
        # SQLAlchemy returns DateTime columns as naive in SQLite; treat
        # them as UTC for the arithmetic. Postgres returns aware values
        # natively. Coerce both sides to aware-UTC before subtracting.
        started = session.started_at
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        delta = stopped_at - started
        # Don't overwrite duration if the chunk pipeline already accumulated it.
        if not session.duration or session.duration <= 0:
            session.duration = max(0.0, delta.total_seconds())
    room.status = "idle"
    if session.room_source_id:
        source = (
            db.query(RoomAudioSource)
            .filter(RoomAudioSource.id == session.room_source_id)
            .first()
        )
        if source:
            source.status = "idle"
    db.commit()
    db.refresh(session)

    return RecordingStopResponse(
        session_id=session.session_id or str(session.id),
        session_pk=session.id,
        stopped_at=stopped_at.isoformat(),
    )


# === ACL =================================================================


@router.post("/{room_id}/acl", response_model=AclResponse)
async def grant_acl(
    room_id: str,
    request: AclGrantRequest,
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
    db: Session = Depends(get_db),
):
    """Grant a user access to a room. Admin-only.

    `role` is intentionally a plain string so new roles (legal_officer,
    observer, etc.) can be added at the API layer without a schema
    migration. We require the role to be in ROOM_ROLES at write time;
    extend that set as needed.
    """
    _require_org_admin(active_org)
    room = _get_room_or_404(db, room_id, active_org.organization.id)

    if request.role not in ROOM_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid role. Allowed: {sorted(ROOM_ROLES)}",
        )

    # Confirm the user belongs to the same org. We don't reveal users from
    # other orgs (returns 404 either way).
    from auth.models import UserOrganization

    membership = (
        db.query(UserOrganization)
        .filter(
            UserOrganization.user_id == request.user_id,
            UserOrganization.organization_id == active_org.organization.id,
        )
        .first()
    )
    if not membership:
        raise HTTPException(
            status_code=404,
            detail="User is not a member of this organization",
        )

    # Upsert: if a row exists, update role; otherwise insert.
    existing = (
        db.query(RoomAcl)
        .filter(
            RoomAcl.room_id == room.id,
            RoomAcl.user_id == request.user_id,
        )
        .first()
    )
    if existing:
        existing.role = request.role
        db.commit()
        db.refresh(existing)
        return _acl_to_response(existing)

    acl = RoomAcl(room_id=room.id, user_id=request.user_id, role=request.role)
    db.add(acl)
    db.commit()
    db.refresh(acl)
    return _acl_to_response(acl)


@router.delete("/{room_id}/acl/{user_id}")
async def revoke_acl(
    room_id: str,
    user_id: int,
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
    db: Session = Depends(get_db),
):
    """Revoke a user's room ACL row. Admin-only."""
    _require_org_admin(active_org)
    room = _get_room_or_404(db, room_id, active_org.organization.id)

    acl = (
        db.query(RoomAcl)
        .filter(RoomAcl.room_id == room.id, RoomAcl.user_id == user_id)
        .first()
    )
    if not acl:
        raise HTTPException(status_code=404, detail="ACL row not found")
    db.delete(acl)
    db.commit()
    return {"deleted": True, "room_id": room_id, "user_id": user_id}


# === System: audio devices ==============================================


def _parse_arecord_l(output: str) -> list[AudioDeviceInfo]:
    """Parse the output of `arecord -l` into AudioDeviceInfo rows.

    arecord(1) emits each card+device combo on a single line in the
    shape::

        card 2: USB [Some USB Card], device 0: USB Audio [USB Audio]

    Some packages split the card and device clauses across lines (the
    device-line is then indented). We match both shapes by searching for
    "card ..." and "device ..." anywhere on the line, then pairing them.
    """
    devices: list[AudioDeviceInfo] = []
    card_pattern = re.compile(r"card\s+(\d+):\s+(\S+)\s+\[([^\]]+)\]")
    device_pattern = re.compile(
        r"device\s+(\d+):\s+([^\[]+?)\s+\[([^\]]+)\]"
    )
    current_card: Optional[dict[str, Any]] = None
    for raw_line in output.splitlines():
        card_match = card_pattern.search(raw_line)
        if card_match:
            current_card = {
                "card": int(card_match.group(1)),
                "card_name": card_match.group(2),
                "card_label": card_match.group(3),
            }
        device_match = device_pattern.search(raw_line)
        if device_match and current_card is not None:
            card = current_card["card"]
            dev = int(device_match.group(1))
            dev_name = device_match.group(2).strip()
            dev_label = device_match.group(3)
            is_usb = (
                "USB" in current_card["card_label"]
                or "USB" in dev_label
                or "usb" in current_card["card_name"].lower()
            )
            devices.append(
                AudioDeviceInfo(
                    card=card,
                    device=dev,
                    card_name=current_card["card_name"],
                    card_label=current_card["card_label"],
                    device_name=dev_name,
                    device_label=dev_label,
                    device_path=f"hw:{card},{dev}",
                    is_usb=is_usb,
                )
            )
    return devices


@system_router.get("/audio-devices", response_model=list[AudioDeviceInfo])
async def list_audio_devices(
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
):
    """Enumerate `arecord -l` capture devices on the backend container.

    Admin-only — only org admins or superusers see hardware. Used by the
    Conference Room setup wizard to populate the device picker.

    Returns an empty list if `arecord` is unavailable (container missing
    alsa-utils, or the host doesn't expose ALSA). Callers should treat
    empty as "no USB mics detected" rather than as an error.
    """
    _require_org_admin(active_org)
    try:
        proc = subprocess.run(
            ["arecord", "-l"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except FileNotFoundError:
        logger.warning("arecord binary not found — install alsa-utils in the backend image")
        return []
    except subprocess.TimeoutExpired:
        logger.warning("arecord -l timed out after 5s")
        return []
    except Exception as exc:
        logger.warning("arecord -l failed: %s", exc)
        return []

    # `arecord -l` returns 0 even when no cards are present (with stderr
    # "no soundcards found"). Treat any non-zero exit as "no devices".
    if proc.returncode != 0:
        logger.info("arecord -l returned %s: %s", proc.returncode, proc.stderr.strip())
        return []
    return _parse_arecord_l(proc.stdout)
