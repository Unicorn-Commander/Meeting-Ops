"""Tests for the Project-Ops action-item bridge writer.

Covers the contract for ``services.projectops_writer``:

   1. creates_tasks_and_stamps      — happy path: a session with 3 action
                                       items + an org default project creates
                                       3 PO tasks, stamps po_task_id /
                                       po_project_number / po_synced_at on
                                       each row, returns created=3 skipped=0.
   2. replay_skips_already_synced   — re-running the writer on the same
                                       session creates 0 and skips 3 (the
                                       po_task_id stamp is the idempotency
                                       key); no duplicate tasks.
   3. noop_when_unconfigured        — PROJECTOPS_API_KEY unset => the client
                                       is log-only; the writer returns
                                       ok=True mode="no-op" with no client
                                       calls and no rows stamped.
   4. failure_returns_ok_false      — when create_task raises, the writer
                                       returns ok=False, the rows are left
                                       unchanged, and NO exception propagates.
   5. no_target_when_unresolved     — no session link, no override, and no
                                       org default => mode="no-target",
                                       created=0 skipped=0, no client calls.
   6. session_link_resolves_target  — session.project_app='project-ops' +
                                       project_id (a UUID) is used directly
                                       as the create target.
   7. override_beats_org_default    — processing_metadata.po_project_override
                                       wins over the org default.
   8. done_status_propagates        — on replay, an already-synced item now
                                       marked 'done' triggers a best-effort
                                       update_task_status(COMPLETED).

The PO HTTP client is replaced by an injected stub (``_FakeProjectOpsClient``)
passed via ``write_action_items_to_projectops(client=...)`` — the same
dependency-injection seam the Brigade writer tests use. No network.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import pytest


# ---------------------------------------------------------------------------
# Test double
# ---------------------------------------------------------------------------


class _FakeProjectOpsClient:
    """Drop-in ProjectOpsClient stub. Records every call; makes no HTTP
    requests. ``create_task`` returns a fixed task id + project number
    unless ``fail`` is set, in which case it raises ProjectOpsClientError
    to exercise the writer's swallow path."""

    def __init__(
        self,
        *,
        is_live: bool = True,
        fail: bool = False,
        task_id: str = "11111111-1111-4111-8111-111111111111",
        project_number: str = "P-00055",
    ) -> None:
        self.is_live = is_live
        self._fail = fail
        self._task_id = task_id
        self._project_number = project_number
        self.created: list[dict[str, Any]] = []
        self.status_updates: list[tuple[str, str]] = []
        self.aclose_called = False

    async def create_task(
        self,
        *,
        project_number: str,
        title: str,
        description: Optional[str] = None,
        priority: str = "MEDIUM",
        due_date: Any = None,
        type: str = "OTHER",
    ) -> dict[str, Any]:
        self.created.append(
            {
                "project_number": project_number,
                "title": title,
                "description": description,
                "priority": priority,
                "due_date": due_date,
                "type": type,
            }
        )
        if self._fail:
            from services.projectops_client import ProjectOpsClientError

            raise ProjectOpsClientError("simulated PO create failure")
        return {"id": self._task_id, "project_number": self._project_number}

    async def update_task_status(self, *, task_id: str, status: str) -> dict[str, Any]:
        self.status_updates.append((task_id, status))
        if self._fail:
            from services.projectops_client import ProjectOpsClientError

            raise ProjectOpsClientError("simulated PO status failure")
        return {}

    async def aclose(self) -> None:
        self.aclose_called = True


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_projectops_env(monkeypatch):
    """Tests must NOT hit a real Project-Ops. Strip env the host shell
    might leak. Tests opt into is_live by injecting a stub client."""
    monkeypatch.delenv("PROJECTOPS_API_KEY", raising=False)
    monkeypatch.delenv("PROJECTOPS_BASE_URL", raising=False)
    yield


# A dedicated loop keeps this version-proof across the get_event_loop()
# deprecation; the writer/client don't cache a loop so isolation is fine.
_LOOP = asyncio.new_event_loop()


