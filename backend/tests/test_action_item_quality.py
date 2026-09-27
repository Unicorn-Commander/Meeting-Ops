"""Tier-1 action-item quality gate.

The negatives are real extraction strings from a customer call, genericised.
The positives are commitments that must survive the same gate.
"""

from __future__ import annotations

import logging

import pytest

from services.action_item_quality import (
    apply_quality_gate,
    classify_action_item,
    gate_summary_lists,
    get_action_item_gate_mode,
    tier2_llm_verifier,
)


@pytest.fixture(autouse=True)
def _enforce_action_item_gate(monkeypatch):
    """Drop-behavior tests in this module assume enforce. Shadow tests opt out."""
    monkeypatch.setenv("ACTION_ITEM_GATE_MODE", "enforce")


NEGATIVES = [
    (
        "Share screen to demonstrate the system, specifically the Texas section and PDF action features.",
        "in_call_navigation",
    ),
    ("Close the project ops window", "in_call_navigation"),
    (
        "Stop the recording and save the segment, cutting off at the phrase 'can you'.",
        "meeting_mechanics",
    ),
    (
        "Record the screen to capture actions; set format to 'selected window'.",
        "in_call_navigation",
    ),
    ("Play the second half of the track for Aaron", "in_call_navigation"),
    (
        "Provide status update on tonight's episode, including script and segment details",
        "meeting_mechanics",
    ),
    ("Take the car to service.", "personal_errand"),
    ("Attend a relative's funeral.", "personal_errand"),
    ("Install shelves in the garage with a friend.", "personal_errand"),
    (
        "A vendor contact will call Aaron back after getting to the location",
        "third_party_todo",
    ),
    (
        "Invite the group to visit her new home once it is more sophisticated.",
        "personal_errand",
    ),
    (
        "Wait for a partner's update regarding timing; remain available for support.",
        "vague_non_commitment",
    ),
    ("Discuss payment process", "vague_non_commitment"),
    (
        "Confirm trip details and let Aaron know when the trip is done.",
        "personal_errand",
    ),
    ("Scroll to the PDF action", "in_call_navigation"),
    ("Click the mute button", "in_call_navigation"),
    ("Refresh the page and pull up the notes", "in_call_navigation"),
    ("Type it in the chat", "in_call_navigation"),
    ("Mute your microphone", "in_call_navigation"),
    ("Think about the pricing", "vague_non_commitment"),
    ("The meeting is about the website redesign", "topic_restatement"),
    ("Pick up groceries on the way home", "personal_errand"),
    ("A supplier will call Aaron back tomorrow", "third_party_todo"),
    ("Remain available after the call", "vague_non_commitment"),
    ("Pull up the Texas section", "in_call_navigation"),
]

POSITIVES = [
    "Collect outstanding invoices from the realty client.",
    "Create a demo guide for the partner to present to the group's leaders.",
    "Pull Home Assistant automations/scenes into a Git repo for routines as code.",
    "Add 'Plain Language' and 'No Keys in Chat' rules to agent join prompts/house rules.",
    "Set up the prospect to use the open-source tax platform on his own cloud/GPU resources.",
    "Compile the list of requirements and break down website details based on what Aaron sent.",
    "Send the amended contract to Aaron.",
    "Update the compliance report and get confirmation from the doctor.",
    "Email the signed SOW to the customer by Friday.",
    "Draft the onboarding checklist for the new workspace.",
    "Fix the billing export so invoices include tax lines.",
    "Schedule follow-up sync",
    "Finalize Q3 budget by Friday",
    "Document onboarding flow",
    "Book the room",
    "File the minutes",
    "Send the redline",
    "Email Dana the signed notes",
    "Investigate slow dashboard",
    "Write API docs for triage",
    "Email the client the timeline",
    "Send the trip report to the client.",
    "Update the funeral home website copy for the client.",
    "Install the garage door relay into Home Assistant.",
]


def test_required_negatives_drop_with_reason():
    assert len(NEGATIVES) >= 14
    for text, reason in NEGATIVES:
        record = classify_action_item(text)
        assert record.kept is False, text
        assert record.reason == reason, (text, record.reason)
        assert 0.0 < record.confidence <= 1.0


def test_required_positives_are_commitments():
    assert len(POSITIVES) >= 8
    for text in POSITIVES:
        record = classify_action_item(text)
        assert record.kept is True, text
        assert record.reason == "commitment", (text, record.reason)
        assert record.confidence >= 0.8


