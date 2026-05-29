"""Session watchdog — auto-finalize abandoned recording sessions.

Always-on recordings that never get a proper Stop (browser tab closed, user
walked away, devops restart, satellite power-cycle, etc.) sit in the DB at
``status='recording'`` forever. Over time the count creeps up and every
endpoint that filters or iterates "active sessions" amplifies its own work,
which can push slow endpoints past Cloudflare's 120 s edge timeout (see the
zombie pile-up on 2026-05-29: 7 sessions in ``status='recording'`` for
2-9 days, leading to a 524 mid-meeting).

Safe by construction:
  - Only flips sessions whose ``updated_at`` is older than ``SESSION_WATCHDOG_HOURS``
    (default 6). Real long-running always-on sessions get a new ``updated_at``
    every time a chunk lands, so they don't trip this.
  - Audio is preserved — the Garage object stays, ``audio_object_key`` stays
    on the row. Only ``status`` and ``ended_at`` flip; the watchdog never
    deletes data.
  - Idempotent: re-running finds nothing left to fail.
  - Best-effort and bounded — runs in a single DB session with a hard cap on
    rows touched per pass so a misconfiguration can't cascade.

Triggered by the Arq cron in ``workers/bulk_import_worker.WorkerSettings``;
also exposed as ``scripts/finalize_abandoned_sessions.py`` for manual ops.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)


def _hours() -> int:
    try:
        return max(1, int(os.getenv("SESSION_WATCHDOG_HOURS", "6")))
    except ValueError:
        return 6


def _max_per_pass() -> int:
    try:
        return max(1, int(os.getenv("SESSION_WATCHDOG_MAX_PER_PASS", "200")))
    except ValueError:
        return 200


def _enabled() -> bool:
    return os.getenv("SESSION_WATCHDOG_ENABLED", "true").strip().lower() in (
        "1", "true", "yes", "on",
    )


def mark_abandoned_recording_sessions(*, dry_run: bool = False) -> dict[str, Any]:
    """Find sessions stuck in ``status='recording'`` whose ``updated_at`` is
    older than the configured threshold and flip them to ``failed``.

    Returns a summary dict. Never raises — exceptions are logged and the
    pass terminates cleanly. Idempotent. The Garage audio + transcripts +
    everything else stays intact; only ``status`` + ``ended_at`` change."""
    if not _enabled():
        return {"enabled": False}

    from database.database import SessionLocal
    from database.models import RecordingSession

    threshold_hours = _hours()
    cap = _max_per_pass()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=threshold_hours)

    summary = {
        "enabled": True,
        "threshold_hours": threshold_hours,
        "candidates": 0,
        "marked_failed": 0,
        "skipped_cap": 0,
        "errors": 0,
        "dry_run": dry_run,
    }

    db = SessionLocal()
    try:
        # `updated_at` is bumped by SQLAlchemy `onupdate=` whenever anything
        # writes to the row, including the every-30-s chunk persistence,
        # so this naturally excludes truly-active recordings.
        candidates = (
            db.query(RecordingSession)
            .filter(
                RecordingSession.status == "recording",
                RecordingSession.updated_at < cutoff,
            )
            .order_by(RecordingSession.id)
            .limit(cap + 1)
            .all()
        )
        summary["candidates"] = min(len(candidates), cap)
        if len(candidates) > cap:
            summary["skipped_cap"] = len(candidates) - cap
            candidates = candidates[:cap]

        now = datetime.now(timezone.utc)
        for sess in candidates:
            try:
                if dry_run:
                    summary["marked_failed"] += 1
                    continue
                sess.status = "failed"
                sess.ended_at = now
                # Compute duration if possible.
                if sess.started_at and not sess.duration:
                    started = sess.started_at
                    if started.tzinfo is None:
                        started = started.replace(tzinfo=timezone.utc)
                    try:
                        sess.duration = (now - started).total_seconds()
                    except Exception:
                        pass
                md = dict(sess.processing_metadata or {})
                md["auto_failed_reason"] = (
                    f"abandoned: status=recording with no updates for >"
                    f"{threshold_hours}h (session_watchdog)"
                )
                md["auto_failed_at"] = now.isoformat()
                sess.processing_metadata = md
                summary["marked_failed"] += 1
            except Exception as exc:  # noqa: BLE001
                summary["errors"] += 1
                logger.warning(
                    "session_watchdog: failed to mark session=%s — %s",
                    getattr(sess, "id", None), exc,
                )
        if not dry_run:
            db.commit()
        logger.info("session_watchdog pass: %s", summary)
        return summary
    except Exception as exc:  # noqa: BLE001
        logger.exception("session_watchdog: top-level error: %s", exc)
        summary["errors"] += 1
        try:
            db.rollback()
        except Exception:
            pass
        return summary
    finally:
        db.close()
