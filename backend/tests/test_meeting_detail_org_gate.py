"""Meeting detail / transcript / summary / action-items / search org gate.

A member of org A must be able to read their own org's meeting surface, and
must NOT be able to read the same surface for an org C session they have no
membership in, including by forging the active-org selector. Every assertion
here drives the real FastAPI routes; the org check is never mocked.

Routes under test (and the line that raises the cross-org 404):

| Surface       | Route                                              | Gate                          | 404 line |
|---------------|----------------------------------------------------|-------------------------------|----------|
| detail        | GET /api/simple/recording-sessions/{id}            | _get_session_for_org          | simple_recording_db.py:1336 |
| transcript    | GET .../recording-sessions/{id}/download/transcript| _get_session_for_org          | simple_recording_db.py:3086 |
| summary       | GET .../recording-sessions/{id}/download/summary/md| _get_session_for_org          | simple_recording_db.py:3210 |
| action items  | GET /api/action-items?session_id={id}              | _resolve_session              | action_items.py:160 |
| search        | GET /api/simple/recording-sessions/search?q=       | _scoped_session_query         | simple_recording_db.py:1155 |
| RAG / ask     | POST /api/ai-chat/rag/query                        | search_chunks(org_id=active)  | ai_chat.py:553 |

The active-org selector (``X-MeetingOps-Org`` header / ``?org=`` query param)
is a convenience, never a boundary: ``resolve_active_organization``
(auth/organization.py:269-279) drops a selector naming an org the caller is
not a member of and falls back to their default org, so a forged selector
resolves to org A and the org-scoped lookups above still 404 on org C.

Fixture pattern follows tests/test_session_scope_flags.py (PR #74) and
tests/test_cross_org_isolation.py. Fictional people/orgs only (example.com).
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import patch

import pytest

from auth.utils import get_password_hash


def _models():
    """Lazy import - these modules are reloaded by the session app fixture."""
    from auth.models import Organization, User, UserOrganization
    from database.database import SessionLocal
    from database.models import ActionItem, RecordingSession

    return Organization, User, UserOrganization, SessionLocal, RecordingSession, ActionItem


def _seed_user(db, *, username: str, email: str):
    _, User, _, _, _, _ = _models()
    user = User(
        email=email,
        username=username,
        hashed_password=get_password_hash("Password123"),
        is_active=True,
        is_verified=True,
        tier="enterprise",  # paid tier so no per-workspace tier gate shadows the org gate
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_session(
    db,
    *,
    organization_id: int,
    user_id: int,
    title: str,
    body: str,
) -> Any:
    _, _, _, _, RecordingSession, _ = _models()
    sess = RecordingSession(
        session_id=str(uuid.uuid4()),
        name=title,
        title=title,
        status="completed",
        organization_id=organization_id,
        user_id=user_id,
        transcript=body,
        transcript_simple=body,
        summary=body,
        final_summary={"executive": body},
        duration=120.0,
    )
    db.add(sess)
    db.commit()
    db.refresh(sess)
    return sess


def _make_action_item(db, *, organization_id: int, session_pk: int, text: str) -> None:
    *_, ActionItem = _models()
    db.add(
        ActionItem(
            session_id=session_pk,
            organization_id=organization_id,
            text=text,
            status="todo",
            sort_order=0,
        )
    )
    db.commit()


def _login_headers(client, username: str) -> dict[str, str]:
    response = client.post(
        "/api/auth/login",
        data={"username": username, "password": "Password123"},
    )
    assert response.status_code == 200, f"Login failed: {response.text}"
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture()
def org_world(client):
    """Two orgs (A and C), one session + one action item each, two users.

    - ``alice``: member of org A only (default org A). Never a member of C.
    - ``carol``: member of org C only; owns the org C session.

    The org C session is owned by carol (not alice) so alice is neither a
    member, the creator, nor a collaborator: ``has_session_access`` returns
    "denied" (session_permissions.py:336), so the cross-org collaborator
    fallback in the detail route cannot rescue it. Orgs are on a paid plan and
    users on a paid tier so no tier gate shadows the org gate under test.
    """
    Organization, _, UserOrganization, SessionLocal, _, _ = _models()
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    try:
        org_a = Organization(name=f"Gate Alpha {suffix}", slug=f"gate-alpha-{suffix}", is_active=True, plan="enterprise")
        org_c = Organization(name=f"Gate Charlie {suffix}", slug=f"gate-charlie-{suffix}", is_active=True, plan="enterprise")
        db.add_all([org_a, org_c])
        db.commit()
        db.refresh(org_a)
        db.refresh(org_c)

        alice = _seed_user(db, username=f"alice_{suffix}", email=f"alice_{suffix}@example.com")
        carol = _seed_user(db, username=f"carol_{suffix}", email=f"carol_{suffix}@example.com")

        db.add_all([
            UserOrganization(user_id=alice.id, organization_id=org_a.id, role="user"),
            UserOrganization(user_id=carol.id, organization_id=org_c.id, role="user"),
        ])
        db.commit()
        alice.default_organization_id = org_a.id
        carol.default_organization_id = org_c.id
        db.commit()

        # Distinct content per org so any cross-contamination is unambiguous.
        # "alphabudget" lives only in org A; "charliesecret" only in org C.
        sess_a = _make_session(
            db, organization_id=org_a.id, user_id=alice.id,
            title="Alpha Quarterly Plan",
            body="Alpha team reviewed the alphabudget roadmap and next quarter targets.",
        )
        sess_c = _make_session(
            db, organization_id=org_c.id, user_id=carol.id,
            title="Charlie Pricing Review",
            body="Charlie team aligned on charliesecret pricing tiers for the launch.",
        )
        _make_action_item(db, organization_id=org_a.id, session_pk=sess_a.id, text="Approve the alphabudget roadmap")
        _make_action_item(db, organization_id=org_c.id, session_pk=sess_c.id, text="Ship the charliesecret pricing page")

        ctx = {
            "org_a_id": org_a.id,
            "org_c_id": org_c.id,
            "org_a_slug": org_a.slug,
            "org_c_slug": org_c.slug,
            "alice_id": alice.id,
            "carol_username": carol.username,
            "sess_a_id": sess_a.session_id,
            "sess_c_id": sess_c.session_id,
            "alpha_keyword": "alphabudget",
            "charlie_keyword": "charliesecret",
        }
    finally:
        db.close()

    ctx["alice_headers"] = _login_headers(client, f"alice_{suffix}")
    ctx["carol_headers"] = _login_headers(client, f"carol_{suffix}")
    return ctx


def _membership_ids(user_id: int) -> list[int]:
    """The caller's real membership set, straight from UserOrganization.

    Same query the org resolver walks (auth/organization.py:269-272); read
    here to assert each test's baseline rather than trusting the fixture."""
    _, _, UserOrganization, SessionLocal, _, _ = _models()
    db = SessionLocal()
    try:
        return sorted(
            row[0]
            for row in db.query(UserOrganization.organization_id)
            .filter(UserOrganization.user_id == user_id)
            .all()
        )
    finally:
        db.close()