def _run(coro):
    return _LOOP.run_until_complete(coro)


def _seed(
    *,
    org_settings: Optional[dict] = None,
    project_app: Optional[str] = None,
    project_id: Optional[str] = None,
    processing_metadata: Optional[dict] = None,
    items: Optional[list[dict]] = None,
):
    """Create one org + one completed session + N action items.

    ``items`` is a list of dicts (text/owner/status/due_date/raw_payload);
    defaults to 3 simple todo items. Returns (org_id, session_id)."""
    from auth.models import Organization, User
    from database.database import SessionLocal
    from database.models import ActionItem, RecordingSession

    db = SessionLocal()
    suffix = uuid.uuid4().hex[:6]
    try:
        org = Organization(
            name=f"POBridge {suffix}",
            slug=f"pob-{suffix}",
            is_active=True,
            settings=org_settings or {},
        )
        db.add(org)
        db.commit()
        db.refresh(org)

        user = db.query(User).filter(User.username == "admin").first()

        session = RecordingSession(
            session_id=str(uuid.uuid4()),
            name="PO bridge test session",
            title="PO bridge test session",
            status="completed",
            organization_id=org.id,
            user_id=user.id if user else None,
            project_app=project_app,
            project_id=project_id,
            processing_metadata=processing_metadata,
            started_at=datetime(2026, 5, 28, 15, 0, tzinfo=timezone.utc),
            transcript_simple="hello project ops",
            duration=120.0,
            participants=[],
            final_summary={"executive": "x", "bullets": [], "actions": []},
        )
        db.add(session)
        db.commit()
        db.refresh(session)

        if items is None:
            items = [
                {"text": "Finalize Q3 budget by Friday", "owner": "Alice"},
                {"text": "Document onboarding flow", "owner": "Bob"},
                {"text": "Schedule follow-up sync", "owner": None},
            ]
        for idx, spec in enumerate(items):
            db.add(
                ActionItem(
                    session_id=session.id,
                    organization_id=org.id,
                    text=spec["text"],
                    owner=spec.get("owner"),
                    status=spec.get("status", "todo"),
                    due_date=spec.get("due_date"),
                    sort_order=idx,
                    source="final_summary",
                    raw_payload=spec.get("raw_payload"),
                )
            )
        db.commit()
        return org.id, session.id
    finally:
        db.close()


def _items_for_session(session_id: int):
    from database.database import SessionLocal
    from database.models import ActionItem

    db = SessionLocal()
    try:
        return (
            db.query(ActionItem)
            .filter(ActionItem.session_id == session_id)
            .order_by(ActionItem.sort_order)
            .all()
        )
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 1. Happy path — 3 creates + stamps
# ---------------------------------------------------------------------------


def test_creates_tasks_and_stamps(client):
    from services.projectops_writer import write_action_items_to_projectops

    org_id, session_id = _seed(
        org_settings={"projectops_default_project_number": "P-00055"},
        items=[
            {
                "text": "Finalize Q3 budget",
                "owner": "Alice",
                "due_date": datetime(2026, 6, 1, tzinfo=timezone.utc),
            },
            {"text": "Document onboarding flow", "owner": "Bob"},
            {"text": "Schedule follow-up sync", "owner": None},
        ],
    )
    stub = _FakeProjectOpsClient(task_id="task-fixed-uuid", project_number="P-00055")

    from database.database import SessionLocal

    db = SessionLocal()
    try:
        result = _run(
            write_action_items_to_projectops(
                db=db, session_pk=session_id, client=stub
            )
        )
    finally:
        db.close()

    assert result.ok is True
    assert result.mode == "live"
    assert result.created == 3
    assert result.skipped == 0

    # 3 create_task calls, each with the resolved target + the item text.
    assert len(stub.created) == 3
    assert {c["project_number"] for c in stub.created} == {"P-00055"}
    assert stub.created[0]["title"] == "Finalize Q3 budget"
    assert stub.created[0]["priority"] == "MEDIUM"
    assert stub.created[0]["type"] == "OTHER"
    # Description carries provenance.
    assert "From meeting:" in stub.created[0]["description"]
    assert "owner: Alice" in stub.created[0]["description"]
    # due_date threaded through (raw datetime; the real client normalizes to
    # ISO). SQLite drops tzinfo on DateTime(timezone=True) round-trip, so
    # compare the calendar date rather than an exact tz-aware instant.
    due = stub.created[0]["due_date"]
    assert due is not None and (due.year, due.month, due.day) == (2026, 6, 1)

    # Every row stamped.
    items = _items_for_session(session_id)
    assert len(items) == 3
    for it in items:
        assert it.raw_payload is not None
        assert it.raw_payload["po_task_id"] == "task-fixed-uuid"
        assert it.raw_payload["po_project_number"] == "P-00055"
        assert it.raw_payload["po_synced_at"].endswith("Z")