# The reviewer's first table. Every one of these is a real deliverable.
REVIEW_DELIVERABLES = [
    ("Send the contract to Marcus by Friday.", "commitment"),
    ("Set up the client's Strix box before Monday.", "commitment"),
    ("Stop billing hourly and move Dana's account to a monthly retainer.", "retained"),
    ("Share the proposal with the client by Thursday.", "commitment"),
    ("Pull the latest invoices from Accounting-Ops and send them to the bookkeeper.", "commitment"),
    ("Write a status update on tonight's episode for the sponsor.", "commitment"),
    ("Mute the alert channel in PagerDuty and document the change.", "commitment"),
    ("Pull up the Q3 numbers and send them to the board.", "commitment"),
    ("Set the format of the monthly report to the client template.", "retained"),
    ("Open a window for the new hire in the payroll system.", "retained"),
    ("Open the support tab in the client portal and file the bug.", "commitment"),
    ("Close the browser tab in the runbook and document the incident.", "commitment"),
    ("Click the link in the DocuSign email and countersign the SOW.", "commitment"),
    ("See the screen recording and send notes to the client.", "commitment"),
    ("Share your screen recording of the demo with the client.", "commitment"),
    ("Review the screen share and send the client a punch list.", "commitment"),
    ("Play the new track for the client at Thursday's listening session.", "retained"),
    ("Start the recording of the training video for the client portal.", "retained"),
    ("Stop the recording of hourly time entries and switch the client to a retainer.", "retained"),
    ("Prepare a status update on tonight's episode for the sponsor.", "commitment"),
    ("Draft a status update on tonight's episode for the sponsor.", "commitment"),
    ("Confirm the trip details with the hotel for the client onsite.", "commitment"),
    ("Email the dentist the signed website proposal.", "commitment"),
    ("Install shelves in the client's garage showroom.", "commitment"),
]

# The reviewer's second table. Junk stays junk; the two real lines stay.
REVIEW_JUNK = [
    ("The vendor will email the signed SOW to Aaron.", "third_party_todo"),
    ("The vendor will send the SOW by Friday.", "third_party_todo"),
    ("Their lawyer will review the redlines by Monday.", "third_party_todo"),
    ("The contractor will install the firewall next week.", "third_party_todo"),
    ("Wait for Dana to send the logo.", "vague_non_commitment"),
    ("Let us sync later on pricing.", "vague_non_commitment"),
    ("Book a flight for my vacation.", "personal_errand"),
    ("Pick up my dry cleaning before the client dinner.", "personal_errand"),
    ("End the recording and export the WAV for the client.", "meeting_mechanics"),
    ("Save this segment for the podcast edit.", "meeting_mechanics"),
    ("Scroll a bit so we can see the footer.", "in_call_navigation"),
    ("Type that in chat so Dana has the link.", "in_call_navigation"),
    ("Go back a slide.", "in_call_navigation"),
    ("Refresh the pricing page before the client demo.", "in_call_navigation"),
    ("This meeting covered the retainer transition.", "topic_restatement"),
    ("Today we talked about pricing.", "topic_restatement"),
    ("Discuss the retainer conversion with Dana on Thursday.", "vague_non_commitment"),
]


def test_review_deliverables_are_kept():
    assert len(REVIEW_DELIVERABLES) == 24
    for text, reason in REVIEW_DELIVERABLES:
        record = classify_action_item(text)
        assert record.kept is True, (text, record.reason)
        assert record.reason == reason, (text, record.reason, reason)


def test_review_junk_drops_and_the_two_real_lines_stay():
    for text, reason in REVIEW_JUNK:
        record = classify_action_item(text)
        assert record.kept is False, (text, record.reason)
        assert record.reason == reason, (text, record.reason, reason)

    follow_up = classify_action_item("Follow up with Dana about the retainer.")
    assert follow_up.kept is True
    assert follow_up.reason == "retained"

    look_into = classify_action_item("I will look into the billing discrepancy.")
    assert look_into.kept is True
    assert look_into.reason == "retained"
    assert look_into.confidence < 0.8


def test_owner_and_due_raise_confidence():
    plain = classify_action_item("Send the amended contract to Aaron.")
    named = classify_action_item(
        "Send the amended contract to Aaron.",
        owner="Aaron Stransky",
        due="2026-09-30",
    )
    assert named.confidence > plain.confidence
    assert named.as_dict()["kept"] is True
    assert named.as_dict()["reason"] == "commitment"


