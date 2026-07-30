"""Durable, tenant-scoped transcript ingestion from Unicorn Stable."""

from __future__ import annotations

import uuid
import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from auth.config import auth_config
from auth.dependencies import (
    get_current_organization,
    get_current_user,
    require_permission,
)
from auth.models import User
from auth.organization import ActiveOrganization
from database.database import get_db
from database.models import RecordingSession, Transcription

router = APIRouter(prefix="/api/v1/sessions", tags=["stable-ingest"])


class StableTranscriptLine(BaseModel):
    participant_id: str = Field(min_length=1, max_length=256)
    name: str = Field(default="", max_length=256)
    text: str = Field(min_length=1, max_length=8000)
    ts: int = Field(ge=0, description="Unix epoch milliseconds")
    is_final: bool = True
    segment_id: Optional[str] = Field(default=None, max_length=256)
    source: Literal["local_mic", "agent_stt", "agent", "unknown"] = "unknown"


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


@router.post(
    "/ingest",
    response_model=StableTranscriptIngestResponse,
    status_code=status.HTTP_200_OK,
)
async def ingest_stable_transcript(
    body: StableTranscriptIngest,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
    _allowed: User = Depends(require_permission("session.create")),
) -> StableTranscriptIngestResponse:
    """Create one completed Meeting-Ops session per Stable export.

    Authentication accepts the existing Meeting-Ops PAT bearer convention.
    The PAT/user and ``X-MeetingOps-Org`` resolve the organization; clients
    cannot select an organization in the JSON body.
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

    org_id = active_org.organization.id
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
    }
    row = RecordingSession(
        session_id=session_uuid,
        name=body.label or f"Stable call · {body.room_name}",
        title=body.label or f"Stable call · {body.room_name}",
        description=f"Transcript imported from Unicorn Stable room {body.room_name}.",
        status="completed",
        mode="federated",
        created_at=_utc(body.exported_at),
        started_at=started,
        ended_at=ended,
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
        speaker_count=len(speakers),
        user_id=current_user.id,
        organization_id=org_id,
        participants=list(participants_by_id.values()),
        source_type="stable",
        external_source=body.source,
        external_id=body.export_id,
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
                    confidence=1.0,
                )
            )
        db.add_all(transcript_rows)
        db.commit()
        db.refresh(row)
    except IntegrityError:
        db.rollback()
        existing = (
            db.query(RecordingSession)
            .filter(
                RecordingSession.organization_id == org_id,
                RecordingSession.external_source == body.source,
                RecordingSession.external_id == body.export_id,
            )
            .first()
        )
        if existing is None:
            raise
        if _stored_payload_sha256(existing) != payload_sha256:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="export_id was already used for different transcript content",
            )
        return _response(existing, created=False)

    return _response(row, created=True)
