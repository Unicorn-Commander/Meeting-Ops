"""Chunked media uploads and pre-recorded meeting processing."""
from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import re
import shutil
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth.dependencies import get_current_organization, get_current_user
from auth.models import User
from auth.organization import ActiveOrganization
from database.database import SessionLocal, get_db
from database.models import RecordingSession, Transcription, UploadJob

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/uploads", tags=["Uploads"])
ws_router = APIRouter(tags=["Uploads"])

DEFAULT_CHUNK_SIZE = 8 * 1024 * 1024
DEFAULT_MAX_FILE_BYTES = 524288000
RECORDINGS_DIR = Path(os.getenv("RECORDINGS_DIR", "/app/recordings"))
UPLOAD_ROOT = RECORDINGS_DIR / "uploads"

AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".opus", ".aac"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi"}
ATTACHABLE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".pdf", ".docx", ".txt", ".md"}
PIPELINE_STAGES = ["queued", "uploading", "extracting", "transcribing", "diarizing", "summarizing", "embedding", "done"]


class UploadStartRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=500)
    total_size: int = Field(gt=0)
    content_type: Optional[str] = None
    action: str
    target_session_id: Optional[str] = None
    # Per-upload pipeline overrides — falls back to org defaults when missing.
    # Schema: services/transcription_options.TranscriptionOptions.
    transcription_options: Optional[dict] = None


class UploadStartResponse(BaseModel):
    upload_id: str
    chunk_size: int
    max_file_bytes: int
    total_chunks: int
    stage: str


class UploadFinalizeResponse(BaseModel):
    job_id: str
    session_id: Optional[int] = None


class UploadStatusResponse(BaseModel):
    upload_id: str
    job_id: str
    filename: str
    stage: str
    progress_pct: int
    error: Optional[str] = None
    session_id: Optional[int] = None
    bytes_received: int
    total_size: int
    received_chunks: int
    total_chunks: int
    last_completed_stage: Optional[str] = None
    retry_count: int = 0


class UploadWebSocketManager:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = {}

    async def connect(self, upload_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.setdefault(upload_id, set()).add(websocket)

    def disconnect(self, upload_id: str, websocket: WebSocket) -> None:
        conns = self._connections.get(upload_id)
        if not conns:
            return
        conns.discard(websocket)
        if not conns:
            self._connections.pop(upload_id, None)

    async def broadcast(self, upload_id: str, payload: dict[str, Any]) -> None:
        conns = list(self._connections.get(upload_id, set()))
        for websocket in conns:
            try:
                await websocket.send_json(payload)
            except Exception:
                self.disconnect(upload_id, websocket)


ws_manager = UploadWebSocketManager()


def get_max_file_bytes() -> int:
    try:
        return int(os.getenv("UPLOAD_MAX_FILE_BYTES", str(DEFAULT_MAX_FILE_BYTES)))
    except ValueError:
        return DEFAULT_MAX_FILE_BYTES


def get_pipeline_concurrency() -> int:
    try:
        return max(1, int(os.getenv("UPLOAD_PIPELINE_CONCURRENCY", "4")))
    except ValueError:
        return 4


def _safe_filename(filename: str) -> str:
    name = Path(filename).name.strip().replace("\x00", "")
    name = re.sub(r"[^A-Za-z0-9._ -]+", "_", name)
    return name[:240] or "upload.bin"


def _job_dir(org_slug: str, upload_id: str) -> Path:
    return UPLOAD_ROOT / org_slug / upload_id


def _detect_kind(filename: str, content_type: Optional[str]) -> str:
    ext = Path(filename).suffix.lower()
    ctype = (content_type or "").lower()
    if ctype.startswith("audio/") or ext in AUDIO_EXTENSIONS:
        return "audio"
    if ctype.startswith("video/") or ext in VIDEO_EXTENSIONS:
        return "video"
    if ext in ATTACHABLE_EXTENSIONS:
        return "attachable"
    return "unknown"


def _title_from_filename(filename: str) -> str:
    stem = Path(filename).stem
    stem = re.sub(r"^(zoom|recording|meeting|audio|video)[ _-]+", "", stem, flags=re.I)
    stem = re.sub(r"(^|[ _-])\d{4}[-_]\d{2}[-_]\d{2}([ _-]|$)", " ", stem)
    stem = re.sub(r"\b\d{8}\b", "", stem)
    words = re.sub(r"[_-]+", " ", stem).strip()
    if not words:
        words = "Uploaded Meeting"
    titled = " ".join(part.capitalize() for part in words.split())
    return titled[:80]


def _created_at_from_filename_or_mtime(path: Path, fallback: datetime) -> datetime:
    match = re.search(r"(\d{4})[-_](\d{2})[-_](\d{2})", path.name)
    if match:
        try:
            return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)), tzinfo=timezone.utc)
        except ValueError:
            pass
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    except OSError:
        return fallback


async def _set_job_state(
    db: Session,
    job: UploadJob,
    *,
    stage: Optional[str] = None,
    progress_pct: Optional[int] = None,
    error_message: Optional[str] = None,
    last_completed_stage: Optional[str] = None,
    session_id: Optional[int] = None,
    commit: bool = True,
) -> None:
    if stage is not None:
        job.stage = stage
    if progress_pct is not None:
        job.progress_pct = max(0, min(100, int(progress_pct)))
    if error_message is not None:
        job.error_message = error_message
    if last_completed_stage is not None:
        job.last_completed_stage = last_completed_stage
    if session_id is not None:
        job.session_id = session_id
    job.updated_at = datetime.now(timezone.utc)
    if commit:
        db.commit()
        db.refresh(job)
    await ws_manager.broadcast(str(job.upload_id), _status_payload(job))