def _session_org_id(session_id: str) -> int | None:
    _, _, _, SessionLocal, RecordingSession, _ = _models()
    db = SessionLocal()
    try:
        row = (
            db.query(RecordingSession.organization_id)
            .filter(RecordingSession.session_id == session_id)
            .first()
        )
        return int(row[0]) if row and row[0] is not None else None
    finally:
        db.close()


# ---------------------------------------------------------------------------
# (1) Baseline: an org A member reads the full org A meeting surface.
# ---------------------------------------------------------------------------


def test_member_reads_own_org_meeting_surface(client, org_world):
    """(1) Alice (org A member) reads detail, transcript, summary and action
    items for an org A session. Asserts the org A content is actually present,
    so the negative tests below prove the gate rather than a broken harness."""
    ctx = org_world
    headers = ctx["alice_headers"]
    sess_a = ctx["sess_a_id"]

    # Baseline: alice is a member of org A only, and the session really lives in A.
    assert _membership_ids(ctx["alice_id"]) == [ctx["org_a_id"]]
    assert _session_org_id(sess_a) == ctx["org_a_id"]

    detail = client.get(f"/api/simple/recording-sessions/{sess_a}", headers=headers)
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert ctx["alpha_keyword"] in (body.get("transcript_simple") or "")
    assert body.get("summary"), "detail lost the summary field"
    assert any(ctx["alpha_keyword"] in (ai.get("text") or "") for ai in body.get("action_items", [])), (
        f"detail action_items missing org A item: {body.get('action_items')}"
    )

    transcript = client.get(f"/api/simple/recording-sessions/{sess_a}/download/transcript", headers=headers)
    assert transcript.status_code == 200, transcript.text
    assert ctx["alpha_keyword"] in transcript.text

    summary = client.get(f"/api/simple/recording-sessions/{sess_a}/download/summary/md", headers=headers)
    assert summary.status_code == 200, summary.text
    assert ctx["alpha_keyword"] in summary.text

    items = client.get("/api/action-items", params={"session_id": sess_a}, headers=headers)
    assert items.status_code == 200, items.text
    assert any(ctx["alpha_keyword"] in (row.get("text") or "") for row in items.json()), (
        f"action-items list missing org A item: {items.json()}"
    )


