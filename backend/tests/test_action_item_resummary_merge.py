"""Re-summary must merge action items, not delete and insert them.

A speaker rename enqueues finalize, which runs the summary again. The
rows a person edited, and the Project-Ops stamps on a row the new
summary still contains, have to survive that pass.
"""

from __future__ import annotations

from datetime import datetime, timezone

from database.models import ActionItem
from services.action_items_extractor import persist_action_items


class _Query:
    def __init__(self, db):
        self._db = db
        self._session_id = None

    def filter(self, *exprs):
        for expr in exprs:
            left = getattr(expr, "left", None)
            right = getattr(expr, "right", None)
            if getattr(left, "key", None) == "session_id":
                self._session_id = right.value
        if self._session_id is None:
            raise AssertionError("expected an ActionItem.session_id filter")
        return self

    def order_by(self, *_args):
        return self

    def all(self):
        rows = [row for row in self._db.rows if row.session_id == self._session_id]
        return sorted(rows, key=lambda row: (row.sort_order or 0, row.id or 0))


class _FakeDB:
    def __init__(self, rows):
        self.rows = list(rows)
        self.deleted = []

    def query(self, model):
        if model is not ActionItem:
            raise AssertionError(model)
        return _Query(self)

    def delete(self, row):
        self.deleted.append(row)
        self.rows = [existing for existing in self.rows if existing is not row]

    def add(self, row):
        self.rows.append(row)

    def flush(self):
        return None


class _Session:
    def __init__(self, final_summary, ai_insights=None, organization_id=3):
        self.id = 42
        self.organization_id = organization_id
        self.final_summary = final_summary
        self.ai_insights = ai_insights


def _summary(*actions):
    return {"actions": list(actions)}


def _machine(item_id, text, *, owner=None, due=None, due_iso=None, payload_extra=None, **fields):
    raw = {"action": text}
    if owner is not None:
        raw["owner"] = owner
    if due_iso is not None:
        raw["due_date"] = due_iso
    if payload_extra:
        raw.update(payload_extra)
    body = dict(
        id=item_id,
        session_id=42,
        organization_id=3,
        text=text,
        owner=owner,
        due_date=due,
        status="todo",
        sort_order=item_id,
        source="final_summary",
        raw_payload=raw,
        project_ops_link_state="local_only",
    )
    body.update(fields)
    return ActionItem(**body)


def _texts(db):
    return [row.text for row in db.rows]


def test_human_status_owner_and_due_edits_survive():
    done_at = datetime(2026, 9, 1, 15, 0, tzinfo=timezone.utc)
    user_due = datetime(2026, 10, 2, tzinfo=timezone.utc)
    done = _machine(1, "File the minutes", owner="Ada")
    done.status = "done"
    done.completed_at = done_at
    renamed = _machine(2, "Send the redline", owner="Speaker 1")
    renamed.owner = "Sam Janowczyk"
    rescheduled = _machine(
        3, "Book the room", owner="Ada", due=user_due, due_iso="2026-09-30",
    )
    rewritten = _machine(22, "Email Dana", owner="Ada")
    rewritten.text = "Email Dana the signed notes"
    db = _FakeDB([done, renamed, rescheduled, rewritten])
    session = _Session(_summary(
        {"action": "File the minutes", "owner": "Bob"},
        {"action": "Send the redline", "owner": "Aaron Stransky"},
        {"action": "Book the room", "owner": "Ada", "due_date": "2026-11-01"},
        {"action": "Email Dana the signed notes", "owner": "Bob"},
    ))

    assert persist_action_items(db, session) == 4

    assert done.id == 1 and done.status == "done" and done.completed_at == done_at
    assert done.owner == "Ada"
    assert renamed.id == 2 and renamed.owner == "Sam Janowczyk" and renamed.status == "todo"
    assert rescheduled.id == 3 and rescheduled.due_date == user_due
    assert rewritten.id == 22 and rewritten.text == "Email Dana the signed notes"
    assert rewritten.owner == "Ada"
    assert _texts(db).count("Email Dana the signed notes") == 1
    assert db.deleted == []
    assert _texts(db) == [
        "File the minutes", "Send the redline", "Book the room", "Email Dana the signed notes",
    ]


def test_cancelled_item_is_kept_when_the_new_summary_drops_it():
    cancelled = _machine(4, "Chase the invoice", owner="Ada")
    cancelled.status = "cancelled"
    db = _FakeDB([cancelled])

    assert persist_action_items(db, _Session(_summary())) == 1
    assert db.rows == [cancelled]
    assert cancelled.status == "cancelled"