def _status_payload(job: UploadJob) -> dict[str, Any]:
    return {
        "upload_id": str(job.upload_id),
        "job_id": str(job.upload_id),
        "filename": job.filename,
        "stage": job.stage,
        "progress_pct": job.progress_pct or 0,
        "error": job.error_message,
        "session_id": job.session_id,
        "bytes_received": int(job.bytes_received or 0),
        "total_size": int(job.total_size or 0),
        "received_chunks": int(job.chunks_received or 0),
        "total_chunks": int(job.total_chunks or 0),
        "last_completed_stage": job.last_completed_stage,
        "retry_count": job.retry_count or 0,
    }


def _get_job(db: Session, upload_id: str, org_id: int) -> UploadJob:
    try:
        uid = uuid.UUID(upload_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Upload not found")
    job = db.query(UploadJob).filter(
        UploadJob.organization_id == org_id,
        UploadJob.upload_id == uid,
    ).first()
    if not job:
        raise HTTPException(status_code=404, detail="Upload not found")
    return job


class UploadPipelineQueue:
    def __init__(self) -> None:
        self.queue: asyncio.Queue[str] = asyncio.Queue()
        self.workers: list[asyncio.Task] = []
        self.running: dict[str, asyncio.Task] = {}
        self._started = False

    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        for idx in range(get_pipeline_concurrency()):
            self.workers.append(asyncio.create_task(self._worker(idx)))
        logger.info("Upload pipeline queue started with %s workers", len(self.workers))

    async def stop(self) -> None:
        for task in self.workers:
            task.cancel()
        for task in list(self.running.values()):
            task.cancel()
        if self.workers:
            await asyncio.gather(*self.workers, return_exceptions=True)
        self.workers.clear()
        self.running.clear()
        self._started = False

    async def enqueue(self, upload_id: str) -> None:
        await self.queue.put(upload_id)

    def cancel(self, upload_id: str) -> None:
        task = self.running.get(upload_id)
        if task:
            task.cancel()

    async def _worker(self, idx: int) -> None:
        while True:
            upload_id = await self.queue.get()
            task = asyncio.current_task()
            if task:
                self.running[upload_id] = task
            try:
                await run_upload_pipeline(upload_id)
            except asyncio.CancelledError:
                await mark_upload_cancelled(upload_id)
            except Exception as exc:
                logger.exception("Upload worker %s failed for %s: %s", idx, upload_id, exc)
                await mark_upload_failed(upload_id, str(exc))
            finally:
                self.running.pop(upload_id, None)
                self.queue.task_done()


upload_pipeline_queue = UploadPipelineQueue()


async def start_upload_pipeline_queue() -> None:
    await upload_pipeline_queue.start()


async def stop_upload_pipeline_queue() -> None:
    await upload_pipeline_queue.stop()


async def cleanup_stale_uploads() -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    db = SessionLocal()
    try:
        stale = db.query(UploadJob).filter(
            UploadJob.stage.in_(["uploading", "queued", "failed", "cancelled"]),
            UploadJob.updated_at < cutoff,
        ).all()
        for job in stale:
            shutil.rmtree(_job_dir(_org_slug_for_job(db, job), str(job.upload_id)), ignore_errors=True)
        if stale:
            logger.info("Cleaned %s stale upload directories", len(stale))
    finally:
        db.close()


def _org_slug_for_job(db: Session, job: UploadJob) -> str:
    from auth.models import Organization
    org = db.query(Organization).filter(Organization.id == job.organization_id).first()
    return org.slug if org else str(job.organization_id)


@router.post("/start", response_model=UploadStartResponse)
async def start_upload(
    request: UploadStartRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
):
    if request.action not in {"transcribe", "attach"}:
        raise HTTPException(status_code=400, detail="action must be 'transcribe' or 'attach'.")

    # Per-org tier quota check (file size, concurrent uploads, monthly hours).
    # Raises HTTPException(402/429) with a structured detail payload so the
    # frontend can show a useful upsell when the user hits a tier ceiling.
    from services.quotas import check_upload_quota
    check_upload_quota(db, active_org.organization, request.total_size)

    # Host-level hard cap (env-tunable). Enforces a global ceiling on top of
    # the tier limits — useful when an operator wants to keep total per-host
    # bandwidth bounded regardless of org tier.
    max_file_bytes = get_max_file_bytes()
    if request.total_size > max_file_bytes:
        raise HTTPException(
            status_code=413,
            detail={
                "message": f"File is larger than the configured upload limit of {max_file_bytes} bytes.",
                "max_file_bytes": max_file_bytes,
            },
        )

    kind = _detect_kind(request.filename, request.content_type)
    if request.action == "transcribe" and kind not in {"audio", "video"}:
        raise HTTPException(status_code=400, detail="Only audio and video files can be transcribed.")

    target_session = None
    if request.action == "attach":
        if not request.target_session_id:
            raise HTTPException(status_code=400, detail="target_session_id is required for attach uploads.")
        target_session = _find_session(db, request.target_session_id, active_org.organization.id)
        if not target_session:
            raise HTTPException(status_code=404, detail="Target session not found in active organization.")

    # Validate + normalize per-upload transcription options. Bad values
    # raise 422 with field-level detail (Pydantic). None means "use org
    # defaults", which the pipeline workers handle naturally.
    options_payload: Optional[dict] = None
    if request.transcription_options:
        from services.transcription_options import TranscriptionOptions
        options_payload = TranscriptionOptions(**request.transcription_options).to_jsonb()

    upload_id = uuid.uuid4()
    total_chunks = max(1, math.ceil(request.total_size / DEFAULT_CHUNK_SIZE))
    job = UploadJob(
        organization_id=active_org.organization.id,
        user_id=current_user.id,
        upload_id=upload_id,
        filename=_safe_filename(request.filename),
        content_type=request.content_type,
        action=request.action,
        total_size=request.total_size,
        total_chunks=total_chunks,
        stage="uploading",
        progress_pct=0,
        session_id=target_session.id if target_session else None,
        transcription_options=options_payload,
    )
    db.add(job)
    db.commit()
    _job_dir(active_org.organization.slug, str(upload_id)).mkdir(parents=True, exist_ok=True)

    return UploadStartResponse(
        upload_id=str(upload_id),
        chunk_size=DEFAULT_CHUNK_SIZE,
        max_file_bytes=max_file_bytes,
        total_chunks=total_chunks,
        stage="uploading",
    )


@router.get("/quotas")
async def get_quota_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
):
    """Snapshot of the active org's quota usage and tier limits.

    Returns the data the frontend needs to show usage bars + upsell prompts
    before a user even attempts an upload. Pure read: no quota enforcement
    happens here, only at /uploads/start.
    """
    from services.quotas import get_usage
    return get_usage(db, active_org.organization)


