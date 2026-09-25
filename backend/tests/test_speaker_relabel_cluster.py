"""Naming a speaker cluster must rewrite every STORED label the cluster
carries — transcript rows, diarized segments, summary prose — not just the
diarizer code. Shape of session 934 (2026-09-07): finalize had written the
auto-profile handle "Speaker 3F97" into rows + summary; re-linking the
cluster to a named profile changed nothing because only "SPEAKER_00" was
matched."""

from __future__ import annotations

import json

from api.speakers import _cluster_current_labels, _relabel_cluster
from database.models import ActionItem, RecordingSession, SpeakerProfile, SpeakerSessionLink, Transcription


class _Q:
    def __init__(self, first=None, all_=None):
        self._first, self._all = first, list(all_ or [])

    def filter(self, *a, **k):
        return self

    def first(self):
        return self._first

    def all(self):
        return list(self._all)


class _FakeDB:
    def __init__(self, rows, *, still_used=None, prev_profile=None, items=None):
        self.rows, self.still_used, self.prev_profile = rows, still_used, prev_profile
        self.items = list(items or [])

    def query(self, model):
        if model is Transcription:
            return _Q(all_=self.rows)
        if model is ActionItem:
            return _Q(all_=self.items)
        if model is SpeakerSessionLink:
            return _Q(first=self.still_used)
        if model is SpeakerProfile:
            return _Q(first=self.prev_profile)
        raise AssertionError(model)


def _segments(cluster_name="Speaker 3F97"):
    return [
        {"start": 0.0, "end": 5.0, "raw_label": "SPEAKER_01", "speaker": "Aaron Stransky", "text": "hi"},
        {"start": 5.0, "end": 9.0, "raw_label": "SPEAKER_00", "speaker": cluster_name, "text": "hey"},
        {"start": 9.0, "end": 12.0, "raw_label": "SPEAKER_01", "speaker": "Aaron Stransky", "text": "so"},
        {"start": 12.0, "end": 20.0, "raw_label": "SPEAKER_00", "speaker": cluster_name, "text": "well"},
    ]


def _session(cluster_name="Speaker 3F97"):
    prose = f"Aaron Stransky and {cluster_name} discussed parts."
    return RecordingSession(
        id=934, organization_id=1, status="completed",
        transcript_diarized={"segments": _segments(cluster_name), "speakers": ["Aaron Stransky", cluster_name]},
        summary=json.dumps({"executive": prose}),
        final_summary={"executive": prose, "bullets": [f"{cluster_name} will order the parts."]},
        ai_insights=None,
        processing_metadata={"summary_input_hash": "deadbeef", "upload_id": "x"},
    )


def _rows(cluster_name="Speaker 3F97"):
    mk = lambda text, spk, s, e: Transcription(session_id=934, text=text, speaker=spk, start_time=s, end_time=e)
    return [
        mk("hi", "Aaron Stransky", 0.0, 5.0),
        mk("hey", cluster_name, 5.0, 9.0),
        mk("so", "Aaron Stransky", 9.0, 12.0),
        mk("well", "SPEAKER_00", 12.0, 20.0),      # stale diarizer code left on a row
        mk("??", "Speaker 2", 12.5, 19.0),          # older normalized label, inside the cluster's time
    ]


def _link(speaker_id=199):
    return SpeakerSessionLink(id=930, session_id=934, organization_id=1, raw_label="SPEAKER_00", speaker_id=speaker_id)


def test_session_934_shape_rows_segments_and_prose_all_renamed():
    session, rows, link = _session(), _rows(), _link()
    db = _FakeDB(rows, still_used=None, prev_profile=SpeakerProfile(id=198, display_name="Speaker 3F97"))

    olds = _cluster_current_labels(db, session, link, previous_speaker_id=198)
    assert olds == {"SPEAKER_00", "Speaker 3F97"}

    counts = _relabel_cluster(db, session, link, olds, "Sam Janowczyk")

    assert counts == {"rows": 3, "segments": 2, "summary": True, "action_items": 0, "hash_reset": True}
    assert [r.speaker for r in rows] == [
        "Aaron Stransky", "Sam Janowczyk", "Aaron Stransky", "Sam Janowczyk", "Sam Janowczyk",
    ]
    segs = session.transcript_diarized["segments"]
    assert [s["speaker"] for s in segs] == ["Aaron Stransky", "Sam Janowczyk", "Aaron Stransky", "Sam Janowczyk"]
    assert all(s["raw_label"] for s in segs)
    assert session.transcript_diarized["speakers"] == ["Aaron Stransky", "Sam Janowczyk"]
    assert "Speaker 3F97" not in session.summary and "Sam Janowczyk" in json.loads(session.summary)["executive"]
    assert session.final_summary["bullets"] == ["Sam Janowczyk will order the parts."]
    assert "summary_input_hash" not in session.processing_metadata
    assert session.processing_metadata["upload_id"] == "x"


def test_relabel_is_idempotent():
    session, rows, link = _session(), _rows(), _link()
    db = _FakeDB(rows, prev_profile=SpeakerProfile(id=198, display_name="Speaker 3F97"))
    olds = _cluster_current_labels(db, session, link, previous_speaker_id=198)
    _relabel_cluster(db, session, link, olds, "Sam Janowczyk")
    again = _relabel_cluster(db, session, link, _cluster_current_labels(db, session, link, 198), "Sam Janowczyk")
    assert again == {"rows": 0, "segments": 0, "summary": False, "action_items": 0, "hash_reset": False}