# ---------------------------------------------------------------------------
# 2. Replay — re-run skips all, creates none
# ---------------------------------------------------------------------------


def test_replay_skips_already_synced(client):
    from services.projectops_writer import write_action_items_to_projectops
    from database.database import SessionLocal

    org_id, session_id = _seed(
        org_settings={"projectops_default_project_number": "P-00055"}
    )

    # First run stamps all 3.
    first = _FakeProjectOpsClient()
    db = SessionLocal()
    try:
        r1 = _run(
            write_action_items_to_projectops(
                db=db, session_pk=session_id, client=first
            )
        )
    finally:
        db.close()
    assert r1.created == 3 and r1.skipped == 0
    assert len(first.created) == 3

    # Second run: a fresh stub sees the stamps and creates nothing.
    second = _FakeProjectOpsClient()
    db = SessionLocal()
    try:
        r2 = _run(
            write_action_items_to_projectops(
                db=db, session_pk=session_id, client=second
            )
        )
    finally:
        db.close()

    assert r2.ok is True
    assert r2.mode == "live"
    assert r2.created == 0
    assert r2.skipped == 3
    assert second.created == []  # no duplicate tasks
    # Items still marked todo => no status propagation either.
    assert second.status_updates == []


# ---------------------------------------------------------------------------
# 3. No-op when PROJECTOPS_API_KEY unset
# ---------------------------------------------------------------------------


def test_noop_when_unconfigured(client):
    from services.projectops_client import ProjectOpsClient
    from services.projectops_writer import write_action_items_to_projectops
    from database.database import SessionLocal

    org_id, session_id = _seed(
        org_settings={"projectops_default_project_number": "P-00055"}
    )

    # A real client with no env key is log-only.
    probe = ProjectOpsClient()
    assert probe.is_live is False

    db = SessionLocal()
    try:
        result = _run(
            write_action_items_to_projectops(
                db=db, session_pk=session_id, client=probe
            )
        )
    finally:
        db.close()

    assert result.ok is True
    assert result.mode == "no-op"
    assert result.created == 0
    assert result.skipped == 0

    # Nothing got stamped (no client calls happened).
    for it in _items_for_session(session_id):
        assert (it.raw_payload or {}).get("po_task_id") is None


# ---------------------------------------------------------------------------
# 4. Failure path — ok=False, rows unchanged, no exception
# ---------------------------------------------------------------------------


def test_failure_returns_ok_false_rows_unchanged(client):
    from services.projectops_writer import write_action_items_to_projectops
    from database.database import SessionLocal

    org_id, session_id = _seed(
        org_settings={"projectops_default_project_number": "P-00055"}
    )
    failing = _FakeProjectOpsClient(fail=True)

    db = SessionLocal()
    try:
        # Must NOT raise.
        result = _run(
            write_action_items_to_projectops(
                db=db, session_pk=session_id, client=failing
            )
        )
    finally:
        db.close()

    assert result.ok is False
    assert result.mode == "error"
    assert result.created == 0

    # Rows left untouched — nothing stamped.
    for it in _items_for_session(session_id):
        assert (it.raw_payload or {}).get("po_task_id") is None


