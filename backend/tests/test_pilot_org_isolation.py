"""Pilot gate: every Meeting-Ops read is tenant scoped.

The fixture deliberately gives each tenant an exclusive title, transcript,
summary, speaker, and search token.  The caller is always a member of org B;
any appearance of the org-A marker is an unambiguous cross-tenant leak.
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from auth.utils import get_password_hash


ALPHA_MARKER = "alpha-private-marker"
BRAVO_MARKER = "bravo-private-marker"


def _models():
    from auth.models import Organization, User, UserOrganization
    from database.database import SessionLocal
    from database.models import ChatHistory, RecordingSession, Transcription

    return (
        Organization,
        User,
        UserOrganization,
        SessionLocal,
        RecordingSession,
        Transcription,
        ChatHistory,
    )


def _login(client, username: str, password: str) -> str:
    response = client.post(
        "/api/auth/login",
        data={"username": username, "password": password},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def _seed_user(db, username: str, email: str):
    _, User, _, _, _, _, _ = _models()
    user = User(
        username=username,
        email=email,
        hashed_password=get_password_hash("Password123"),
        is_active=True,
        is_verified=True,
        tier="enterprise",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _summary(marker: str, person: str) -> dict:
    return {
        "executive": f"{marker} executive summary for {person}.",
        "bullets": [f"{marker} bullet"],
        "decisions": [f"{marker} decision"],
        "actions": [f"{marker} action for {person}"],
        "participants": [{"name": person, "email": f"{person.lower().replace(' ', '.')}@example.com"}],
    }


def _insights(marker: str, person: str) -> dict:
    return {
        "summary": f"{marker} cached insights",
        "keywords": [{"word": marker, "frequency": 1, "trend": "stable", "category": "topic"}],
        "action_items": [],
        "speaker_insights": [{
            "speaker": person,
            "talkTime": 12,
            "wordCount": 4,
            "sentiment": "neutral",
            "engagement": 0.5,
            "keyTopics": [marker],
        }],
        "sentiment": {"positive": 0, "neutral": 100, "negative": 0},
        "duration": 120,
        "topics": [marker],
        "key_decisions": [f"{marker} decision"],
        "follow_ups": [],
    }


def _meeting(db, *, org_id: int, user_id: int, marker: str, person: str, audio_path: str):
    _, _, _, _, RecordingSession, Transcription, _ = _models()
    summary = _summary(marker, person)
    session = RecordingSession(
        session_id=str(uuid.uuid4()),
        name=f"{marker} meeting",
        title=f"{marker} meeting",
        description=f"{marker} description",
        status="completed",
        mode="upload",
        organization_id=org_id,
        user_id=user_id,
        created_at=datetime.now(timezone.utc),
        duration=120.0,
        audio_file=audio_path,
        transcript_simple=f"{marker} transcript spoken by {person}.",
        transcript=json.dumps({"text": f"{marker} transcript spoken by {person}."}),
        transcript_diarized={"segments": [{"speaker": person, "text": f"{marker} transcript."}]},
        summary=json.dumps(summary),
        final_summary=summary,
        summary_preview=summary["executive"],
        ai_insights=_insights(marker, person),
        processing_metadata={"word_count": 4, "speaker_count": 1},
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    db.add_all([
        Transcription(
            session_id=session.id,
            text=f"{marker} transcript segment",
            speaker=person,
            start_time=0.0,
            end_time=12.0,
            confidence=0.99,
        ),
    ])
    db.commit()
    return session


@pytest.fixture()
def pilot_orgs(client):
    (
        Organization,
        _,
        UserOrganization,
        SessionLocal,
        _,
        _,
        ChatHistory,
    ) = _models()
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    media_root = Path(os.environ["RECORDINGS_DIR"])
    alpha_audio = media_root / f"{suffix}-alpha.wav"
    bravo_audio = media_root / f"{suffix}-bravo.wav"
    alpha_audio.write_bytes(b"RIFFalpha-private-audio")
    bravo_audio.write_bytes(b"RIFFbravo-private-audio")
    try:
        org_a = Organization(
            name=f"Org Alpha {suffix}",
            slug=f"alpha-{suffix}",
            is_active=True,
            plan="enterprise",
        )
        org_b = Organization(
            name=f"Org Bravo {suffix}",
            slug=f"bravo-{suffix}",
            is_active=True,
            plan="enterprise",
        )
        db.add_all([org_a, org_b])
        db.commit()
        db.refresh(org_a)
        db.refresh(org_b)

        user_a = _seed_user(db, f"alpha_member_{suffix}", f"alpha_{suffix}@example.com")
        user_b = _seed_user(db, f"bravo_member_{suffix}", f"bravo_{suffix}@example.com")
        db.add_all([
            UserOrganization(user_id=user_a.id, organization_id=org_a.id, role="user"),
            UserOrganization(user_id=user_b.id, organization_id=org_b.id, role="user"),
        ])
        db.commit()

        session_a = _meeting(
            db,
            org_id=org_a.id,
            user_id=user_a.id,
            marker=ALPHA_MARKER,
            person="Mira Vale",
            audio_path=str(alpha_audio),
        )
        session_b = _meeting(
            db,
            org_id=org_b.id,
            user_id=user_b.id,
            marker=BRAVO_MARKER,
            person="Niko Rowan",
            audio_path=str(bravo_audio),
        )
        db.add(ChatHistory(
            session_key=session_a.session_id,
            organization_id=org_a.id,
            role="assistant",
            content=f"{ALPHA_MARKER} chat history",
        ))
        db.add(ChatHistory(
            session_key="__rag__",
            organization_id=org_a.id,
            role="assistant",
            content=f"{ALPHA_MARKER} RAG history",
        ))
        db.commit()

        ctx = {
            "org_a_id": org_a.id,
            "org_b_id": org_b.id,
            "org_a_slug": org_a.slug,
            "org_b_slug": org_b.slug,
            "user_b": user_b.username,
            "session_a": session_a.session_id,
            "session_b": session_b.session_id,
            "session_a_pk": session_a.id,
        }
    finally:
        db.close()

    token = _login(client, ctx["user_b"], "Password123")
    ctx["headers_b"] = {"Authorization": f"Bearer {token}"}
    ctx["token_b"] = token
    return ctx


def _assert_clean(value, ctx):
    text = json.dumps(value, default=str).lower()
    assert ALPHA_MARKER not in text, f"org-A marker leaked: {value!r}"
    assert ctx["session_a"].lower() not in text, f"org-A session id leaked: {value!r}"


def test_meeting_list_detail_and_legacy_detail_are_org_scoped(client, pilot_orgs):
    ctx = pilot_orgs
    headers = ctx["headers_b"]

    listed = client.get("/api/simple/recording-sessions", headers=headers)
    assert listed.status_code == 200, listed.text
    assert any(row["id"] == ctx["session_b"] for row in listed.json()["items"])
    _assert_clean(listed.json(), ctx)

    legacy_list = client.get("/api/recording-sessions", headers=headers)
    assert legacy_list.status_code == 200, legacy_list.text
    _assert_clean(legacy_list.json(), ctx)

    for path in (
        f"/api/simple/recording-sessions/{ctx['session_a']}",
        f"/api/recording-sessions/{ctx['session_a']}",
    ):
        response = client.get(path, headers=headers)
        assert response.status_code == 404, f"{path}: {response.text}"


def test_keyword_and_semantic_search_are_org_scoped(client, pilot_orgs, monkeypatch):
    ctx = pilot_orgs
    headers = ctx["headers_b"]

    keyword = client.get(
        "/api/simple/recording-sessions/search",
        params={"q": ALPHA_MARKER},
        headers=headers,
    )
    assert keyword.status_code == 200, keyword.text
    assert keyword.json() == []

    calls = []

    def fake_search(self, query, limit=10, organization_id=None):
        calls.append(organization_id)
        marker = ALPHA_MARKER if organization_id == ctx["org_a_id"] else BRAVO_MARKER
        return [{
            "session_id": ctx["session_a"] if marker == ALPHA_MARKER else ctx["session_b"],
            "title": f"{marker} semantic hit",
            "snippet": f"{marker} semantic snippet",
            "score": 0.99,
            "organization_id": organization_id,
        }]

    monkeypatch.setattr(
        "services.semantic_search_service.SemanticSearchService.search",
        fake_search,
    )
    semantic = client.get(
        "/api/simple/recording-sessions/semantic-search",
        params={"q": "planning"},
        headers=headers,
    )
    assert semantic.status_code == 200, semantic.text
    assert calls == [ctx["org_b_id"]]
    _assert_clean(semantic.json(), ctx)


def test_insights_transcript_and_media_reads_refuse_org_a(client, pilot_orgs):
    ctx = pilot_orgs
    headers = ctx["headers_b"]
    paths = [
        f"/api/simple/recording-sessions/{ctx['session_a']}/insights",
        f"/api/simple/recording-sessions/{ctx['session_a']}/download/transcript",
        f"/api/simple/recording-sessions/{ctx['session_a']}/download/transcript/simple",
        f"/api/simple/recording-sessions/{ctx['session_a']}/download/audio",
        f"/api/simple/recording-sessions/{ctx['session_a']}/download/summary/pdf",
        f"/api/simple/recording-sessions/{ctx['session_a']}/download/summary/md",
        f"/api/simple/recording-sessions/{ctx['session_a']}/download/summary/docx",
        f"/api/recording-sessions/{ctx['session_a']}/export",
    ]
    for path in paths:
        response = client.get(path, headers=headers)
        assert response.status_code == 404, f"{path}: {response.status_code} {response.text[:300]}"

    # The positive transcript read proves the fixture and endpoint are live.
    own = client.get(
        f"/api/simple/recording-sessions/{ctx['session_b']}/download/transcript/simple",
        headers=headers,
    )
    assert own.status_code == 200, own.text
    assert BRAVO_MARKER in own.text
    _assert_clean(own.text, ctx)


@pytest.mark.parametrize(
    "path",
    [
        "/api/analytics/summary",
        "/api/analytics/sessions",
        "/api/analytics/speakers",
        "/api/analytics/duration-trends",
        "/api/analytics/performance",
    ],
)
def test_all_analytics_aggregates_are_org_scoped(client, pilot_orgs, path):
    response = client.get(path, headers=pilot_orgs["headers_b"])
    assert response.status_code == 200, f"{path}: {response.text}"
    _assert_clean(response.json(), pilot_orgs)
    if path.endswith("/summary"):
        assert response.json()["session_stats"]["total_sessions"] == 1
        assert response.json()["session_stats"]["total_duration"] == 120
    elif path.endswith("/sessions"):
        assert len(response.json()) == 1
        assert response.json()[0]["id"] == pilot_orgs["session_b"]
    elif path.endswith("/speakers"):
        assert response.json()["total_speakers"] == 1
    elif path.endswith("/duration-trends"):
        assert sum(row["sessions"] for row in response.json()["trends"]) == 1
    elif path.endswith("/performance"):
        assert response.json()["sessions_processed"] == 1


def test_per_meeting_chat_rag_and_chat_history_are_org_scoped(client, pilot_orgs, monkeypatch):
    ctx = pilot_orgs
    headers = ctx["headers_b"]

    chat = client.get(
        f"/api/ai-chat/sessions/{ctx['session_a']}/messages",
        headers=headers,
    )
    assert chat.status_code == 200, chat.text
    assert chat.json() == []

    rag_history = client.get("/api/ai-chat/rag/history", headers=headers)
    assert rag_history.status_code == 200, rag_history.text
    assert rag_history.json() == []

    def fake_chunks(self, query, limit=10, organization_id=None):
        marker = ALPHA_MARKER if organization_id == ctx["org_a_id"] else BRAVO_MARKER
        return [{
            "session_id": ctx["session_a"] if marker == ALPHA_MARKER else ctx["session_b"],
            "title": f"{marker} RAG meeting",
            "text": f"{marker} RAG snippet",
            "content_type": "transcript",
            "score": 0.98,
            "organization_id": organization_id,
        }]

    monkeypatch.setattr(
        "services.semantic_search_service.SemanticSearchService.search_chunks",
        fake_chunks,
    )
    with patch("api.ai_chat._llm_call", return_value="Bravo-only answer"):
        rag = client.post(
            "/api/ai-chat/rag/query",
            json={"message": "planning", "limit": 5},
            headers=headers,
        )
    assert rag.status_code == 200, rag.text
    _assert_clean(rag.json(), ctx)

    per_meeting = client.post(
        f"/api/ai-chat/sessions/{ctx['session_a']}/messages",
        json={"message": "What happened?"},
        headers=headers,
    )
    assert per_meeting.status_code == 404, per_meeting.text


def test_missing_and_forged_org_context_never_expands_scope(client, pilot_orgs):
    ctx = pilot_orgs
    headers = ctx["headers_b"]

    # No selector is the normal authenticated request and must resolve to B.
    no_selector = client.get("/api/simple/recording-sessions", headers=headers)
    assert no_selector.status_code == 200, no_selector.text
    _assert_clean(no_selector.json(), ctx)

    # Both a foreign slug and a numeric org-id masquerading as a slug are
    # untrusted selectors. The resolver falls back to B, never to all tenants.
    for forged in (ctx["org_a_slug"], str(ctx["org_a_id"]), "not-a-real-org"):
        response = client.get(
            "/api/simple/recording-sessions",
            headers={**headers, "X-MeetingOps-Org": forged},
        )
        assert response.status_code == 200, response.text
        _assert_clean(response.json(), ctx)

    # Both membership-wide listing and the platform-admin flag stay scoped for
    # a regular member. Neither may silently become an all-tenants view.
    for query in ("?include_all_my_orgs=true", "?all_tenants=true"):
        response = client.get(
            f"/api/simple/recording-sessions{query}",
            headers=headers,
        )
        assert response.status_code == 200, response.text
        _assert_clean(response.json(), ctx)


async def _mcp_call_as_b(app, token: str, function, *args, **kwargs):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://meeting-ops.test",
    ) as backend:
        async def api(method: str, path: str, **request_kwargs):
            response = await backend.request(
                method.upper(),
                path,
                headers={"Authorization": f"Bearer {token}"},
                **request_kwargs,
            )
            response.raise_for_status()
            return response.json()

        with patch("services.mcp_app._api", api):
            return await function(*args, **kwargs)


def test_mcp_read_tools_inherit_org_scoped_rest_reads(client, app, pilot_orgs, monkeypatch):
    ctx = pilot_orgs
    from services import mcp_app

    def fake_search(self, query, limit=10, organization_id=None):
        marker = ALPHA_MARKER if organization_id == ctx["org_a_id"] else BRAVO_MARKER
        return [{
            "session_id": ctx["session_a"] if marker == ALPHA_MARKER else ctx["session_b"],
            "title": f"{marker} search hit",
            "snippet": f"{marker} search snippet",
            "score": 0.99,
            "organization_id": organization_id,
        }]

    def fake_chunks(self, query, limit=10, organization_id=None):
        marker = ALPHA_MARKER if organization_id == ctx["org_a_id"] else BRAVO_MARKER
        return [{
            "session_id": ctx["session_a"] if marker == ALPHA_MARKER else ctx["session_b"],
            "title": f"{marker} RAG hit",
            "text": f"{marker} RAG snippet",
            "content_type": "transcript",
            "score": 0.99,
            "organization_id": organization_id,
        }]

    monkeypatch.setattr("services.semantic_search_service.SemanticSearchService.search", fake_search)
    monkeypatch.setattr("services.semantic_search_service.SemanticSearchService.search_chunks", fake_chunks)
    with patch("api.ai_chat._llm_call", return_value="Bravo-only answer"):
        outputs = asyncio.run(_mcp_outputs(app, mcp_app, ctx))

    for output in outputs:
        _assert_clean(output, ctx)
    assert BRAVO_MARKER in outputs[0]  # list_meetings is a live positive read
    assert "No recording sessions found" not in outputs[0]


async def _mcp_outputs(app, mcp_app, ctx):
    token = ctx["token_b"]
    return [
        await _mcp_call_as_b(app, token, mcp_app.list_meetings),
        await _mcp_call_as_b(app, token, mcp_app.search_meetings, "planning"),
        await _mcp_call_as_b(app, token, mcp_app.ask_about_meetings, "planning"),
        await _mcp_call_as_b(app, token, mcp_app.get_analytics),
        await _mcp_call_as_b(app, token, mcp_app.get_meeting_details, ctx["session_b"]),
        await _mcp_call_as_b(app, token, mcp_app.get_meeting_transcript, ctx["session_b"]),
        await _mcp_call_as_b(app, token, mcp_app.chat_with_meeting, ctx["session_b"], "What happened?"),
        await _mcp_call_as_b(app, token, mcp_app.get_meeting_insights, ctx["session_b"]),
        await _mcp_call_as_b(app, token, mcp_app.get_cross_app_hints, ctx["session_b"]),
    ]


def test_mcp_cross_app_hint_for_org_a_is_empty_for_org_b(client, app, pilot_orgs):
    from services import mcp_app

    output = asyncio.run(_mcp_call_as_b(
        app,
        pilot_orgs["token_b"],
        mcp_app.get_cross_app_hints,
        pilot_orgs["session_a"],
    ))
    payload = json.loads(output)
    assert payload["cross_app_references"] == {
        "mentioned_contacts": [],
        "mentioned_projects": [],
        "mentioned_cases": [],
    }
    # The stable MCP error shape echoes the caller-supplied id as a request
    # correlation field. It contains no meeting row, snippet, or reference.
    assert ALPHA_MARKER not in json.dumps(payload).lower()


@pytest.mark.parametrize("tool_name", [
    "get_meeting_details",
    "get_meeting_transcript",
    "get_meeting_insights",
    "chat_with_meeting",
])
def test_mcp_session_tools_refuse_org_a_session(client, app, pilot_orgs, tool_name):
    from services import mcp_app

    function = getattr(mcp_app, tool_name)
    args = (pilot_orgs["session_a"], "What happened?") if tool_name == "chat_with_meeting" else (pilot_orgs["session_a"],)
    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        asyncio.run(_mcp_call_as_b(app, pilot_orgs["token_b"], function, *args))
    assert exc_info.value.response.status_code == 404
