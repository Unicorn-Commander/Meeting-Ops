"""Hosted MCP streamable-HTTP endpoint tests.

Verifies the mounted /mcp endpoint enforces PAT auth, handles CORS
preflight, and exposes the shared tool surface end-to-end via the
FastMCP HTTP transport.
"""

import json
import time
import types
from unittest.mock import patch

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


# ---------------------------------------------------------------------------
# Fixtures: a real PAT in the test DB so the auth path resolves cleanly.
# ---------------------------------------------------------------------------


@pytest.fixture()
def valid_pat(app):
    """Mint a real PAT for the seeded admin user in the test SQLite DB.

    Imports happen inside the fixture so SQLAlchemy mapper configuration
    waits for the `app` fixture to reload database modules + create the
    schema — otherwise the mappers see half a graph and raise.
    """
    from auth.models import User
    from auth.pat import create_pat
    from database.database import SessionLocal

    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.username == "admin").first()
        assert admin is not None, "conftest must seed the admin user"
        _row, plaintext = create_pat(db, user=admin, name="mcp-test-pat")
        return plaintext
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Auth gating
# ---------------------------------------------------------------------------


def test_mcp_without_authorization_returns_401(client):
    """GET /mcp without Authorization → 401 + JSON body + Bearer challenge."""
    r = client.get("/mcp")
    assert r.status_code == 401
    body = r.json()
    assert body["error"] == "unauthorized"
    assert "Authorization" in body["detail"]
    challenge = r.headers.get("www-authenticate", "")
    assert challenge.lower().startswith("bearer")
    assert 'realm="meeting-ops-mcp"' in challenge
    assert 'resource_metadata="' in challenge
    assert 'error="invalid_token"' not in challenge


def test_mcp_with_invalid_bearer_returns_401(client):
    """Invalid PAT prefix or unknown PAT → 401."""
    r = client.get(
        "/mcp",
        headers={"Authorization": "Bearer mops_pat_DOESNOTEXIST"},
    )
    assert r.status_code == 401
    assert r.json()["error"] == "unauthorized"
    assert 'error="invalid_token"' in r.headers.get("www-authenticate", "")


def test_mcp_with_non_kc_jwt_bearer_returns_401(client):
    """A JWT-shaped bearer with no valid uchub signature is rejected."""
    with patch("auth.oidc_sso.verify_kc_bearer_token", return_value=None):
        r = client.get(
            "/mcp",
            headers={"Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.x"},
        )
    assert r.status_code == 401
    assert 'error="invalid_token"' in r.headers.get("www-authenticate", "")


# ---------------------------------------------------------------------------
# CORS preflight
# ---------------------------------------------------------------------------


