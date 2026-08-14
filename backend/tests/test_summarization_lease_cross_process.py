"""One meeting gets one summarizer even when the backend is more than one process.

``test_one_summary_per_meeting.py`` pins the in-process guard: N viewers of one
meeting produce one background run. That guard is a dict living inside a
service singleton, so it is worth exactly one process. Production runs a single
uvicorn worker today; add ``--workers``, a replica, or move a summarizer into
the arq worker containers (same image, already running) and each process gets
its own dict, agrees with itself, and summarizes the same transcript again.

These tests prove the cross-process half, and they do it the only way that
counts: by starting **separate operating-system processes**, each with its own
interpreter, its own SQLAlchemy engine and its own copy of the manager's dict,
and letting them collide on one session id. Two coroutines in one event loop
could not tell the difference between a working lease and no lease at all.

Requires PostgreSQL — the suite's default SQLite database is a file per test
run, and exclusion between processes is precisely what it cannot demonstrate.
Set ``MEETING_OPS_POSTGRES_CONTRACT_URL`` (the existing convention, see
``test_stable_ingest_postgres_contract.py``) to a database that has had
``alembic upgrade head`` applied.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

PG_URL_ENV = "MEETING_OPS_POSTGRES_CONTRACT_URL"
BACKEND_DIR = Path(__file__).parents[1]
CHILD_SCRIPT = Path(__file__).with_name("_summarization_lease_child.py")

# Enough for every child to be spawned and to have finished importing before
# the barrier releases them.
BARRIER_DELAY_SECONDS = 4.0
CHILD_TIMEOUT_SECONDS = 120


def _postgres_url() -> str:
    url = os.getenv(PG_URL_ENV)
    if not url:
        pytest.skip(
            f"{PG_URL_ENV} is required: exclusion between processes cannot be "
            f"demonstrated against the suite's per-run SQLite file"
        )
    return url


@pytest.fixture
def leases_table():
    """A Postgres engine, with the lease table proven to exist first."""
    engine = create_engine(_postgres_url(), pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            present = connection.execute(
                text("SELECT to_regclass('public.summarization_leases')")
            ).scalar()
        assert present, (
            "summarization_leases is missing from the target database. Run "
            "`alembic upgrade head` against it — without the table every "
            "acquire fails open and these tests would prove nothing."
        )
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def session_id(leases_table):
    value = f"xproc-{uuid.uuid4()}"
    yield value
    with leases_table.begin() as connection:
        connection.execute(
            text("DELETE FROM summarization_leases WHERE session_id = :sid"),
            {"sid": value},
        )


def _child_env(url: str, ttl_seconds: int | None = None) -> dict:
    env = dict(os.environ)
    env["DATABASE_URL"] = url  # conftest points the parent at SQLite
    env["PYTHONPATH"] = str(BACKEND_DIR)
    env["ENVIRONMENT"] = "test"
    if ttl_seconds is not None:
        env["SUMMARIZATION_LEASE_TTL_SECONDS"] = str(ttl_seconds)
    return env


def _spawn(session_id: str, url: str, *, start_at: float, ttl=None, **flags):
    command = [
        sys.executable,
        str(CHILD_SCRIPT),
        "--session-id",
        session_id,
        "--start-at",
        repr(start_at),
        "--op",
        flags.pop("op", "acquire"),
    ]
    if flags.get("hold_seconds"):
        command += ["--hold-seconds", repr(flags["hold_seconds"])]
    if flags.get("release"):
        command += ["--release"]
    return subprocess.Popen(
        command,
        cwd=str(BACKEND_DIR),
        env=_child_env(url, ttl),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _collect(process) -> dict:
    stdout, stderr = process.communicate(timeout=CHILD_TIMEOUT_SECONDS)
    assert process.returncode == 0, (
        f"lease child exited {process.returncode}\nstdout:\n{stdout}\nstderr:\n{stderr}"
    )
    lines = [line for line in stdout.strip().splitlines() if line.startswith("{")]
    assert lines, f"lease child printed no result\nstdout:\n{stdout}\nstderr:\n{stderr}"
    result = json.loads(lines[-1])
    # acquire() fails OPEN on a database error, so a child that cannot reach
    # Postgres reports "acquired" and several of these tests would pass while
    # proving nothing. (This is not hypothetical: passing the children a
    # SQLAlchemy-masked URL did exactly that.) Refuse the result instead.
    assert not result.get("degraded"), (
        "the lease child could not reach the database and fell back to "
        f"in-process-only protection, so this result is meaningless: {result}"
        f"\nstderr:\n{stderr}"
    )
    return result


def _race(session_id: str, url: str, count: int, **flags) -> list:
    start_at = time.time() + BARRIER_DELAY_SECONDS
    processes = [_spawn(session_id, url, start_at=start_at, **flags) for _ in range(count)]
    return [_collect(process) for process in processes]


def _holders(engine, session_id: str) -> list:
    with engine.connect() as connection:
        return [
            row[0]
            for row in connection.execute(
                text("SELECT holder FROM summarization_leases WHERE session_id = :sid"),
                {"sid": session_id},
            )
        ]


def test_five_separate_processes_produce_one_summarization_lease(leases_table, session_id):
    """The headline: five backends, one meeting, one run.

    This is the test that a change reverting the lease cannot pass. Each child
    is a real process, so the in-process dict inside every one of them says
    "nobody is summarizing this" — only the shared row can make four of them
    back off.
    """
    results = _race(session_id, _postgres_url(), 5, hold_seconds=1.0)

    winners = [r for r in results if r["acquired"]]
    assert len(winners) == 1, (
        f"expected exactly one process to win the meeting, got {len(winners)}: {results}"
    )
    # Every child really was a distinct process with a distinct identity.
    assert len({r["pid"] for r in results}) == 5
    assert len({r["holder"] for r in results}) == 5
    # And the winner is the holder recorded in the database.
    assert _holders(leases_table, session_id) == [winners[0]["holder"]]


def test_a_second_process_is_refused_while_the_first_still_holds(leases_table, session_id):
    url = _postgres_url()

    first = _collect(_spawn(session_id, url, start_at=0.0, hold_seconds=0.0))
    assert first["acquired"] is True
    # The child exited without releasing — a backend that crashed mid-meeting.

    second = _collect(_spawn(session_id, url, start_at=0.0))
    assert second["acquired"] is False, "a live lease must not be stealable"
    assert _holders(leases_table, session_id) == [first["holder"]]


def test_a_lapsed_lease_is_taken_over_so_a_crash_does_not_silence_a_meeting(
    leases_table, session_id
):
    """The other half of the trade: nobody is locked out forever.

    A process that dies holding a lease leaves the row behind. The expiry is
    what stops that from meaning "this meeting is never summarized again".
    """
    url = _postgres_url()

    first = _collect(_spawn(session_id, url, start_at=0.0, ttl=2))
    assert first["acquired"] is True

    blocked = _collect(_spawn(session_id, url, start_at=0.0, ttl=2))
    assert blocked["acquired"] is False

    time.sleep(3)  # outlive the 2s TTL

    taken_over = _collect(_spawn(session_id, url, start_at=0.0, ttl=2))
    assert taken_over["acquired"] is True, "an expired lease must be reclaimable"
    assert _holders(leases_table, session_id) == [taken_over["holder"]]


def test_a_released_lease_frees_the_meeting_immediately(leases_table, session_id):
    url = _postgres_url()

    first = _collect(_spawn(session_id, url, start_at=0.0, release=True))
    assert first["acquired"] is True
    assert first.get("released") is True
    assert _holders(leases_table, session_id) == []

    second = _collect(_spawn(session_id, url, start_at=0.0))
    assert second["acquired"] is True


def test_a_process_cannot_release_a_lease_it_does_not_hold(leases_table, session_id):
    """Guards the release path: it is holder-scoped, not session-scoped.

    Both summarizers share one lease per meeting, and both call release on
    websocket teardown. A release that ignored the holder would let the legacy
    summarizer's teardown hand the unified agent's meeting to anyone.
    """
    url = _postgres_url()

    owner = _collect(_spawn(session_id, url, start_at=0.0))
    assert owner["acquired"] is True

    impostor = _collect(_spawn(session_id, url, start_at=0.0, op="impostor-release"))
    assert impostor["is_held"] is True, "a non-owner must not be able to clear the lease"
    assert _holders(leases_table, session_id) == [owner["holder"]]


def test_two_different_meetings_do_not_block_each_other(leases_table):
    """Guards against a 'fix' that is simply one global lock."""
    url = _postgres_url()
    first_meeting = f"xproc-{uuid.uuid4()}"
    second_meeting = f"xproc-{uuid.uuid4()}"
    try:
        start_at = time.time() + BARRIER_DELAY_SECONDS
        processes = [
            _spawn(first_meeting, url, start_at=start_at, hold_seconds=1.0),
            _spawn(second_meeting, url, start_at=start_at, hold_seconds=1.0),
        ]
        results = [_collect(process) for process in processes]
        assert all(r["acquired"] for r in results), (
            f"separate meetings must each get a run: {results}"
        )
    finally:
        with leases_table.begin() as connection:
            connection.execute(
                text("DELETE FROM summarization_leases WHERE session_id IN (:a, :b)"),
                {"a": first_meeting, "b": second_meeting},
            )