# ---------------------------------------------------------------------------
# (2) The same four surfaces are refused for an org C session.
# ---------------------------------------------------------------------------


def test_member_denied_foreign_org_meeting_surface(client, org_world):
    """(2) Alice (org A only) gets 404 for detail, transcript, summary and
    action items on an org C session she has no membership in.

    The code's chosen status is 404 (never 403), so existence is not leaked:
    detail simple_recording_db.py:1336, transcript :3086, summary :3210,
    action items action_items.py:160. Each route resolves the session through
    the caller's ACTIVE org (org A) and finds nothing."""
    ctx = org_world
    headers = ctx["alice_headers"]
    sess_c = ctx["sess_c_id"]

    # Baseline: alice is NOT a member of org C, and the session really lives in C.
    assert ctx["org_c_id"] not in _membership_ids(ctx["alice_id"])
    assert _session_org_id(sess_c) == ctx["org_c_id"]

    # Baseline: the org C session is genuinely readable by an org C member, so
    # the 404s below are the org gate, not a missing row.
    carol_view = client.get(f"/api/simple/recording-sessions/{sess_c}", headers=ctx["carol_headers"])
    assert carol_view.status_code == 200, (
        f"Harness: org C member cannot read the org C session "
        f"(status {carol_view.status_code}); the 404s below would prove nothing."
    )
    assert ctx["charlie_keyword"] in carol_view.text

    detail = client.get(f"/api/simple/recording-sessions/{sess_c}", headers=headers)
    assert detail.status_code == 404, (
        f"Leak: detail of org C session returned {detail.status_code} to an "
        f"org A member (expected 404 per simple_recording_db.py:1336). Body: {detail.text[:300]}"
    )
    assert ctx["charlie_keyword"] not in detail.text

    transcript = client.get(f"/api/simple/recording-sessions/{sess_c}/download/transcript", headers=headers)
    assert transcript.status_code == 404, (
        f"Leak: transcript of org C session returned {transcript.status_code} "
        f"(expected 404 per simple_recording_db.py:3086). Body: {transcript.text[:300]}"
    )
    assert ctx["charlie_keyword"] not in transcript.text

    summary = client.get(f"/api/simple/recording-sessions/{sess_c}/download/summary/md", headers=headers)
    assert summary.status_code == 404, (
        f"Leak: summary of org C session returned {summary.status_code} "
        f"(expected 404 per simple_recording_db.py:3210). Body: {summary.text[:300]}"
    )
    assert ctx["charlie_keyword"] not in summary.text

    items = client.get("/api/action-items", params={"session_id": sess_c}, headers=headers)
    assert items.status_code == 404, (
        f"Leak: action items of org C session returned {items.status_code} "
        f"(expected 404 per action_items.py:160). Body: {items.text[:300]}"
    )
    assert ctx["charlie_keyword"] not in items.text


# ---------------------------------------------------------------------------
# (3) A forged active-org selector does not open the org C session.
# ---------------------------------------------------------------------------


def test_forged_org_selector_does_not_grant_foreign_org_session(client, org_world):
    """(3) Naming org C via ``?org=`` or ``X-MeetingOps-Org`` cannot read the
    org C session, because the selector is dropped for a non-member and the
    active org falls back to org A (auth/organization.py:269-279).

    The selector is proven inert, not merely harmful: the SAME selector still
    lets alice read her own org A session (fallback lands on org A)."""
    ctx = org_world
    sess_a, sess_c = ctx["sess_a_id"], ctx["sess_c_id"]

    # Baseline: alice is not a member of org C; the C session really lives in C.
    assert ctx["org_c_id"] not in _membership_ids(ctx["alice_id"])
    assert _session_org_id(sess_c) == ctx["org_c_id"]

    for label, headers, params in (
        ("query", ctx["alice_headers"], {"org": ctx["org_c_slug"]}),
        ("header", {**ctx["alice_headers"], "X-MeetingOps-Org": ctx["org_c_slug"]}, {}),
    ):
        denied = client.get(f"/api/simple/recording-sessions/{sess_c}", headers=headers, params=params)
        assert denied.status_code == 404, (
            f"Leak ({label}): forged org selector read the org C session with "
            f"status {denied.status_code}. Body: {denied.text[:300]}"
        )
        assert ctx["charlie_keyword"] not in denied.text, (
            f"Leak ({label}): forged org selector surfaced org C content."
        )

        # Inert selector: alice's own org A session is still readable under it.
        allowed = client.get(f"/api/simple/recording-sessions/{sess_a}", headers=headers, params=params)
        assert allowed.status_code == 200, (
            f"Harness ({label}): the fallback broke alice's read of her own org "
            f"A session (status {allowed.status_code}); the 404 above would prove nothing."
        )
        assert ctx["alpha_keyword"] in allowed.text


