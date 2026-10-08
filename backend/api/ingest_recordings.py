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
    parse_iso,
    wall_clock,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ingest", tags=["recording-ingest"])

EXTERNAL_SOURCE_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,63}$")
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
MAX_METADATA_BYTES = 16 * 1024
FILE_READ_CHUNK_SIZE = 1024 * 1024


class IngestStatusResponse(BaseModel):
    session_id: str
    status: Literal["processing", "completed", "failed"]
    meeting_date: Optional[str] = None
    meeting_time: Optional[str] = None
    error: Optional[str] = None


class IngestCreateResponse(IngestStatusResponse):
    upload_id: Optional[str] = None
    created: bool


class IngestRetryResponse(BaseModel):
    session_id: str
    status: Literal["processing"]


class WhoAmIResponse(BaseModel):
    organization_id: int
    organization_slug: str
    organization_name: str
    scope: str
    expires_at: Optional[datetime] = None
    token_prefix: str


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
            "external_source must match ^[a-z0-9][a-z0-9._-]{1,63}$"
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


def _parse_duration(raw: Optional[str]) -> Optional[float]:
    if raw is None or raw == "":
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        _unprocessable("duration_seconds must be a number >= 0")
    if not math.isfinite(value) or value < 0:
        _unprocessable("duration_seconds must be a number >= 0")
    return value


def _parse_metadata(raw: Optional[str]) -> dict[str, str]:
    if raw is None:
        return {}
    if len(raw.encode("utf-8")) > MAX_METADATA_BYTES:
        _unprocessable("metadata must be at most 16 KB")
    try:
        value = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        _unprocessable("metadata must be a JSON object")
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
        "session_id": session.session_id or str(session.id),
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
    external_source = _validate_external_source(external_source)
    external_id = _validate_external_id(external_id)
    recorded_at_utc = _parse_recorded_at(recorded_at)
    duration = _parse_duration(duration_seconds)
    if title is not None and len(title) > 200:
        _unprocessable("title must be at most 200 characters")
    if source_app is not None and len(source_app) > 64:
        _unprocessable("source_app must be at most 64 characters")
    metadata_value = _parse_metadata(metadata)
    if sha256 is not None and not SHA256_RE.fullmatch(sha256):
        _unprocessable("sha256 must be a 64-character hexadecimal digest")
    timezone_value = _resolve_timezone(db, principal.organization.id, timezone_name)

    existing = _find_session(
        db,
        principal.organization.id,
        external_source,
        external_id,
    )
    if existing is not None:
        logger.info(
            "recording ingest duplicate pat_id=%s org_id=%s external_source=%s external_id=%s session_id=%s",
            principal.token.id,
            principal.organization.id,
            external_source,
            external_id,
            existing.session_id or existing.id,
        )
        response.status_code = status.HTTP_200_OK
        return _status_response(db, existing, created=False)  # type: ignore[return-value]

    media_kind = upload_api._detect_kind(file.filename or "", file.content_type)
    if media_kind not in {"audio", "video"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only audio and video files can be ingested.",
        )

    upload_id = uuid.uuid4()
    filename = upload_api._safe_filename(file.filename or "upload.bin")
    job_dir = upload_api._job_dir(principal.organization.slug, str(upload_id))
    source_path = job_dir / filename
    job_dir.mkdir(parents=True, exist_ok=True)
    try:
        file_size, actual_sha256 = await _store_upload(file, source_path)
        if sha256 is not None and actual_sha256.lower() != sha256.lower():
            _unprocessable("sha256 does not match the received file")

        from services.quotas import check_upload_quota

        check_upload_quota(db, principal.organization, file_size)

        now = datetime.now(timezone.utc)
        meeting_date, meeting_time = wall_clock(recorded_at_utc, timezone_value)
        ingest_signal = {
            "value": recorded_at_utc.isoformat(),
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
            "external_source": external_source,
            "external_id": external_id,
            "source_app": source_app,
            "recorded_at": recorded_at_utc.isoformat(),
            "timezone": timezone_value,
            "metadata": metadata_value,
            "pat_id": principal.token.id,
            "client": request.headers.get("user-agent"),
        }
        if duration is not None:
            ingest_metadata["duration_seconds"] = duration

        session = RecordingSession(
            session_id=str(uuid.uuid4()),
            name=(title or upload_api._title_from_filename(filename))[:200],
            title=(title or upload_api._title_from_filename(filename))[:200],
            description=f"Uploaded from {filename}",
            meeting_type="upload",
            created_at=now,
            started_at=recorded_at_utc.replace(tzinfo=None),
            ended_at=(
                recorded_at_utc.replace(tzinfo=None) + timedelta(seconds=duration)
                if duration is not None
                else None
            ),
            meeting_date=meeting_date,
            meeting_time=meeting_time,
            duration=duration or 0,
            status="processing",
            user_id=principal.user.id,
            organization_id=principal.organization.id,
            audio_file=str(source_path),
            source_type="upload",
            external_source=external_source,
            external_id=external_id,
            processing_metadata={
                "upload_id": str(upload_id),
                "audio_sha256": actual_sha256,
                "original_filename": filename,
                "content_type": file.content_type,
                "meeting_provenance": provenance,
                "provenance_probe_file": None,
                "ingest": ingest_metadata,
            },
        )
        db.add(session)
        db.flush()
        job = UploadJob(
            organization_id=principal.organization.id,
            user_id=principal.user.id,
            upload_id=upload_id,
            filename=filename,
            content_type=file.content_type,
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
        db.commit()
        db.refresh(session)
    except IntegrityError:
        db.rollback()
        duplicate = _find_session(
            db,
            principal.organization.id,
            external_source,
            external_id,
        )
        _remove_job_dir(principal.organization.slug, upload_id)
        if duplicate is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Recording identity conflicted with another ingest",
            )
        logger.info(
            "recording ingest race duplicate pat_id=%s org_id=%s external_source=%s external_id=%s session_id=%s",
            principal.token.id,
            principal.organization.id,
            external_source,
            external_id,
            duplicate.session_id or duplicate.id,
        )
        response.status_code = status.HTTP_200_OK
        return _status_response(db, duplicate, created=False)  # type: ignore[return-value]
    except Exception:
        db.rollback()
        _remove_job_dir(principal.organization.slug, upload_id)
        raise

    await upload_api.upload_pipeline_queue.enqueue(str(upload_id))
    logger.info(
        "recording ingest created pat_id=%s org_id=%s external_source=%s external_id=%s session_id=%s upload_id=%s",
        principal.token.id,
        principal.organization.id,
        external_source,
        external_id,
        session.session_id or session.id,
        upload_id,
    )
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
        session_id=session.session_id or str(session.id),
        status="processing",
    )