def test_mcp_options_preflight_for_claude_origin(client, monkeypatch):
    """OPTIONS /mcp from claude.ai returns 204 with permissive CORS headers."""
    monkeypatch.setenv("MCP_ALLOWED_ORIGINS", "https://claude.ai")
    r = client.options(
        "/mcp",
        headers={
            "Origin": "https://claude.ai",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert r.status_code in (204, 200)
    assert r.headers.get("access-control-allow-origin") == "https://claude.ai"
    allow_methods = r.headers.get("access-control-allow-methods", "")
    assert "POST" in allow_methods
    allow_headers = r.headers.get("access-control-allow-headers", "")
    assert "authorization" in allow_headers.lower()


def test_mcp_options_preflight_for_wildcard_origin(client, monkeypatch):
    """The explicit wildcard preserves the legacy echo-any-origin behavior."""
    monkeypatch.setenv("MCP_ALLOWED_ORIGINS", "*")
    r = client.options(
        "/mcp",
        headers={"Origin": "https://my-custom-mcp-client.example"},
    )
    assert r.status_code in (204, 200)
    assert (
        r.headers.get("access-control-allow-origin")
        == "https://my-custom-mcp-client.example"
    )


def test_mcp_options_rejects_disallowed_origin_before_auth(client, monkeypatch):
    monkeypatch.setenv("MCP_ALLOWED_ORIGINS", "https://allowed.example")
    r = client.options(
        "/mcp",
        headers={
            "Origin": "https://not-allowed.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert r.status_code == 403
    assert r.json()["error"] == "forbidden"
    assert "access-control-allow-origin" not in r.headers
    assert "www-authenticate" not in r.headers


def test_mcp_trailing_slash_redirects_to_canonical_path(client):
    r = client.get("/mcp/", follow_redirects=False)
    assert r.status_code == 308
    assert r.headers["location"].endswith("/mcp")


def test_protected_resource_metadata_both_paths(client, monkeypatch):
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://meeting.example")
    monkeypatch.setenv("KEYCLOAK_URL", "https://auth.example")
    monkeypatch.setenv("KEYCLOAK_REALM", "uchub-test")

    expected_resource = "https://meeting.example/mcp"
    for path in (
        "/.well-known/oauth-protected-resource",
        "/.well-known/oauth-protected-resource/mcp",
    ):
        r = client.get(path)
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("application/json")
        assert r.headers["access-control-allow-origin"] == "*"
        assert r.headers["cache-control"] == "public, max-age=3600"
        document = r.json()
        assert document["resource"] == expected_resource
        assert document["authorization_servers"] == [
            "https://auth.example/realms/uchub-test"
        ]
        assert document["bearer_methods_supported"] == ["header"]
        assert document["scopes_supported"] == [
            "openid", "profile", "email", "offline_access", "mcp"
        ]
        assert document["resource_name"] == "Meeting-Ops MCP"

    options = client.options("/.well-known/oauth-protected-resource/mcp")
    assert options.status_code == 204
    assert options.headers["access-control-allow-origin"] == "*"


@pytest.fixture()
def signed_kc_token(monkeypatch):
    """A locally signed access token served by a test JWKS client."""
    from auth import oidc_sso

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_key = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    public_key = key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    fake_jwks = types.SimpleNamespace(
        get_signing_key_from_jwt=lambda _token: types.SimpleNamespace(key=public_key)
    )
    monkeypatch.setattr(oidc_sso, "_get_jwks_client", lambda: fake_jwks)
    now = int(time.time())
    return pyjwt.encode(
        {
            "iss": oidc_sso.KC_ISSUER,
            "aud": oidc_sso.KC_CLIENT_ID,
            "azp": oidc_sso.KC_CLIENT_ID,
            "typ": "Bearer",
            "sub": "fictional-subject-123",
            "uc_uid": "fictional-uid-123",
            "email": "oauth-tester@example.com",
            "preferred_username": "oauth-tester",
            "groups": [],
            "scope": "openid profile email offline_access mcp",
            "exp": now + 300,
            "iat": now,
        },
        private_key,
        algorithm="RS256",
    )


def test_mcp_accepts_signed_keycloak_access_token(client, signed_kc_token):
    r = client.post(
        "/mcp",
        json=_initialize_payload(),
        headers={
            "Authorization": f"Bearer {signed_kc_token}",
            "Accept": "application/json, text/event-stream",
        },
    )
    assert r.status_code in (200, 202), r.text
    body = _decode_response(r)
    assert body is not None
    assert body.get("result", {}).get("serverInfo", {}).get("name") == "Meeting-Ops"


@pytest.mark.parametrize(
    "claims",
    [
        {"sub": "admin", "uc_uid": "opaque-subject"},
        {"sub": "opaque-subject", "uc_uid": "admin"},
    ],
)
def test_keycloak_stable_identity_reuses_existing_local_user(client, claims):
    """Opaque claims may match an existing local identity, never provision one."""
    from auth.dependencies import resolve_keycloak_user
    from auth.models import User
    from database.database import SessionLocal

    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.username == "admin").one()
        resolved = resolve_keycloak_user(db, claims)
        assert resolved is not None
        assert resolved.id == existing.id
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Valid PAT path — full MCP handshake + list_meetings invocation
# ---------------------------------------------------------------------------


def _initialize_payload(rpc_id: int = 1) -> dict:
    """Build the JSON-RPC initialize payload an MCP client sends first."""
    return {
        "jsonrpc": "2.0",
        "id": rpc_id,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "meeting-ops-test", "version": "0.0.1"},
        },
    }


def _initialized_notification() -> dict:
    return {
        "jsonrpc": "2.0",
        "method": "notifications/initialized",
        "params": {},
    }


def _parse_sse_event(text: str) -> dict | None:
    """Pull the first `data:` JSON payload out of an SSE event stream."""
    for line in text.splitlines():
        if line.startswith("data:"):
            return json.loads(line[5:].strip())
    return None


def _decode_response(r) -> dict | None:
    """Both ``application/json`` and ``text/event-stream`` carry JSON-RPC."""
    ctype = r.headers.get("content-type", "")
    if "application/json" in ctype:
        return r.json()
    if "event-stream" in ctype:
        return _parse_sse_event(r.text)
    return None


def test_mcp_valid_pat_initializes_session(client, valid_pat):
    """A valid PAT can complete the MCP initialize handshake."""
    r = client.post(
        "/mcp",
        json=_initialize_payload(),
        headers={
            "Authorization": f"Bearer {valid_pat}",
            "Accept": "application/json, text/event-stream",
        },
    )
    assert r.status_code in (200, 202), r.text
    body = _decode_response(r)
    assert body is not None
    assert body.get("jsonrpc") == "2.0"
    assert body.get("id") == 1
    result = body.get("result", {})
    assert result.get("serverInfo", {}).get("name") == "Meeting-Ops"
    # Server returned a session id so subsequent calls can be correlated.
    assert "mcp-session-id" in {k.lower() for k in r.headers.keys()}


def test_mcp_list_tools_returns_all_registered_tools(client, valid_pat):
    """The tools/list RPC over HTTP returns every canonical read-only tool."""
    headers = {
        "Authorization": f"Bearer {valid_pat}",
        "Accept": "application/json, text/event-stream",
    }
    init = client.post("/mcp", json=_initialize_payload(), headers=headers)
    assert init.status_code in (200, 202), init.text
    session_id = init.headers.get("mcp-session-id") or init.headers.get("Mcp-Session-Id")
    assert session_id

    session_headers = dict(headers)
    session_headers["MCP-Session-Id"] = session_id

    # The MCP spec requires the client to fire `initialized` before
    # issuing any other request.
    client.post("/mcp", json=_initialized_notification(), headers=session_headers)

    r = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        headers=session_headers,
    )
    assert r.status_code in (200, 202), r.text
    body = _decode_response(r)
    assert body is not None and body.get("id") == 2
    tools = body.get("result", {}).get("tools", [])
    names = {t["name"] for t in tools}
    for expected in (
        "search_meetings",
        "list_meetings",
        "get_meeting_details",
        "get_meeting_transcript",
        "chat_with_meeting",
        "get_analytics",
        "get_meeting_insights",
        "ask_about_meetings",
    ):
        assert expected in names, f"tool missing from /mcp: {expected}"


