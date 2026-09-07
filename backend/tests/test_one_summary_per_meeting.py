"""N people opening one meeting must produce one summarization run, not N.

The websocket that carries live summaries is opened per viewer, and it asks
the summarizer to start on connect. With three people watching the same
meeting that is three calls to start — so the guard that turns them into one
background task is the thing standing between "one summary" and "three
concurrent summarizers billing three times against the same transcript".

These tests pin that guard on both summarizers the websocket can reach:
``unified_agent_service`` (tried first) and ``auto_summarization_service``
(the fallback). They also pin that a *different* meeting still gets its own
run — a guard that collapsed everything into one would pass a naive count.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest


def test_concurrent_viewers_start_one_summarization_task(monkeypatch):
    from services.auto_summarization_service import AutoSummarizationService

    service = AutoSummarizationService()
    started: list[str] = []

    async def _fake_loop(session_id, websocket_callback=None):
        started.append(session_id)
        # Outlive the joins below so the task stays in active_tasks.
        await asyncio.sleep(3600)

    monkeypatch.setattr(service, "_summarization_loop", _fake_loop)
    monkeypatch.setattr(
        "services.auto_summarization_service._resolve_org_id",
        lambda _session_id: 1,
    )

    session_id = str(uuid.uuid4())

    async def _five_viewers_open_the_meeting():
        await asyncio.gather(
            *(
                service.start_auto_summarization(session_id, organization_id=1)
                for _ in range(5)
            )
        )
        # Let the created task actually enter the loop before we count.
        await asyncio.sleep(0)
        try:
            assert started == [session_id], (
                f"expected exactly one summarization run, got {len(started)}"
            )
            assert len(service.active_tasks) == 1
        finally:
            await service.stop_auto_summarization(session_id)

    asyncio.run(_five_viewers_open_the_meeting())
    assert service.active_tasks == {}


def test_a_second_meeting_still_gets_its_own_run(monkeypatch):
    """Guards against a 'fix' that simply never starts a second summarizer."""
    from services.auto_summarization_service import AutoSummarizationService

    service = AutoSummarizationService()
    started: list[str] = []

    async def _fake_loop(session_id, websocket_callback=None):
        started.append(session_id)
        await asyncio.sleep(3600)

    monkeypatch.setattr(service, "_summarization_loop", _fake_loop)
    monkeypatch.setattr(
        "services.auto_summarization_service._resolve_org_id",
        lambda _session_id: 1,
    )

    first, second = str(uuid.uuid4()), str(uuid.uuid4())

    async def _two_meetings():
        await service.start_auto_summarization(first, organization_id=1)
        await service.start_auto_summarization(first, organization_id=1)
        await service.start_auto_summarization(second, organization_id=1)
        await asyncio.sleep(0)
        try:
            assert sorted(started) == sorted([first, second])
            assert len(service.active_tasks) == 2
        finally:
            await service.stop_auto_summarization(first)
            await service.stop_auto_summarization(second)

    asyncio.run(_two_meetings())


def test_unified_agent_refuses_a_second_analysis_for_one_meeting():
    """The websocket tries this summarizer first; it must be singular too."""
    from services.unified_agent_service import UnifiedAgentService

    service = UnifiedAgentService()
    session_id = str(uuid.uuid4())
    # Simulate the first viewer having already started analysis.
    service.active_sessions[session_id] = {"session_id": session_id}

    async def _second_viewer():
        return await service.start_meeting_analysis(session_id)

    assert asyncio.run(_second_viewer()) is False
    assert len(service.active_sessions) == 1


@pytest.mark.parametrize("viewers", [2, 5, 25])
def test_the_guard_holds_for_any_number_of_viewers(monkeypatch, viewers):
    from services.auto_summarization_service import AutoSummarizationService

    service = AutoSummarizationService()
    started: list[str] = []

    async def _fake_loop(session_id, websocket_callback=None):
        started.append(session_id)
        await asyncio.sleep(3600)

    monkeypatch.setattr(service, "_summarization_loop", _fake_loop)
    monkeypatch.setattr(
        "services.auto_summarization_service._resolve_org_id",
        lambda _session_id: 1,
    )
    session_id = str(uuid.uuid4())

    async def _run():
        await asyncio.gather(
            *(
                service.start_auto_summarization(session_id, organization_id=1)
                for _ in range(viewers)
            )
        )
        await asyncio.sleep(0)
        try:
            assert len(started) == 1
        finally:
            await service.stop_auto_summarization(session_id)

    asyncio.run(_run())


@pytest.fixture
def lease_table():
    """Create the lease table on the suite's SQLite database.

    Without it every acquire fails open (by design — a guard that stopped all
    summarization when the database blinked would be worse than the duplicate
    it prevents), and these tests would silently fall back to proving only the
    in-process dict. Cross-process exclusion itself is proved against
    PostgreSQL in ``test_summarization_lease_cross_process.py``; SQLite cannot
    show it.
    """
    from database.database import engine
    from database.models import SummarizationLease

    SummarizationLease.__table__.create(bind=engine, checkfirst=True)
    yield
    from services.summarization_lease import summarization_lease

    summarization_lease._leases.clear()


def test_two_viewers_racing_across_the_org_lookup_start_one_run(monkeypatch, lease_table):
    """Two people joining at 9:00 sharp is not a theoretical race.

    The websocket calls ``start_auto_summarization`` WITHOUT an
    organization_id, so the service awaits a database lookup between "is one
    already running?" and "record that one is running". Every viewer who
    connected in that window is already past the check. The other tests in this
    file all pass ``organization_id=1``, which skips the await and hides it.
    """
    import time

    from services.auto_summarization_service import AutoSummarizationService

    service = AutoSummarizationService()
    started: list[str] = []

    async def _fake_loop(session_id, websocket_callback=None):
        started.append(session_id)
        await asyncio.sleep(3600)

    def _slow_org_lookup(_session_id):
        # Runs in a worker thread, so the event loop is free to let the second
        # viewer through — exactly what the real DB round-trip does.
        time.sleep(0.05)
        return 1

    monkeypatch.setattr(service, "_summarization_loop", _fake_loop)
    monkeypatch.setattr(
        "services.auto_summarization_service._resolve_org_id", _slow_org_lookup
    )

    session_id = str(uuid.uuid4())

    async def _two_viewers_join_at_once():
        await asyncio.gather(
            *(service.start_auto_summarization(session_id) for _ in range(2))
        )
        await asyncio.sleep(0)
        try:
            assert started == [session_id], (
                f"expected one summarization run, got {len(started)} — the guard "
                f"lost the race across its own await"
            )
            assert len(service.active_tasks) == 1
        finally:
            await service.stop_auto_summarization(session_id)

    asyncio.run(_two_viewers_join_at_once())


def test_the_legacy_summarizer_stays_off_a_meeting_the_agent_already_owns(
    monkeypatch, lease_table
):
    """The two summarizers must exclude each other, not just themselves.

    The websocket tries the unified agent first and falls back to the legacy
    service when it returns False. Since "already running" is one of the
    reasons it returns False, the fallback used to hand the second viewer of a
    meeting a second summarizer — a different one, so neither service's own
    dict objected. One lease per meeting, shared by both, is what closes that.
    """
    from services.auto_summarization_service import AutoSummarizationService
    from services.summarization_lease import summarization_lease

    service = AutoSummarizationService()
    started: list[str] = []

    async def _fake_loop(session_id, websocket_callback=None):
        started.append(session_id)
        await asyncio.sleep(3600)

    monkeypatch.setattr(service, "_summarization_loop", _fake_loop)
    monkeypatch.setattr(
        "services.auto_summarization_service._resolve_org_id",
        lambda _session_id: 1,
    )

    session_id = str(uuid.uuid4())

    async def _agent_first_then_legacy():
        # Stand in for unified_agent_service having taken this meeting.
        assert await summarization_lease.acquire(session_id) is True
        try:
            await service.start_auto_summarization(session_id, organization_id=1)
            assert started == [], "legacy summarizer started on top of the agent's run"
            assert service.active_tasks == {}
        finally:
            await summarization_lease.release(session_id)

    asyncio.run(_agent_first_then_legacy())


def test_the_agent_refuses_a_meeting_the_legacy_summarizer_already_owns(
    monkeypatch, lease_table
):
    """And the same exclusion in the other direction."""
    from services.summarization_lease import summarization_lease
    from services.unified_agent_service import UnifiedAgentService

    service = UnifiedAgentService()
    session_id = str(uuid.uuid4())

    async def _legacy_first_then_agent():
        assert await summarization_lease.acquire(session_id) is True
        try:
            assert await service.start_meeting_analysis(session_id) is False
            assert service.active_sessions == {}
        finally:
            await summarization_lease.release(session_id)

    asyncio.run(_legacy_first_then_agent())


def test_stopping_a_run_hands_the_meeting_back(monkeypatch, lease_table):
    """A meeting must be summarizable again after its run ends."""
    from services.auto_summarization_service import AutoSummarizationService
    from services.summarization_lease import summarization_lease

    service = AutoSummarizationService()
    started: list[str] = []

    async def _fake_loop(session_id, websocket_callback=None):
        started.append(session_id)
        await asyncio.sleep(3600)

    monkeypatch.setattr(service, "_summarization_loop", _fake_loop)
    monkeypatch.setattr(
        "services.auto_summarization_service._resolve_org_id",
        lambda _session_id: 1,
    )

    session_id = str(uuid.uuid4())

    async def _start_stop_start():
        await service.start_auto_summarization(session_id, organization_id=1)
        # Let the task reach its first line before it is cancelled, or the
        # "ran twice" assertion below counts one run instead of two.
        await asyncio.sleep(0)
        assert started == [session_id]

        await service.stop_auto_summarization(session_id)
        assert await summarization_lease.is_held(session_id) is False

        await service.start_auto_summarization(session_id, organization_id=1)
        await asyncio.sleep(0)
        try:
            assert started == [session_id, session_id]
        finally:
            await service.stop_auto_summarization(session_id)

    asyncio.run(_start_stop_start())