def test_vague_item_with_a_concrete_deliverable_is_kept():
    record = classify_action_item(
        "Discuss the payment process and send the revised invoice to the client."
    )
    assert record.kept is True
    assert record.reason == "commitment"


def test_partner_update_noun_does_not_rescue_a_wait():
    record = classify_action_item(
        "Wait for a partner's update regarding timing; remain available for support."
    )
    assert record.kept is False
    assert record.reason == "vague_non_commitment"


def test_outbound_status_report_is_kept():
    record = classify_action_item(
        "Send a status update on the deployment to the client by Friday."
    )
    assert record.kept is True
    assert record.reason == "commitment"


def test_speaker_label_is_not_treated_as_a_real_owner():
    named = classify_action_item("Send the amended contract to Aaron.", owner="Aaron")
    labeled = classify_action_item("Send the amended contract to Aaron.", owner="Speaker 2")
    assert named.confidence > labeled.confidence


def test_gate_drops_logs_and_counts(caplog):
    items = [
        {"action": NEGATIVES[0][0], "owner": "Speaker 1"},
        {"task": "Send the amended contract to Aaron.", "assignee": "Aaron"},
        "Close the project ops window",
        {"text": "Book the room", "owner": "Ada"},
    ]
    with caplog.at_level(logging.INFO, logger="services.action_item_quality"):
        result = apply_quality_gate(items, source="unit")

    assert [item_text_of(item) for item in result.kept] == [
        "Send the amended contract to Aaron.",
        "Book the room",
    ]
    assert result.dropped_count == 2
    assert result.counts["in_call_navigation"] == 2
    assert result.kept[0]["quality"]["kept"] is True
    assert result.kept[0]["quality"]["reason"] == "commitment"
    assert result.dropped[0]["quality"]["kept"] is False
    assert result.dropped[0]["quality"]["reason"] == "in_call_navigation"
    drop_lines = [rec.message for rec in caplog.records if "dropped reason=" in rec.message]
    assert len(drop_lines) == 2
    assert any("reason=in_call_navigation" in line and "source=unit" in line for line in drop_lines)
    batch = [rec.message for rec in caplog.records if " gate source=" in rec.message]
    assert len(batch) == 1
    assert "kept=2" in batch[0]
    assert "dropped=2" in batch[0]
    assert "in_call_navigation:2" in batch[0]


def test_repeat_drop_is_counted_but_not_logged_twice(caplog):
    first = apply_quality_gate(
        [{"text": "Close the project ops window"}],
        source="unit",
    )
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="services.action_item_quality"):
        second = apply_quality_gate(first.dropped, source="unit")
    assert second.dropped_count == 1
    assert not any("dropped reason=" in rec.message for rec in caplog.records)
    assert any("dropped=1" in rec.message for rec in caplog.records)


def test_gate_summary_lists_filters_every_key_and_leaves_prose():
    payload = {
        "executive": "Close the project ops window came up, then we assigned the contract.",
        "actions": [
            {"action": "Close the project ops window"},
            {"action": "Send the amended contract to Aaron.", "owner": "Aaron"},
        ],
        "action_items": ["Take the car to service.", "Compile the list of requirements and break down website details based on what Aaron sent."],
        "actionItems": [{"task": "Scroll to the PDF action", "assignee": "Speaker 3"}],
        "decisions": ["Use the open-source tax platform."],
    }
    gate_summary_lists(payload, source="summary")
    assert len(payload["actions"]) == 1
    assert payload["actions"][0]["quality"]["reason"] == "commitment"
    assert payload["action_items"] == [
        "Compile the list of requirements and break down website details based on what Aaron sent."
    ]
    assert payload["actionItems"] == []
    assert payload["decisions"] == ["Use the open-source tax platform."]
    assert "Close the project ops window" in payload["executive"]


def test_string_items_stay_strings_when_kept():
    result = apply_quality_gate(
        ["Send the amended contract to Aaron.", "Discuss payment process"],
        source="strings",
    )
    assert result.kept == ["Send the amended contract to Aaron."]
    assert result.dropped == ["Discuss payment process"]


def test_empty_and_blank_items_drop_without_inventing_text():
    record = classify_action_item("   ")
    assert record.kept is False
    assert record.reason == "empty"
    assert apply_quality_gate([], source="empty").kept == []


