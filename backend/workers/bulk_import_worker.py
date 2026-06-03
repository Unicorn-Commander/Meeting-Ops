"""Arq worker for bulk import processing.

B-import.4: replaces the in-process asyncio queue with a durable Arq
worker backed by Redis. Jobs persist in Redis so a uvicorn restart
mid-batch resumes cleanly.

Config:
  ARQ_ENABLED=true|false  (default: true)
  ARQ_REDIS_URL           (default: redis://:default@unicorn-redis:6379/4)
  BULK_IMPORT_WORKERS     (default: 2, maps to Arq max_jobs)
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from typing import Any

from arq import create_pool, cron
from arq.connections import RedisSettings

from database.database import SessionLocal
from database.models import BulkImportFile, BulkImportJob
from services.bulk_import_queue import (
    _do_process_file,
    bulk_import_queue,
    get_bulk_import_concurrency,
    start_bulk_import_queue,
    stop_bulk_import_queue,
)

logger = logging.getLogger(__name__)


async def process_bulk_file(ctx: dict[str, Any], file_id: str) -> dict[str, Any]:
    """Arq task: process one bulk-import file."""
    file_uuid = uuid.UUID(file_id)
    logger.info("arq worker: processing file_id=%s", file_id)
    try:
        await _do_process_file(file_uuid)
        return {"status": "done", "file_id": file_id}
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.exception("arq worker: crashed on file_id=%s: %s", file_id, exc)
        await asyncio.to_thread(bulk_import_queue._mark_failed, file_uuid, str(exc))
        return {"status": "failed", "file_id": file_id, "error": str(exc)[:2000]}


async def media_retention_task(ctx: dict[str, Any]) -> dict[str, Any]:
    """Daily cron: reclaim local disk now that Garage is the durable home for
    audio. Evicts local working copies of older completed sessions that have a
    size-verified Garage copy, and LRU-caps the re-materialization cache. Never
    deletes a Garage object; fully reversible (audio re-fetches on read)."""
    from services.media_retention import run_retention
    result = await asyncio.to_thread(run_retention)
    logger.info("arq cron: media_retention result=%s", result)
    return result


async def session_watchdog_task(ctx: dict[str, Any]) -> dict[str, Any]:
    """Every-30-min cron: clear two classes of zombies.

    1. status='recording' with no chunk update past SESSION_WATCHDOG_MINUTES
       (default 30 min) — phone tab evicted, dev tab crashed, etc. Flipped
       to ``failed`` so endpoints iterating active recordings stay fast and
       Cloudflare's 120 s edge timeout doesn't trip (see the 2026-05-29
       524 incident).
    2. status='processing' with no resolution past
       SESSION_WATCHDOG_PROCESSING_MINUTES (default 360 min = 6 h) — worker
       OOM, host restart mid-pass, Stage 7 exception that didn't bubble up.
       Triaged by content: rows with transcript text → 'completed'
       (preserve the work); rows with no transcript → 'failed'. Added
       2026-06-03 after bigboy accumulated 101 stuck-processing rows from
       a chain of rapid redeploys earlier the same day.

    Audio + transcripts + graph + Garage all stay intact in both passes —
    only status (+ ended_at + processing_metadata audit fields) change.
    Configurable via SESSION_WATCHDOG_* env vars; both default-enabled."""
    from services.session_watchdog import (
        mark_abandoned_recording_sessions,
        mark_abandoned_processing_sessions,
    )
    recording_result = await asyncio.to_thread(mark_abandoned_recording_sessions)
    processing_result = await asyncio.to_thread(mark_abandoned_processing_sessions)
    combined = {
        "recording": recording_result,
        "processing": processing_result,
    }
    logger.info("arq cron: session_watchdog result=%s", combined)
    return combined


# v3.18.3 background-jobification: long-running handlers now enqueue
# arq jobs instead of awaiting inline (Codex Performance Finding S1).
# The workers themselves live in dedicated modules; we import them here
# so the arq runner registers them on startup.
from workers.finalize_workers import finalize_session_job  # noqa: E402
from workers.digest_workers import generate_digest_job  # noqa: E402
from workers.tts_workers import (  # noqa: E402
    render_tts_summary_job,
    render_tts_podcast_job,
)


class WorkerSettings:
    """Arq worker configuration."""

    functions = [
        process_bulk_file,
        finalize_session_job,
        generate_digest_job,
        render_tts_summary_job,
        render_tts_podcast_job,
    ]
    # Daily local-disk retention (Garage cutover housekeeping). 04:30 UTC is a
    # low-traffic window; the task is read-mostly + best-effort.
    # Session watchdog runs every 30 min on the half-hour to keep the active-
    # recordings set tight (see services/session_watchdog.py).
    cron_jobs = [
        cron(media_retention_task, hour={4}, minute={30}),
        cron(session_watchdog_task, minute={0, 30}),
    ]
    max_jobs = get_bulk_import_concurrency()
    redis_settings = RedisSettings.from_dsn(
        os.getenv("ARQ_REDIS_URL") or os.getenv("REDIS_URL", "redis://unicorn-redis:6379/4")
    )
    job_timeout = 3600


_arq_pool = None


async def get_arq_pool():
    """Lazily create the Arq Redis pool."""
    global _arq_pool
    if _arq_pool is None:
        _arq_pool = await create_pool(
            RedisSettings.from_dsn(
                os.getenv("ARQ_REDIS_URL") or os.getenv("REDIS_URL", "redis://unicorn-redis:6379/4")
            )
        )
    return _arq_pool


async def close_arq_pool():
    """Close the Arq Redis pool on shutdown."""
    global _arq_pool
    if _arq_pool is not None:
        await _arq_pool.close()
        _arq_pool = None


async def enqueue_file(file_id: uuid.UUID) -> str:
    """Enqueue a single file for processing via Arq."""
    pool = await get_arq_pool()
    j = await pool.enqueue_job(
        "process_bulk_file",
        file_id=str(file_id),
        job_id=f"bulk-import-{file_id}",
    )
    return j.job_id


async def recover_pending_jobs():
    """Restart recovery: scan bulk_import_files where status is in
    {queued, uploading} and re-enqueue them."""
    db = SessionLocal()
    try:
        pending = (
            db.query(BulkImportFile)
            .filter(BulkImportFile.status.in_(("queued", "uploading")))
            .all()
        )
        recovered = 0
        for row in pending:
            job = (
                db.query(BulkImportJob)
                .filter(BulkImportJob.id == row.job_id)
                .first()
            )
            if not job or job.cancelled_at is not None or job.status in (
                "cancelled", "complete", "failed",
            ):
                continue
            try:
                await enqueue_file(row.id)
                recovered += 1
                logger.info("arq recovery: re-enqueued file_id=%s", row.id)
            except Exception as exc:
                logger.warning(
                    "arq recovery: failed to enqueue file_id=%s: %s", row.id, exc,
                )
        logger.info(
            "arq recovery: %d/%d pending files re-enqueued",
            recovered, len(pending),
        )
    finally:
        db.close()


async def start_arq_worker():
    """Start the Arq worker pool and recover pending jobs."""
    enabled = os.getenv("ARQ_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")
    if not enabled:
        logger.info("arq: disabled (ARQ_ENABLED=false), using in-process queue")
        await start_bulk_import_queue()
        return
    await recover_pending_jobs()
    logger.info("arq worker started: max_jobs=%d, redis_db=4", WorkerSettings.max_jobs)


async def stop_arq_worker():
    """Stop the Arq worker pool."""
    enabled = os.getenv("ARQ_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")
    if not enabled:
        await stop_bulk_import_queue()
        return
    await close_arq_pool()
    logger.info("arq worker stopped")


def bulk_import_enqueue(file_id: uuid.UUID) -> bool:
    """Non-blocking enqueue for the API layer."""
    async def _enqueue():
        try:
            await enqueue_file(file_id)
            return True
        except Exception:
            return False
    try:
        loop = asyncio.get_running_loop()
        return loop.run_until_complete(_enqueue())
    except Exception:
        return False
