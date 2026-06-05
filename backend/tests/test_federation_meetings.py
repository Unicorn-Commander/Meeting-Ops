"""Unit tests for the inbound Customer-Ops federation surface.

Covers the auth flow (Brigade token verify + workspace->org binding),
the read-scope gate, JSON-RPC tool dispatch/routing, and serialization.
The JSONB ``@>`` containment SQL is Postgres-only (the suite test DB is
SQLite) so the live query is smoke-tested against the dogfood Postgres
at deploy time, not here.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from api import federation_meetings as fm
from services import brigade_jwt_verifier as bv
from services.brigade_jwt_verifier import BrigadeJWTVerificationResult


def _req(auth: str | None = None) -> Request:
    headers = []
    if auth is not None:
        headers.append((b"authorization", auth.encode()))
    return Request({"type": "http", "headers": headers})


class _FakeOrg:
    def __init__(self, oid: int):
        self.id = oid


# ── scope extraction ───────────────────────────────────────────────────


def test_extract_scopes_space_delimited():
    assert bv.extract_scopes({"scope": "a b meetings:read"}) == {
        "a",
        "b",
        "meetings:read",
    }


def test_extract_scopes_list_and_missing():
    assert bv.extract_scopes({"scopes": ["x", "y"]}) == {"x", "y"}
    assert bv.extract_scopes({}) == set()
    assert bv.extract_scopes(None) == set()


# ── verifier early rejects (no crypto / network needed) ────────────────


def test_verifier_rejects_empty_and_pat():
    assert bv.verify_brigade_jwt_with_reason("").reason == "personal-access-token"
    assert (
        bv.verify_brigade_jwt_with_reason("mops_pat_abc").reason
        == "personal-access-token"
    )


def test_verifier_rejects_malformed_header():
    res = bv.verify_brigade_jwt_with_reason("not-a-jwt")
    assert res.valid is False
    assert res.reason == "header-unparseable"


def test_verifier_rejects_disallowed_alg():
    # HS256 is not in ALLOWED_BRIGADE_ALGORITHMS -> rejected before any
    # key resolution / network. Exercises header parse + the alg gate.
    from jose import jwt as jose_jwt

    tok = jose_jwt.encode({"sub": "x"}, "secret", algorithm="HS256")
    res = bv.verify_brigade_jwt_with_reason(tok)
    assert res.valid is False
    assert res.reason == "alg-rejected"


# ── require_brigade_token (auth flow + tenant binding) ─────────────────


def test_require_token_missing_header():
    with pytest.raises(HTTPException) as ei:
        fm.require_brigade_token(_req(None), db=None)
    assert ei.value.status_code == 401


def test_require_token_invalid(monkeypatch):
    monkeypatch.setattr(
        fm,
        "verify_brigade_jwt_with_reason",
        lambda _t: BrigadeJWTVerificationResult(False, None, "signature-invalid"),
    )
    with pytest.raises(HTTPException) as ei:
        fm.require_brigade_token(_req("Bearer xyz"), db=None)
    assert ei.value.status_code == 401


def test_require_token_workspace_not_provisioned(monkeypatch):
    monkeypatch.setattr(
        fm,
        "verify_brigade_jwt_with_reason",
        lambda _t: BrigadeJWTVerificationResult(
            True, {"sub": "u1", "workspace_id": "ws-none", "scope": "meetings:read"}, None
        ),
    )
    monkeypatch.setattr(fm, "org_for_workspace_id", lambda _db, _ws: None)
    with pytest.raises(HTTPException) as ei:
        fm.require_brigade_token(_req("Bearer xyz"), db=object())
    assert ei.value.status_code == 403


def test_require_token_binds_org(monkeypatch):
    monkeypatch.setattr(
        fm,
        "verify_brigade_jwt_with_reason",
        lambda _t: BrigadeJWTVerificationResult(
            True,
            {"sub": "u1", "workspace_id": "ws-1", "scope": "meetings:read other"},
            None,
        ),
    )
    monkeypatch.setattr(fm, "org_for_workspace_id", lambda _db, _ws: _FakeOrg(42))
    ctx = fm.require_brigade_token(_req("Bearer xyz"), db=object())
    assert ctx.org_id == 42
    assert ctx.workspace_id == "ws-1"
    assert ctx.sub == "u1"
    assert "meetings:read" in ctx.scopes


# ── read-scope gate ────────────────────────────────────────────────────


def test_require_read_scope():
    ok = fm.FederationContext(org_id=1, workspace_id="w", sub="s", scopes={fm.READ_SCOPE})
    fm._require_read_scope(ok)  # no raise
    bad = fm.FederationContext(org_id=1, workspace_id="w", sub="s", scopes={"other"})
    with pytest.raises(HTTPException) as ei:
        fm._require_read_scope(bad)
    assert ei.value.status_code == 403


# ── JSON-RPC tool dispatch routing ─────────────────────────────────────


def test_dispatch_requires_contact_id():
    ctx = fm.FederationContext(org_id=1, workspace_id="w", sub="s", scopes={fm.READ_SCOPE})
    with pytest.raises(HTTPException) as ei:
        fm._dispatch_tool(object(), ctx, "list_meetings_for_contact", {})
    assert ei.value.status_code == 400


def test_dispatch_routes_each_tool(monkeypatch):
    ctx = fm.FederationContext(org_id=7, workspace_id="w", sub="s", scopes={fm.READ_SCOPE})
    calls = {}
    monkeypatch.setattr(
        fm, "list_meetings_for_contact",
        lambda db, org, cid, **k: calls.setdefault("m", (org, cid, k)) or {"items": []},
    )
    monkeypatch.setattr(
        fm, "list_summaries_for_contact",
        lambda db, org, cid, **k: calls.setdefault("s", (org, cid, k)) or [],
    )
    monkeypatch.setattr(
        fm, "list_action_items_for_contact",
        lambda db, org, cid, **k: calls.setdefault("a", (org, cid, k)) or [],
    )
    fm._dispatch_tool(object(), ctx, "list_meetings_for_contact", {"contact_id": "c1", "limit": 5})
    fm._dispatch_tool(object(), ctx, "list_summaries_for_contact", {"contact_id": "c2"})
    fm._dispatch_tool(object(), ctx, "list_action_items_for_contact", {"contact_id": "c3"})
    assert calls["m"][0] == 7 and calls["m"][1] == "c1"
    assert calls["s"][1] == "c2"
    assert calls["a"][1] == "c3"
    with pytest.raises(KeyError):
        fm._dispatch_tool(object(), ctx, "nope", {"contact_id": "x"})


def test_rpc_envelope_helpers():
    assert fm._rpc_ok(1, {"k": 1}) == {"jsonrpc": "2.0", "id": 1, "result": {"k": 1}}
    err = fm._rpc_err(2, -32601, "boom")
    assert err["error"]["code"] == -32601 and err["error"]["message"] == "boom"


# ── serialization helpers ──────────────────────────────────────────────


def test_participants_public_projection():
    class _S:
        participants = [
            {"id": "1", "name": "Alice", "email": "a@x.com", "contact_id": "co-1"},
            {"id": "2", "name": "Bob"},  # no email/contact_id
            "junk",  # non-dict ignored
        ]

    out = fm._participants_public(_S())
    assert out == [
        {"contact_id": "co-1", "display_name": "Alice", "email": "a@x.com"},
        {"contact_id": None, "display_name": "Bob", "email": None},
    ]


def test_clamp_limit():
    assert fm._clamp_limit(None) == fm.DEFAULT_LIMIT
    assert fm._clamp_limit(0) == fm.DEFAULT_LIMIT
    assert fm._clamp_limit(5) == 5
    assert fm._clamp_limit(9999) == fm.MAX_LIMIT
