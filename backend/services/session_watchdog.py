"""Session watchdog — auto-finalize abandoned recording sessions.

Always-on recordings that never get a proper Stop (browser tab closed, user
walked away, devops restart, satellite power-cycle, etc.) sit in the DB at
``status='recording'`` forever. Over time the count creeps up and every
endpoint that filters or iterates "active sessions" amplifies its own work,
which can push slow endpoints past Cloudflare's 120 s edge timeout (see the
zombie pile-up on 2026-05-29: 7 sessions in ``status='recording'`` for
2-9 days, leading to a 524 mid-meeting).

Safe by construction:
  - Only flips sessions whose ``updated_at`` is older than the threshold.
    The default is ``SESSION_WATCHDOG_MINUTES`` (default 30 minutes, v3.22.5),
    superseding the legacy ``SESSION_WATCHDOG_HOURS`` knob (kept for back-compat
    — if both are set, MINUTES wins; if only HOURS is set, we still honor it).
    Real long-running always-on sessions get a new ``updated_at`` every time a
    chunk lands (~every 30 s), so 30 min of zero activity is the right signal
    that a phone tab got evicted or a desktop tab crashed — the original 6 h
    threshold was sized for desktop "leave the laptop running overnight" use
    and didn't catch phone-tab eviction (see 2026-06-01 incident: phone Chrome
    tab evicted at 21 min stale, blocked Record on next visit).
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


# Default idle threshold. Phones lose their service worker / MediaRecorder
# the moment the OS swaps the tab out of foreground (often <5 min on iOS).
# 30 minutes is "definitely dead, but won't trip a healthy chunk cadence" —
# the FullAudioRecorder uploads every 30s, so a live session is touched
# 60x within the window.
DEFAULT_WATCHDOG_MINUTES = 30


def _threshold_minutes() -> int:
    """Resolved idle threshold, in minutes.

    Precedence:
      1. ``SESSION_WATCHDOG_MINUTES`` (new in v3.22.5; preferred)
      2. ``SESSION_WATCHDOG_HOURS`` (legacy; multiplied by 60)
      3. :data:`DEFAULT_WATCHDOG_MINUTES`

    Always returns a value >= 1 minute. The MINUTES knob takes priority even
    when HOURS is also set, so a deploy can opt in to the new default by just
    unsetting HOURS (which most prod envs don't set explicitly anyway).
    """
    raw_minutes = os.getenv("SESSION_WATCHDOG_MINUTES")
    if raw_minutes is not None:
        try:
            return max(1, int(raw_minutes))
        except ValueError:
            pass
    raw_hours = os.getenv("SESSION_WATCHDOG_HOURS")
    if raw_hours is not None:
        try:
            return max(1, int(raw_hours) * 60)
        except ValueError:
            pass
    return DEFAULT_WATCHDOG_MINUTES


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

    threshold_minutes = _threshold_minutes()
    # Legacy field kept for back-compat with any caller / dashboard parsing
    # the old key. New code should read ``threshold_minutes``.
    threshold_hours_legacy = round(threshold_minutes / 60, 3)
    cap = _max_per_pass()
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=threshold_minutes)

    summary = {
        "enabled": True,
        "threshold_minutes": threshold_minutes,
        "threshold_hours": threshold_hours_legacy,
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
                    f"{threshold_minutes}m (session_watchdog)"
                )
                md["auto_failed_at"] = now.isoformat()
                sess.processing_metadata = md
                summary["marked_failed"] += 1
                # Structured log line — prod monitoring (loki on centerdeep)
                # greps for this prefix to count force-fail rate. Phone-tab
                # eviction shows up here, so a sudden spike is the canary
                # for "Free mobile users are losing recordings".
                logger.warning(
                    "session_watchdog.force_fail session_id=%s db_id=%s "
                    "user_id=%s org_id=%s idle_minutes=%d threshold_minutes=%d",
                    getattr(sess, "session_id", None),
                    getattr(sess, "id", None),
                    getattr(sess, "user_id", None),
                    getattr(sess, "organization_id", None),
                    threshold_minutes,
                    threshold_minutes,
                )
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