def test_tier2_hook_is_unwired_and_returns_items():
    items = [{"text": "Send the amended contract to Aaron."}]
    assert tier2_llm_verifier(items, transcript="unused") == items
    assert "tier2_llm_verifier" not in apply_quality_gate.__code__.co_names
    assert "tier2_llm_verifier" not in classify_action_item.__code__.co_names
    assert "TODO(tier-2)" in (tier2_llm_verifier.__doc__ or "")


def test_quality_record_lands_on_raw_payload_too():
    result = apply_quality_gate(
        [{
            "text": "Send the amended contract to Aaron.",
            "raw_payload": {"action": "Send the amended contract to Aaron.", "owner": "Aaron"},
        }],
        source="payload",
    )
    quality = result.kept[0]["quality"]
    assert result.kept[0]["raw_payload"]["quality"] == quality
    assert result.kept[0]["raw_payload"]["owner"] == "Aaron"


def test_fixture_count_covers_the_required_set():
    assert len(NEGATIVES) + len(POSITIVES) >= 25


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
        return self

    def order_by(self, *_args):
        return self

    def all(self):
        rows = [row for row in self._db.rows if row.session_id == self._session_id]
        return sorted(rows, key=lambda row: (row.sort_order or 0, row.id or 0))


class _FakeDB:
    def __init__(self, rows):
        self.rows = list(rows)

    def query(self, model):
        return _Query(self)

    def delete(self, row):
        self.rows = [existing for existing in self.rows if existing is not row]

    def add(self, row):
        self.rows.append(row)

    def flush(self):
        return None


class _Session:
    def __init__(self, final_summary):
        self.id = 42
        self.organization_id = 3
        self.final_summary = final_summary
        self.ai_insights = None


def test_persist_stores_commitments_and_drops_navigation(caplog):
    from database.models import ActionItem
    from services.action_items_extractor import persist_action_items

    db = _FakeDB([])
    session = _Session({
        "actions": [
            {"action": "Close the project ops window", "owner": "Speaker 1"},
            {"action": "Send the amended contract to Aaron.", "owner": "Aaron"},
            "Take the car to service.",
        ]
    })
    with caplog.at_level(logging.INFO, logger="services.action_item_quality"):
        stored = persist_action_items(db, session)
    texts = [row.text for row in db.rows]
    assert stored == 1
    assert texts == ["Send the amended contract to Aaron."]
    assert db.rows[0].raw_payload["quality"]["kept"] is True
    assert db.rows[0].raw_payload["quality"]["reason"] == "commitment"
    assert any("reason=in_call_navigation" in rec.message for rec in caplog.records)
    assert any("reason=personal_errand" in rec.message for rec in caplog.records)
    assert isinstance(db.rows[0], ActionItem)


def test_persist_keeps_a_manual_row_even_when_the_text_would_be_dropped():
    from database.models import ActionItem
    from services.action_items_extractor import persist_action_items

    manual = ActionItem(
        id=9,
        session_id=42,
        organization_id=3,
        text="Close the project ops window",
        owner="Ada",
        status="todo",
        sort_order=0,
        source="manual",
        raw_payload={"text": "Close the project ops window"},
    )
    db = _FakeDB([manual])
    session = _Session({"actions": [{"action": "Close the project ops window"}]})
    assert persist_action_items(db, session) == 1
    assert db.rows == [manual]
    assert manual.text == "Close the project ops window"


def item_text_of(item):
    if isinstance(item, str):
        return item
    return item.get("text") or item.get("action") or item.get("task")


def test_commitment_rules_have_no_format_braces_and_prompts_keep_the_json_contract():
    from pathlib import Path

    from services.action_item_quality import COMMITMENT_EXTRACTION_RULES

    assert "{" not in COMMITMENT_EXTRACTION_RULES
    assert "}" not in COMMITMENT_EXTRACTION_RULES
    assert "who will do what, by when" in COMMITMENT_EXTRACTION_RULES
    root = Path(__file__).resolve().parents[1]
    uploads = (root / "api" / "uploads.py").read_text()
    assert "COMMITMENT_EXTRACTION_RULES" in uploads
    assert '"actions":' in uploads
    insights = (root / "api" / "ai_insights.py").read_text()
    assert "text, assignee, priority" in insights
    assert "COMMITMENT_EXTRACTION_RULES" in (root / "models" / "unified_agent.py").read_text()
    joined = "\n".join(
        (root / rel).read_text()
        for rel in (
            "api/recording.py",
            "services/unified_agent_service.py",
            "services/auto_summarization_service.py",
            "services/meeting_notes_service.py",
            "services/agent_manager_service.py",
            "create_agent_tables.py",
        )
    )
    assert joined.count("who will do what, by when") >= 6


