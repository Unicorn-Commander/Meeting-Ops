"""Grounded summary contracts use only fictional meeting data."""

from __future__ import annotations

import asyncio
import json
import uuid


def test_ground_summary_keeps_verified_cite_and_moves_fabrication():
    from services.summary_grounding import ground_summary

    transcript = "Alice Morgan: I will send the sample report tomorrow. Bob Lee: Use the blue design."
    summary = {
        "actions": [
            {
                "action": "Alice will send the sample report tomorrow.",
                "cites": [{
                    "start_s": 3,
                    "end_s": 8,
                    "speaker": "Alice Morgan",
                    "quote": "I will send the sample report tomorrow.",
                }],
            },
            {
                "action": "Bob will share the architecture packet.",
                "cites": [{
                    "start_s": 12,
                    "end_s": 18,
                    "speaker": "Bob Lee",
                    "quote": "I will share the architecture packet.",
                }],
            },
        ],
        "decisions": [{
            "text": "Use the blue design.",
            "cites": [{
                "start_s": 20,
                "end_s": 24,
                "speaker": "Bob Lee",
                "quote": "Use the blue design.",
            }],
        }],
        "projects": ["Blue Design", "Ghost Project"],
    }

    grounded = ground_summary(summary, transcript)

    assert len(grounded["actions"]) == 1
    assert grounded["actions"][0]["cites"][0]["quote"].startswith("I will send")
    assert len(grounded["decisions"]) == 1
    assert grounded["projects"] == ["Blue Design"]
    assert len(grounded["unverified"]) == 1
    assert grounded["unverified"][0]["reason"] == (
        "citation quote was not found in the transcript"
    )
    assert grounded["unverified"][0]["action"].startswith("Bob will share")


def test_participants_dedupe_names_and_keep_generic_voice_out():
    from services.summary_grounding import dedupe_participants

    participants = dedupe_participants([
        {"name": "Alice Morgan", "speaker_id": "voice-a"},
        {"name": " alice   morgan ", "speaker_id": "voice-a"},
        {"name": "Speaker 4", "speaker_id": "voice-four"},
        {"name": "Morgan Lee", "speaker_id": "voice-b"},
    ])

    assert [row["name"] for row in participants] == ["Alice Morgan", "Morgan Lee"]


def test_rendering_has_markers_and_old_items_stay_unchanged():
    from services.summary_grounding import render_cited_item

    cited = {
        "text": "Alice will send the sample report.",
        "cites": [{"start_s": 754, "end_s": 760, "speaker": "Alice Morgan", "quote": "send the sample report"}],
    }
    assert render_cited_item(cited) == "Alice will send the sample report. [12:34]"
    assert render_cited_item(cited, plain=True).endswith("(cited: 12:34)")
    assert render_cited_item("Legacy summary item") == "Legacy summary item"


