"""MCP tool ⇄ REST response-contract tests.

The MCP tools in ``services.mcp_app`` do not touch the database — they
render whatever the backend REST endpoints hand back. That makes the JSON
*shape* of those endpoints a real API contract, and it has silently drifted
before: the sessions list moved from a bare JSON list to a cursor-paginated
``{"items": ...}`` envelope, and ``list_meetings`` kept reading a
``"sessions"`` key that never existed. The tool answered "No recording
sessions found." for every caller while the backend was returning a full
page (issue #9).

Nothing failed, because no test ever fed a tool the payload its endpoint
actually produces. These tests do exactly that. The payload literals below
are copied from the endpoint source — keep them in sync when an endpoint
changes shape, and the next drift fails here instead of in production.

Payload sources:
  * api/simple_recording_db.py — list_sessions (``items``/``has_more``),
    semantic_search_sessions (``results``), search_sessions (bare list)
  * api/analytics_simple.py — get_analytics_summary (``session_stats`` +
    ``speaking_time``), get_duration_trends (``trends``)
"""

import asyncio

import pytest

from services import mcp_app
from services.mcp_app import _unwrap_list_payload


# ── Payload fixtures: the shapes the endpoints really return ───────────

# api/simple_recording_db.py::list_sessions -> {"items", "next_cursor", "has_more"}
SESSIONS_ENVELOPE = {
    "items": [
        {
            "id": "11111111-1111-1111-1111-111111111111",
            "name": "Ryan Otto sync",
            "title": "Ryan Otto sync",
            "description": "",
            "created_at": "2026-07-31T15:04:00+00:00",
            "status": "completed",
            "duration": 1830.0,
            "organization_id": 7,
            "organization_name": "Brightwater Labs",
        },
        {
            "id": "22222222-2222-2222-2222-222222222222",
            "name": "Always-on 2026-07-28 09:00",
            "title": None,
            "description": "",
            "created_at": "2026-07-28T09:00:00+00:00",
            "status": "recording",
            "duration": 0.0,
            "organization_id": 7,
            "organization_name": "Brightwater Labs",
        },
    ],
    "next_cursor": None,
    "has_more": False,
}

# api/simple_recording_db.py::semantic_search_sessions -> {"query", "results", "count"}
SEMANTIC_ENVELOPE = {
    "query": "meeting",
    "results": [
        {
            "session_id": "11111111-1111-1111-1111-111111111111",
            "title": "Ryan Otto sync",
            "score": 0.8123,
            "match_type": "transcript",
            "snippet": "we agreed to ship the invoice flow",
            "created_at": "2026-07-31T15:04:00+00:00",
        }
    ],
    "count": 1,
}

# api/analytics_simple.py::get_analytics_summary
ANALYTICS_SUMMARY = {
    "time_range": "month",
    "generated_at": "2026-08-02T00:00:00+00:00",
    "session_stats": {
        "total_sessions": 12,
        "total_duration": 21600,
        "average_duration": 1800.0,
        "total_speakers": 3,
    },
    "speaking_time": [
        {"speaker": "Shafen", "duration": 930.0, "segments": 44, "percentage": 51.0},
        {"speaker": "Ryan", "duration": 890.0, "segments": 39, "percentage": 49.0},
    ],
    "keywords": [],
    "meeting_trends": [],
    "action_items": {"total": 0, "completed": 0, "pending": 0, "overdue": 0},
}

# api/analytics_simple.py::get_duration_trends -> {"time_range", "group_by", "trends"}
DURATION_TRENDS = {
    "time_range": "month",
    "group_by": "day",
    "trends": [
        {
            "period": "2026-07-31",
            "sessions": 3,
            "total_duration": 5400.0,
            "avg_duration": 1800.0,
            "min_duration": 600.0,
            "max_duration": 2400.0,
        }
    ],
}


@pytest.fixture
def fake_api(monkeypatch):
    """Stub ``_api`` with a path -> payload map and record the calls made."""
    calls: list[tuple[str, str, dict]] = []

    def _install(routes: dict[str, object]):
        async def _fake(method: str, path: str, **kwargs):
            calls.append((method, path, kwargs.get("params") or {}))
            for prefix, payload in routes.items():
                if path.startswith(prefix):
                    if isinstance(payload, Exception):
                        raise payload
                    return payload
            raise AssertionError(f"unexpected backend call: {method} {path}")

        monkeypatch.setattr(mcp_app, "_api", _fake)
        return calls

    _install.calls = calls
    return _install


# ── _unwrap_list_payload ───────────────────────────────────────────────


def test_unwrap_handles_every_known_envelope():
    assert _unwrap_list_payload(SESSIONS_ENVELOPE)[0] == SESSIONS_ENVELOPE["items"]
    assert _unwrap_list_payload(SEMANTIC_ENVELOPE)[0] == SEMANTIC_ENVELOPE["results"]
    assert _unwrap_list_payload(DURATION_TRENDS)[0] == DURATION_TRENDS["trends"]
    # Legacy bare-list shape (pre-3214f92 list endpoint, current /search).
    rows = [{"id": "a"}, {"id": "b"}]
    assert _unwrap_list_payload(rows) == (rows, False)


def test_unwrap_propagates_has_more():
    assert _unwrap_list_payload({"items": [{"id": "a"}], "has_more": True})[1] is True
    assert _unwrap_list_payload({"items": [{"id": "a"}], "has_more": False})[1] is False


def test_unwrap_degrades_instead_of_raising():
    for junk in (None, "", 0, {"detail": "nope"}, {"items": "not-a-list"}):
        assert _unwrap_list_payload(junk) == ([], False)