_STANDARD_COMMITMENTS_BRIEF = """\
1. Main Topics (3-5 concrete bullet points)
- The retainer transition

2. Key Decisions Made
- Move Dana's account to a monthly retainer.

3. Commitments only (who will do what, by when; use 'owner not stated' when absent)
- Send the amended contract to Aaron.
- Email the signed SOW to the customer by Friday.
- Close the project ops window

4. Open Questions and Risks
- Who signs first?
"""

_EXECUTIVE_COMMITMENTS_BRIEF = """\
1. Key Decisions (bullet points)
- Adopt the monthly retainer.

2. Commitments only: who will do what, by when. Use a real name for the owner when the transcript has one, otherwise the speaker label.
- Send the amended contract to Aaron.
- Email the signed SOW to the customer by Friday.

3. Strategic Implications
- Margin improves next quarter.

4. Next Steps
- Schedule the kickoff.
"""

_ACTION_ITEMS_BRIEF = """\
Key Decisions
- Use the retainer.

Action Items
- Send the amended contract to Aaron.
- Email the signed SOW to the customer by Friday.
"""


def test_parse_summary_commitments_only_heading_fills_action_items():
    """A brief written under the standard prompt lands commitments in action_items."""
    from services.auto_summarization_service import _parse_summary

    parsed = _parse_summary(_STANDARD_COMMITMENTS_BRIEF)
    for line in (
        "Send the amended contract to Aaron.",
        "Email the signed SOW to the customer by Friday.",
    ):
        assert line in parsed["action_items"]
        assert line not in parsed["key_decisions"]
    block = parsed["sections"]["action_items"]
    assert "Send the amended contract to Aaron." in block
    assert "Email the signed SOW to the customer by Friday." in block
    # The navigation line was parsed into the action bucket. The gate may
    # remove it from the list; it must not be filed as a decision.
    assert "Close the project ops window" in block
    assert "Close the project ops window" not in parsed["key_decisions"]
    assert "Move Dana's account to a monthly retainer." in parsed["key_decisions"]
    assert "Who signs first?" not in parsed["action_items"]
    assert "Who signs first?" not in block


def test_parse_summary_executive_commitments_heading_fills_action_items():
    """The executive template uses the same parser and the same heading."""
    from services.auto_summarization_service import _parse_summary

    parsed = _parse_summary(_EXECUTIVE_COMMITMENTS_BRIEF)
    assert "Send the amended contract to Aaron." in parsed["action_items"]
    assert "Email the signed SOW to the customer by Friday." in parsed["action_items"]
    assert "Send the amended contract to Aaron." not in parsed["key_decisions"]
    assert "Adopt the monthly retainer." in parsed["key_decisions"]
    assert "Margin improves next quarter." not in parsed["action_items"]
    assert "Schedule the kickoff." not in parsed["action_items"]
    assert "Margin improves next quarter." not in parsed["sections"]["action_items"]
    assert "Schedule the kickoff." not in parsed["sections"]["action_items"]


def test_gate_mode_defaults_to_shadow(monkeypatch):
    monkeypatch.delenv("ACTION_ITEM_GATE_MODE", raising=False)
    assert get_action_item_gate_mode() == "shadow"


def test_unknown_gate_mode_stays_shadow(monkeypatch):
    monkeypatch.setenv("ACTION_ITEM_GATE_MODE", "observe")
    assert get_action_item_gate_mode() == "shadow"


def test_enforce_gate_mode_is_case_insensitive(monkeypatch):
    monkeypatch.setenv("ACTION_ITEM_GATE_MODE", "ENFORCE")
    assert get_action_item_gate_mode() == "enforce"


