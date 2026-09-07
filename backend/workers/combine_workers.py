"""Arq worker: combined-meeting summary (docs/COMBINED-MEETINGS-CONTRACT.md).

``combine_sessions_job`` assembles the combined transcript from the parts,
then runs the SAME summary + insights calls ``finalize_session_job`` makes
(``api.uploads._summarize_session`` — which also promotes action items —
and ``api.ai_insights._generate_ai_insights``) against the combined row.
It never writes ``transcriptions`` rows, never touches the parts, and skips
the finalize side effects that would double-count a meeting: no Qdrant
index, no Brigade graph write, no Project-Ops triage push.

Drift guard + failure recording mirror finalize: the worker re-reads the
row, bails if a newer job stamped ``processing_job_id``, and on failure
stamps ``status='failed'`` + the error in ``processing_metadata`` instead
of dropping it (a transient LLM outage additionally raises arq Retry, and
the retry's success flips the row back to ``completed``).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from arq import Retry

logger = logging.getLogger(__name__)


def _stamp_failure(db, session, own_job_id: str | None, stage: str, exc: BaseException) -> str:
    """Record a failure on the combined row the way finalize records a
    summary failure (``summary_error`` in processing_metadata), but with
    ``status='failed'`` so the watchdog's needs_summary re-drive (which would
    run finalize + Brigade + Project-Ops on it) leaves it alone."""
    from sqlalchemy.orm.attributes import flag_modified

    error = f"{stage}: {str(exc)[:480]}"
    try:
        db.rollback()
    except Exception:  # noqa: BLE001
        pass
    now = datetime.now(timezone.utc)
    session.status = "failed"
    metadata = dict(session.processing_metadata or {})
    metadata["summary_error"] = error
    metadata["combine_error"] = error
    metadata["completion"] = {
        "completed_at": now.isoformat(),
        "job_id": own_job_id,
        "summary_error": error,
        "mode": "combined",
    }
    session.processing_metadata = metadata
    flag_modified(session, "processing_metadata")
    session.updated_at = now
    db.commit()
    return error


async def combine_sessions_job(
    ctx: dict[str, Any],
    combined_session_id: int,
    user_id: int | None = None,
    org_id: int | None = None,
    request_id: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Build the combined transcript, then summary + insights.

    ``force`` is the "Re-run summary" button: it bypasses the summarizer's
    identical-input short-circuit so a deliberate regenerate always runs.
    """
    from middleware.request_context import bind_request_id

    own_job_id = ctx.get("job_id") if isinstance(ctx, dict) else None
    bind_request_id(request_id or own_job_id)

    from sqlalchemy.orm.attributes import flag_modified

    from database.database import SessionLocal
    from database.models import RecordingSession
    from services import session_combine as sc

    db = SessionLocal()
    try:
        session = (
            db.query(RecordingSession)
            .filter(RecordingSession.id == combined_session_id)
            .first()
        )
        if not session:
            logger.warning("combine_sessions_job: session %s gone", combined_session_id)
            return {
                "status": "skipped",
                "reason": "session_missing",
                "session_pk": combined_session_id,
            }
        if not bool(getattr(session, "is_combined", False)):
            logger.warning(
                "combine_sessions_job: session %s is not a combined meeting — skipping",
                combined_session_id,
            )
            return {
                "status": "skipped",
                "reason": "not_combined",
                "session_pk": combined_session_id,
            }

        current_job_id = getattr(session, "processing_job_id", None)
        if own_job_id and current_job_id and current_job_id != own_job_id:
            logger.warning(
                "combine_sessions_job: drift on session=%s own=%s current=%s — skipping",
                combined_session_id, own_job_id, current_job_id,
            )
            return {
                "status": "skipped",
                "reason": "drift",
                "session_pk": combined_session_id,
                "own_job_id": own_job_id,
                "current_job_id": current_job_id,
            }

        # ---- Step 1: assemble the transcript from the parts ----
        try:
            built = sc.build_combined_transcript(db, session)
            if not built["parts"]:
                raise RuntimeError("combined meeting has no parts")
            sc.apply_combined_transcript(session, built)
            session.status = "processing"
            metadata = dict(session.processing_metadata or {})
            metadata.pop("summary_error", None)
            metadata.pop("combine_error", None)
            combined_md = dict(metadata.get("combined") or {})
            combined_md["parts"] = [p.id for p in built["parts"]]
            combined_md["assembled_at"] = datetime.now(timezone.utc).isoformat()
            metadata["combined"] = combined_md
            session.processing_metadata = metadata
            flag_modified(session, "processing_metadata")
            db.commit()
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "combine_sessions_job: transcript assembly failed session=%s",
                combined_session_id,
            )
            error = _stamp_failure(db, session, own_job_id, "assemble", exc)
            return {"status": "failed", "session_pk": combined_session_id, "error": error}

        # ---- Step 2: summary (the finalize call; also promotes action items) ----
        try:
            from api.uploads import _summarize_session

            await _summarize_session(db, session, template="standard", force=force)
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "combine_sessions_job: summary failed session=%s", combined_session_id
            )
            error = _stamp_failure(db, session, own_job_id, "summary", exc)
            from services.transient_errors import is_transient_error, retry_transient

            if is_transient_error(exc):
                await retry_transient(ctx, exc)
            return {
                "status": "failed",
                "session_pk": combined_session_id,
                "error": error,
                "retryable": True,
            }

        # ---- Step 3: AI insights (best-effort, the finalize call) ----
        insights_error: str | None = None
        try:
            from api.ai_insights import _generate_ai_insights

            full_text = (session.transcript_simple or "").strip()
            insights = await _generate_ai_insights(
                full_text,
                built["rows"],
                session,
                db,
                session.organization_id,
            )
            session.ai_insights = insights.model_dump()
        except Exception as exc:  # noqa: BLE001
            insights_error = str(exc)[:500]
            logger.warning(
                "combine_sessions_job: insights failed session=%s: %s",
                combined_session_id, exc,
            )

        # ---- Step 4: mark completed ----
        now = datetime.now(timezone.utc)
        session.status = "completed"
        metadata = dict(session.processing_metadata or {})
        metadata.pop("summary_error", None)
        metadata.pop("combine_error", None)
        metadata["completion"] = {
            "completed_at": now.isoformat(),
            "job_id": own_job_id,
            "summary_error": None,
            "insights_error": insights_error,
            "mode": "combined",
        }
        session.processing_metadata = metadata
        flag_modified(session, "processing_metadata")
        session.updated_at = now
        db.commit()
        return {
            "status": "completed",
            "session_pk": combined_session_id,
            "session_id": session.session_id,
            "parts": [p.id for p in built["parts"]],
            "insights_error": insights_error,
        }
    except asyncio.CancelledError:
        raise
    except Retry:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "combine_sessions_job: unexpected crash session=%s", combined_session_id
        )
        try:
            session = (
                db.query(RecordingSession)
                .filter(RecordingSession.id == combined_session_id)
                .first()
            )
            if session is not None:
                _stamp_failure(db, session, own_job_id, "crash", exc)
        except Exception:  # noqa: BLE001
            logger.exception(
                "combine_sessions_job: could not record failure session=%s",
                combined_session_id,
            )
        return {
            "status": "failed",
            "session_pk": combined_session_id,
            "error": str(exc)[:500],
        }
    finally:
        db.close()