# ── list_meetings ──────────────────────────────────────────────────────


def test_list_meetings_reads_the_paginated_envelope(fake_api):
    """The regression from issue #9: an envelope must not read as empty."""
    calls = fake_api({"/api/simple/recording-sessions": SESSIONS_ENVELOPE})

    out = asyncio.run(mcp_app.list_meetings())

    assert "No recording sessions found." not in out
    assert "Showing 2 sessions" in out
    assert "Ryan Otto sync" in out
    assert "11111111-1111-1111-1111-111111111111" in out
    # PR #10's cross-org flag must still go out on the wire.
    assert calls[0][2]["include_all_my_orgs"] is True
    # And the workspace each meeting came from is surfaced, since a page
    # now spans several of them.
    assert "Brightwater Labs" in out


def test_list_meetings_still_reads_the_legacy_bare_list(fake_api):
    fake_api({"/api/simple/recording-sessions": SESSIONS_ENVELOPE["items"]})
    assert "Ryan Otto sync" in asyncio.run(mcp_app.list_meetings())


def test_list_meetings_status_filter_is_applied(fake_api):
    """The REST endpoint has no ?status= param, so the tool must filter."""
    calls = fake_api({"/api/simple/recording-sessions": SESSIONS_ENVELOPE})

    out = asyncio.run(mcp_app.list_meetings(status="completed"))

    assert "Ryan Otto sync" in out
    assert "Always-on" not in out
    assert "status" not in calls[0][2]


def test_list_meetings_offset_is_applied(fake_api):
    fake_api({"/api/simple/recording-sessions": SESSIONS_ENVELOPE})

    out = asyncio.run(mcp_app.list_meetings(offset=1))

    assert "Always-on" in out
    assert "Ryan Otto sync" not in out


def test_list_meetings_reports_empty_honestly(fake_api):
    fake_api({"/api/simple/recording-sessions": {"items": [], "has_more": False}})
    assert asyncio.run(mcp_app.list_meetings()) == "No recording sessions found."


# ── search_meetings ────────────────────────────────────────────────────


def test_search_meetings_uses_semantic_results(fake_api):
    """Semantic hits come back in {"results": [...]}, not a bare list."""
    fake_api({"/api/simple/recording-sessions/semantic-search": SEMANTIC_ENVELOPE})

    out = asyncio.run(mcp_app.search_meetings("meeting"))

    assert "Ryan Otto sync" in out
    assert "score: 0.812" in out


def test_search_meetings_falls_back_to_keyword_when_semantic_is_empty(fake_api):
    """Empty semantic results (unindexed Qdrant, tier gate) keep the net."""
    calls = fake_api({
        "/api/simple/recording-sessions/semantic-search": {
            "query": "meeting", "results": [], "count": 0,
        },
        "/api/simple/recording-sessions/search": [
            {"id": "33333333", "name": "Fallback meeting", "status": "completed",
             "created_at": "2026-05-02T10:00:00+00:00"},
        ],
    })

    out = asyncio.run(mcp_app.search_meetings("meeting"))

    assert "Fallback meeting" in out
    assert any(path.endswith("/search") for _, path, _ in calls)


def test_search_meetings_falls_back_when_semantic_errors(fake_api):
    fake_api({
        "/api/simple/recording-sessions/semantic-search": RuntimeError("qdrant down"),
        "/api/simple/recording-sessions/search": [
            {"id": "44444444", "name": "Keyword only", "status": "completed",
             "created_at": "2026-05-02T10:00:00+00:00"},
        ],
    })
    assert "Keyword only" in asyncio.run(mcp_app.search_meetings("meeting"))


# ── get_analytics ──────────────────────────────────────────────────────


def test_analytics_reads_the_nested_session_stats(fake_api):
    """The measured bug: 'Total sessions: 0' beside a full speaker list."""
    fake_api({
        "/api/analytics/summary": ANALYTICS_SUMMARY,
        "/api/analytics/duration-trends": DURATION_TRENDS,
    })

    out = asyncio.run(mcp_app.get_analytics("month"))

    assert "**Total sessions:** 12" in out
    assert "**Total sessions:** 0" not in out
    assert "Average duration:** 30m 0s" in out


def test_analytics_speaker_rows_carry_real_time(fake_api):
    fake_api({
        "/api/analytics/summary": ANALYTICS_SUMMARY,
        "/api/analytics/duration-trends": DURATION_TRENDS,
    })

    out = asyncio.run(mcp_app.get_analytics("month"))

    assert "**Shafen**: 15m 30s (44 segments)" in out
    assert "0m 0s (0 segments)" not in out


def test_analytics_trend_buckets_are_labelled(fake_api):
    calls = fake_api({
        "/api/analytics/summary": ANALYTICS_SUMMARY,
        "/api/analytics/duration-trends": DURATION_TRENDS,
    })

    out = asyncio.run(mcp_app.get_analytics("week"))

    assert "- 2026-07-31: 3 sessions, avg 30m" in out
    # The trend window must track the requested range, not silently default.
    trend_call = next(c for c in calls if c[1].endswith("duration-trends"))
    assert trend_call[2]["time_range"] == "week"


def test_analytics_survives_a_trends_outage(fake_api):
    fake_api({
        "/api/analytics/summary": ANALYTICS_SUMMARY,
        "/api/analytics/duration-trends": RuntimeError("boom"),
    })

    out = asyncio.run(mcp_app.get_analytics("month"))

    assert "**Total sessions:** 12" in out
    assert "Recent Duration Trends" not in out