def test_shadow_mode_annotates_counts_and_drops_nothing(monkeypatch, caplog):
    monkeypatch.setenv("ACTION_ITEM_GATE_MODE", "shadow")
    items = [
        {"text": "Close the project ops window", "owner": "Speaker 1"},
        {"text": "Send the amended contract to Aaron.", "owner": "Aaron"},
    ]
    with caplog.at_level(logging.INFO, logger="services.action_item_quality"):
        result = apply_quality_gate(items, source="unit")
    assert [item["text"] for item in result.kept] == [
        "Close the project ops window",
        "Send the amended contract to Aaron.",
    ]
    assert result.dropped_count == 1
    assert result.counts["in_call_navigation"] == 1
    assert result.kept[0]["quality"]["kept"] is False
    assert result.kept[0]["quality"]["reason"] == "in_call_navigation"
    assert result.kept[1]["quality"]["kept"] is True
    assert any("would_drop reason=in_call_navigation" in rec.message for rec in caplog.records)
    assert any("mode=shadow" in rec.message and "would_drop=1" in rec.message for rec in caplog.records)


def test_enforce_mode_removes_rejected_items(monkeypatch):
    monkeypatch.setenv("ACTION_ITEM_GATE_MODE", "enforce")
    result = apply_quality_gate(
        [
            {"text": "Close the project ops window"},
            "Send the amended contract to Aaron.",
        ],
        source="unit",
    )
    assert result.kept == ["Send the amended contract to Aaron."]
    assert result.dropped_count == 1
    assert result.dropped[0]["quality"]["kept"] is False


def test_shadow_summary_lists_keep_and_annotate(monkeypatch):
    monkeypatch.setenv("ACTION_ITEM_GATE_MODE", "shadow")
    payload = {
        "actions": [
            {"action": "Close the project ops window"},
            {"action": "Send the amended contract to Aaron.", "owner": "Aaron"},
        ],
        "decisions": ["Use the retainer."],
    }
    gate_summary_lists(payload, source="summary")
    assert len(payload["actions"]) == 2
    assert payload["actions"][0]["quality"]["reason"] == "in_call_navigation"
    assert payload["actions"][0]["quality"]["kept"] is False
    assert payload["actions"][1]["quality"]["reason"] == "commitment"
    assert payload["decisions"] == ["Use the retainer."]


def test_shadow_and_enforce_projectops_push(monkeypatch):
    from services.projectops_writer import _gate_pending_items, _withhold_from_push

    class _Row:
        def __init__(self, text, source="final_summary"):
            self.text = text
            self.owner = "Ada"
            self.source = source
            self.raw_payload = {"action": text}

    class _DB:
        def commit(self):
            self.committed = True

    class _PushSession:
        processing_metadata = None

    def _run(mode):
        monkeypatch.setenv("ACTION_ITEM_GATE_MODE", mode)
        window = _Row("Close the project ops window")
        send = _Row("Send the amended contract to Aaron.")
        manual = _Row("Close the project ops window", source="manual")
        manual.raw_payload = {"text": "Close the project ops window"}
        db = _DB()
        session = _PushSession()
        pushable, classified = _gate_pending_items(
            db, session, [window, send, manual], source="unit-push",
        )
        return pushable, classified, session, window, send, manual

    pushable, classified, session, window, send, manual = _run("shadow")
    assert [row.text for row in pushable] == [
        "Close the project ops window",
        "Send the amended contract to Aaron.",
        "Close the project ops window",
    ]
    assert classified == 1
    note = session.processing_metadata["action_item_quality"]
    assert note["mode"] == "shadow"
    assert note["would_drop"] == 1
    assert note["dropped"] == 0
    assert note["by_reason"] == {"in_call_navigation": 1}
    assert window.raw_payload["quality"]["kept"] is False
    assert send.raw_payload["quality"]["kept"] is True
    assert "quality" not in manual.raw_payload
    assert _withhold_from_push(session, classified) == 0

    pushable, classified, session, window, send, manual = _run("enforce")
    assert [row.text for row in pushable] == [
        "Send the amended contract to Aaron.",
        "Close the project ops window",
    ]
    assert pushable[-1] is manual
    note = session.processing_metadata["action_item_quality"]
    assert note["mode"] == "enforce"
    assert note["dropped"] == 1
    assert note["would_drop"] == 0
    assert window.raw_payload["quality"]["kept"] is False
    assert _withhold_from_push(session, classified) == 1


def _machine_window():
    from database.models import ActionItem

    return ActionItem(
        id=7,
        session_id=42,
        organization_id=3,
        text="Close the project ops window",
        owner="Speaker 1",
        status="todo",
        sort_order=0,
        source="final_summary",
        raw_payload={"action": "Close the project ops window", "owner": "Speaker 1"},
    )


