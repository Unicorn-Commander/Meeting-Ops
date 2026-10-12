"""Server-side recording imports used by the Meeting-Ops MCP tool.

This module deliberately calls the existing upload service helpers instead of
calling the backend over HTTP.  The caller and active organization are passed
in by the MCP transport (or by the in-process agent dispatcher), so the same
feature gate, quota check, upload job, and processing queue used by the UI
remain the source of truth.
"""
from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import logging
import mimetypes
import os
import shutil
import socket
import uuid
from pathlib import Path
from typing import Any, Optional
from urllib.parse import unquote, urljoin, urlsplit

import httpx
from fastapi import HTTPException
from sqlalchemy import Text
from sqlalchemy.orm import Session

from auth.models import AuditLog, User
from auth.organization import ActiveOrganization
from database.models import RecordingSession, UploadJob


logger = logging.getLogger("meeting-ops-mcp-import")
IMPORT_ROOTS_ENV = "MEETING_OPS_IMPORT_ROOTS"
MAX_REDIRECTS = 5
DOWNLOAD_CHUNK_SIZE = 1024 * 1024


def _configured_import_roots() -> tuple[Path, ...]:
    """Return canonical import roots; empty/unset means local import is off."""
    raw = os.getenv(IMPORT_ROOTS_ENV, "")
    roots: list[Path] = []
    for item in raw.split(os.pathsep):
        value = item.strip()
        if not value:
            continue
        try:
            root = Path(value).expanduser().resolve(strict=True)
        except OSError:
            # A configured-but-missing root cannot authorize a path.  Keeping
            # it out of the list is safer than resolving it lexically.
            continue
        if root.is_dir():
            roots.append(root)
    return tuple(roots)


def _resolve_local_source(local_path: str) -> Path:
    if not local_path or not local_path.strip():
        raise HTTPException(status_code=400, detail="local_path must not be empty.")
    candidate = Path(local_path)
    if not candidate.is_absolute():
        raise HTTPException(
            status_code=400,
            detail="local_path must be an absolute path under MEETING_OPS_IMPORT_ROOTS.",
        )

    roots = _configured_import_roots()
    if not roots:
        raise HTTPException(
            status_code=403,
            detail=f"Local imports are disabled; configure {IMPORT_ROOTS_ENV}.",
        )
    try:
        resolved = candidate.resolve(strict=True)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Import file not found.") from exc
    except OSError as exc:
        raise HTTPException(status_code=400, detail="Import file cannot be resolved.") from exc

    if not resolved.is_file():
        raise HTTPException(status_code=400, detail="local_path must point to a regular file.")
    if not any(resolved == root or root in resolved.parents for root in roots):
        raise HTTPException(
            status_code=403,
            detail=f"local_path must be under an allowlisted {IMPORT_ROOTS_ENV} root.",
        )
    return resolved


def _public_ip_addresses(host: str, port: int) -> set[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    try:
        literal = ipaddress.ip_address(host)
        return {literal}
    except ValueError:
        pass

    try:
        addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise HTTPException(status_code=400, detail="source_url host could not be resolved.") from exc

    resolved: set[ipaddress.IPv4Address | ipaddress.IPv6Address] = set()
    for address in addresses:
        try:
            ip = ipaddress.ip_address(address[4][0])
        except (IndexError, ValueError):
            continue
        # IPv4-mapped IPv6 addresses inherit the IPv4 address's network class.
        resolved.add(ip.ipv4_mapped or ip)
    if not resolved:
        raise HTTPException(status_code=400, detail="source_url host has no usable address.")
    return resolved


def _validate_public_https_url(raw_url: str) -> None:
    try:
        parsed = urlsplit(raw_url)
        port = parsed.port or 443
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="source_url is malformed.") from exc
    if parsed.scheme.lower() != "https":
        raise HTTPException(status_code=400, detail="source_url must use https.")
    if parsed.username or parsed.password or not parsed.hostname:
        raise HTTPException(status_code=400, detail="source_url must have a public host and no credentials.")
    for address in _public_ip_addresses(parsed.hostname, port):
        if not address.is_global:
            raise HTTPException(
                status_code=400,
                detail="source_url must not resolve to a private or local network.",
            )


def _url_filename(raw_url: str, content_type: Optional[str]) -> str:
    path_name = Path(unquote(urlsplit(raw_url).path)).name
    if path_name:
        return path_name
    extension = mimetypes.guess_extension((content_type or "").split(";", 1)[0].strip())
    return f"imported-recording{extension or '.bin'}"