@router.post("/{upload_id}/chunk")
async def upload_chunk(
    upload_id: str,
    chunk_index: int = Form(...),
    data: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
):
    job = _get_job(db, upload_id, active_org.organization.id)
    if job.user_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Upload belongs to another user.")
    if job.stage not in {"uploading", "queued"}:
        raise HTTPException(status_code=409, detail=f"Upload is already {job.stage}.")
    if chunk_index < 0 or chunk_index >= job.total_chunks:
        raise HTTPException(status_code=400, detail="chunk_index is out of range.")

    chunks_dir = _job_dir(active_org.organization.slug, upload_id) / "chunks"
    chunks_dir.mkdir(parents=True, exist_ok=True)
    target = chunks_dir / f"{chunk_index:08d}.part"
    body = await data.read()
    if not body:
        raise HTTPException(status_code=400, detail="Empty chunk.")
    target.write_bytes(body)

    files = list(chunks_dir.glob("*.part"))
    job.chunks_received = len(files)
    job.bytes_received = sum(p.stat().st_size for p in files)
    job.progress_pct = min(99, int((job.bytes_received / job.total_size) * 100))
    job.updated_at = datetime.now(timezone.utc)
    db.commit()
    await ws_manager.broadcast(upload_id, _status_payload(job))
    return {"received_chunks": job.chunks_received, "total_chunks": job.total_chunks}


@router.post("/{upload_id}/finalize", response_model=UploadFinalizeResponse)
async def finalize_upload(
    upload_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
):
    job = _get_job(db, upload_id, active_org.organization.id)
    if job.user_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Upload belongs to another user.")
    if job.chunks_received != job.total_chunks:
        raise HTTPException(status_code=400, detail="Not all chunks have been received.")

    base_dir = _job_dir(active_org.organization.slug, upload_id)
    chunks_dir = base_dir / "chunks"
    final_path = base_dir / job.filename
    with final_path.open("wb") as out:
        for idx in range(job.total_chunks):
            chunk = chunks_dir / f"{idx:08d}.part"
            if not chunk.exists():
                raise HTTPException(status_code=400, detail=f"Missing chunk {idx}.")
            with chunk.open("rb") as inp:
                shutil.copyfileobj(inp, out)

    actual_size = final_path.stat().st_size
    if actual_size != job.total_size:
        raise HTTPException(status_code=400, detail=f"Size mismatch: expected {job.total_size}, got {actual_size}.")

    # Both transcribe (new session) and attach (existing session) flow through
    # the same processing pipeline; run_upload_pipeline branches on job.action
    # to either create a new RecordingSession or reuse the target one.
    job.stage = "queued"
    job.progress_pct = 0
    job.error_message = None
    job.job_started_at = None
    db.commit()
    await ws_manager.broadcast(upload_id, _status_payload(job))
    await upload_pipeline_queue.enqueue(upload_id)
    return UploadFinalizeResponse(job_id=upload_id, session_id=job.session_id)


@router.get("/{upload_id}/status", response_model=UploadStatusResponse)
async def get_upload_status(
    upload_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
):
    job = _get_job(db, upload_id, active_org.organization.id)
    if job.user_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Upload belongs to another user.")
    return UploadStatusResponse(**_status_payload(job))


@router.delete("/{upload_id}")
async def cancel_upload(
    upload_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
):
    job = _get_job(db, upload_id, active_org.organization.id)
    if job.user_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Upload belongs to another user.")
    upload_pipeline_queue.cancel(upload_id)
    job.stage = "cancelled"
    job.progress_pct = 0
    job.job_completed_at = datetime.now(timezone.utc)
    job.updated_at = datetime.now(timezone.utc)
    if job.session_id:
        session = db.query(RecordingSession).filter(
            RecordingSession.id == job.session_id,
            RecordingSession.organization_id == active_org.organization.id,
        ).first()
        if session and session.status != "completed":
            db.query(Transcription).filter(Transcription.session_id == session.id).delete()
            db.delete(session)
            job.session_id = None
    db.commit()
    shutil.rmtree(_job_dir(active_org.organization.slug, upload_id), ignore_errors=True)
    await ws_manager.broadcast(upload_id, _status_payload(job))
    return {"status": "cancelled"}


MAX_UPLOAD_RETRIES = int(os.getenv("UPLOAD_MAX_RETRIES", "3"))