@pytest.mark.parametrize("mode", ["shadow", "enforce"])
def test_resummary_does_not_delete_a_row_only_because_the_gate_rejects_it(mode, monkeypatch):
    monkeypatch.setenv("ACTION_ITEM_GATE_MODE", mode)
    from services.action_items_extractor import persist_action_items

    window = _machine_window()
    db = _FakeDB([window])
    session = _Session({
        "actions": [
            {"action": "Close the project ops window", "owner": "Speaker 1"},
            {"action": "Send the amended contract to Aaron.", "owner": "Aaron"},
        ]
    })
    assert persist_action_items(db, session) == 2
    assert persist_action_items(db, session) == 2
    texts = [row.text for row in db.rows]
    assert texts.count("Close the project ops window") == 1
    assert texts.count("Send the amended contract to Aaron.") == 1
    assert window in db.rows
    if mode == "shadow":
        assert window.raw_payload["quality"]["kept"] is False
        assert window.raw_payload["quality"]["reason"] == "in_call_navigation"
    else:
        assert "quality" not in window.raw_payload


@pytest.mark.parametrize("mode", ["shadow", "enforce"])
def test_resummary_still_deletes_a_row_the_new_summary_omits(mode, monkeypatch):
    monkeypatch.setenv("ACTION_ITEM_GATE_MODE", mode)
    from services.action_items_extractor import persist_action_items

    window = _machine_window()
    db = _FakeDB([window])
    session = _Session({
        "actions": [
            {"action": "Send the amended contract to Aaron.", "owner": "Aaron"},
        ]
    })
    assert persist_action_items(db, session) == 1
    assert window not in db.rows
    assert [row.text for row in db.rows] == ["Send the amended contract to Aaron."]


def test_shadow_persist_stores_a_new_line_the_gate_would_drop(monkeypatch, caplog):
    monkeypatch.setenv("ACTION_ITEM_GATE_MODE", "shadow")
    from services.action_items_extractor import persist_action_items

    db = _FakeDB([])
    session = _Session({
        "actions": [
            {"action": "Close the project ops window", "owner": "Speaker 1"},
            {"action": "Send the amended contract to Aaron.", "owner": "Aaron"},
        ]
    })
    with caplog.at_level(logging.INFO, logger="services.action_item_quality"):
        assert persist_action_items(db, session) == 2
    texts = [row.text for row in db.rows]
    assert texts == [
        "Close the project ops window",
        "Send the amended contract to Aaron.",
    ]
    window = db.rows[0]
    assert window.raw_payload["quality"]["kept"] is False
    assert any("would_drop reason=in_call_navigation" in rec.message for rec in caplog.records)


def test_parse_summary_action_items_heading_still_fills_action_items():
    from services.auto_summarization_service import _parse_summary

    parsed = _parse_summary(_ACTION_ITEMS_BRIEF)
    assert parsed["action_items"] == [
        "Send the amended contract to Aaron.",
        "Email the signed SOW to the customer by Friday.",
    ]
    assert parsed["key_decisions"] == ["Use the retainer."]
    assert "Send the amended contract to Aaron." not in parsed["key_decisions"]


def test_gate_error_fails_open_and_keeps_every_item(monkeypatch, caplog):
    import services.action_item_quality as q

    def boom(*args, **kwargs):
        raise RuntimeError("classifier exploded")

    monkeypatch.setattr(q, "classify_action_item", boom)
    items = [{"text": "Send the amended contract to Aaron."}, "Close the project ops window"]
    with caplog.at_level(logging.WARNING, logger="services.action_item_quality"):
        result = apply_quality_gate(items, source="unit")
    assert result.kept == items
    assert result.dropped == []
    assert result.counts == {"gate_error": 1}
    warnings = [rec for rec in caplog.records if rec.levelno == logging.WARNING and "gate_error" in rec.message]
    assert len(warnings) == 1
    assert "RuntimeError" in warnings[0].message
    assert "amended contract" not in warnings[0].message


def test_item_text_never_reaches_info_logs(caplog):
    text = "Close the project ops window and share the secret plan"
    with caplog.at_level(logging.INFO, logger="services.action_item_quality"):
        apply_quality_gate([{"text": text}], source="unit")
    info_messages = [rec.message for rec in caplog.records if rec.levelno >= logging.INFO]
    assert info_messages, "expected the drop/would_drop INFO lines"
    assert all("secret plan" not in message for message in info_messages)
    assert any("text_len=" in message for message in info_messages)
