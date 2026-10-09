"""PAT-only recording ingestion for the Meeting Minutes desktop app."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api import uploads as upload_api
from auth.models import Organization, PersonalAccessToken, User, UserOrganization
from auth.pat import TOKEN_PREFIX as PAT_PREFIX, resolve_pat_record
from database.database import get_db
from database.models import RecordingSession, UploadJob
from services.meeting_provenance import (
    build_meeting_provenance,
    org_timezone,
    wall_clock,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ingest", tags=["recording-ingest"])

# recording_sessions.external_source is VARCHAR(50) (alembic 058).
EXTERNAL_SOURCE_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,49}$")
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
MAX_METADATA_BYTES = 16 * 1024
FILE_READ_CHUNK_SIZE = 1024 * 1024
INGEST_UPLOAD_ACTION = "ingest"
INGEST_METADATA_FILENAME = "ingest.json"


class IngestStatusResponse(BaseModel):
    # recording_sessions.id, the id the web UI links with (/sessions/<id>)
    session_id: int
    status: Literal["processing", "completed", "failed"]
    meeting_date: Optional[str] = None
    meeting_time: Optional[str] = None
    error: Optional[str] = None


class IngestCreateResponse(IngestStatusResponse):
    upload_id: Optional[str] = None
    created: bool


class IngestRetryResponse(BaseModel):
    session_id: int
    status: Literal["processing"]


class WhoAmIResponse(BaseModel):
    organization_id: int
    organization_slug: str
    organization_name: str
    scope: str
    expires_at: Optional[datetime] = None
    token_prefix: str


class IngestUploadInitRequest(BaseModel):
    external_source: str
    external_id: str
    recorded_at: str
    sha256: str
    total_size: int
    duration_seconds: Optional[float] = None
    title: Optional[str] = None
    timezone: Optional[str] = None
    source_app: Optional[str] = None
    metadata: Optional[Any] = None
    filename: Optional[str] = None
    content_type: Optional[str] = None


@dataclass(frozen=True)
class ValidatedIngest:
    external_source: str
    external_id: str
    recorded_at: datetime
    duration: Optional[float]
    title: Optional[str]
    timezone: str
    source_app: Optional[str]
    metadata: dict[str, str]
    sha256: Optional[str]


@dataclass
class IngestPrincipal:
    user: User
    token: PersonalAccessToken
    organization: Organization
    membership: UserOrganization


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="A recording ingest PAT is required",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _unprocessable(detail: str) -> None:
    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)


def require_recording_ingest_principal(
    request: Request,
    db: Session = Depends(get_db),
) -> IngestPrincipal:
    """Resolve only an org-bound, active ``recordings.ingest`` PAT.

    This dependency intentionally does not call the browser/JWT auth stack or
    resolve a default organization. The token's organization is the only
    tenant boundary for every route in this router.
    """
    authorization = request.headers.get("Authorization") or ""
    scheme, _, plaintext = authorization.partition(" ")
    plaintext = plaintext.strip()
    if (
        scheme.lower() != "bearer"
        or not plaintext
        or not plaintext.startswith(PAT_PREFIX)
    ):
        raise _unauthorized()

    token = resolve_pat_record(db, plaintext=plaintext)
    if token is None:
        raise _unauthorized()
    if token.scope != "recordings.ingest" or token.organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="PAT is not authorized for recording ingestion",
        )

    organization = (
        db.query(Organization)
        .filter(
            Organization.id == token.organization_id,
            Organization.is_active.is_(True),
        )
        .first()
    )
    if organization is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="PAT organization is not active",
        )

    membership = (
        db.query(UserOrganization)
        .filter(
            UserOrganization.user_id == token.user_id,
            UserOrganization.organization_id == organization.id,
        )
        .first()
    )
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="PAT user is no longer a member of its organization",
        )

    logger.debug(
        "recording ingest authenticated pat_id=%s user_id=%s org_id=%s",
        token.id,
        token.user_id,
        organization.id,
    )
    return IngestPrincipal(
        user=token.user,
        token=token,
        organization=organization,
        membership=membership,
    )


def _validate_external_source(value: str) -> str:
    if not EXTERNAL_SOURCE_RE.fullmatch(value or ""):
        _unprocessable(
            "external_source must match ^[a-z0-9][a-z0-9._-]{1,49}$"
        )
    return value


def _validate_external_id(value: str) -> str:
    if not value or len(value) > 128:
        _unprocessable("external_id must be 1..128 characters")
    if "/" in value or any(ord(char) < 32 or ord(char) == 127 or char.isspace() for char in value):
        _unprocessable("external_id must not contain slash, whitespace, or control characters")
    return value


def _parse_recorded_at(raw: str) -> datetime:
    if not raw:
        _unprocessable("recorded_at is required")
    try:
        value = datetime.fromisoformat(
            raw[:-1] + "+00:00" if raw.endswith("Z") else raw
        )
    except (TypeError, ValueError):
        _unprocessable("recorded_at must be ISO-8601 with Z or an offset")
    if value.tzinfo is None:
        _unprocessable("recorded_at must include Z or an offset")
    value = value.astimezone(timezone.utc)
    now = datetime.now(timezone.utc)
    if value < now - timedelta(days=365 * 5) or value > now + timedelta(days=1):
        _unprocessable("recorded_at must be between now-5-years and now+1-day")
    return value


def _parse_duration(raw: Optional[Any]) -> Optional[float]:
    if raw is None or raw == "":
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        _unprocessable("duration_seconds must be a number >= 0")
    if not math.isfinite(value) or value < 0:
        _unprocessable("duration_seconds must be a number >= 0")
    return value


def _parse_metadata(raw: Optional[Any]) -> dict[str, str]:
    if raw is None:
        return {}
    if isinstance(raw, str):
        if len(raw.encode("utf-8")) > MAX_METADATA_BYTES:
            _unprocessable("metadata must be at most 16 KB")
        try:
            value = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            _unprocessable("metadata must be a JSON object")
    else:
        value = raw
    if not isinstance(value, dict) or any(not isinstance(item, str) for item in value.values()):
        _unprocessable("metadata must be a JSON object with string values")
    if len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) > MAX_METADATA_BYTES:
        _unprocessable("metadata must be at most 16 KB")
    return value


def _resolve_timezone(db: Session, org_id: int, requested: Optional[str]) -> str:
    if requested is None:
        return org_timezone(db, org_id) or "UTC"
    try:
        ZoneInfo(requested)
    except Exception:  # noqa: BLE001
        _unprocessable("timezone must be a valid IANA timezone")
    return requested


def _validate_ingest_fields(
    db: Session,
    principal: IngestPrincipal,
    *,
    external_source: str,
    external_id: str,
    recorded_at: str,
    duration_seconds: Optional[Any],
    title: Optional[str],
    timezone_name: Optional[str],
    source_app: Optional[str],
    metadata: Optional[Any],
    sha256: Optional[str],
    sha256_required: bool = False,
) -> ValidatedIngest:
    external_source = _validate_external_source(external_source)
    external_id = _validate_external_id(external_id)
    recorded_at_utc = _parse_recorded_at(recorded_at)
    duration = _parse_duration(duration_seconds)
    if title is not None and len(title) > 200:
        _unprocessable("title must be at most 200 characters")
    if source_app is not None and len(source_app) > 64:
        _unprocessable("source_app must be at most 64 characters")
    metadata_value = _parse_metadata(metadata)
    if sha256_required and not sha256:
        _unprocessable("sha256 is required")
    if sha256 is not None and not SHA256_RE.fullmatch(sha256):
        _unprocessable("sha256 must be a 64-character hexadecimal digest")
    timezone_value = _resolve_timezone(db, principal.organization.id, timezone_name)
    return ValidatedIngest(
        external_source=external_source,
        external_id=external_id,
        recorded_at=recorded_at_utc,
        duration=duration,
        title=title,
        timezone=timezone_value,
        source_app=source_app,
        metadata=metadata_value,
        sha256=sha256.lower() if sha256 else None,
    )


def _status_for(session: RecordingSession, job: Optional[UploadJob]) -> str:
    if session.status == "failed" or (job is not None and job.stage in {"failed", "cancelled"}):
        return "failed"
    if session.status == "completed" or (job is not None and job.stage == "done"):
        return "completed"
    return "processing"


def _error_for(session: RecordingSession, job: Optional[UploadJob]) -> Optional[str]:
    metadata = session.processing_metadata if isinstance(session.processing_metadata, dict) else {}
    error = metadata.get("upload_error")
    if error:
        return str(error)
    return job.error_message if job is not None and job.error_message else None


def _job_for_session(db: Session, session: RecordingSession) -> Optional[UploadJob]:
    return (
        db.query(UploadJob)
        .filter(
            UploadJob.organization_id == session.organization_id,
            UploadJob.session_id == session.id,
        )
        .order_by(UploadJob.created_at.desc(), UploadJob.id.desc())
        .first()
    )


def _status_response(
    db: Session,
    session: RecordingSession,
    *,
    created: Optional[bool] = None,
    upload_id: Optional[str] = None,
) -> IngestStatusResponse | IngestCreateResponse:
    job = _job_for_session(db, session)
    payload: dict[str, Any] = {
        "session_id": session.id,
        "status": _status_for(session, job),
        "meeting_date": session.meeting_date.isoformat() if session.meeting_date else None,
        "meeting_time": session.meeting_time.isoformat() if session.meeting_time else None,
        "error": _error_for(session, job),
    }
    if created is not None:
        payload["created"] = created
        payload["upload_id"] = upload_id
        return IngestCreateResponse(**payload)
    return IngestStatusResponse(**payload)


def _find_session(
    db: Session,
    organization_id: int,
    external_source: str,
    external_id: str,
) -> Optional[RecordingSession]:
    return (
        db.query(RecordingSession)
        .filter(
            RecordingSession.organization_id == organization_id,
            RecordingSession.external_source == external_source,
            RecordingSession.external_id == external_id,
        )
        .first()
    )


def _remove_job_dir(org_slug: str, upload_id: uuid.UUID) -> None:
    shutil.rmtree(upload_api._job_dir(org_slug, str(upload_id)), ignore_errors=True)


def _ingest_sidecar_path(org_slug: str, upload_id: uuid.UUID | str) -> Path:
    return upload_api._job_dir(org_slug, str(upload_id)) / INGEST_METADATA_FILENAME


def _write_ingest_sidecar(org_slug: str, upload_id: uuid.UUID, payload: dict[str, Any]) -> None:
    path = _ingest_sidecar_path(org_slug, upload_id)
    temporary_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path.write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        temporary_path.replace(path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def _read_ingest_sidecar(org_slug: str, upload_id: uuid.UUID | str) -> Optional[dict[str, Any]]:
    path = _ingest_sidecar_path(org_slug, upload_id)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _ingest_upload_job(
    db: Session,
    principal: IngestPrincipal,
    upload_id: str,
) -> UploadJob:
    try:
        parsed_upload_id = uuid.UUID(upload_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload not found")
    job = (
        db.query(UploadJob)
        .filter(
            UploadJob.organization_id == principal.organization.id,
            UploadJob.upload_id == parsed_upload_id,
            UploadJob.action == INGEST_UPLOAD_ACTION,
            UploadJob.stage == "uploading",
        )
        .first()
    )
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload not found")
    return job


def _received_indices(job: UploadJob, org_slug: str) -> list[int]:
    return upload_api.received_chunk_indices(
        upload_api._job_dir(org_slug, str(job.upload_id)) / "chunks",
        int(job.total_chunks or 0),
    )


def _discard_ingest_upload(db: Session, org_slug: str, organization_id: int, upload_id: uuid.UUID) -> None:
    """Delete an unlinked in-progress ingest and its bytes.

    A concurrent complete may have linked the job to the winning session by
    the time the loser observes the duplicate. In that case its directory is
    the winner's live pipeline input and must remain untouched.
    """
    job = (
        db.query(UploadJob)
        .filter(
            UploadJob.organization_id == organization_id,
            UploadJob.upload_id == upload_id,
        )
        .first()
    )
    if job is not None and job.session_id is not None:
        return
    if job is not None:
        db.delete(job)
        db.commit()
    _remove_job_dir(org_slug, upload_id)


def _find_resumable_ingest_upload(
    db: Session,
    principal: IngestPrincipal,
    fields: ValidatedIngest,
) -> Optional[UploadJob]:
    if not fields.sha256:
        return None
    candidates = (
        db.query(UploadJob)
        .filter(
            UploadJob.organization_id == principal.organization.id,
            UploadJob.action == INGEST_UPLOAD_ACTION,
            UploadJob.stage == "uploading",
            UploadJob.session_id.is_(None),
            UploadJob.audio_sha256 == fields.sha256,
        )
        .order_by(UploadJob.created_at.asc(), UploadJob.id.asc())
        .all()
    )
    for job in candidates:
        sidecar = _read_ingest_sidecar(principal.organization.slug, job.upload_id)
        if not sidecar:
            continue
        if (
            sidecar.get("external_source") == fields.external_source
            and sidecar.get("external_id") == fields.external_id
            and str(sidecar.get("sha256", "")).lower() == fields.sha256
        ):
            return job
    return None


async def _create_ingest_session_and_job(
    db: Session,
    principal: IngestPrincipal,
    fields: ValidatedIngest,
    *,
    upload_id: uuid.UUID,
    filename: str,
    content_type: Optional[str],
    source_path: Path,
    file_size: int,
    actual_sha256: str,
    client: Optional[str],
    pat_id: Optional[int] = None,
    job: Optional[UploadJob] = None,
) -> tuple[RecordingSession, bool]:
    """Create the pre-session + pipeline job used by both ingest upload paths."""
    existing = _find_session(
        db,
        principal.organization.id,
        fields.external_source,
        fields.external_id,
    )
    if existing is not None:
        if job is not None:
            _discard_ingest_upload(
                db,
                principal.organization.slug,
                principal.organization.id,
                upload_id,
            )
        return existing, False

    now = datetime.now(timezone.utc)
    meeting_date, meeting_time = wall_clock(fields.recorded_at, fields.timezone)
    ingest_signal = {
        "value": fields.recorded_at.isoformat(),
        "source": "ingest.recorded_at",
        "confidence": 1.0,
    }
    provenance = build_meeting_provenance(
        audio_path=None,
        original_filename=filename,
        filename_date=None,
        filename_time=None,
        uploaded_at=now,
        source_type="upload",
        now=now,
    )
    provenance["when"]["recorded_at"] = ingest_signal
    provenance["when"]["candidates"] = [
        ingest_signal,
        *[
            candidate
            for candidate in provenance["when"].get("candidates", [])
            if candidate.get("source") != "upload_time"
        ],
        *[
            candidate
            for candidate in provenance["when"].get("candidates", [])
            if candidate.get("source") == "upload_time"
        ],
    ]
    ingest_metadata: dict[str, Any] = {
        "external_source": fields.external_source,
        "external_id": fields.external_id,
        "source_app": fields.source_app,
        "recorded_at": fields.recorded_at.isoformat(),
        "timezone": fields.timezone,
        "metadata": fields.metadata,
        "pat_id": pat_id if pat_id is not None else principal.token.id,
        "client": client,
    }
    session_metadata: dict[str, Any] = {
        "upload_id": str(upload_id),
        "audio_sha256": actual_sha256,
        "original_filename": filename,
        "content_type": content_type,
        "meeting_provenance": provenance,
        "provenance_probe_file": None,
        "ingest": ingest_metadata,
    }
    if fields.duration is not None:
        # Preserve the public ingest ledger shape while retaining the optional
        # client duration for the shared pipeline's measured-duration fallback.
        session_metadata["ingest_duration_seconds"] = fields.duration

    owner_user_id = job.user_id if job is not None else principal.user.id
    title = (fields.title or upload_api._title_from_filename(filename))[:200]
    session = RecordingSession(
        session_id=str(uuid.uuid4()),
        name=title,
        title=title,
        description=f"Uploaded from {filename}",
        meeting_type="upload",
        created_at=now,
        started_at=fields.recorded_at.replace(tzinfo=None),
        ended_at=(
            fields.recorded_at.replace(tzinfo=None) + timedelta(seconds=fields.duration)
            if fields.duration is not None
            else None
        ),
        meeting_date=meeting_date,
        meeting_time=meeting_time,
        duration=fields.duration or 0,
        status="processing",
        user_id=owner_user_id,
        organization_id=principal.organization.id,
        audio_file=str(source_path),
        source_type="upload",
        external_source=fields.external_source,
        external_id=fields.external_id,
        processing_metadata=session_metadata,
    )
    try:
        db.add(session)
        db.flush()
        if job is None:
            job = UploadJob(
                organization_id=principal.organization.id,
                user_id=owner_user_id,
                upload_id=upload_id,
                filename=filename,
                content_type=content_type,
                action="attach",
                total_size=file_size,
                bytes_received=file_size,
                chunks_received=1,
                total_chunks=1,
                stage="queued",
                progress_pct=0,
                session_id=session.id,
                audio_sha256=actual_sha256,
            )
            db.add(job)
        else:
            job.filename = filename
            job.content_type = content_type
            job.action = "attach"
            job.total_size = file_size
            job.bytes_received = file_size
            job.chunks_received = 1
            job.total_chunks = 1
            job.stage = "queued"
            job.progress_pct = 0
            job.session_id = session.id
            job.audio_sha256 = actual_sha256
            job.error_message = None
            job.job_started_at = None
            job.job_completed_at = None
        db.commit()
        db.refresh(session)
        return session, True
    except IntegrityError:
        db.rollback()
        duplicate = _find_session(
            db,
            principal.organization.id,
            fields.external_source,
            fields.external_id,
        )
        if duplicate is None:
            if job is not None:
                _discard_ingest_upload(
                    db,
                    principal.organization.slug,
                    principal.organization.id,
                    upload_id,
                )
            else:
                _remove_job_dir(principal.organization.slug, upload_id)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Recording identity conflicted with another ingest",
            )
        if job is not None:
            _discard_ingest_upload(
                db,
                principal.organization.slug,
                principal.organization.id,
                upload_id,
            )
        else:
            _remove_job_dir(principal.organization.slug, upload_id)
        return duplicate, False
    except Exception:
        db.rollback()
        if job is not None:
            _discard_ingest_upload(
                db,
                principal.organization.slug,
                principal.organization.id,
                upload_id,
            )
        else:
            _remove_job_dir(principal.organization.slug, upload_id)
        raise


async def _store_upload(file: UploadFile, target: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    total = 0
    with target.open("wb") as output:
        while True:
            block = await file.read(FILE_READ_CHUNK_SIZE)
            if not block:
                break
            total += len(block)
            if total > upload_api.get_max_file_bytes():
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail={
                        "message": "File is larger than the configured upload limit.",
                        "max_file_bytes": upload_api.get_max_file_bytes(),
                    },
                )
            digest.update(block)
            output.write(block)
    if total <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty")
    return total, digest.hexdigest()


def _validated_media_filename(filename: Optional[str], content_type: Optional[str]) -> str:
    normalized = upload_api._safe_filename(filename or "recording.m4a")
    if upload_api._detect_kind(normalized, content_type) not in {"audio", "video"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only audio and video files can be ingested.",
        )
    return normalized


def _init_sidecar(
    fields: ValidatedIngest,
    *,
    filename: str,
    content_type: Optional[str],
    total_size: int,
    pat_id: int,
    client: Optional[str],
) -> dict[str, Any]:
    return {
        "external_source": fields.external_source,
        "external_id": fields.external_id,
        "recorded_at": fields.recorded_at.isoformat(),
        "duration_seconds": fields.duration,
        "title": fields.title,
        "timezone": fields.timezone,
        "source_app": fields.source_app,
        "metadata": fields.metadata,
        "sha256": fields.sha256,
        "total_size": total_size,
        "filename": filename,
        "content_type": content_type,
        "pat_id": pat_id,
        "client": client,
    }


def _fields_from_sidecar(
    db: Session,
    principal: IngestPrincipal,
    sidecar: dict[str, Any],
) -> ValidatedIngest:
    return _validate_ingest_fields(
        db,
        principal,
        external_source=str(sidecar.get("external_source") or ""),
        external_id=str(sidecar.get("external_id") or ""),
        recorded_at=str(sidecar.get("recorded_at") or ""),
        duration_seconds=sidecar.get("duration_seconds"),
        title=sidecar.get("title"),
        timezone_name=sidecar.get("timezone"),
        source_app=sidecar.get("source_app"),
        metadata=sidecar.get("metadata"),
        sha256=sidecar.get("sha256"),
        sha256_required=True,
    )


@router.get("/whoami", response_model=WhoAmIResponse)
async def ingest_whoami(
    principal: IngestPrincipal = Depends(require_recording_ingest_principal),
) -> WhoAmIResponse:
    return WhoAmIResponse(
        organization_id=principal.organization.id,
        organization_slug=principal.organization.slug,
        organization_name=principal.organization.name,
        scope=principal.token.scope,
        expires_at=principal.token.expires_at,
        token_prefix=principal.token.token_prefix,
    )


@router.post("/uploads", status_code=status.HTTP_201_CREATED)
async def init_ingest_upload(
    payload: IngestUploadInitRequest,
    http_request: Request,
    response: Response,
    db: Session = Depends(get_db),
    principal: IngestPrincipal = Depends(require_recording_ingest_principal),
) -> dict[str, Any]:
    fields = _validate_ingest_fields(
        db,
        principal,
        external_source=payload.external_source,
        external_id=payload.external_id,
        recorded_at=payload.recorded_at,
        duration_seconds=payload.duration_seconds,
        title=payload.title,
        timezone_name=payload.timezone,
        source_app=payload.source_app,
        metadata=payload.metadata,
        sha256=payload.sha256,
        sha256_required=True,
    )
    assert fields.sha256 is not None
    if payload.total_size <= 0:
        _unprocessable("total_size must be greater than zero")
    if payload.total_size > upload_api.get_max_file_bytes():
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={
                "message": "File is larger than the configured upload limit.",
                "max_file_bytes": upload_api.get_max_file_bytes(),
            },
        )
    filename = _validated_media_filename(payload.filename, payload.content_type)
    existing = _find_session(
        db,
        principal.organization.id,
        fields.external_source,
        fields.external_id,
    )
    if existing is not None:
        response.status_code = status.HTTP_200_OK
        existing_body = _status_response(db, existing)
        return {
            **existing_body.model_dump(),
            "created": False,
        }

    resumable = _find_resumable_ingest_upload(db, principal, fields)
    if resumable is not None:
        response.status_code = status.HTTP_200_OK
        return {
            "upload_id": str(resumable.upload_id),
            "chunk_size": upload_api.DEFAULT_CHUNK_SIZE,
            "total_chunks": int(resumable.total_chunks),
            "received": _received_indices(resumable, principal.organization.slug),
        }

    from services.quotas import check_upload_quota

    check_upload_quota(db, principal.organization, payload.total_size)
    upload_id = uuid.uuid4()
    total_chunks = max(1, math.ceil(payload.total_size / upload_api.DEFAULT_CHUNK_SIZE))
    job = UploadJob(
        organization_id=principal.organization.id,
        user_id=principal.user.id,
        upload_id=upload_id,
        filename=filename,
        content_type=payload.content_type,
        action=INGEST_UPLOAD_ACTION,
        total_size=payload.total_size,
        bytes_received=0,
        chunks_received=0,
        total_chunks=total_chunks,
        stage="uploading",
        progress_pct=0,
        audio_sha256=fields.sha256,
    )
    db.add(job)
    db.commit()
    try:
        job_dir = upload_api._job_dir(principal.organization.slug, str(upload_id))
        job_dir.mkdir(parents=True, exist_ok=True)
        _write_ingest_sidecar(
            principal.organization.slug,
            upload_id,
            _init_sidecar(
                fields,
                filename=filename,
                content_type=payload.content_type,
                total_size=payload.total_size,
                pat_id=principal.token.id,
                client=(http_request.headers.get("user-agent") or "")[:200] or None,
            ),
        )
    except Exception:
        db.rollback()
        db.delete(db.query(UploadJob).filter(UploadJob.upload_id == upload_id).one())
        db.commit()
        _remove_job_dir(principal.organization.slug, upload_id)
        raise
    return {
        "upload_id": str(upload_id),
        "chunk_size": upload_api.DEFAULT_CHUNK_SIZE,
        "total_chunks": total_chunks,
        "received": [],
    }


@router.get("/uploads/{upload_id}")
async def ingest_upload_status(
    upload_id: str,
    db: Session = Depends(get_db),
    principal: IngestPrincipal = Depends(require_recording_ingest_principal),
) -> dict[str, Any]:
    job = _ingest_upload_job(db, principal, upload_id)
    return {
        "upload_id": str(job.upload_id),
        "chunk_size": upload_api.DEFAULT_CHUNK_SIZE,
        "total_chunks": int(job.total_chunks),
        "received": _received_indices(job, principal.organization.slug),
    }


@router.put("/uploads/{upload_id}/chunks/{index}")
async def ingest_upload_chunk(
    upload_id: str,
    index: int,
    request: Request,
    db: Session = Depends(get_db),
    principal: IngestPrincipal = Depends(require_recording_ingest_principal),
) -> dict[str, Any]:
    job = _ingest_upload_job(db, principal, upload_id)
    total_chunks = int(job.total_chunks)
    if index < 0 or index >= total_chunks:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="chunk index is out of range")
    expected_size = upload_api.DEFAULT_CHUNK_SIZE
    if index == total_chunks - 1:
        expected_size = int(job.total_size) - (index * upload_api.DEFAULT_CHUNK_SIZE)
    body = await request.body()
    if len(body) != expected_size:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "chunk has the wrong size",
                "expected_size": expected_size,
                "received_size": len(body),
            },
        )

    chunks_dir = upload_api._job_dir(principal.organization.slug, upload_id) / "chunks"
    chunks_dir.mkdir(parents=True, exist_ok=True)
    target = chunks_dir / f"{index:08d}.part"
    temporary_path = chunks_dir / f".{index:08d}.{uuid.uuid4().hex}.part"
    try:
        temporary_path.write_bytes(body)
        temporary_path.replace(target)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()
    received = _received_indices(job, principal.organization.slug)
    job.chunks_received = len(received)
    job.bytes_received = sum(
        (chunks_dir / f"{chunk_index:08d}.part").stat().st_size
        for chunk_index in received
    )
    job.progress_pct = min(99, int((job.bytes_received / job.total_size) * 100))
    job.updated_at = datetime.now(timezone.utc)
    db.commit()
    return {"received": received}


@router.post(
    "/uploads/{upload_id}/complete",
    response_model=IngestCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def complete_ingest_upload(
    upload_id: str,
    http_request: Request,
    response: Response,
    db: Session = Depends(get_db),
    principal: IngestPrincipal = Depends(require_recording_ingest_principal),
) -> IngestCreateResponse | JSONResponse:
    job = _ingest_upload_job(db, principal, upload_id)
    sidecar = _read_ingest_sidecar(principal.organization.slug, job.upload_id)
    if sidecar is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload not found")
    fields = _fields_from_sidecar(db, principal, sidecar)
    received = _received_indices(job, principal.organization.slug)
    missing = [index for index in range(int(job.total_chunks)) if index not in received]
    if missing:
        return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"missing": missing})

    job_dir = upload_api._job_dir(principal.organization.slug, str(job.upload_id))
    try:
        final_path = upload_api.assemble_chunked_upload(
            job_dir,
            job.filename,
            int(job.total_chunks),
            int(job.total_size),
        )
    except FileNotFoundError:
        received = _received_indices(job, principal.organization.slug)
        missing = [index for index in range(int(job.total_chunks)) if index not in received]
        return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"missing": missing})
    except ValueError:
        _unprocessable("assembled upload size does not match total_size")
    actual_sha256 = await upload_api._sha256_file(final_path)
    if actual_sha256.lower() != str(sidecar.get("sha256", "")).lower():
        _unprocessable("sha256 does not match the received file")

    existing = _find_session(
        db,
        principal.organization.id,
        fields.external_source,
        fields.external_id,
    )
    if existing is not None:
        _discard_ingest_upload(
            db,
            principal.organization.slug,
            principal.organization.id,
            job.upload_id,
        )
        response.status_code = status.HTTP_200_OK
        return _status_response(db, existing, created=False)  # type: ignore[return-value]

    session, created = await _create_ingest_session_and_job(
        db,
        principal,
        fields,
        upload_id=job.upload_id,
        filename=job.filename,
        content_type=job.content_type,
        source_path=final_path,
        file_size=int(job.total_size),
        actual_sha256=actual_sha256,
        client=str(sidecar.get("client") or "")[:200] or None,
        pat_id=(
            int(sidecar["pat_id"])
            if sidecar.get("pat_id") is not None
            else principal.token.id
        ),
        job=job,
    )
    if not created:
        response.status_code = status.HTTP_200_OK
        return _status_response(db, session, created=False)  # type: ignore[return-value]
    await upload_api.upload_pipeline_queue.enqueue(str(job.upload_id))
    return _status_response(
        db,
        session,
        created=True,
        upload_id=str(job.upload_id),
    )  # type: ignore[return-value]


@router.post(
    "/recordings",
    response_model=IngestCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def ingest_recording(
    request: Request,
    response: Response,
    file: UploadFile = File(...),
    external_source: str = Form(...),
    external_id: str = Form(...),
    recorded_at: str = Form(...),
    duration_seconds: Optional[str] = Form(None),
    title: Optional[str] = Form(None),
    timezone_name: Optional[str] = Form(None, alias="timezone"),
    source_app: Optional[str] = Form(None),
    metadata: Optional[str] = Form(None),
    sha256: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    principal: IngestPrincipal = Depends(require_recording_ingest_principal),
) -> IngestCreateResponse:
    fields = _validate_ingest_fields(
        db,
        principal,
        external_source=external_source,
        external_id=external_id,
        recorded_at=recorded_at,
        duration_seconds=duration_seconds,
        title=title,
        timezone_name=timezone_name,
        source_app=source_app,
        metadata=metadata,
        sha256=sha256,
    )
    existing = _find_session(
        db,
        principal.organization.id,
        fields.external_source,
        fields.external_id,
    )
    if existing is not None:
        response.status_code = status.HTTP_200_OK
        return _status_response(db, existing, created=False)  # type: ignore[return-value]

    filename = _validated_media_filename(file.filename, file.content_type)
    upload_id = uuid.uuid4()
    job_dir = upload_api._job_dir(principal.organization.slug, str(upload_id))
    source_path = job_dir / filename
    job_dir.mkdir(parents=True, exist_ok=True)
    try:
        file_size, actual_sha256 = await _store_upload(file, source_path)
        if fields.sha256 is not None and actual_sha256.lower() != fields.sha256:
            _unprocessable("sha256 does not match the received file")
        from services.quotas import check_upload_quota

        check_upload_quota(db, principal.organization, file_size)
        session, created = await _create_ingest_session_and_job(
            db,
            principal,
            fields,
            upload_id=upload_id,
            filename=filename,
            content_type=file.content_type,
            source_path=source_path,
            file_size=file_size,
            actual_sha256=actual_sha256,
            client=(request.headers.get("user-agent") or "")[:200] or None,
        )
    except Exception:
        db.rollback()
        _remove_job_dir(principal.organization.slug, upload_id)
        raise
    if not created:
        _remove_job_dir(principal.organization.slug, upload_id)
        response.status_code = status.HTTP_200_OK
        return _status_response(db, session, created=False)  # type: ignore[return-value]
    await upload_api.upload_pipeline_queue.enqueue(str(upload_id))
    return _status_response(
        db,
        session,
        created=True,
        upload_id=str(upload_id),
    )  # type: ignore[return-value]


@router.get(
    "/recordings/{external_source}/{external_id}",
    response_model=IngestStatusResponse,
)
async def ingest_recording_status(
    external_source: str,
    external_id: str,
    db: Session = Depends(get_db),
    principal: IngestPrincipal = Depends(require_recording_ingest_principal),
) -> IngestStatusResponse:
    session = _find_session(
        db,
        principal.organization.id,
        external_source,
        external_id,
    )
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recording not found")
    return _status_response(db, session)  # type: ignore[return-value]


@router.post(
    "/recordings/{external_source}/{external_id}/retry",
    response_model=IngestRetryResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_ingest_recording(
    external_source: str,
    external_id: str,
    db: Session = Depends(get_db),
    principal: IngestPrincipal = Depends(require_recording_ingest_principal),
) -> IngestRetryResponse:
    session = _find_session(
        db,
        principal.organization.id,
        external_source,
        external_id,
    )
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recording not found")
    job = _job_for_session(db, session)
    if _status_for(session, job) != "failed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only failed recordings can be retried",
        )
    if job is None or job.stage not in {"failed", "cancelled"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Recording has no retryable upload job",
        )
    if (job.retry_count or 0) >= upload_api.MAX_UPLOAD_RETRIES and not principal.user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Upload retry limit reached",
        )
    if not upload_api._job_dir(principal.organization.slug, str(job.upload_id)).exists():
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Upload bytes are no longer on disk; please re-upload",
        )

    session.status = "processing"
    metadata = dict(session.processing_metadata or {})
    for key in ("upload_error", "no_speech", "upload_failed_at"):
        metadata.pop(key, None)
    session.processing_metadata = metadata
    db.commit()
    await upload_api._enqueue_retry_job(db, job)
    logger.info(
        "recording ingest retry pat_id=%s org_id=%s external_source=%s external_id=%s session_id=%s upload_id=%s",
        principal.token.id,
        principal.organization.id,
        external_source,
        external_id,
        session.session_id or session.id,
        job.upload_id,
    )
    return IngestRetryResponse(
        session_id=session.id,
        status="processing",
    )
