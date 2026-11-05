"""MCP session-id prefixes resolve inside the caller's organization only.

Fictional sessions in two organizations. The lookup hits the real
``recording_sessions`` table: ``organization_id`` plus a bound
``session_id LIKE :prefix``, capped at two rows.
"""

from __future__ import annotations

import asyncio
import uuid

import httpx
import pytest

from auth.models import Organization, User, UserOrganization
from database.database import SessionLocal, engine
from database.models import Base, RecordingSession
from database import models_rooms  # noqa: F401 - registers room FK targets
from services.mcp_session_resolve import (
    PREFIX_ROW_CAP,
    is_session_id_prefix,
    prefix_lookup_query,
    resolve_session_id_prefix,
    session_id_like_pattern,
)


ORG_A_SESSION = "aaaa1111-1111-4111-8111-111111111111"
ORG_B_SAME_PREFIX = "aaaa1111-2222-4222-8222-222222222222"
ORG_B_ONLY = "bbbb2222-2222-4222-8222-222222222222"
AMBIGUOUS = (
    "cccc3333-1111-4111-8111-111111111111",
    "cccc3333-2222-4222-8222-222222222222",
    "cccc3333-3333-4333-8333-333333333333",
)
OTHER_ORG_AMBIGUOUS = "cccc3333-9999-4999-8999-999999999999"
LONGER_HEX = "dddd4444-abcd-4ddd-8ddd-dddddddddddd"
INTEGER_LOOKALIKE = "12345678-aaaa-4aaa-8aaa-aaaaaaaaaaaa"


@pytest.fixture
def db():
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def _org(db, slug: str) -> Organization:
    org = Organization(name=f"Example Org {slug}", slug=slug, is_active=True)
    db.add(org)
    db.flush()
    db.refresh(org)
    return org


def _user(db, email: str, organization: Organization) -> User:
    user = User(
        email=email,
        username=email.split("@")[0] + uuid.uuid4().hex[:6],
        hashed_password="not-a-real-secret",
        is_active=True,
        is_verified=True,
        default_organization_id=organization.id,
    )
    db.add(user)
    db.flush()
    db.refresh(user)
    db.add(UserOrganization(user_id=user.id, organization_id=organization.id, role="user"))
    db.flush()
    return user


def _session(db, org: Organization, session_id: str, *, title: str) -> RecordingSession:
    row = RecordingSession(
        session_id=session_id,
        name=title,
        title=title,
        status="completed",
        organization_id=org.id,
        participants=[],
        tags=[],
    )
    db.add(row)
    db.flush()
    db.refresh(row)
    return row


@pytest.fixture
def two_orgs(db):
    suffix = uuid.uuid4().hex[:8]
    org_a = _org(db, f"harbor-pine-example-{suffix}")
    org_b = _org(db, f"larkspur-example-{suffix}")
    caller = _user(db, f"casey.quinn.{suffix}@example.com", org_a)
    _user(db, f"riley.north.{suffix}@example.com", org_b)
    _session(db, org_a, ORG_A_SESSION, title="Harbor Pine kickoff")
    _session(db, org_b, ORG_B_SAME_PREFIX, title="Larkspur planning")
    _session(db, org_b, ORG_B_ONLY, title="Larkspur only")
    for index, session_id in enumerate(AMBIGUOUS, start=1):
        _session(db, org_a, session_id, title=f"Harbor Pine overlap {index}")
    _session(db, org_b, OTHER_ORG_AMBIGUOUS, title="Larkspur overlap")
    _session(db, org_a, LONGER_HEX, title="Harbor Pine longer prefix")
    lookalike = _session(db, org_a, INTEGER_LOOKALIKE, title="Harbor Pine integer lookalike")
    return {
        "org_a": org_a,
        "org_b": org_b,
        "caller": caller,
        "lookalike_pk": lookalike.id,
    }


