"""Generic arq job runner — v3.18.3 background-jobification of long handlers.

Codex audit Performance Finding S1: four HTTP handlers can exceed
Cloudflare's 120-second origin timeout when the underlying work
(server-side summarize + insights + Brigade write + digest map-reduce +
TTS render) runs longer than the edge tolerates. The fix is to move
that work into an arq worker function, have the handler return 202 +
job_id immediately, and have the frontend poll `GET /api/jobs/{job_id}`
until the worker finishes.

This module exposes a thin wrapper over the existing arq Redis pool
(reusing the singleton from `workers.bulk_import_worker`) plus a small
in-process idempotency window so a frontend that hammers the same
endpoint twice in a row doesn't double-spend Brigade / PO writes.

Public surface:

  enqueue_job(function_name, *args, **kwargs) -> str
    Enqueue a job by registered function name; returns the arq job_id.

  get_job_status(job_id) -> dict
    Read status from arq: pending | running | completed | failed |
    not_found. Always includes job_id + timing fields when known.

The actual worker functions live in `workers/finalize_workers.py`,
`workers/digest_workers.py`, `workers/tts_workers.py`. They're all
registered on `workers.bulk_import_worker.WorkerSettings.functions`
so the existing arq deployment topology (one worker per uvicorn host)
needs zero process changes.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from typing import Any

from arq.jobs import Job, JobStatus

from workers.bulk_import_worker import get_arq_pool

logger = logging.getLogger(__name__)


# Idempotency window: (function_name, args_hash) -> (job_id, expires_at).
# Purely in-process — the goal is to swallow a fast double-click from
# the same user in the same FastAPI process, not enforce idempotency
# across the cluster. The worker functions themselves are responsible
# for being safe to run twice (drift checks + MERGE semantics).
_IDEMPOTENCY_WINDOW_SECONDS = 300
_idempotency_cache: dict[str, tuple[str, float]] = {}


def _hash_args(function_name: str, args: tuple, kwargs: dict) -> str:
    """Stable hash of (function, args, kwargs) for the idempotency window.

    JSON encoding catches the 99% case (primitives + dicts); anything
    that doesn't serialize falls back to repr(), which is good enough
    because a non-JSON arg means the dedup window may miss but never
    falsely merge two different calls."""
    try:
        payload = json.dumps([function_name, list(args), kwargs], sort_keys=True, default=str)
    except (TypeError, ValueError):
        payload = repr((function_name, args, kwargs))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _gc_idempotency_cache() -> None:
    """Drop expired entries; called on every enqueue so the dict never
    grows unbounded in long-running uvicorn processes."""
    now = time.time()
    expired = [k for k, (_, exp) in _idempotency_cache.items() if exp <= now]
    for k in expired:
        _idempotency_cache.pop(k, None)


async def enqueue_job(function_name: str, *args: Any, **kwargs: Any) -> str:
    """Enqueue an arq job by registered function name.

    Within the idempotency window (default 5 minutes), an identical
    `(function_name, args, kwargs)` returns the previously-enqueued
    job_id instead of creating a new arq job. Outside the window, or
    when the arq pool errors, we fall through to a fresh enqueue.
    """
    _gc_idempotency_cache()
    key = _hash_args(function_name, args, kwargs)
    existing = _idempotency_cache.get(key)
    if existing:
        existing_job_id, _expires = existing
        logger.info(
            "job_runner: idempotent hit fn=%s job_id=%s", function_name, existing_job_id,
        )
        return existing_job_id

    pool = await get_arq_pool()
    job = await pool.enqueue_job(function_name, *args, **kwargs)
    if job is None:
        # arq returns None when the configured `_job_id` already exists.
        # We don't pass _job_id, so this shouldn't happen — but if it
        # does, log + raise so the caller can decide what to do.
        raise RuntimeError(
            f"arq.enqueue_job returned None for fn={function_name}"
        )

    _idempotency_cache[key] = (job.job_id, time.time() + _IDEMPOTENCY_WINDOW_SECONDS)
    logger.info(
        "job_runner: enqueued fn=%s job_id=%s args=%s",
        function_name, job.job_id, args[:3],  # truncate args in logs
    )
    return job.job_id


def _status_to_string(status: JobStatus | None) -> str:
    """Map arq's JobStatus enum to the public status strings we expose."""
    if status is None:
        return "not_found"
    if status == JobStatus.queued or status == JobStatus.deferred:
        return "pending"
    if status == JobStatus.in_progress:
        return "running"
    if status == JobStatus.complete:
        return "completed"  # may still be "failed" — caller checks result
    if status == JobStatus.not_found:
        return "not_found"
    return "pending"


async def get_job_status(job_id: str) -> dict[str, Any]:
    """Look up an arq job's status + result.

    Returns:
        {
          "job_id": str,
          "status": "pending"|"running"|"completed"|"failed"|"not_found",
          "result": <worker-return-value> or None,
          "error": str or None,
          "queued_at": isoformat or None,
          "started_at": isoformat or None,
          "finished_at": isoformat or None,
        }
    """
    pool = await get_arq_pool()
    job = Job(job_id, pool)

    try:
        info = await job.info()
    except Exception as exc:  # noqa: BLE001
        logger.warning("job_runner: info() failed for %s: %s", job_id, exc)
        info = None

    try:
        status = await job.status()
    except Exception as exc:  # noqa: BLE001
        logger.warning("job_runner: status() failed for %s: %s", job_id, exc)
        status = None

    status_str = _status_to_string(status)

    result_value: Any = None
    error_value: str | None = None
    if status == JobStatus.complete:
        try:
            result_value = await job.result(timeout=0.1)
        except Exception as exc:  # noqa: BLE001
            # arq's `result()` raises with the worker's exception when the
            # job crashed — surface that as a failed status.
            status_str = "failed"
            error_value = str(exc)[:2000]

    def _iso(dt: Any) -> str | None:
        if dt is None:
            return None
        try:
            return dt.isoformat()
        except Exception:  # noqa: BLE001
            return str(dt)

    queued_at = _iso(getattr(info, "enqueue_time", None)) if info else None
    started_at = _iso(getattr(info, "start_time", None)) if info else None
    finished_at = _iso(getattr(info, "finish_time", None)) if info else None

    return {
        "job_id": job_id,
        "status": status_str,
        "result": result_value,
        "error": error_value,
        "queued_at": queued_at,
        "started_at": started_at,
        "finished_at": finished_at,
    }


def reset_idempotency_cache_for_tests() -> None:
    """Hook for tests to flush the in-process dedup cache between cases."""
    _idempotency_cache.clear()