async def _download_url(raw_url: str, destination: Path, max_bytes: int) -> tuple[str, Optional[str], int]:
    """Download an HTTPS source with bounded redirects and streamed bytes."""
    current_url = raw_url
    for redirect_count in range(MAX_REDIRECTS + 1):
        # Validate every hop, including the final URL.  Automatic client
        # redirects are disabled so a public URL cannot redirect to localhost
        # or another private network without this check seeing it.
        _validate_public_https_url(current_url)
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=False) as client:
            async with client.stream("GET", current_url) as response:
                if 300 <= response.status_code < 400:
                    location = response.headers.get("location")
                    if not location:
                        raise HTTPException(status_code=502, detail="source_url redirect had no location.")
                    if redirect_count >= MAX_REDIRECTS:
                        raise HTTPException(status_code=502, detail="source_url exceeded the redirect limit.")
                    current_url = urljoin(current_url, location)
                    continue
                if response.status_code >= 400:
                    raise HTTPException(
                        status_code=502,
                        detail=f"source_url returned HTTP {response.status_code}.",
                    )

                content_length = response.headers.get("content-length")
                if content_length:
                    try:
                        if int(content_length) > max_bytes:
                            raise HTTPException(
                                status_code=413,
                                detail=f"source_url exceeds the {max_bytes} byte upload limit.",
                            )
                    except ValueError:
                        # A malformed length is not a reason to trust the
                        # response; the streamed byte cap below still applies.
                        pass

                content_type = response.headers.get("content-type")
                filename = _url_filename(current_url, content_type)
                total = 0
                with destination.open("wb") as output:
                    async for block in response.aiter_bytes(DOWNLOAD_CHUNK_SIZE):
                        total += len(block)
                        if total > max_bytes:
                            raise HTTPException(
                                status_code=413,
                                detail=f"source_url exceeds the {max_bytes} byte upload limit.",
                            )
                        output.write(block)
                if total <= 0:
                    raise HTTPException(status_code=400, detail="source_url returned an empty file.")
                return filename, content_type, total
    raise HTTPException(status_code=502, detail="source_url exceeded the redirect limit.")


async def _sha256_file(path: Path) -> str:
    def digest() -> str:
        hasher = hashlib.sha256()
        with path.open("rb") as source:
            while block := source.read(8 * 1024 * 1024):
                hasher.update(block)
        return hasher.hexdigest()

    return await asyncio.to_thread(digest)


def _normalize_tags(raw_tags: Optional[list[str]]) -> list[str]:
    if raw_tags is None:
        return []
    if not isinstance(raw_tags, list):
        raise HTTPException(status_code=400, detail="tags must be a list of strings.")
    result: list[str] = []
    seen: set[str] = set()
    for item in raw_tags:
        if not isinstance(item, str):
            raise HTTPException(status_code=400, detail="tags must be a list of strings.")
        cleaned = item.strip()
        if not cleaned:
            continue
        key = cleaned.casefold()
        if key not in seen:
            seen.add(key)
            result.append(cleaned[:100])
    return result


def _find_existing_import(
    db: Session,
    *,
    caller_id: int,
    organization_id: int,
    source_sha256: str,
) -> Optional[RecordingSession]:
    """Find an import made by this caller for this exact source digest."""
    needle = f"%{source_sha256}%"
    candidates = (
        db.query(RecordingSession)
        .filter(
            RecordingSession.organization_id == organization_id,
            RecordingSession.user_id == caller_id,
            RecordingSession.processing_metadata.isnot(None),
            RecordingSession.processing_metadata.cast(Text).like(needle),
        )
        .order_by(RecordingSession.id.asc())
        .all()
    )
    for session in candidates:
        marker = (session.processing_metadata or {}).get("mcp_import")
        if (
            isinstance(marker, dict)
            and marker.get("caller_id") == caller_id
            and marker.get("source_sha256") == source_sha256
        ):
            return session
    return None


def _session_status(db: Session, session: RecordingSession) -> str:
    job = (
        db.query(UploadJob)
        .filter(UploadJob.session_id == session.id)
        .order_by(UploadJob.id.desc())
        .first()
    )
    return str(job.stage if job is not None else session.status or "unknown")