@router.post("/{upload_id}/retry", response_model=UploadStatusResponse)
async def retry_upload(
    upload_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
):
    """Re-queue a failed or cancelled upload through the processing pipeline.

    The chunked file bytes still live on disk under uploads/<org>/<upload_id>/
    until cancellation tears them down. Retry skips the upload phase entirely
    and re-runs extraction → transcription → diarization → summary → embed.
    Capped at UPLOAD_MAX_RETRIES (default 3); the cap can be raised by a
    superuser via the ?force=true query param.
    """
    job = _get_job(db, upload_id, active_org.organization.id)
    if job.user_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Upload belongs to another user.")

    if job.stage not in ("failed", "cancelled"):
        raise HTTPException(
            status_code=409,
            detail=f"Upload is in stage '{job.stage}'; only failed or cancelled uploads can be retried.",
        )

    if (job.retry_count or 0) >= MAX_UPLOAD_RETRIES and not current_user.is_superuser:
        raise HTTPException(
            status_code=429,
            detail=f"Upload has been retried {job.retry_count} times (cap {MAX_UPLOAD_RETRIES}). "
            "Contact an administrator to retry further.",
        )

    job_dir = _job_dir(active_org.organization.slug, upload_id)
    if not job_dir.exists():
        raise HTTPException(
            status_code=410,
            detail="Upload bytes are no longer on disk; please re-upload.",
        )

    job.stage = "queued"
    job.progress_pct = 0
    job.error_message = None
    job.last_completed_stage = None
    job.retry_count = (job.retry_count or 0) + 1
    job.job_started_at = None
    job.job_completed_at = None
    job.updated_at = datetime.now(timezone.utc)
    db.commit()

    await ws_manager.broadcast(upload_id, _status_payload(job))
    await upload_pipeline_queue.enqueue(upload_id)

    logger.info(
        f"Upload {upload_id} retry #{job.retry_count} enqueued by user {current_user.id} (org {active_org.organization.slug})"
    )
    return UploadStatusResponse(**_status_payload(job))


class ReprocessRequest(BaseModel):
    """Body for the reprocess endpoint — same options as a fresh upload."""
    transcription_options: Optional[dict] = None