def test_manual_item_survives_and_is_not_duplicated():
    manual = ActionItem(
        id=5,
        session_id=42,
        organization_id=3,
        text="Buy coffee",
        owner="Aaron",
        status="todo",
        sort_order=9,
        source="manual",
        raw_payload={"manual": True, "created_by_user_id": 7},
        project_ops_link_state="local_only",
    )
    echoed = ActionItem(
        id=6,
        session_id=42,
        organization_id=3,
        text="Send the deck",
        owner="Aaron",
        status="todo",
        sort_order=10,
        source="manual",
        raw_payload={"manual": True, "created_by_user_id": 7},
        project_ops_link_state="local_only",
    )
    db = _FakeDB([manual, echoed])
    session = _Session(_summary(
        {"action": "Send the deck", "owner": "Someone else"},
        {"action": "Book the studio", "owner": "Ada"},
    ))

    assert persist_action_items(db, session) == 3

    assert manual in db.rows and manual.text == "Buy coffee" and manual.owner == "Aaron"
    assert echoed in db.rows and echoed.source == "manual" and echoed.owner == "Aaron"
    assert [row.text for row in db.rows if row.text == "Send the deck"] == ["Send the deck"]
    assert [row.text for row in db.rows if row.text == "Book the studio"] == ["Book the studio"]


def test_manual_row_does_not_consume_the_match_for_a_stamped_machine_row():
    stamped = _machine(
        16,
        "Send the redline",
        owner="Ada",
        payload_extra={"po_task_id": "task-16"},
        project_ops_task_id="task-16",
        project_ops_link_state="approved_linked",
    )
    manual = ActionItem(
        id=17,
        session_id=42,
        organization_id=3,
        text="Send the redline",
        owner="Aaron",
        status="todo",
        sort_order=20,
        source="manual",
        raw_payload={"manual": True},
        project_ops_link_state="local_only",
    )
    db = _FakeDB([stamped, manual])

    assert persist_action_items(db, _Session(_summary(
        {"action": "Send the redline", "owner": "Ada"},
    ))) == 2

    assert db.rows == [stamped, manual]
    assert stamped.raw_payload["po_task_id"] == "task-16"
    assert manual.source == "manual" and manual.owner == "Aaron"


def test_project_ops_stamps_survive_on_a_matched_machine_item():
    row = _machine(
        8,
        "Send the redline",
        owner="Speaker 1",
        payload_extra={
            "po_task_id": "task-8",
            "po_triage_submitted_at": "2026-09-01T00:00:00Z",
            "po_proposal_id": "proposal-8",
            "po_project_number": "P-00055",
            "po_synced_at": "2026-09-01T00:00:01Z",
            "po_triage_source_type": "MEETING_OPS",
        },
        project_ops_task_id="task-8",
        project_ops_proposal_id="proposal-8",
        project_ops_project_number="P-00055",
        project_ops_link_state="approved_linked",
    )
    db = _FakeDB([row])
    session = _Session(_summary(
        {"action": "Send the redline", "owner": "Aaron Stransky"},
    ))

    assert persist_action_items(db, session) == 1

    assert db.rows == [row]
    assert row.id == 8 and row.status == "todo"
    assert row.owner == "Aaron Stransky"
    assert row.project_ops_task_id == "task-8"
    assert row.project_ops_proposal_id == "proposal-8"
    assert row.project_ops_project_number == "P-00055"
    assert row.project_ops_link_state == "approved_linked"
    assert row.raw_payload["po_task_id"] == "task-8"
    assert row.raw_payload["po_triage_submitted_at"] == "2026-09-01T00:00:00Z"
    assert row.raw_payload["po_proposal_id"] == "proposal-8"
    assert row.raw_payload["po_project_number"] == "P-00055"
    assert row.raw_payload["po_synced_at"] == "2026-09-01T00:00:01Z"
    assert row.raw_payload["po_triage_source_type"] == "MEETING_OPS"
    assert row.raw_payload["owner"] == "Aaron Stransky"