async def import_recording_for_caller(
    *,
    db: Session,
    caller: User,
    active_org: ActiveOrganization,
    source_url: Optional[str] = None,
    local_path: Optional[str] = None,
    title: Optional[str] = None,
    tags: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Materialize and queue one recording through the normal upload pipeline."""
    if bool(source_url) == bool(local_path):
        raise HTTPException(status_code=400, detail="Provide exactly one of source_url or local_path.")

    # These are the same checks made by POST /api/uploads/start.  Keep them
    # before any durable row is created, and do not weaken them for MCP.
    from auth.tier import gate_feature_for_caller
    from services.quotas import check_upload_quota
    from api import uploads

    gate_feature_for_caller(caller, "audio_upload", active_org)
    max_file_bytes = uploads.get_max_file_bytes()
    stage_root = uploads.UPLOAD_ROOT / ".mcp-import"
    stage_root.mkdir(parents=True, exist_ok=True)
    stage_path = stage_root / f"{uuid.uuid4().hex}.part"
    source_kind = "url" if source_url else "local_path"
    source_host: Optional[str] = None

    try:
        if local_path:
            source_path = _resolve_local_source(local_path)
            try:
                if source_path.stat().st_size > max_file_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"local_path exceeds the {max_file_bytes} byte upload limit.",
                    )
            except OSError as exc:
                raise HTTPException(status_code=400, detail="Import file cannot be read.") from exc
            await asyncio.to_thread(shutil.copyfile, source_path, stage_path)
            filename = source_path.name
            content_type = mimetypes.guess_type(filename)[0]
        else:
            parsed_url = urlsplit(source_url or "")
            source_host = parsed_url.hostname
            filename, content_type, _ = await _download_url(
                source_url or "", stage_path, max_file_bytes
            )

        actual_size = stage_path.stat().st_size
        if actual_size <= 0:
            raise HTTPException(status_code=400, detail="Import source returned an empty file.")
        if actual_size > max_file_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"Import source exceeds the {max_file_bytes} byte upload limit.",
            )

        safe_filename = uploads._safe_filename(filename)
        if uploads._detect_kind(safe_filename, content_type) not in {"audio", "video"}:
            raise HTTPException(status_code=400, detail="Import source must be an audio or video file.")

        source_sha256 = await _sha256_file(stage_path)
        existing = _find_existing_import(
            db,
            caller_id=caller.id,
            organization_id=active_org.organization.id,
            source_sha256=source_sha256,
        )
        if existing is not None:
            db.add(
                AuditLog(
                    user_id=caller.id,
                    organization_id=active_org.organization.id,
                    action="mcp_import_recording_duplicate",
                    resource_type="recording_session",
                    resource_id=str(existing.id),
                    details={
                        "source_kind": source_kind,
                        "source_sha256": source_sha256,
                        "source_host": source_host,
                    },
                )
            )
            db.commit()
            return {
                "session_id": existing.id,
                "status": _session_status(db, existing),
            }

        # The quota service owns tier-specific file, concurrency, and monthly
        # hour limits.  It is called after materialization so URL imports are
        # checked against the actual byte count, just like a finalized UI file.
        check_upload_quota(db, active_org.organization, actual_size)

        upload_id = uuid.uuid4()
        job_dir = uploads._job_dir(active_org.organization.slug, str(upload_id))
        job_dir.mkdir(parents=True, exist_ok=True)
        target_path = job_dir / safe_filename
        os.replace(stage_path, target_path)

        job = UploadJob(
            organization_id=active_org.organization.id,
            user_id=caller.id,
            upload_id=upload_id,
            filename=safe_filename,
            content_type=content_type,
            # The session is created before queue submission so MCP can return
            # its id.  The shared pipeline's attach branch then processes this
            # pre-created row without creating a second session.
            action="attach",
            total_size=actual_size,
            bytes_received=actual_size,
            chunks_received=1,
            total_chunks=1,
            stage="queued",
            progress_pct=0,
            audio_sha256=source_sha256,
        )
        db.add(job)
        db.flush()

        # This helper is the same session construction path used by the UI
        # upload pipeline.  The job is already persisted as ``attach`` so a
        # crash after this helper commits cannot make recovery create a second
        # session.  The caller receives a stable session_id before expensive
        # STT/diarization work begins.
        session = await uploads._create_upload_session(
            db, job, target_path, source_path=target_path
        )
        requested_title = (title or "").strip()
        if requested_title:
            session.title = requested_title[:200]
            session.name = session.title
            session.title_user_set = True
        session.tags = _normalize_tags(tags)
        session.source_type = "mcp_import"
        metadata = dict(session.processing_metadata or {})
        metadata["mcp_import"] = {
            "caller_id": caller.id,
            "source_sha256": source_sha256,
            "source_kind": source_kind,
            "source_name": safe_filename,
        }
        session.processing_metadata = metadata
        job.stage = "queued"
        job.progress_pct = 0
        db.add(
            AuditLog(
                user_id=caller.id,
                organization_id=active_org.organization.id,
                action="mcp_import_recording",
                resource_type="recording_session",
                resource_id=str(session.id),
                details={
                    "source_kind": source_kind,
                    "source_sha256": source_sha256,
                    "source_name": safe_filename,
                    "source_host": source_host,
                    "upload_id": str(upload_id),
                },
            )
        )
        db.commit()

        try:
            await uploads.upload_pipeline_queue.enqueue(str(upload_id))
        except Exception:  # noqa: BLE001
            # The persisted queued job is recoverable on backend startup.  A
            # queue hiccup must not turn a successful source import into a
            # false failure after the caller already has a session handle.
            logger.exception("MCP import queue submission failed for upload=%s", upload_id)

        return {"session_id": session.id, "status": str(job.stage)}
    finally:
        try:
            stage_path.unlink(missing_ok=True)
        except OSError:
            pass