@router.post("/sessions/{session_id}/reprocess", response_model=UploadStatusResponse)
async def reprocess_session(
    session_id: str,
    request: ReprocessRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
):
    """Re-run the transcription / diarization / summarization / embedding
    pipeline against an existing session's audio file.

    Reuses the chunked-upload UploadJob shape so the frontend's existing
    progress + retry tray surfaces the work uniformly. The audio bytes are
    NOT re-uploaded — we point a synthetic UploadJob at the session's
    existing audio path on disk.

    Accepts either the UUID `session_id` column or the integer primary key
    so callers can use whichever they already have in hand. Mirrors the
    lookup pattern used by ai_chat and other session-scoped endpoints.
    """
    rec = (
        db.query(RecordingSession)
        .filter(
            RecordingSession.session_id == session_id,
            RecordingSession.organization_id == active_org.organization.id,
        )
        .first()
    )
    if not rec:
        # Fall back to integer primary key lookup for older frontend paths
        # that pass the numeric id.
        try:
            pk = int(session_id)
        except (TypeError, ValueError):
            pk = None
        if pk is not None:
            rec = (
                db.query(RecordingSession)
                .filter(
                    RecordingSession.id == pk,
                    RecordingSession.organization_id == active_org.organization.id,
                )
                .first()
            )
    if not rec:
        raise HTTPException(status_code=404, detail="Session not found in active organization.")
    if not rec.audio_file or not Path(rec.audio_file).exists():
        raise HTTPException(status_code=410, detail="Session audio file is not on disk; cannot reprocess.")

    # Invalidate the cached ai_insights so the next /insights GET re-extracts
    # against the new transcript/diarization. The pipeline also overwrites
    # summary fields when it completes, but ai_insights lives separately.
    rec.ai_insights = None
    db.commit()

    # Validate options early.
    options_payload: Optional[dict] = None
    if request.transcription_options:
        from services.transcription_options import TranscriptionOptions
        options_payload = TranscriptionOptions(**request.transcription_options).to_jsonb()

    # Park the existing audio under a fresh upload_id directory so the
    # pipeline's source-of-truth path matches the chunked flow's layout.
    job_id = uuid.uuid4()
    job_dir = _job_dir(active_org.organization.slug, str(job_id))
    job_dir.mkdir(parents=True, exist_ok=True)
    src_audio = Path(rec.audio_file)
    parked = job_dir / src_audio.name
    if not parked.exists():
        try:
            os.symlink(src_audio.resolve(), parked)
        except OSError:
            shutil.copy2(src_audio, parked)

    job = UploadJob(
        organization_id=active_org.organization.id,
        user_id=current_user.id,
        upload_id=job_id,
        filename=src_audio.name,
        content_type="application/octet-stream",
        action="attach",
        total_size=src_audio.stat().st_size,
        bytes_received=src_audio.stat().st_size,
        chunks_received=1,
        total_chunks=1,
        stage="queued",
        progress_pct=0,
        session_id=rec.id,
        transcription_options=options_payload,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    await ws_manager.broadcast(str(job_id), _status_payload(job))
    await upload_pipeline_queue.enqueue(str(job_id))
    logger.info(
        f"Reprocess enqueued for session {session_id} (job {job_id}) by user {current_user.id} "
        f"(org {active_org.organization.slug}) with options={options_payload}"
    )
    return UploadStatusResponse(**_status_payload(job))


async def mark_upload_cancelled(upload_id: str) -> None:
    db = SessionLocal()
    try:
        job = db.query(UploadJob).filter(UploadJob.upload_id == uuid.UUID(upload_id)).first()
        if job:
            job.stage = "cancelled"
            job.job_completed_at = datetime.now(timezone.utc)
            job.updated_at = datetime.now(timezone.utc)
            db.commit()
            await ws_manager.broadcast(upload_id, _status_payload(job))
    finally:
        db.close()


async def mark_upload_failed(upload_id: str, error: str) -> None:
    db = SessionLocal()
    try:
        job = db.query(UploadJob).filter(UploadJob.upload_id == uuid.UUID(upload_id)).first()
        if job:
            job.stage = "failed"
            job.error_message = error[:2000]
            job.job_completed_at = datetime.now(timezone.utc)
            job.updated_at = datetime.now(timezone.utc)
            db.commit()
            await ws_manager.broadcast(upload_id, _status_payload(job))
    finally:
        db.close()


async def run_upload_pipeline(upload_id: str) -> None:
    db = SessionLocal()
    try:
        job = db.query(UploadJob).filter(UploadJob.upload_id == uuid.UUID(upload_id)).first()
        if not job or job.stage == "cancelled":
            return
        org_slug = _org_slug_for_job(db, job)
        base_dir = _job_dir(org_slug, upload_id)
        source_path = base_dir / job.filename
        if not source_path.exists() or source_path.stat().st_size == 0:
            raise RuntimeError("Uploaded file is missing or empty.")
        if source_path.stat().st_size > get_max_file_bytes():
            raise RuntimeError(f"File exceeds upload limit of {get_max_file_bytes()} bytes.")

        job.job_started_at = datetime.now(timezone.utc)
        await _set_job_state(db, job, stage="queued", progress_pct=1, commit=True)

        media_kind = _detect_kind(job.filename, job.content_type)
        if media_kind not in {"audio", "video"}:
            raise RuntimeError("Unsupported media format for transcription.")

        # Always normalize to 16 kHz mono PCM WAV before handing off to the
        # STT provider. whisper.cpp's HTTP server can decode m4a/mp3 internally
        # but it is strictly faster + more reliable on a pre-extracted WAV,
        # and the wav file size gives the timeout heuristic an accurate
        # signal (compressed audio MB/min lies about real duration). The
        # extra ffmpeg pass is cheap (~1.4 kx realtime in practice).
        audio_path = base_dir / "extracted.wav"
        if not audio_path.exists() or audio_path.stat().st_size == 0:
            await _set_job_state(db, job, stage="extracting", progress_pct=3)
            await _extract_audio(source_path, audio_path, upload_id, db, job)
            await _set_job_state(db, job, progress_pct=100, last_completed_stage="extracting")

        # Materialize per-upload preferences. Empty / None object = use the
        # active org's saved settings end-to-end.
        from services.transcription_options import coerce_options
        opts = coerce_options(job.transcription_options)

        session = await _resolve_session_for_job(db, job, audio_path)
        await _set_job_state(db, job, stage="transcribing", progress_pct=5, session_id=session.id)
        transcription_result = await _transcribe_audio(
            audio_path,
            session.organization_id,
            db,
            provider_override=opts.stt_provider,
            model_override=opts.stt_model,
            language=opts.language or "en",
        )
        await _persist_transcription(db, session, transcription_result)
        await _set_job_state(db, job, progress_pct=100, last_completed_stage="transcribing")

        # Diarization. Honor explicit off / manual count overrides; auto is
        # the default when the option is missing.
        if (opts.diarization_mode or "auto") != "off":
            await _set_job_state(db, job, stage="diarizing", progress_pct=10)
            num_speakers = (
                opts.diarization_num_speakers
                if opts.diarization_mode == "manual"
                else None
            )
            try:
                # 1) Run speaker-svc diarization to get speaker segments
                from services.providers.registry import get_provider_registry
                diar_registry = get_provider_registry(db)
                diar_provider = diar_registry.get_diarization(session.organization_id)
                diar_segments = await diar_provider.diarize(
                    str(audio_path),
                    num_speakers=num_speakers,
                )
                # 2) Merge labels onto the transcription segments + persist
                if diar_segments:
                    _assign_speakers_from_diarization(session, diar_segments)
                    db.commit()
                # 3) Optionally enrich with library matches (voice fingerprinting)
                fingerprint_enabled = (
                    True if opts.voice_fingerprint is None
                    else bool(opts.voice_fingerprint)
                )
                if fingerprint_enabled:
                    from services.speaker_service import identify_speakers
                    await asyncio.to_thread(identify_speakers, session, db)
            except Exception as exc:
                logger.warning("Speaker diarization/identification failed for upload %s: %s", upload_id, exc)
            await _set_job_state(db, job, progress_pct=100, last_completed_stage="diarizing")

        await _set_job_state(db, job, stage="summarizing", progress_pct=10)
        await _summarize_session(
            db,
            session,
            template=opts.summary_template or "standard",
            llm_model=opts.llm_model,
            llm_thinking=opts.llm_thinking,
        )
        await _set_job_state(db, job, progress_pct=100, last_completed_stage="summarizing")

        await _set_job_state(db, job, stage="embedding", progress_pct=10)
        try:
            from services.meeting_embeddings import embed_meeting
            await asyncio.to_thread(embed_meeting, session, db)
        except Exception as exc:
            logger.warning("Meeting embedding failed for upload %s: %s", upload_id, exc)

        session.status = "completed"
        session.updated_at = datetime.now(timezone.utc)
        job.stage = "done"
        job.progress_pct = 100
        job.last_completed_stage = "done"
        job.job_completed_at = datetime.now(timezone.utc)
        job.updated_at = datetime.now(timezone.utc)
        db.commit()
        await ws_manager.broadcast(upload_id, _status_payload(job))
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        db.rollback()
        job = db.query(UploadJob).filter(UploadJob.upload_id == uuid.UUID(upload_id)).first()
        if job:
            job.stage = "failed"
            job.error_message = str(exc)[:2000]
            job.job_completed_at = datetime.now(timezone.utc)
            job.updated_at = datetime.now(timezone.utc)
            db.commit()
            await ws_manager.broadcast(upload_id, _status_payload(job))
        raise
    finally:
        db.close()


async def _extract_audio(source_path: Path, audio_path: Path, upload_id: str, db: Session, job: UploadJob) -> None:
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-y", "-i", str(source_path), "-vn", "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(audio_path),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    stderr = []
    while True:
        line = await proc.stderr.readline() if proc.stderr else b""
        if not line:
            break
        text = line.decode(errors="ignore")
        stderr.append(text)
        match = re.search(r"time=(\d+):(\d+):(\d+(?:\.\d+)?)", text)
        if match:
            seconds = int(match.group(1)) * 3600 + int(match.group(2)) * 60 + float(match.group(3))
            pct = min(95, int(seconds))
            await _set_job_state(db, job, progress_pct=pct)
    code = await proc.wait()
    if code != 0 or not audio_path.exists():
        raise RuntimeError("Audio extraction failed: " + "".join(stderr)[-500:])


async def _create_upload_session(db: Session, job: UploadJob, audio_path: Path) -> RecordingSession:
    created_at = _created_at_from_filename_or_mtime(audio_path, datetime.now(timezone.utc))
    session = RecordingSession(
        session_id=str(uuid.uuid4()),
        name=_title_from_filename(job.filename),
        title=_title_from_filename(job.filename),
        description=f"Uploaded from {job.filename}",
        meeting_type="upload",
        created_at=created_at,
        started_at=created_at,
        status="processing",
        user_id=job.user_id,
        organization_id=job.organization_id,
        audio_file=str(audio_path),
        source_type="upload",
        processing_metadata={
            "upload_id": str(job.upload_id),
            "original_filename": job.filename,
            "content_type": job.content_type,
        },
    )
    db.add(session)
    db.flush()
    job.session_id = session.id
    db.commit()
    db.refresh(session)
    return session


async def _attach_to_existing_session(db: Session, job: UploadJob, audio_path: Path) -> RecordingSession:
    """Bind the uploaded audio onto a pre-existing RecordingSession.

    The session row was selected at /uploads/start and its id stored on
    job.session_id. We update the audio path, mark it processing, and let the
    pipeline transcribe / diarize / summarize / embed exactly as it would for
    a brand-new upload — so attach gets the same provider-resolved STT and
    LLM as any other upload, instead of going through the legacy NPU-first
    path the old api/audio_upload.py used.
    """
    if not job.session_id:
        raise RuntimeError("attach upload has no target_session_id on the job row.")
    session = (
        db.query(RecordingSession)
        .filter(
            RecordingSession.id == job.session_id,
            RecordingSession.organization_id == job.organization_id,
        )
        .first()
    )
    if not session:
        raise RuntimeError(f"target session {job.session_id} not found in org {job.organization_id}.")

    session.audio_file = str(audio_path)
    session.status = "processing"
    session.updated_at = datetime.now(timezone.utc)
    metadata = dict(session.processing_metadata or {})
    metadata.update({
        "attached_upload_id": str(job.upload_id),
        "attached_filename": job.filename,
        "attached_content_type": job.content_type,
        "attached_at": datetime.now(timezone.utc).isoformat(),
    })
    session.processing_metadata = metadata
    db.commit()
    db.refresh(session)
    return session


async def _resolve_session_for_job(db: Session, job: UploadJob, audio_path: Path) -> RecordingSession:
    """Branch on job.action: attach reuses the target session, transcribe creates a new one."""
    if job.action == "attach":
        return await _attach_to_existing_session(db, job, audio_path)
    return await _create_upload_session(db, job, audio_path)


async def _transcribe_audio(
    audio_path: Path,
    org_id: int,
    db: Session,
    *,
    provider_override: Optional[str] = None,
    model_override: Optional[str] = None,
    language: str = "en",
) -> dict[str, Any]:
    """Transcribe via the configured STT provider (Whisper or Parakeet).

    Diarization runs separately after this step. The provider is resolved
    through ProviderRegistry; per-upload overrides win over the org's
    saved Provider Settings so a single recording can route through
    Parakeet while the org default stays Whisper (or vice versa).
    """
    from services.providers.registry import get_provider_registry
    from services.transcription_options import normalized_provider_name, TranscriptionOptions
    registry = get_provider_registry(db)
    norm_provider = normalized_provider_name(
        TranscriptionOptions(stt_provider=provider_override) if provider_override else TranscriptionOptions()
    )
    stt = registry.get_stt(
        org_id,
        provider_override=norm_provider,
        model_override=model_override,
    )
    result = await asyncio.wait_for(stt.transcribe(str(audio_path), language=language), timeout=1800)
    if not result or not result.get("segments"):
        raise RuntimeError("Transcription produced no segments.")
    # _persist_transcription expects audio_duration; the providers return
    # `duration` directly, so mirror it for back-compat.
    result.setdefault("audio_duration", result.get("duration", 0.0))
    result.setdefault("model", "whisper.cpp-large-v3-turbo")
    return result


def _assign_speakers_from_diarization(session: RecordingSession, diar_segments: list[dict]) -> None:
    """Merge diarization output onto the transcription segments.

    For each transcription segment, pick the diarization speaker that
    covers the most of its [start, end] interval. Updates the JSONB
    `transcript_diarized.segments` and the rows in the `transcriptions`
    table. Idempotent — safe to re-run on re-process.
    """
    if not diar_segments:
        return
    transcript = session.transcript_diarized
    if not isinstance(transcript, dict):
        return
    segments = transcript.get("segments") or []
    if not segments:
        return

    # Sort diarization segments once; use a small linear scan per segment
    # since both lists are usually <500 items.
    diar_sorted = sorted(diar_segments, key=lambda s: float(s.get("start") or 0))

    def _label_for(seg_start: float, seg_end: float) -> Optional[str]:
        best_label: Optional[str] = None
        best_overlap = 0.0
        for d in diar_sorted:
            d_start = float(d.get("start") or 0)
            d_end = float(d.get("end") or 0)
            if d_end < seg_start:
                continue
            if d_start > seg_end:
                break
            overlap = max(0.0, min(seg_end, d_end) - max(seg_start, d_start))
            if overlap > best_overlap:
                best_overlap = overlap
                best_label = d.get("speaker")
        return best_label

    for seg in segments:
        start = float(seg.get("start") or 0)
        end = float(seg.get("end") or 0)
        label = _label_for(start, end)
        if label:
            seg["speaker"] = label

    transcript["segments"] = segments
    transcript["diarization_backend"] = (
        diar_sorted[0].get("backend") if diar_sorted else None
    )
    session.transcript_diarized = transcript

    # Also rewrite the per-segment Transcription rows so list/detail views
    # render speaker labels even when they don't go through transcript_diarized.
    from sqlalchemy.orm.session import Session as _SAS  # local import to avoid module cycle
    db: Optional[_SAS] = getattr(session, "_sa_instance_state", None) and session._sa_instance_state.session  # type: ignore[union-attr]
    if db is None:
        return
    rows = db.query(Transcription).filter(Transcription.session_id == session.id).all()
    for row in rows:
        label = _label_for(float(row.start_time or 0), float(row.end_time or 0))
        if label:
            row.speaker = label


async def _persist_transcription(db: Session, session: RecordingSession, result: dict[str, Any]) -> None:
    segments = result.get("segments", [])
    session.transcript_diarized = result
    session.transcript_simple = " ".join(s.get("text", "") for s in segments if s.get("text")).strip()
    session.transcript = json.dumps(result)
    audio_duration = result.get("audio_duration") or max((float(s.get("end", 0)) for s in segments), default=0)
    session.duration = float(audio_duration or 0)
    db.query(Transcription).filter(Transcription.session_id == session.id).delete()
    for segment in segments:
        text = (segment.get("text") or "").strip()
        if not text:
            continue
        db.add(Transcription(
            session_id=session.id,
            text=text,
            speaker=segment.get("speaker"),
            start_time=float(segment.get("start") or 0),
            end_time=float(segment.get("end") or 0),
            confidence=float(segment.get("confidence") or 0.95),
        ))
    metadata = session.processing_metadata or {}
    metadata.update({
        "word_count": len((session.transcript_simple or "").split()),
        "transcription_model": result.get("model", "whisper"),
        "transcription_language": result.get("language", "en"),
        "npu_accelerated": result.get("npu_accelerated", False),
        "processing_started_from_upload": True,
    })
    # Word-level timestamps: only Parakeet provides these natively. Store
    # them separately so the frontend can render word-by-word highlighting
    # without the segment-level renderer having to know about them.
    word_timestamps = result.get("words") or []
    if word_timestamps:
        metadata["word_timestamps"] = word_timestamps
        metadata["has_word_timestamps"] = True
    rtf = result.get("rtf")
    if rtf is not None:
        metadata["transcription_rtf"] = rtf
    session.processing_metadata = metadata
    db.commit()
    db.refresh(session)


_SUMMARY_TEMPLATE_GUIDANCE: dict[str, str] = {
    "standard": (
        "Produce a balanced meeting summary covering main topics, key "
        "decisions, action items, and follow-ups. Keep tone neutral and "
        "useful for someone who missed the meeting."
    ),
    "executive": (
        "Produce an executive-style summary: lead with strategic implications "
        "and decisions, then action items with owners, then a one-line "
        "recap. Skip routine status updates."
    ),
    "technical": (
        "Produce a technical summary: architecture/design decisions, "
        "implementation details, technical debt mentioned, dependencies and "
        "blockers, then action items. Keep code/system terms verbatim."
    ),
}


# When MEETING_OPS_SUMMARIZER_URL is set, the upload pipeline's summary step
# routes directly there instead of through the per-org ProviderRegistry/
# LiteLLM gateway. Keeps the hop count low (fewer things to debug) and lets
# us reuse the Qwen3.6-35B-A3B-Vision instance already loaded for David's
# listing-ops flow on midboy1:8088. v1 only — long-term this should fold
# back into ProviderRegistry for unified usage metering and per-org auth.
MEETING_OPS_SUMMARIZER_SYSTEM_PROMPT = """You are the meeting-ops-summarizer.

Given a meeting transcript with speaker labels and timestamps, produce:

1. **Executive summary** — 3-5 sentences. What was this meeting about, what was the outcome.
2. **Decisions made** — bullet list. Format: "decision (decided by Speaker)".
3. **Action items** — bullet list. Format: "Owner: action by deadline if specified".
   If no owner or deadline mentioned, say so explicitly.
4. **Open questions** — bullet list of things raised but not resolved.

Writing rules:
- No em-dashes. Use commas, periods, or two sentences.
- Casual professional tone. Not corporate, not pitch-y.
- Don't fabricate. If a section is empty, write "none" rather than inventing.
- If the transcript is unclear at any point, say so rather than guessing.
- Quote sparingly only when exact wording matters.

After the human-readable sections, emit a final fenced JSON block with the
same content split into keys executive (string), decisions (array of
strings), actions (array of {action,owner,priority}), questions (array of
strings), title (short string). The fenced block looks like:

```json
{"executive": "...", "decisions": [...], "actions": [...], "questions": [...], "title": "..."}
```
"""


def _direct_summarizer_provider():
    """Build a LiteLLMProvider pointing at the direct meeting-ops LLM
    endpoint, or return None when no env is configured (caller falls back
    to ProviderRegistry).

    Prefers MEETING_OPS_LLM_URL (the broader knob that ProviderRegistry
    also reads). Falls back to MEETING_OPS_SUMMARIZER_URL for backward
    compat with the earlier deploy that only had a summarizer-specific
    override.
    """
    base = os.getenv("MEETING_OPS_LLM_URL", "").strip() or os.getenv("MEETING_OPS_SUMMARIZER_URL", "").strip()
    model = os.getenv("MEETING_OPS_LLM_MODEL", "").strip() or os.getenv("MEETING_OPS_SUMMARIZER_MODEL", "").strip()
    if not base or not model:
        return None
    from services.providers.impl_llm import LiteLLMProvider
    return LiteLLMProvider(
        api_key=os.getenv("MEETING_OPS_LLM_API_KEY", "") or os.getenv("MEETING_OPS_SUMMARIZER_API_KEY", ""),
        endpoint=base,
        model=model,
        thinking=False,  # Qwen 3.6 emits <think> by default; suppress.
    )



_FENCED_JSON_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
_BARE_JSON_RE = re.compile(r"(\{(?:[^{}]|\{[^{}]*\})*\})", re.DOTALL)


def _parse_summarizer_json(text: str, *, fallback_title: str) -> dict[str, Any]:
    """Pull the JSON object the summarizer was asked to emit.

    Qwen 3.6 emits prose then a ```json fenced block; older models return
    bare JSON. Try fenced first, then bare, then surface the raw text as
    the executive summary so the rest of the pipeline still gets
    something readable.
    """
    text = text or ""
    for pattern in (_FENCED_JSON_RE, _BARE_JSON_RE):
        for match in pattern.finditer(text):
            blob = match.group(1)
            try:
                data = json.loads(blob)
            except Exception:
                continue
            if isinstance(data, dict):
                return data
    return {
        "executive": text.strip() or "Summary generation returned no content.",
        "bullets": [],
        "actions": [],
        "decisions": [],
        "title": fallback_title,
    }


async def _summarize_session(
    db: Session,
    session: RecordingSession,
    *,
    template: str = "standard",
    llm_model: Optional[str] = None,
    llm_thinking: Optional[bool] = None,
) -> None:
    transcript = session.transcript_simple or ""
    if not transcript.strip():
        session.summary = json.dumps({"executive": "No transcript text was available.", "bullets": [], "actions": [], "decisions": []})
        db.commit()
        return

    style = _SUMMARY_TEMPLATE_GUIDANCE.get(template, _SUMMARY_TEMPLATE_GUIDANCE["standard"])

    # Per-upload override wins, then env-configured direct route, then the
    # org's ProviderRegistry default.
    direct = None if llm_model else _direct_summarizer_provider()
    if direct is not None:
        llm = direct
        # Use the deploy-doc system prompt verbatim when on the direct
        # route — that's the prompt David and Aaron specced for the
        # midboy1:8088 Qwen path.
        system_prompt = MEETING_OPS_SUMMARIZER_SYSTEM_PROMPT
    else:
        from services.providers.registry import get_provider_registry
        registry = get_provider_registry(db)
        llm = registry.get_llm(
            session.organization_id,
            task="quality",
            model_override=llm_model,
            thinking_override=llm_thinking,
        )
        system_prompt = (
            f"You are a meeting analyst. {style} Produce concise, useful meeting summaries."
        )

    prompt = (
        f"{style}\n\n"
        "Return strict JSON with keys executive, bullets, actions, decisions, title. "
        "actions should be an array of objects with action, owner, priority when known.\n\n"
        f"Transcript:\n{transcript[:24000]}"
    )
    text = await asyncio.wait_for(
        llm.chat(
            system_prompt=system_prompt,
            user_prompt=prompt,
            max_tokens=2000,
            temperature=0.2,
        ),
        timeout=240,
    )
    analysis = _parse_summarizer_json(text, fallback_title=session.title or "")
    session.summary = json.dumps(analysis)
    session.final_summary = {
        "executive": analysis.get("executive", ""),
        "bullets": analysis.get("bullets", []),
        "actions": analysis.get("actions", []),
        "decisions": analysis.get("decisions", []),
        "title": analysis.get("title", session.title),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    session.ai_insights = analysis
    new_title = analysis.get("title")
    if isinstance(new_title, str):
        new_title = new_title.strip()
        if new_title and new_title.lower() not in {"untitled", "meeting", "recording"}:
            session.title = new_title[:200]
    db.commit()
    db.refresh(session)


def _find_session(db: Session, session_id: str, org_id: int) -> Optional[RecordingSession]:
    query = db.query(RecordingSession).filter(RecordingSession.organization_id == org_id)
    session = query.filter(RecordingSession.session_id == session_id).first()
    if session:
        return session
    try:
        return query.filter(RecordingSession.id == int(session_id)).first()
    except (TypeError, ValueError):
        return None


@ws_router.websocket("/ws/uploads/{job_id}")
async def uploads_websocket(websocket: WebSocket, job_id: str):
    db = SessionLocal()
    try:
        try:
            uid = uuid.UUID(job_id)
        except ValueError:
            await websocket.close(code=1008)
            return
        job = db.query(UploadJob).filter(UploadJob.upload_id == uid).first()
        if not job:
            await websocket.close(code=1008)
            return
        await ws_manager.connect(job_id, websocket)
        await websocket.send_json(_status_payload(job))
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        ws_manager.disconnect(job_id, websocket)
        db.close()