def test_column_stamp_is_copied_back_when_the_blob_lost_it():
    row = _machine(
        9,
        "Ping the vendor",
        owner="Ada",
        project_ops_task_id="task-from-column",
        project_ops_link_state="approved_linked",
        project_ops_submitted_at=datetime(2026, 9, 3, tzinfo=timezone.utc),
    )
    db = _FakeDB([row])

    persist_action_items(db, _Session(_summary(
        {"action": "Ping the vendor", "owner": "Ada"},
    )))

    assert db.rows == [row]
    assert row.project_ops_task_id == "task-from-column"
    assert row.project_ops_link_state == "approved_linked"
    assert row.raw_payload["po_task_id"] == "task-from-column"
    assert row.raw_payload["po_triage_submitted_at"] == "2026-09-03T00:00:00Z"


def test_untouched_machine_item_missing_from_the_new_summary_is_removed():
    stale = _machine(10, "Order the parts", owner="Ada")
    kept = _machine(11, "Send the redline", owner="Ada")
    db = _FakeDB([stale, kept])
    session = _Session(_summary(
        {"action": "Send the redline", "owner": "Ada"},
        {"action": "Book the studio", "owner": "Mei"},
    ))

    assert persist_action_items(db, session) == 2

    assert stale in db.deleted and stale not in db.rows
    assert kept in db.rows and kept.id == 11
    fresh = [row for row in db.rows if row.text == "Book the studio"]
    assert len(fresh) == 1 and fresh[0].id is None and fresh[0].status == "todo"
    assert fresh[0].source == "final_summary"


def test_second_persist_does_not_duplicate_rows_or_change_ids():
    due = datetime(2026, 9, 30, tzinfo=timezone.utc)
    session = _Session(_summary(
        {"action": "Send the redline", "owner": "Ada", "due_date": "2026-09-30"},
        {"action": "Book the studio", "owner": "Mei"},
    ))
    db = _FakeDB([])

    assert persist_action_items(db, session) == 2
    first = list(db.rows)
    assert first[0].due_date == due

    assert persist_action_items(db, session) == 2
    assert db.rows == first
    assert db.deleted == []
    assert [row.text for row in db.rows] == ["Send the redline", "Book the studio"]


def test_case_and_whitespace_match_the_same_row():
    row = _machine(12, "Send  the redline", owner="Ada")
    db = _FakeDB([row])

    persist_action_items(db, _Session(_summary(
        {"action": "send the redline", "owner": "Ada"},
    )))

    assert db.rows == [row]
    assert row.id == 12
    assert row.text == "send the redline"


def test_a_different_sentence_does_not_reuse_the_row():
    row = _machine(13, "Send the redline.", owner="Ada")
    db = _FakeDB([row])

    persist_action_items(db, _Session(_summary(
        {"action": "Send the redline", "owner": "Ada"},
    )))

    assert row in db.deleted
    assert len(db.rows) == 1 and db.rows[0] is not row
    assert db.rows[0].text == "Send the redline"
    assert db.rows[0].raw_payload.get("po_task_id") is None


def test_shared_prefix_is_not_the_same_item():
    stem = "x" * 120
    row = _machine(15, stem + " alpha", owner="Ada")
    db = _FakeDB([row])

    persist_action_items(db, _Session(_summary(
        {"action": stem + " beta", "owner": "Ada"},
    )))

    assert row in db.deleted
    assert [item.text for item in db.rows] == [stem + " beta"]


def test_rows_for_another_session_are_left_alone():
    other = _machine(18, "Order the parts", owner="Ada")
    other.session_id = 99
    mine = _machine(19, "Send the redline", owner="Ada")
    db = _FakeDB([other, mine])

    persist_action_items(db, _Session(_summary()))

    assert other in db.rows and other.text == "Order the parts"
    assert mine in db.deleted


def test_missing_organization_does_not_touch_rows():
    row = _machine(20, "Send the redline", owner="Ada")
    db = _FakeDB([row])
    session = _Session(_summary(), organization_id=None)

    assert persist_action_items(db, session) == 0
    assert db.rows == [row] and db.deleted == []


def test_row_without_a_payload_snapshot_is_kept():
    legacy = ActionItem(
        id=21,
        session_id=42,
        organization_id=3,
        text="Legacy task",
        owner=None,
        status="todo",
        sort_order=0,
        source="final_summary",
        raw_payload=None,
        project_ops_link_state="local_only",
    )
    db = _FakeDB([legacy])

    persist_action_items(db, _Session(_summary(
        {"action": "A brand new task"},
    )))

    assert legacy in db.rows and legacy.text == "Legacy task"
    assert any(row.text == "A brand new task" for row in db.rows)
