"""Arq worker: bounded, fair server-side session reprocess — tier-A launch.

Moves `_run_session_reprocess` (api/recording.py — the whole-file transcribe +
diarize + summary + title pass fired at Stop via /full-audio) off unbounded
fire-and-forget BackgroundTasks and onto the existing Arq/Redis worker (shared
with bulk-import, redis db 4), so:

  - GPU concurrency is bounded by the worker's ``max_jobs`` — no single account
    can monopolize the pipeline; everyone queues.
  - a per-org daily audio-hours SOFT cap DEPRIORITIZES (never blocks): once an
    org passes ``REPROCESS_MAX_DAILY_AUDIO_HOURS_PER_ORG`` (default 16) of audio
    submitted today, its new jobs are deferred to the back of the line so other
    orgs run first — then they still complete.

Only paid tiers reach here (``canonical_reprocess`` gates Free/Basic out
upstream in api/recording.py before enqueue).

``REPROCESS_ARQ_ENABLED=false`` (or ``ARQ_ENABLED=false``) keeps the legacy
in-process path — a direct ``_run_session_reprocess`` call — which preserves the
test suite's monkeypatches of ``recording._run_session_reprocess`` and supports
any deploy that hasn't flipped the flag. Mirrors workers/bulk_import_worker.py.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
def _arq_enabled() -> bool:
    raw = os.getenv("REPROCESS_ARQ_ENABLED")
    if raw is None:
        raw = os.getenv("ARQ_ENABLED", "true")
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _max_daily_audio_hours() -> float:
    try:
        return max(0.0, float(os.getenv("REPROCESS_MAX_DAILY_AUDIO_HOURS_PER_ORG", "16")))
    except ValueError:
        return 16.0


def _over_cap_defer_seconds() -> int:
    try:
        return max(0, int(os.getenv("REPROCESS_OVER_CAP_DEFER_SECONDS", "300")))
    except ValueError:
        return 300


# --------------------------------------------------------------------------- #
# Daily per-org audio-hours counter (Redis, self-expiring at UTC midnight)
# --------------------------------------------------------------------------- #
def _today_key(org_id: int) -> str:
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"reprocess:org:{org_id}:audio_hours:{day}"


def _seconds_until_utc_midnight() -> int:
    now = datetime.now(timezone.utc)
    midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(60, int((midnight - now).total_seconds()))


async def _add_org_audio_hours(redis, org_id: int, hours: float) -> float:
    """Atomically add ``hours`` to the org's today counter (INCRBYFLOAT) + set a
    midnight-UTC TTL so it self-resets daily; return the new daily total.

    Fail-open: any redis error returns 0.0 so a metering hiccup never blocks or
    wrongly defers a reprocess."""
    try:
        key = _today_key(org_id)
        new_total = await redis.incrbyfloat(key, float(hours))
        try:
            await redis.expire(key, _seconds_until_utc_midnight())
        except Exception:  # noqa: BLE001
            pass
        return float(new_total)
    except Exception as exc:  # noqa: BLE001
        logger.warning("reprocess metering incr failed org=%s: %s", org_id, exc)
        return 0.0


# --------------------------------------------------------------------------- #
# Org / duration resolution (for metering)
# --------------------------------------------------------------------------- #
def _resolve_org_and_hours(session_pk: int) -> tuple[Optional[int], float]:
    """Look up (organization_id, audio_hours) for metering. Sync DB read; the
    enqueue path runs at Stop, not a hot loop. Best-effort -> (None, 0.0).

    Imports Organization + RoomAudioSource so a RecordingSession query doesn't
    raise NoReferencedTableError (the FK-registration gotcha the watchdog also
    guards against)."""
    try:
        from database.database import SessionLocal
        from database.models import RecordingSession
        from auth.models import Organization  # noqa: F401
        try:
            from database.models_rooms import RoomAudioSource  # noqa: F401
        except Exception:
            pass
        db = SessionLocal()
        try:
            s = db.query(RecordingSession).filter(RecordingSession.id == session_pk).first()
            if not s:
                return None, 0.0
            org_id = getattr(s, "organization_id", None)
            dur = getattr(s, "duration", None)
            hours = (float(dur) / 3600.0) if dur else 0.0
            return org_id, hours
        finally:
            db.close()
    except Exception as exc:  # noqa: BLE001
        logger.warning("reprocess org/hours resolve failed session=%s: %s", session_pk, exc)
        return None, 0.0


# --------------------------------------------------------------------------- #
# The Arq job — wraps _run_session_reprocess unchanged
# --------------------------------------------------------------------------- #
async def reprocess_session_job(
    ctx: dict[str, Any],
    session_pk: int,
    org_id: Optional[int] = None,
    audio_hours: float = 0.0,
) -> dict[str, Any]:
    """Run the whole-file reprocess for a session inside the bounded worker.

    Thin wrapper: imports ``_run_session_reprocess`` at call time (so a test
    monkeypatch is honored), runs it, returns a status dict. The wrapped
    function owns its own status/metadata writes (incl. the v3.26.13 status
    flip)."""
    try:
        from api.recording import _run_session_reprocess
        await _run_session_reprocess(session_pk)
        return {"status": "completed", "session_pk": session_pk, "org_id": org_id}
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("reprocess_session_job crash session=%s", session_pk)
        return {"status": "failed", "session_pk": session_pk, "error": str(exc)[:500]}


# --------------------------------------------------------------------------- #
# Enqueue helper — the single entry point all call sites use
# --------------------------------------------------------------------------- #
def _inprocess(session_pk: int, background_tasks) -> None:
    from api.recording import _run_session_reprocess
    if background_tasks is not None:
        background_tasks.add_task(_run_session_reprocess, session_pk)
    else:
        asyncio.create_task(_run_session_reprocess(session_pk))


async def enqueue_reprocess(session_pk: int, *, background_tasks=None) -> Optional[str]:
    """Enqueue a reprocess.

    ARQ on  -> bounded Arq job + per-org daily soft-cap deprioritization.
    ARQ off -> legacy in-process direct call (preserves test monkeypatches +
               ARQ-disabled deploys).
    Any Arq error falls back to in-process so a reprocess is never lost."""
    if not _arq_enabled():
        _inprocess(session_pk, background_tasks)
        return None

    try:
        from workers.bulk_import_worker import get_arq_pool
        pool = await get_arq_pool()
        org_id, audio_hours = _resolve_org_and_hours(session_pk)
        defer = 0
        if org_id is not None and audio_hours > 0:
            new_total = await _add_org_audio_hours(pool, org_id, audio_hours)
            if new_total > _max_daily_audio_hours():
                defer = _over_cap_defer_seconds()
                logger.warning(
                    "reprocess soft-cap: org=%s at %.1fh/day (cap %.0f) — deferring %ss "
                    "(deprioritize, not block)",
                    org_id, new_total, _max_daily_audio_hours(), defer,
                )
        # Arq reserved kwargs are underscore-prefixed (_job_id, _defer_by). A
        # bare "job_id" gets forwarded to reprocess_session_job() and raises
        # TypeError; _job_id also doubles as the per-session idempotency key.
        kwargs: dict[str, Any] = {"_job_id": f"reprocess-{session_pk}"}
        if defer:
            kwargs["_defer_by"] = defer
        job = await pool.enqueue_job(
            "reprocess_session_job", session_pk, org_id, audio_hours, **kwargs
        )
        return job.job_id if job else None
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "reprocess enqueue failed session=%s (%s) — in-process fallback",
            session_pk, exc,
        )
        _inprocess(session_pk, background_tasks)
        return None


# --------------------------------------------------------------------------- #
# Restart recovery — re-enqueue reprocesses in flight at crash
# --------------------------------------------------------------------------- #
async def recover_reprocess_jobs() -> None:
    """On worker start, re-enqueue sessions stuck mid-reprocess (status=processing,
    non-terminal reprocess_status, updated within 6h) so a worker restart doesn't
    strand them until the watchdog. Bounded + best-effort."""
    if not _arq_enabled():
        return
    try:
        from database.database import SessionLocal
        from database.models import RecordingSession
        from auth.models import Organization  # noqa: F401
        try:
            from database.models_rooms import RoomAudioSource  # noqa: F401
        except Exception:
            pass
        cutoff = datetime.now(timezone.utc) - timedelta(hours=6)
        db = SessionLocal()
        try:
            rows = (
                db.query(RecordingSession)
                .filter(
                    RecordingSession.status == "processing",
                    RecordingSession.updated_at >= cutoff,
                )
                .order_by(RecordingSession.id.desc())
                .limit(200)
                .all()
            )
            recovered = 0
            for s in rows:
                md = s.processing_metadata or {}
                if md.get("reprocess_status") == "complete":
                    continue
                try:
                    await enqueue_reprocess(s.id)
                    recovered += 1
                except Exception as exc:  # noqa: BLE001
                    logger.warning("reprocess recovery: re-enqueue failed session=%s: %s", s.id, exc)
            logger.info("reprocess recovery: %d processing sessions re-enqueued", recovered)
        finally:
            db.close()
    except Exception as exc:  # noqa: BLE001
        logger.warning("reprocess recovery failed: %s", exc)
