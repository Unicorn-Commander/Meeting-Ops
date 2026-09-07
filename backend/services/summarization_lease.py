"""One live summarization run per meeting — across processes, not just this one.

The live-summary websocket is opened *per viewer* and asks the summarizer to
start on connect, so three people watching one meeting is three ``start``
calls. Both summarizers the socket can reach — ``unified_agent_service`` and
``auto_summarization_service`` — collapse those into one background run using
an in-process dict (``active_sessions`` / ``active_tasks``).

That dict is correct only while the backend is exactly one process. Production
runs a single uvicorn worker today, so it holds. The moment anyone adds
``--workers``, a second replica, or moves a summarizer into the arq workers
(same image, already running beside the backend), each process gets its own
dict, and the same meeting is summarized N times: N LLM bills against one
transcript, with nothing in the logs to say so.

This module is the cross-process backstop. The in-process dicts stay as the
cheap fast path; the lease row is the correctness layer underneath them.

Why a lease row and not ``pg_try_advisory_lock``
------------------------------------------------
A session-scoped advisory lock lives on a *connection*, so holding one for the
length of a meeting means holding a pooled connection for the length of a
meeting. ``database.database`` builds the engine on SQLAlchemy's default
QueuePool — ``pool_size=5``, ``max_overflow=10``, i.e. 15 connections for the
whole process — shared with every HTTP request handler, and sets
``pool_recycle=1800`` precisely because connections here are not meant to be
held open for long. Five concurrent live meetings would permanently consume a
third of that pool; fifteen would deadlock the API while every summarizer sat
there holding a lock. The one advisory lock already in this codebase
(``api/stable_ingest.py``) is ``pg_advisory_xact_lock`` — transaction-scoped
and short — which is the shape advisory locks actually fit here.

A lease row needs only short transactions, survives process death through its
expiry, and can be inspected with a ``SELECT`` when someone asks "why is
nothing summarizing this meeting".

Failure policy: fail OPEN
-------------------------
If the lease table is unreachable or missing (e.g. a deploy that has not run
``alembic upgrade head`` yet), acquisition is granted and the failure is logged
at ERROR. A guard that failed closed would silently stop producing summaries
for every meeting — strictly worse than the duplicate billing it defends
against. When that happens the in-process dict is still enforced, so behaviour
degrades to exactly what it was before this module existed.

Scope
-----
This guards the *live, long-running* summarizers only:
``unified_agent_service.start_meeting_analysis`` and
``auto_summarization_service.start_auto_summarization``. One-shot
finalize/satellite summarization (``analyze_meeting``, the finalize workers)
is deliberately NOT gated: those run once per completed session, and blocking
one behind a live lease would lose a summary rather than save a duplicate.

Times are stored as naive UTC. The column is ``TIMESTAMP WITHOUT TIME ZONE``
(the convention in ``database.models``), and comparing that against an
aware bind parameter makes Postgres apply an implicit cast that depends on the
session ``TimeZone``. Binding naive UTC on both sides keeps the comparison
purely timestamp-vs-timestamp on Postgres and native on SQLite.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import os
import socket
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable, Dict, Optional, Union

from sqlalchemy import delete, insert, select, update
from sqlalchemy.exc import IntegrityError

from database.database import SessionLocal
from database.models import SummarizationLease as SummarizationLeaseRow

logger = logging.getLogger(__name__)

DEFAULT_LEASE_TTL_SECONDS = 120
DEFAULT_HEARTBEAT_SECONDS = 30

LostCallback = Callable[[str], Union[None, Awaitable[None]]]


def _positive_int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        logger.warning("%s=%r is not an integer; using %s", name, raw, default)
        return default
    return value if value > 0 else default


def lease_ttl_seconds() -> int:
    """How long a lease stays valid without a heartbeat.

    Read per call so operators can retune without a code change, and so tests
    can shorten it. The ceiling on "how long a meeting goes unsummarized after
    the process holding its lease dies".
    """
    return _positive_int_env("SUMMARIZATION_LEASE_TTL_SECONDS", DEFAULT_LEASE_TTL_SECONDS)


def heartbeat_interval_seconds() -> int:
    """Gap between heartbeats. Must stay well under the TTL."""
    return _positive_int_env("SUMMARIZATION_LEASE_HEARTBEAT_SECONDS", DEFAULT_HEARTBEAT_SECONDS)


_holder_cache: Optional[tuple] = None


def holder_id() -> str:
    """Identity of this process as a lease holder.

    Cached per PID rather than at import: uvicorn ``--workers`` and any
    ``fork`` after import would otherwise hand every child the parent's id,
    and children would happily renew each other's leases.
    """
    global _holder_cache
    pid = os.getpid()
    if _holder_cache is None or _holder_cache[0] != pid:
        _holder_cache = (pid, f"{socket.gethostname()}:{pid}:{uuid.uuid4().hex[:8]}")
    return _holder_cache[1]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# Synchronous DB primitives. Called through asyncio.to_thread; each opens and
# closes its own short-lived session so nothing holds a pooled connection.
# ---------------------------------------------------------------------------


def _try_acquire_row(session_id: str, holder: str, ttl_seconds: int) -> bool:
    """Claim the lease for ``session_id``. True only if this holder won it."""
    now = _utcnow()
    expires_at = now + timedelta(seconds=ttl_seconds)
    db = SessionLocal()
    try:
        # 1. Take over an expired lease (previous holder died). Two processes
        #    racing here serialise on the row lock: the loser re-evaluates its
        #    WHERE against the winner's committed row, no longer matches, and
        #    reports 0 rows.
        stolen = db.execute(
            update(SummarizationLeaseRow)
            .where(
                SummarizationLeaseRow.session_id == session_id,
                SummarizationLeaseRow.expires_at <= now,
            )
            .values(
                holder=holder,
                acquired_at=now,
                heartbeat_at=now,
                expires_at=expires_at,
            )
        ).rowcount
        if stolen:
            db.commit()
            return True

        # 2. A row exists and has not expired: somebody is summarizing this
        #    meeting right now.
        existing = db.execute(
            select(SummarizationLeaseRow.session_id).where(
                SummarizationLeaseRow.session_id == session_id
            )
        ).first()
        if existing is not None:
            db.rollback()
            return False

        # 3. No row at all — claim it. If another process claims it in the
        #    same instant, the primary key makes exactly one of us win.
        db.execute(
            insert(SummarizationLeaseRow).values(
                session_id=session_id,
                holder=holder,
                acquired_at=now,
                heartbeat_at=now,
                expires_at=expires_at,
            )
        )
        db.commit()
        return True
    except IntegrityError:
        db.rollback()
        return False
    finally:
        db.close()


def _renew_row(session_id: str, holder: str, ttl_seconds: int) -> bool:
    """Push the expiry out. False means this holder no longer owns the lease.

    Deliberately does not require the lease to be unexpired: if it lapsed and
    nobody took it, reclaiming it is right. If somebody *did* take it, the
    holder no longer matches and we correctly learn we lost it.
    """
    now = _utcnow()
    db = SessionLocal()
    try:
        renewed = db.execute(
            update(SummarizationLeaseRow)
            .where(
                SummarizationLeaseRow.session_id == session_id,
                SummarizationLeaseRow.holder == holder,
            )
            .values(heartbeat_at=now, expires_at=now + timedelta(seconds=ttl_seconds))
        ).rowcount
        db.commit()
        return bool(renewed)
    finally:
        db.close()


def _release_row(session_id: str, holder: str) -> None:
    """Drop our own lease. Never touches a lease owned by anybody else."""
    db = SessionLocal()
    try:
        db.execute(
            delete(SummarizationLeaseRow).where(
                SummarizationLeaseRow.session_id == session_id,
                SummarizationLeaseRow.holder == holder,
            )
        )
        db.commit()
    finally:
        db.close()


def _is_held_row(session_id: str) -> bool:
    """True when any process holds an unexpired lease on this session."""
    now = _utcnow()
    db = SessionLocal()
    try:
        row = db.execute(
            select(SummarizationLeaseRow.session_id).where(
                SummarizationLeaseRow.session_id == session_id,
                SummarizationLeaseRow.expires_at > now,
            )
        ).first()
        return row is not None
    finally:
        db.close()


@dataclass
class _LocalLease:
    session_id: str
    holder: str
    task: Optional[asyncio.Task] = None
    on_lost: Optional[LostCallback] = None
    degraded: bool = False  # DB unreachable at acquire time; in-process only


class SummarizationLeaseManager:
    """Async facade over the lease row, with an in-process fast path."""

    def __init__(self) -> None:
        self._leases: Dict[str, _LocalLease] = {}

    def held_locally(self, session_id: str) -> bool:
        """True when *this* process holds the lease. No I/O."""
        return session_id in self._leases

    async def acquire(
        self,
        session_id: str,
        on_lost: Optional[LostCallback] = None,
    ) -> bool:
        """Claim the right to be the only summarizer for ``session_id``.

        ``on_lost(session_id)`` is invoked if the heartbeat later discovers the
        lease has been taken over — the caller must stop its run, because
        somebody else is now billing against the same transcript.
        """
        # Reserve synchronously. Everything below this line awaits, and N
        # viewers connecting in the same instant all reach here before the
        # first await returns; without the reservation they would all be told
        # "yes". This dict is also the cheap fast path the callers rely on.
        if session_id in self._leases:
            return False
        lease = _LocalLease(session_id=session_id, holder=holder_id(), on_lost=on_lost)
        self._leases[session_id] = lease

        try:
            acquired = await asyncio.to_thread(
                _try_acquire_row, session_id, lease.holder, lease_ttl_seconds()
            )
        except Exception as exc:  # noqa: BLE001 — fail open, loudly
            lease.degraded = True
            logger.error(
                "summarization lease unavailable for session %s (%s). Falling back to "
                "in-process duplicate protection ONLY — if a second backend process "
                "exists it can now summarize this meeting a second time.",
                session_id,
                exc,
                exc_info=True,
            )
            return True

        if not acquired:
            self._leases.pop(session_id, None)
            logger.info(
                "summarization lease for session %s is held by another process; "
                "not starting a second summarizer",
                session_id,
            )
            return False

        lease.task = asyncio.create_task(
            self._heartbeat(lease), name=f"summarization-lease:{session_id}"
        )
        logger.info(
            "summarization lease acquired for session %s by %s (ttl=%ss)",
            session_id,
            lease.holder,
            lease_ttl_seconds(),
        )
        return True

    async def release(self, session_id: str) -> None:
        """Give up our lease so the next viewer can start a fresh run."""
        lease = self._leases.pop(session_id, None)
        if lease is None:
            return

        task = lease.task
        if task is not None and task is not asyncio.current_task():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:  # noqa: BLE001
                logger.debug("summarization lease heartbeat ended with an error", exc_info=True)

        if lease.degraded:
            return

        try:
            await asyncio.to_thread(_release_row, session_id, lease.holder)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "could not release summarization lease for session %s (%s); "
                "it expires on its own within %ss",
                session_id,
                exc,
                lease_ttl_seconds(),
            )

    async def is_held(self, session_id: str) -> bool:
        """True when this or any other process is summarizing this session."""
        if session_id in self._leases:
            return True
        try:
            return await asyncio.to_thread(_is_held_row, session_id)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "could not read summarization lease for session %s (%s); "
                "reporting 'not held'",
                session_id,
                exc,
            )
            return False

    async def release_all(self) -> None:
        for session_id in list(self._leases):
            await self.release(session_id)

    async def _heartbeat(self, lease: _LocalLease) -> None:
        """Keep the lease alive, and stop the run if we ever lose it.

        Runs as its own task rather than inline in the summarization loop: a
        summarization tick can block on an LLM call for minutes, and a lease
        whose renewal is stuck behind that call would lapse and be stolen while
        this process was still, from its own point of view, running fine.
        """
        interval = heartbeat_interval_seconds()
        while True:
            await asyncio.sleep(interval)
            try:
                still_ours = await asyncio.to_thread(
                    _renew_row, lease.session_id, lease.holder, lease_ttl_seconds()
                )
            except Exception as exc:  # noqa: BLE001
                # A blip is survivable: the lease outlives several missed beats.
                logger.warning(
                    "summarization lease heartbeat failed for session %s (%s); retrying in %ss",
                    lease.session_id,
                    exc,
                    interval,
                )
                continue

            if still_ours:
                continue

            # Another holder owns this meeting now. Drop the reservation before
            # calling back, so the callback's own release() is a no-op instead
            # of deleting the new owner's row.
            logger.error(
                "summarization lease for session %s was taken over by another holder; "
                "stopping this process's run so the meeting is not summarized twice",
                lease.session_id,
            )
            self._leases.pop(lease.session_id, None)
            if lease.on_lost is not None:
                try:
                    result = lease.on_lost(lease.session_id)
                    if inspect.isawaitable(result):
                        await result
                except Exception:  # noqa: BLE001
                    logger.error(
                        "summarization lease on_lost handler failed for session %s",
                        lease.session_id,
                        exc_info=True,
                    )
            return


# Singleton shared by both summarizers: the lease is per *meeting*, not per
# service, so whichever summarizer gets there first excludes the other.
summarization_lease = SummarizationLeaseManager()