def test_nested_cites_json_fixture_is_parsed(client, monkeypatch):
    import api.uploads as uploads_mod
    from database.database import SessionLocal
    from database.models import RecordingSession

    class FakeLLM:
        async def chat(self, **_kwargs):
            return """```json
{"executive":"Alice Morgan and Bob Lee agreed on a blue design and a sample report.",
 "bullets":[],
 "actions":[{"action":"Alice will send the sample report tomorrow.","owner":"Alice Morgan","cites":[{"start_s":3,"end_s":8,"speaker":"Alice Morgan","quote":"I will send the sample report tomorrow."}]},
             {"action":"Bob will share the architecture packet.","owner":"Bob Lee","cites":[{"start_s":12,"end_s":18,"speaker":"Bob Lee","quote":"I will share the architecture packet."}]}],
 "decisions":[{"text":"Use the blue design.","cites":[{"start_s":20,"end_s":24,"speaker":"Bob Lee","quote":"Use the blue design."}]}],
 "participants":[{"name":"Alice Morgan","speaker_id":"voice-a"},{"name":" alice  morgan ","speaker_id":"voice-a"},{"name":"Speaker 4","speaker_id":"voice-four"}],
 "projects":["Blue Design","Ghost Project"],"questions":[],"title":"Blue Design Review"}
```"""

    monkeypatch.setattr(uploads_mod, "_direct_summarizer_provider", lambda: FakeLLM())
    db = SessionLocal()
    session = RecordingSession(
        session_id=str(uuid.uuid4()),
        name="grounding-fictional-call",
        title="Grounding fictional call",
        status="completed",
        transcript_simple=(
            "I will send the sample report tomorrow. Use the blue design."
        ),
        transcript_diarized={
            "segments": [
                {
                    "start_s": 3,
                    "end_s": 8,
                    "speaker": "Alice Morgan",
                    "text": "I will send the sample report tomorrow.",
                },
                {
                    "start_s": 20,
                    "end_s": 24,
                    "speaker": "Bob Lee",
                    "text": "Use the blue design.",
                },
            ],
        },
        participants=[
            {"name": "Alice Morgan", "speaker_id": "voice-a"},
            {"name": " alice morgan ", "speaker_id": "voice-a"},
            {"name": "Speaker 4", "speaker_id": "voice-four"},
        ],
        organization_id=1,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    try:
        asyncio.run(uploads_mod._summarize_session(db, session, force=True))
        stored = session.final_summary
        assert stored["actions"][0]["cites"][0]["start_s"] == 3.0
        assert len(stored["actions"]) == 1
        assert stored["decisions"] == ["Use the blue design. [00:20]"]
        assert stored["decisions_cited"][0]["cites"][0]["start_s"] == 20.0
        assert "; ".join(stored["decisions"])  # the reader in ai_chat.py joins strings
        assert stored["projects"] == ["Blue Design"]
        assert [p["name"] for p in stored["participants"]] == ["Alice Morgan"]
        assert len(stored["unverified"]) == 1
        assert stored["unverified"][0]["reason"] == (
            "citation quote was not found in the transcript"
        )
        assert json.loads(session.summary)["actions"] == stored["actions"]
    finally:
        db.close()


def test_mcp_summary_rendering_uses_citation_markers(monkeypatch):
    from services import mcp_app

    async def fake_api(_method, _path, **_kwargs):
        return {
            "title": "Blue Design Review",
            "status": "completed",
            "final_summary": {
                "decisions": [{
                    "text": "Use the blue design.",
                    "cites": [{"start_s": 20, "end_s": 24, "speaker": "Bob Lee", "quote": "Use the blue design."}],
                }],
                "actions": [{
                    "action": "Alice will send the sample report.",
                    "cites": [{"start_s": 754, "end_s": 760, "speaker": "Alice Morgan", "quote": "send the sample report"}],
                }],
            },
        }

    monkeypatch.setattr(mcp_app, "_api", fake_api)
    rendered = asyncio.run(mcp_app.get_meeting_details("fictional-session"))
    assert "Use the blue design. [00:20]" in rendered
    assert "(cited: 00:20)" in rendered
    assert "Alice will send the sample report. [12:34]" in rendered


def test_render_prefix_is_compact_and_quotes_check_the_words_alone():
    from services.summary_grounding import (
        render_timestamped_segments,
        spoken_text,
        validate_item_cites,
    )

    segments = [
        {"start_s": 754.2, "end_s": 758.9, "speaker": "Alice Morgan", "text": "We should send the"},
        {"start_s": 759.0, "end_s": 761.0, "speaker": "Bob Lee", "text": "sample report on Friday."},
    ]
    rendered, _ = render_timestamped_segments(segments)
    assert rendered.split("\n")[0] == "[754-759] Alice Morgan: We should send the"
    # A quote across two lines verifies against the words, never the prefix.
    item = {"text": "x", "cites": [{"quote": "send the sample report", "start_s": 1, "end_s": 2}]}
    assert validate_item_cites(item, spoken_text(segments))[1] is None
    faked = {"text": "x", "cites": [{"quote": "[754-759] Alice Morgan", "start_s": 1, "end_s": 2}]}
    assert validate_item_cites(faked, spoken_text(segments))[1]


def test_cite_times_come_from_the_segment_not_the_model():
    from services.summary_grounding import stamp_cites_from_segments

    segments = [
        {"start_s": 10, "end_s": 14, "text": "use the blue design"},
        {"start_s": 300, "end_s": 305, "text": "again use the blue design please"},
    ]
    summary = {"decisions": [{"text": "d", "cites": [{"quote": "use the blue design", "start_s": 290, "end_s": 291}]}]}
    stamp_cites_from_segments(summary, segments)
    assert summary["decisions"][0]["cites"][0]["start_s"] == 300.0
    assert summary["decisions"][0]["cites"][0]["end_s"] == 305.0


def test_a_verified_quote_without_times_stays_and_renders_no_marker():
    from services.summary_grounding import render_cited_item, validate_item_cites

    item = {"text": "Use blue.", "cites": [{"speaker": "Bob Lee", "quote": "use the blue design"}]}
    cites, reason = validate_item_cites(item, "We will use the blue design.")
    assert reason is None and "start_s" not in cites[0]
    assert render_cited_item({"text": "Use blue.", "cites": cites}) == "Use blue."


def test_a_partial_run_keeps_the_complete_summary(client, monkeypatch):
    import api.uploads as uploads_mod
    from database.database import SessionLocal
    from database.models import RecordingSession

    class FakeLLM:
        async def chat(self, *, user_prompt, **_kwargs):
            if "chunk 1 of" in user_prompt:
                raise RuntimeError("simulated outage")
            if "CHUNK DIGESTS" in user_prompt:
                return '```json\n{"executive":"Only the second half of this meeting was covered here.","title":"Bad title","actions":[],"decisions":[]}\n```'
            return '{"key_points": ["a point"], "action_items": []}'

    monkeypatch.setattr(uploads_mod, "_direct_summarizer_provider", lambda: FakeLLM())
    monkeypatch.setenv("MEETING_OPS_SUMMARY_MAPREDUCE", "1")
    monkeypatch.setenv("MEETING_OPS_SUMMARY_CHUNK_TOKENS", "2000")
    monkeypatch.setenv("MEETING_OPS_SUMMARY_CHUNK_OVERLAP_TOKENS", "0")
    words = " ".join(f"word{i}" for i in range(12))
    db = SessionLocal()
    good = json.dumps({"executive": "The complete summary from the earlier run.", "actions": []})
    session = RecordingSession(
        session_id=str(uuid.uuid4()),
        name="partial-run-fictional-call",
        title="Good title",
        status="completed",
        summary=good,
        transcript_simple=words,
        transcript_diarized={
            "segments": [
                {"start_s": i, "end_s": i + 1, "speaker": "Alice Morgan" if i % 2 else "Bob Lee", "text": words}
                for i in range(1500)
            ],
        },
        processing_metadata={"summary_input_hash": "older-complete-run"},
        organization_id=1,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    try:
        asyncio.run(uploads_mod._summarize_session(db, session))
        db.refresh(session)
        assert session.summary == good
        assert session.title == "Good title"
    finally:
        db.delete(session)
        db.commit()
        db.close()


def test_a_true_quote_that_runs_long_keeps_the_commitment_and_a_fabricated_one_does_not():
    from services.summary_grounding import MAX_CITATION_QUOTE_CHARS, validate_item_cites

    said = " ".join(f"word{i}" for i in range(80))
    cites, reason = validate_item_cites(
        {"text": "x", "cites": [{"quote": said, "start_s": 1, "end_s": 2}]}, said
    )
    assert reason is None
    assert len(cites[0]["quote"]) <= MAX_CITATION_QUOTE_CHARS
    assert said.startswith(cites[0]["quote"])

    invented = " ".join(f"other{i}" for i in range(80))
    cites, reason = validate_item_cites(
        {"text": "x", "cites": [{"quote": invented, "start_s": 1, "end_s": 2}]}, said
    )
    assert cites is None and reason == "citation quote was not found in the transcript"


def test_a_first_name_folds_into_the_one_full_name_it_could_be():
    from services.summary_grounding import dedupe_participants

    rows = dedupe_participants([
        {"name": "Avery Quimby", "kind": "human"},
        {"name": "Jordan", "kind": "human", "id": "abc"},
        {"id": "4a77", "name": "Unicorn Stable Transcript Bridge", "role": "recorder"},
        {"name": "Jordan Reyes"},
        {"name": "Speaker 4"},
    ])
    assert [r["name"] for r in rows] == ["Avery Quimby", "Jordan Reyes"]
    assert rows[1]["id"] == "abc" and rows[1]["kind"] == "human"


def test_a_first_name_two_people_share_stays_apart():
    from services.summary_grounding import dedupe_participants

    rows = dedupe_participants([{"name": "Sam"}, {"name": "Sam Ortiz"}, {"name": "Sam Lee"}])
    assert [r["name"] for r in rows] == ["Sam", "Sam Ortiz", "Sam Lee"]


def test_a_quote_may_differ_in_punctuation_but_not_in_words():
    from services.summary_grounding import validate_item_cites

    said = "Yeah, I'll keep it close -- patent pending, right?"
    item = {"text": "x", "cites": [{"quote": "yeah i'll keep it close patent pending right", "start_s": 1, "end_s": 2}]}
    assert validate_item_cites(item, said)[1] is None
    wrong = {"text": "x", "cites": [{"quote": "yeah i will keep it close", "start_s": 1, "end_s": 2}]}
    assert validate_item_cites(wrong, said)[1]