class _BoomDB:
    def query(self, *args, **kwargs):
        raise AssertionError("exact ids must not run the prefix query")


def test_prefix_classification_boundaries():
    assert is_session_id_prefix("a" * 8)
    assert is_session_id_prefix("a" * 31)
    assert is_session_id_prefix("ABCDEf12")
    assert is_session_id_prefix("abcdef12-abcd")
    assert not is_session_id_prefix("a" * 7)
    assert not is_session_id_prefix("a" * 32)
    assert not is_session_id_prefix("11111111-2222-4333-8444-555555555555")
    assert not is_session_id_prefix("11111111222243338444555555555555")
    assert not is_session_id_prefix("42")
    assert not is_session_id_prefix("12345678")
    assert not is_session_id_prefix("sess-xyz")
    assert not is_session_id_prefix("")


def test_like_pattern_regroups_hex_into_the_stored_uuid_shape():
    assert session_id_like_pattern("abcdef12") == "abcdef12%"
    assert session_id_like_pattern("abcdef12abcd") == "abcdef12-abcd%"
    assert session_id_like_pattern("ABCDEf12-abcd") == "abcdef12-abcd%"
    assert PREFIX_ROW_CAP == 2


def test_prefix_lookup_sql_is_parameterized_like_capped_at_two(db, two_orgs):
    pattern = session_id_like_pattern("aaaa1111")
    query = prefix_lookup_query(db, two_orgs["org_a"].id, pattern)
    compiled = query.statement.compile(dialect=db.bind.dialect)
    sql = str(compiled)
    folded = sql.lower()
    assert "like" in folded
    assert "organization_id" in folded
    assert "limit" in folded
    assert "aaaa1111" not in folded
    bound = [value for value in compiled.params.values() if isinstance(value, str)]
    assert "aaaa1111%" in bound
    assert two_orgs["org_a"].id in list(compiled.params.values())
    assert PREFIX_ROW_CAP in list(compiled.params.values()) or f"limit {PREFIX_ROW_CAP}" in folded


def test_prefix_resolves_inside_the_callers_org_only(db, two_orgs):
    resolved = resolve_session_id_prefix(db, two_orgs["org_a"].id, "aaaa1111")

    assert resolved.error is None
    assert resolved.session_id == ORG_A_SESSION
    assert resolved.session_id != ORG_B_SAME_PREFIX


def test_longer_hex_prefix_matches_across_the_stored_hyphen(db, two_orgs):
    resolved = resolve_session_id_prefix(db, two_orgs["org_a"].id, "dddd4444abcd")

    assert resolved.error is None
    assert resolved.session_id == LONGER_HEX


def test_prefix_that_matches_another_org_does_not_resolve(db, two_orgs):
    resolved = resolve_session_id_prefix(db, two_orgs["org_a"].id, "bbbb2222")

    assert resolved.error is None
    assert resolved.session_id == "bbbb2222"


def test_ambiguous_prefix_names_the_in_org_count(db, two_orgs):
    resolved = resolve_session_id_prefix(db, two_orgs["org_a"].id, "cccc3333")

    assert resolved.session_id == "cccc3333"
    assert resolved.error == (
        "ambiguous session id prefix 'cccc3333': 3 matches, pass the full id"
    )


def test_full_uuid_and_integer_ids_do_not_query():
    full = "11111111-2222-4333-8444-555555555555"
    bare = "11111111222243338444555555555555"
    for original in (full, bare, "42", "12345678", "abc", "sess-xyz"):
        resolved = resolve_session_id_prefix(_BoomDB(), 1, original)
        assert resolved.error is None
        assert resolved.session_id == original


def test_uppercase_prefix_still_matches_the_stored_lowercase_id(db, two_orgs):
    resolved = resolve_session_id_prefix(db, two_orgs["org_a"].id, "AAAA1111")

    assert resolved.error is None
    assert resolved.session_id == ORG_A_SESSION