# ---------------------------------------------------------------------------
# 5. No target resolved — mode="no-target"
# ---------------------------------------------------------------------------


def test_no_target_when_unresolved(client):
    from services.projectops_writer import write_action_items_to_projectops
    from database.database import SessionLocal

    # No org default, no override, no session->PO link.
    org_id, session_id = _seed()
    stub = _FakeProjectOpsClient()

    db = SessionLocal()
    try:
        result = _run(
            write_action_items_to_projectops(
                db=db, session_pk=session_id, client=stub
            )
        )
    finally:
        db.close()

    assert result.ok is True
    assert result.mode == "no-target"
    assert result.created == 0
    assert result.skipped == 0
    assert stub.created == []  # writer returns before any client call


# ---------------------------------------------------------------------------
# 6. Session->PO link resolves the target (UUID used directly)
# ---------------------------------------------------------------------------


def test_session_link_resolves_target(client):
    from services.projectops_writer import write_action_items_to_projectops
    from database.database import SessionLocal

    project_uuid = "abcdef12-3456-4789-8abc-def012345678"
    # No org default — resolution must come from the session link.
    org_id, session_id = _seed(
        project_app="project-ops",
        project_id=project_uuid,
    )
    stub = _FakeProjectOpsClient(project_number="P-00099")

    db = SessionLocal()
    try:
        result = _run(
            write_action_items_to_projectops(
                db=db, session_pk=session_id, client=stub
            )
        )
    finally:
        db.close()

    assert result.created == 3
    # The session's PO project UUID was fed to create_task verbatim.
    assert {c["project_number"] for c in stub.created} == {project_uuid}
    # Stamp uses the project number echoed back by the create response.
    for it in _items_for_session(session_id):
        assert it.raw_payload["po_project_number"] == "P-00099"


# ---------------------------------------------------------------------------
# 7. Per-meeting override beats the org default
# ---------------------------------------------------------------------------


def test_override_beats_org_default(client):
    from services.projectops_writer import write_action_items_to_projectops
    from database.database import SessionLocal

    org_id, session_id = _seed(
        org_settings={"projectops_default_project_number": "P-00001"},
        processing_metadata={"po_project_override": "P-00077"},
    )
    stub = _FakeProjectOpsClient(project_number="P-00077")

    db = SessionLocal()
    try:
        result = _run(
            write_action_items_to_projectops(
                db=db, session_pk=session_id, client=stub
            )
        )
    finally:
        db.close()

    assert result.created == 3
    assert {c["project_number"] for c in stub.created} == {"P-00077"}


# ---------------------------------------------------------------------------
# 8. Marked-done propagates COMPLETED on the skip path
# ---------------------------------------------------------------------------


def test_done_status_propagates_on_replay(client):
    from services.projectops_writer import write_action_items_to_projectops
    from database.database import SessionLocal

    # Items already bridged (po_task_id stamped) AND locally marked done.
    org_id, session_id = _seed(
        org_settings={"projectops_default_project_number": "P-00055"},
        items=[
            {
                "text": "Already done item",
                "owner": "Alice",
                "status": "done",
                "raw_payload": {"po_task_id": "task-A", "po_project_number": "P-00055"},
            },
            {
                "text": "Still open item",
                "owner": "Bob",
                "status": "todo",
                "raw_payload": {"po_task_id": "task-B", "po_project_number": "P-00055"},
            },
        ],
    )
    stub = _FakeProjectOpsClient()

    db = SessionLocal()
    try:
        result = _run(
            write_action_items_to_projectops(
                db=db, session_pk=session_id, client=stub
            )
        )
    finally:
        db.close()

    assert result.created == 0
    assert result.skipped == 2
    # Only the 'done' item triggers a status nudge; 'todo' -> PENDING is skipped.
    assert ("task-A", "COMPLETED") in stub.status_updates
    assert all(tid != "task-B" for tid, _ in stub.status_updates)