def test_previous_profile_still_used_by_another_cluster_is_not_a_match_key():
    # Both clusters were "Aaron Stransky"; SPEAKER_00 gets re-pointed to Sam.
    session, rows, link = _session("Aaron Stransky"), _rows("Aaron Stransky"), _link()
    db = _FakeDB(rows, still_used=object(), prev_profile=SpeakerProfile(id=7, display_name="Aaron Stransky"))

    olds = _cluster_current_labels(db, session, link, previous_speaker_id=7)
    assert olds == {"SPEAKER_00"}          # the shared name must not drive string matching

    counts = _relabel_cluster(db, session, link, olds, "Sam Janowczyk")
    # Rows: 5-9 and 12-20 belong to SPEAKER_00 by time, the SPEAKER_01 rows stay Aaron.
    assert [r.speaker for r in rows] == [
        "Aaron Stransky", "Sam Janowczyk", "Aaron Stransky", "Sam Janowczyk", "Sam Janowczyk",
    ]
    assert counts["rows"] == 3 and counts["segments"] == 2
    # Prose untouched: "Aaron Stransky" is still legitimately the other speaker.
    assert counts["summary"] is False
    assert json.loads(session.summary)["executive"] == "Aaron Stransky and Aaron Stransky discussed parts."


def test_unrelated_cluster_rows_never_stolen():
    session, rows, link = _session(), _rows(), _link()
    db = _FakeDB(rows, prev_profile=SpeakerProfile(id=198, display_name="Speaker 3F97"))
    _relabel_cluster(db, session, link, _cluster_current_labels(db, session, link, 198), "Sam Janowczyk")
    assert rows[0].speaker == "Aaron Stransky" and rows[2].speaker == "Aaron Stransky"


def test_no_segments_falls_back_to_label_match_only():
    session, rows, link = _session(), _rows(), _link()
    session.transcript_diarized = None
    db = _FakeDB(rows, prev_profile=SpeakerProfile(id=198, display_name="Speaker 3F97"))
    olds = _cluster_current_labels(db, session, link, previous_speaker_id=198)
    counts = _relabel_cluster(db, session, link, olds, "Sam Janowczyk")
    assert counts["segments"] == 0
    assert [r.speaker for r in rows] == [
        "Aaron Stransky", "Sam Janowczyk", "Aaron Stransky", "Sam Janowczyk", "Speaker 2",
    ]


def _items(cluster_name="Speaker 3F97"):
    mk = lambda text, owner: ActionItem(session_id=934, organization_id=1, text=text, owner=owner)
    return [
        mk(f"{cluster_name} to order the parts", cluster_name),
        mk("Send the deck", "Aaron Stransky"),
        mk("Follow up with SPEAKER_00 on pricing", None),
        mk("Speaker 3F970 is a different handle", "Speaker 3F970"),
    ]


def test_action_item_owners_and_text_follow_the_new_name():
    """Owners were only fixed by the LLM re-summary before; the instant
    relabel now carries the name onto the items too (2026-09-24)."""
    session, rows, link, items = _session(), _rows(), _link(), _items()
    db = _FakeDB(rows, prev_profile=SpeakerProfile(id=198, display_name="Speaker 3F97"), items=items)

    olds = _cluster_current_labels(db, session, link, previous_speaker_id=198)
    counts = _relabel_cluster(db, session, link, olds, "Sam Janowczyk")

    assert counts["action_items"] == 2
    assert [(i.owner, i.text) for i in items] == [
        ("Sam Janowczyk", "Sam Janowczyk to order the parts"),
        ("Aaron Stransky", "Send the deck"),
        (None, "Follow up with Sam Janowczyk on pricing"),
        ("Speaker 3F970", "Speaker 3F970 is a different handle"),   # word-bounded: untouched
    ]
    assert "summary_input_hash" not in session.processing_metadata


def test_action_items_alone_still_reset_the_summary_hash():
    session = _session("Speaker 3F97")
    session.final_summary, session.summary = None, None
    session.transcript_diarized = None
    link, items = _link(), _items()
    db = _FakeDB([], items=items)
    counts = _relabel_cluster(db, session, link, {"Speaker 3F97"}, "Sam Janowczyk")
    assert counts["action_items"] == 1 and counts["hash_reset"] is True


def test_relabeled_machine_item_still_counts_as_machine_for_the_merge():
    """The relabel renames inside raw_payload too, so persist_action_items
    keeps treating the row as an untouched machine row (not a human edit
    that would be kept forever beside a re-extracted duplicate)."""
    from services.action_items_extractor import _row_is_human

    blob = {"action": "Speaker 3F97 to order the parts", "owner": "Speaker 3F97"}
    item = ActionItem(session_id=934, organization_id=1, text=blob["action"],
                      owner="Speaker 3F97", status="todo", source="final_summary",
                      raw_payload=dict(blob))
    assert _row_is_human(item) is False
    session, link = _session(), _link()
    db = _FakeDB(_rows(), prev_profile=SpeakerProfile(id=198, display_name="Speaker 3F97"), items=[item])
    _relabel_cluster(db, session, link, _cluster_current_labels(db, session, link, 198), "Sam Janowczyk")
    assert (item.owner, item.text) == ("Sam Janowczyk", "Sam Janowczyk to order the parts")
    assert item.raw_payload == {"action": "Sam Janowczyk to order the parts", "owner": "Sam Janowczyk"}
    assert _row_is_human(item) is False
