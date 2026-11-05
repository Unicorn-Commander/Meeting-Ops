"""Contract tests for transcript pagination shared by both agent surfaces."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace

from services.transcript_pagination import paginate_transcript


def _segmented_source(count: int = 4) -> dict:
    return {
        "duration": float(count * 15),
        "transcript_diarized": {
            "segments": [
                {
                    "start": index * 15,
                    "end": (index + 1) * 15,
                    "speaker": "SPEAKER_00" if index % 2 == 0 else "SPEAKER_01",
                    "text": f"Agenda point {index} is complete.",
                }
                for index in range(count)
            ]
        },
        "transcript_simple": " ".join(
            f"Agenda point {index} is complete." for index in range(count)
        ),
    }


def test_default_text_page_has_timestamps_and_default_budget():
    page = paginate_transcript(_segmented_source())

    assert page["truncated"] is False
    assert page["next_offset"] is None
    assert page["total_segments"] == 4
    assert "[00:00] Speaker 1: Agenda point 0 is complete." in page["text"]
    assert "[00:15] Speaker 2: Agenda point 1 is complete." in page["text"]
    assert len(page["text"]) < 10_000


def test_segment_offset_walks_long_transcript_without_gaps_or_duplicates():
    source = _segmented_source(18)
    expected = [
        item["text"]
        for item in paginate_transcript(source, format="segments")["segments"]
    ]
    seen: list[str] = []
    offset = 0

    while True:
        page = paginate_transcript(source, max_chars=120, offset=offset)
        seen.extend(item["text"] for item in page["segments"])
        if page["next_offset"] is None:
            break
        assert page["next_offset"] > offset
        offset = page["next_offset"]

    assert seen == expected
    assert len(seen) == len(set(seen)) == 18


def test_character_ceiling_is_clamped_to_200000():
    source = {
        "transcript_diarized": {
            "segments": [
                {"start": index, "end": index + 1, "text": "x" * 10_000}
                for index in range(30)
            ]
        }
    }

    page = paginate_transcript(source, max_chars=400_000)

    assert len(page["text"]) <= 200_000
    assert page["truncated"] is True
    assert page["next_offset"] is not None


def test_segments_format_has_contract_fields():
    page = paginate_transcript(_segmented_source(2), format="segments")

    assert page["segments"] == [
        {
            "index": 0,
            "start_s": 0.0,
            "end_s": 15.0,
            "text": "Agenda point 0 is complete.",
            "speaker": "Speaker 1",
        },
        {
            "index": 1,
            "start_s": 15.0,
            "end_s": 30.0,
            "text": "Agenda point 1 is complete.",
            "speaker": "Speaker 2",
        },
    ]
    assert page["total_segments"] == 2
    assert page["next_offset"] is None
    assert page["truncated"] is False
    assert page["duration_s"] == 30.0


def test_blob_fallback_uses_character_offsets_and_discloses_storage_shape():
    blob = "A fictional blob transcript. " * 60
    first = paginate_transcript({"transcript_simple": blob}, max_chars=400)

    assert first["blob_only"] is True
    assert first["text"].startswith("[--:--] ")
    assert "offset is in characters" in first["text"]
    assert first["total_segments"] == 0
    assert first["next_offset"] is not None

    second = paginate_transcript(
        {"transcript_simple": blob},
        max_chars=400,
        offset=first["next_offset"],
    )
    assert second["text"].startswith("[--:--] ")
    assert second["next_offset"] > first["next_offset"]


def test_speaker_field_and_prefix_are_omitted_without_speaker_data():
    source = {
        "transcript_diarized": {
            "segments": [
                {"start": 12, "end": 20, "text": "No speaker was recorded."},
            ]
        }
    }

    page = paginate_transcript(source, format="segments")

    assert page["text"] == "[00:12] No speaker was recorded."
    assert "speaker" not in page["segments"][0]


class _NoRowsDB:
    def query(self, _model):
        return self

    def filter(self, *_args):
        return self

    def order_by(self, *_args):
        return self

    def all(self):
        return []


class _RowsDB(_NoRowsDB):
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


def _agent_session(source: dict) -> SimpleNamespace:
    return SimpleNamespace(
        id=44,
        session_id="fictional-session",
        title="Northstar Example review",
        name="Northstar Example review",
        status="completed",
        created_at=datetime(2026, 11, 5, tzinfo=timezone.utc),
        duration=source.get("duration", 0),
        transcript_diarized=source.get("transcript_diarized"),
        transcript_simple=source.get("transcript_simple"),
        transcript=source.get("transcript"),
        processing_metadata={},
        final_summary=None,
        summary=None,
    )


def test_agent_tool_uses_shared_text_and_segments_contract(monkeypatch):
    from services import agent_tools

    session = _agent_session(_segmented_source(3))
    monkeypatch.setattr(agent_tools, "_resolve_session", lambda *_args: session)

    text_result = asyncio.run(
        agent_tools.get_meeting_transcript_impl(
            _NoRowsDB(),
            7,
            session_id="fictional-session",
            max_chars=10_000,
        )
    )
    assert text_result["transcript"].startswith("[00:00] Speaker 1:")
    assert text_result["truncated"] is False

    segment_result = asyncio.run(
        agent_tools.get_meeting_transcript_impl(
            _NoRowsDB(),
            7,
            session_id="fictional-session",
            format="segments",
        )
    )
    assert segment_result["segments"][1]["index"] == 1
    assert segment_result["duration_s"] == 45.0


def test_agent_tool_falls_back_to_transcription_rows(monkeypatch):
    from services import agent_tools

    session = _agent_session({})
    rows = [
        SimpleNamespace(
            start_time=4.0,
            end_time=9.0,
            speaker="Cora Lane",
            text="Stored segment text.",
        )
    ]
    monkeypatch.setattr(agent_tools, "_resolve_session", lambda *_args: session)
    result = asyncio.run(
        agent_tools.get_meeting_transcript_impl(
            _RowsDB(rows),
            7,
            session_id="fictional-session",
        )
    )

    assert "[00:04] Cora Lane: Stored segment text." in result["transcript"]


def test_mcp_tool_returns_text_and_json_pages(monkeypatch):
    from services import mcp_app

    payload = _segmented_source(3)
    payload.update(
        {"title": "Northstar Example review", "name": "Northstar Example review"}
    )

    async def fake_api(_method, _path, **_kwargs):
        return payload

    monkeypatch.setattr(mcp_app, "_api", fake_api)

    text_result = asyncio.run(
        mcp_app.get_meeting_transcript("fictional-session", max_chars=10_000)
    )
    assert "# Transcript: Northstar Example review" in text_result
    assert "[00:00] Speaker 1:" in text_result

    json_result = asyncio.run(
        mcp_app.get_meeting_transcript(
            "fictional-session", format="segments", max_chars=10_000
        )
    )
    parsed = json.loads(json_result)
    assert parsed["segments"][0]["index"] == 0
    assert parsed["total_segments"] == 3
    assert parsed["duration_s"] == 45.0
