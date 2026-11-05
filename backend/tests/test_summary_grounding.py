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
        assert len(stored["decisions"]) == 1
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