def test_mcp_list_meetings_tool_call_forwards_pat(client, valid_pat):
    """End-to-end: tools/call list_meetings hits the backend with the PAT.

    We patch the shared HTTP client so the test doesn't depend on a real
    /api/simple/recording-sessions DB row — we just need to prove the PAT
    that arrived on /mcp is the one forwarded to the backend.
    """
    headers = {
        "Authorization": f"Bearer {valid_pat}",
        "Accept": "application/json, text/event-stream",
    }
    init = client.post("/mcp", json=_initialize_payload(), headers=headers)
    session_id = init.headers.get("mcp-session-id") or init.headers.get("Mcp-Session-Id")
    assert session_id

    session_headers = dict(headers)
    session_headers["MCP-Session-Id"] = session_id
    client.post("/mcp", json=_initialized_notification(), headers=session_headers)

    captured = {}

    class _FakeResp:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return []

    class _FakeClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, headers=None, params=None):
            captured["method"] = "get"
            captured["url"] = url
            captured["headers"] = headers
            captured["params"] = params
            return _FakeResp()

        async def post(self, url, headers=None, json=None):
            captured["method"] = "post"
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return _FakeResp()

    with patch("services.mcp_app.httpx.AsyncClient", _FakeClient):
        r = client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "list_meetings",
                    "arguments": {"limit": 5},
                },
            },
            headers=session_headers,
        )

    assert r.status_code in (200, 202), r.text
    body = _decode_response(r)
    assert body is not None
    # Tool ran without error.
    assert body.get("id") == 3
    assert "error" not in body or body.get("error") is None
    result = body.get("result", {})
    # FastMCP wraps string return values into a content array.
    content = result.get("content", [])
    assert content, f"unexpected tool result shape: {result!r}"

    # The PAT pinned by the HTTP middleware was forwarded verbatim.
    assert captured.get("headers", {}).get("Authorization") == f"Bearer {valid_pat}"
    assert "/api/simple/recording-sessions" in captured.get("url", "")


# ---------------------------------------------------------------------------
# Health surface
# ---------------------------------------------------------------------------


def test_health_includes_mcp_status(client):
    """The top-level /health endpoint reports MCP availability."""
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert "mcp" in data
    assert data["mcp"] in ("ok", "disabled") or data["mcp"].startswith("error")


# ---------------------------------------------------------------------------
# Disabled mode
# ---------------------------------------------------------------------------


def test_mcp_disabled_via_env(monkeypatch):
    """When MCP_HOSTED_ENABLED=false, mount_mcp_app is a no-op."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    monkeypatch.setenv("MCP_HOSTED_ENABLED", "false")

    test_app = FastAPI()
    from api.mcp_http import mount_mcp_app, mcp_health_status

    mount_mcp_app(test_app)
    assert mcp_health_status() == "disabled"

    with TestClient(test_app) as tc:
        r = tc.get("/mcp")
        assert r.status_code == 404
