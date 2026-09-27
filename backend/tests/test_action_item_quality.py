"""Tier-1 action-item quality gate.

The negatives are real extraction strings from a customer call, genericised.
The positives are commitments that must survive the same gate.
"""

from __future__ import annotations

import logging

from services.action_item_quality import (
    apply_quality_gate,
    classify_action_item,
    gate_summary_lists,
    tier2_llm_verifier,
)


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


def item_text_of(item):
    if isinstance(item, str):
        return item
    return item.get("text") or item.get("action") or item.get("task")
