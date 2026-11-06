"""WebSocket handshake auth for the meeting sockets (v3.29.3, item D).

The live sockets were unauthenticated at the app layer: `/ws/transcription/{id}`
(push audio -> server STT + replay a session's transcription),
`/ws/transcription-auto/{id}` (live transcription + progressive summaries), and
`/ws/audio-levels`. On a self-hosted node without oauth2-proxy in front, anyone
could attach to ANY session (cross-tenant read) or drive server compute.

v3.29.3 adds a `?token=` JWT check at the handshake (auth.ws_auth.enforce_ws_auth),
org-scoping the session-bound sockets, with a `WS_REQUIRE_AUTH` kill-switch.

These drive the real sockets through Starlette's TestClient and assert:
  * no token            -> closed 1008 (all three)
  * valid token + own   -> accepted (status frame)
  * valid token + other org's session -> closed 1008 (cross-tenant)
  * WS_REQUIRE_AUTH=false -> no token is allowed again (kill-switch)
"""
from __future__ import annotations

import uuid as _uuid

import pytest
from starlette.websockets import WebSocketDisconnect

from auth.utils import get_password_hash

WS_CLOSE_POLICY_VIOLATION = 1008


def _models():
    from auth.models import Organization, User, UserOrganization
    from database.database import SessionLocal
    from database.models import RecordingSession
    return Organization, User, UserOrganization, SessionLocal, RecordingSession


def _seed_user_and_org(slug, username):
    Organization, User, UserOrganization, SessionLocal, _ = _models()
    db = SessionLocal()
    try:
        org = db.query(Organization).filter(Organization.slug == slug).first()
        if not org:
            org = Organization(name=slug.replace("-", " ").title(), slug=slug, is_active=True)
            db.add(org); db.commit(); db.refresh(org)
        user = db.query(User).filter(User.username == username).first()
        if not user:
            user = User(
                email=f"{username}@meeting-ops.local", username=username,
                hashed_password=get_password_hash("admin123"), is_active=True,
                is_verified=True, tier="enterprise", is_superuser=False,
            )
            db.add(user); db.commit(); db.refresh(user)
        mem = (
            db.query(UserOrganization)
            .filter(UserOrganization.user_id == user.id, UserOrganization.organization_id == org.id)
            .first()
        )
        if not mem:
            db.add(UserOrganization(user_id=user.id, organization_id=org.id, role="admin")); db.commit()
        return org.id, org.slug, user.id
    finally:
        db.close()


def _create_session(org_id, user_id):
    _, _, _, SessionLocal, RecordingSession = _models()
    db = SessionLocal()
    try:
        sid = str(_uuid.uuid4())
        s = RecordingSession(
            session_id=sid, name=f"ws-{sid[:8]}", title=f"ws-{sid[:8]}",
            meeting_type="meeting", mode="upload", status="recording",
            duration=0.0, user_id=user_id, organization_id=org_id,
            processing_metadata={},
        )
        db.add(s); db.commit(); db.refresh(s)
        return s.session_id
    finally:
        db.close()


def _token(client, username, password="admin123"):
    resp = client.post("/api/auth/login", data={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _expect_closed_1008(client, url):
    """Connecting must fail with a 1008 policy-violation close (server closes
    before/at accept). Starlette surfaces this as WebSocketDisconnect."""
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(url) as ws:
            ws.receive_text()  # should not reach a frame
    assert exc.value.code == WS_CLOSE_POLICY_VIOLATION


def test_ws_transcription_rejects_without_token(client):
    org_id, _, user_id = _seed_user_and_org("ws-auth-a", "ws_auth_a")
    sid = _create_session(org_id, user_id)
    _expect_closed_1008(client, f"/ws/transcription/{sid}")


def test_ws_audio_levels_rejects_without_token(client):
    _expect_closed_1008(client, "/ws/audio-levels")


def test_ws_transcription_auto_rejects_without_token(client):
    org_id, _, user_id = _seed_user_and_org("ws-auth-b", "ws_auth_b")
    sid = _create_session(org_id, user_id)
    _expect_closed_1008(client, f"/ws/transcription-auto/{sid}")


def test_transcription_auto_router_imports_without_aiohttp():
    """1008 is required. The hosted runner saw 1000 because aiohttp was
    missing, system_service failed to import, and the route was not mounted.
    Starlette's not-found handler closes an unknown websocket with 1000.
    The socket must still exist so the unauthenticated close stays 1008.
    """
    import os
    import subprocess
    import sys
    from pathlib import Path

    script = """
import sys
class _Block:
    def find_spec(self, fullname, path, target=None):
        if fullname == "aiohttp" or fullname.startswith("aiohttp."):
            raise ModuleNotFoundError(fullname)
        return None
sys.meta_path.insert(0, _Block())
import api.websocket_auto_summary as mod
paths = [getattr(route, "path", "") for route in mod.router.routes]
assert "/ws/transcription-auto/{session_id}" in paths, paths
"""
    env = os.environ.copy()
    env["ENVIRONMENT"] = "test"
    env["DATABASE_URL"] = "sqlite:///:memory:"
    backend = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(backend),
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]


def test_ws_tts_progress_rejects_without_token(client):
    _expect_closed_1008(client, f"/ws/tts/{_uuid.uuid4()}")


def test_ws_upload_progress_rejects_without_token(client):
    _expect_closed_1008(client, f"/ws/uploads/{_uuid.uuid4()}")


def test_ws_live_transcription_rejects_without_token(client):
    _expect_closed_1008(client, "/api/live-transcription/ws")


def test_ws_transcription_accepts_with_valid_token_own_session(client):
    org_id, _, user_id = _seed_user_and_org("ws-auth-c", "ws_auth_c")
    sid = _create_session(org_id, user_id)
    token = _token(client, "ws_auth_c")
    # Own session + valid token -> accepted; the plain transcription socket
    # sends a {"type":"status"} frame right after accept (no Redis needed).
    with client.websocket_connect(f"/ws/transcription/{sid}?token={token}") as ws:
        msg = ws.receive_json()
        assert msg.get("type") == "status"


def test_ws_transcription_rejects_cross_org_session(client):
    # User in org A, session belongs to org B -> cross-tenant -> rejected even
    # with a valid token.
    _, _, _ = _seed_user_and_org("ws-auth-d", "ws_auth_d")
    org_b, _, user_b = _seed_user_and_org("ws-auth-e", "ws_auth_e")
    other_session = _create_session(org_b, user_b)
    token_a = _token(client, "ws_auth_d")
    _expect_closed_1008(client, f"/ws/transcription/{other_session}?token={token_a}")


def test_ws_kill_switch_allows_without_token(client, monkeypatch):
    # WS_REQUIRE_AUTH=false -> pre-v3.29.3 open behaviour (no token accepted).
    monkeypatch.setenv("WS_REQUIRE_AUTH", "false")
    org_id, _, user_id = _seed_user_and_org("ws-auth-f", "ws_auth_f")
    sid = _create_session(org_id, user_id)
    with client.websocket_connect(f"/ws/transcription/{sid}") as ws:
        msg = ws.receive_json()
        assert msg.get("type") == "status"
