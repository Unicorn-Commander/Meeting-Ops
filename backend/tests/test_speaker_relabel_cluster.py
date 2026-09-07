"""Naming a speaker cluster must rewrite every STORED label the cluster
carries — transcript rows, diarized segments, summary prose — not just the
diarizer code. Shape of session 934 (2026-09-07): finalize had written the
auto-profile handle "Speaker 3F97" into rows + summary; re-linking the
cluster to a named profile changed nothing because only "SPEAKER_00" was
matched."""

from __future__ import annotations

import json

from api.speakers import _cluster_current_labels, _relabel_cluster
from database.models import RecordingSession, SpeakerProfile, SpeakerSessionLink, Transcription


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
    def __init__(self, rows, *, still_used=None, prev_profile=None):
        self.rows, self.still_used, self.prev_profile = rows, still_used, prev_profile

    def query(self, model):
        if model is Transcription:
            return _Q(all_=self.rows)
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

    assert counts == {"rows": 3, "segments": 2, "summary": True, "hash_reset": True}
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
    assert again == {"rows": 0, "segments": 0, "summary": False, "hash_reset": False}


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