# ---------------------------------------------------------------------------
# (4) Search / RAG never surface org C text to an org A caller.
# ---------------------------------------------------------------------------


def test_full_text_search_never_returns_foreign_org_text(client, org_world):
    """(4a) The Postgres full-text search route is org-scoped via
    _scoped_session_query (simple_recording_db.py:1155): searching org C's
    exclusive keyword from org A returns nothing, while org A's own keyword is
    found (baseline, so the negative is not vacuous)."""
    ctx = org_world
    headers = ctx["alice_headers"]

    # Baseline: org A finds its own meeting.
    positive = client.get(
        "/api/simple/recording-sessions/search",
        params={"q": ctx["alpha_keyword"]},
        headers=headers,
    )
    assert positive.status_code == 200, positive.text
    assert positive.json(), "Harness: org A cannot find its own meeting, so the negative below proves nothing."

    negative = client.get(
        "/api/simple/recording-sessions/search",
        params={"q": ctx["charlie_keyword"]},
        headers=headers,
    )
    assert negative.status_code == 200, negative.text
    rows = negative.json()
    assert rows == [], (
        f"Leak: search surfaced org C text to org A: {rows}"
    )
    assert ctx["charlie_keyword"] not in negative.text


def test_rag_query_never_returns_foreign_org_text(client, org_world):
    """(4b) The cross-meeting RAG route scopes its vector search to the
    caller's active org (ai_chat.py:553, organization_id=active_org).

    Qdrant is not reachable in the test env, so SemanticSearchService.search_chunks
    is replaced with an org-aware fake that simulates a correctly-filtered store:
    it returns org C's secret ONLY when asked for org C (or with no filter at
    all, i.e. an unfiltered leak). The LLM is stubbed to echo the assembled
    context, so any org C chunk that reached the prompt would surface in the
    answer. The org gate itself is NOT mocked: the route still computes the
    active org and passes it to search_chunks, which is what we assert."""
    ctx = org_world
    headers = ctx["alice_headers"]
    org_a, org_c = ctx["org_a_id"], ctx["org_c_id"]
    sess_a, sess_c = ctx["sess_a_id"], ctx["sess_c_id"]
    charlie = ctx["charlie_keyword"]
    calls: list[Any] = []

    def fake_search_chunks(self, query, limit=10, organization_id=None):
        calls.append(organization_id)
        # A correctly-filtered store: org C content is returned only when the
        # caller's org is C, or when the filter is missing entirely (the leak).
        if organization_id == org_c or organization_id is None:
            return [{
                "session_id": sess_c,
                "title": "Charlie Pricing Review",
                "content_type": "transcript",
                "chunk_index": 0,
                "text": f"Charlie aligned on {charlie} pricing tiers.",
                "speakers": [],
                "score": 0.9,
                "created_at": "2026-05-19T00:00:00+00:00",
            }]
        return [{
            "session_id": sess_a,
            "title": "Alpha Quarterly Plan",
            "content_type": "transcript",
            "chunk_index": 0,
            "text": "Alpha reviewed the alphabudget roadmap.",
            "speakers": [],
            "score": 0.9,
            "created_at": "2026-05-19T00:00:00+00:00",
        }]

    def fake_llm(db, organization_id, **kwargs):
        # Echo the assembled context so a leaked org C chunk would appear in the answer.
        return kwargs.get("system_prompt", "")

    with patch(
        "services.semantic_search_service.SemanticSearchService.search_chunks",
        new=fake_search_chunks,
    ), patch("api.ai_chat._llm_call", new=fake_llm):
        response = client.post(
            "/api/ai-chat/rag/query",
            json={"message": "pricing", "limit": 5},
            headers=headers,
        )

    assert response.status_code == 200, response.text
    body = response.json()

    # Baseline: the route reached the store and returned org A's own meeting.
    assert calls, "Harness: RAG never called the vector store, so the assertions below prove nothing."
    source_ids = {s.get("session_id") for s in body.get("sources", [])}
    assert sess_a in source_ids, f"Harness: RAG did not surface org A's own session: {source_ids}"

    # The route must scope every vector search to org A (never org C, never None).
    for org_id in calls:
        assert org_id == org_a, (
            f"Leak: RAG forwarded organization_id={org_id} to the vector store "
            f"instead of the caller's org A ({org_a})."
        )

    # Org C's session id and its exclusive text must never appear anywhere.
    assert sess_c not in source_ids, f"Leak: RAG sources include org C session: {source_ids}"
    assert charlie not in response.text, "Leak: RAG response surfaced org C text."
