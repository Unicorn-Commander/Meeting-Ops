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