# ── Tools: the resolver sits in front of the existing API path ─────────


FIXTURE_SESSION_IDS = (
    ORG_A_SESSION,
    ORG_B_SAME_PREFIX,
    ORG_B_ONLY,
    *AMBIGUOUS,
    OTHER_ORG_AMBIGUOUS,
    LONGER_HEX,
    INTEGER_LOOKALIKE,
)


def _purge_fixture_sessions(db) -> None:
    db.query(RecordingSession).filter(
        RecordingSession.session_id.in_(FIXTURE_SESSION_IDS)
    ).delete(synchronize_session=False)
    db.commit()


@pytest.fixture
def caller_org():
    """Committed two-org rows. The tool opens its own session to resolve."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        _purge_fixture_sessions(db)
        suffix = uuid.uuid4().hex[:8]
        org_a = _org(db, f"harbor-pine-example-{suffix}")
        org_b = _org(db, f"larkspur-example-{suffix}")
        caller = _user(db, f"casey.quinn.{suffix}@example.com", org_a)
        _user(db, f"riley.north.{suffix}@example.com", org_b)
        _session(db, org_a, ORG_A_SESSION, title="Harbor Pine kickoff")
        _session(db, org_b, ORG_B_SAME_PREFIX, title="Larkspur planning")
        _session(db, org_b, ORG_B_ONLY, title="Larkspur only")
        for index, session_id in enumerate(AMBIGUOUS, start=1):
            _session(db, org_a, session_id, title=f"Harbor Pine overlap {index}")
        _session(db, org_b, OTHER_ORG_AMBIGUOUS, title="Larkspur overlap")
        lookalike = _session(db, org_a, INTEGER_LOOKALIKE, title="Harbor Pine integer lookalike")
        db.commit()
        yield {"caller": caller, "lookalike_pk": lookalike.id}
    finally:
        _purge_fixture_sessions(db)
        db.close()


def _record_api(monkeypatch):
    from services import mcp_app

    calls: list[tuple[str, str, dict | None]] = []

    async def _fake(method: str, path: str, **kwargs):
        body = kwargs.get("json")
        calls.append((method, path, body))
        if path.endswith("/propose"):
            return {"confirmation_token": "tok-example"}
        if path.endswith("/insights"):
            return {"keywords": ["example"]}
        if path.endswith("/messages"):
            return {"content": "Casey Quinn noted the example decision."}
        return {
            "title": "Harbor Pine kickoff",
            "status": "completed",
            "duration": 60,
            "final_summary": "Casey Quinn compared notes with Riley North.",
        }

    monkeypatch.setattr(mcp_app, "_api", _fake)
    return calls


def _bind_caller(caller):
    from services import mcp_app

    user_token = mcp_app.set_mcp_user(caller)
    pat_token = mcp_app.set_pat(None)
    return mcp_app, user_token, pat_token


def _unbind(mcp_app, user_token, pat_token) -> None:
    mcp_app.reset_mcp_user(user_token)
    mcp_app.reset_pat(pat_token)


def _session_refs(calls) -> list[str]:
    """Session id each tool actually sent, from the path or the propose body."""
    refs: list[str] = []
    for _method, path, body in calls:
        if path.endswith("/propose"):
            refs.append((body or {})["payload"]["session_id"])
            continue
        parts = [part for part in path.split("/") if part]
        if parts[-1] in {"insights", "messages"}:
            refs.append(parts[-2])
        else:
            refs.append(parts[-1])
    return refs


def test_tools_resolve_a_unique_prefix_to_the_full_id(caller_org, monkeypatch):
    calls = _record_api(monkeypatch)
    mcp_app, user_token, pat_token = _bind_caller(caller_org["caller"])
    try:
        async def exercise():
            await mcp_app.get_meeting_details("aaaa1111")
            await mcp_app.get_meeting_transcript("aaaa1111")
            await mcp_app.get_meeting_insights("aaaa1111")
            await mcp_app.chat_with_meeting("aaaa1111", "What did Casey Quinn decide?")
            await mcp_app.get_cross_app_hints("aaaa1111")
            await mcp_app.propose_rename_session("aaaa1111", "Fictional retitle")
            await mcp_app.propose_add_tag("aaaa1111", "example")
            await mcp_app.propose_remove_tag("aaaa1111", "example")
            await mcp_app.propose_trigger_reprocess("aaaa1111")
            await mcp_app.propose_draft_followup_email("aaaa1111", recipient_name="Riley North")

        transcript = asyncio.run(mcp_app.get_meeting_transcript("aaaa1111"))
        asyncio.run(exercise())
    finally:
        _unbind(mcp_app, user_token, pat_token)

    assert ORG_A_SESSION in transcript
    refs = _session_refs(calls)
    assert refs
    assert set(refs) == {ORG_A_SESSION}


def test_tools_do_not_resolve_another_orgs_prefix(caller_org, monkeypatch):
    calls = _record_api(monkeypatch)
    mcp_app, user_token, pat_token = _bind_caller(caller_org["caller"])
    try:
        asyncio.run(mcp_app.get_meeting_transcript("bbbb2222"))
    finally:
        _unbind(mcp_app, user_token, pat_token)

    assert _session_refs(calls) == ["bbbb2222"]


def test_unknown_prefix_keeps_the_existing_not_found_text(caller_org, monkeypatch):
    from services import mcp_app

    request = httpx.Request(
        "GET", "http://localhost:9050/api/simple/recording-sessions/bbbb2222"
    )
    response = httpx.Response(404, request=request)
    error = httpx.HTTPStatusError(
        "Client error '404 Not Found' for url "
        "'http://localhost:9050/api/simple/recording-sessions/bbbb2222'",
        request=request,
        response=response,
    )

    async def _fake(method: str, path: str, **kwargs):
        assert path.endswith("/bbbb2222")
        raise error

    monkeypatch.setattr(mcp_app, "_api", _fake)
    _mcp, user_token, pat_token = _bind_caller(caller_org["caller"])
    try:
        with pytest.raises(httpx.HTTPStatusError) as exc:
            asyncio.run(mcp_app.get_meeting_transcript("bbbb2222"))
    finally:
        _unbind(mcp_app, user_token, pat_token)

    assert str(exc.value) == str(error)
    assert ORG_B_ONLY not in str(exc.value)


def test_ambiguous_prefix_is_returned_and_does_not_call_the_api(caller_org, monkeypatch):
    calls = _record_api(monkeypatch)
    mcp_app, user_token, pat_token = _bind_caller(caller_org["caller"])
    expected = "ambiguous session id prefix 'cccc3333': 3 matches, pass the full id"
    try:
        transcript = asyncio.run(mcp_app.get_meeting_transcript("cccc3333"))
        proposal = asyncio.run(mcp_app.propose_rename_session("cccc3333", "Fictional retitle"))
    finally:
        _unbind(mcp_app, user_token, pat_token)

    assert transcript == expected
    assert proposal == expected
    assert calls == []


def test_full_uuid_and_integer_paths_are_unchanged(caller_org, monkeypatch):
    calls = _record_api(monkeypatch)
    mcp_app, user_token, pat_token = _bind_caller(caller_org["caller"])
    pk = str(caller_org["lookalike_pk"])
    try:
        asyncio.run(mcp_app.get_meeting_details(ORG_B_ONLY))
        asyncio.run(mcp_app.get_meeting_transcript("12345678"))
        asyncio.run(mcp_app.chat_with_meeting(pk, "Still the integer id?"))
        asyncio.run(mcp_app.propose_add_tag(pk, "example"))
    finally:
        _unbind(mcp_app, user_token, pat_token)

    assert _session_refs(calls) == [ORG_B_ONLY, "12345678", pk, pk]
