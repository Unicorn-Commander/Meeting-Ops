"""Org gate on session-bound WebSockets (auth/ws_auth.py:160-171).

A session-bound socket (``/ws/transcription/{session_id}``) is admitted only when
the session's owning organization is in the caller's membership set
(``user._org_ids``, materialised in ``authenticate_ws`` from UserOrganization).
The owning org is resolved from the session row itself (``_session_org_id``),
never from a client-supplied selector. Superusers short-circuit the check
(ws_auth.py:166-167). An unresolvable session is allowed through (ws_auth.py:169-170).

These drive the real WebSocket route through Starlette's TestClient (same client
+ fixtures as tests/test_ws_auth.py) and assert the gate, not a mock of it:

  1. member of org A, session in org A            -> accepted (status frame)
  2. same user, session in org C (no membership)  -> closed 1008
  3. superuser, session in an org they are NOT a member of -> accepted
     (asserts the actual rule at ws_auth.py:166-167)
  4. ``?org=<C>`` selector does not open an org C session -> closed 1008

Every test first asserts its own baseline (membership set + the session's real
owning org) so the main assertion proves the gate rather than a fixture mistake.
Fictional orgs/users only. The membership check is NOT mocked.
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


def _seed_org(slug):
    """Create (idempotently) an organization and return its id."""
    Organization, _, _, SessionLocal, _ = _models()
    db = SessionLocal()
    try:
        org = db.query(Organization).filter(Organization.slug == slug).first()
        if not org:
            org = Organization(
                name=slug.replace("-", " ").title(), slug=slug, is_active=True
            )
            db.add(org)
            db.commit()
            db.refresh(org)
        return org.id
    finally:
        db.close()


def _seed_user_in_org(slug, username, superuser=False):
    """Create (idempotently) an org + a user who is a member of ONLY that org.

    Returns (org_id, user_id). The user is a plain member (not superuser unless
    asked), so their membership set is exactly [org_id]."""
    Organization, User, UserOrganization, SessionLocal, _ = _models()
    db = SessionLocal()
    try:
        org = db.query(Organization).filter(Organization.slug == slug).first()
        if not org:
            org = Organization(
                name=slug.replace("-", " ").title(), slug=slug, is_active=True
            )
            db.add(org)
            db.commit()
            db.refresh(org)
        user = db.query(User).filter(User.username == username).first()
        if not user:
            user = User(
                email=f"{username}@example.com",
                username=username,
                hashed_password=get_password_hash("admin123"),
                is_active=True,
                is_verified=True,
                tier="enterprise",
                is_superuser=superuser,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        mem = (
            db.query(UserOrganization)
            .filter(
                UserOrganization.user_id == user.id,
                UserOrganization.organization_id == org.id,
            )
            .first()
        )
        if not mem:
            db.add(
                UserOrganization(
                    user_id=user.id, organization_id=org.id, role="admin"
                )
            )
            db.commit()
        return org.id, user.id
    finally:
        db.close()


def _membership_ids(user_id):
    """The caller's real membership set, straight from UserOrganization.

    This is the same query authenticate_ws runs to build ``user._org_ids``
    (ws_auth.py:81-86); we read it to assert each test's baseline."""
    _, _, UserOrganization, SessionLocal, _ = _models()
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


def _create_session(org_id, user_id):
    """Create a session owned by ``org_id`` and return its session_id (uuid)."""
    _, _, _, SessionLocal, RecordingSession = _models()
    db = SessionLocal()
    try:
        sid = str(_uuid.uuid4())
        s = RecordingSession(
            session_id=sid,
            name=f"gate-{sid[:8]}",
            title=f"gate-{sid[:8]}",
            meeting_type="meeting",
            mode="upload",
            status="recording",
            duration=0.0,
            user_id=user_id,
            organization_id=org_id,
            processing_metadata={},
        )
        db.add(s)
        db.commit()
        db.refresh(s)
        return s.session_id
    finally:
        db.close()


def _session_org_id(sid):
    """The session's real owning org, read back from the DB (baseline check)."""
    _, _, _, SessionLocal, RecordingSession = _models()
    db = SessionLocal()
    try:
        row = (
            db.query(RecordingSession.organization_id)
            .filter(RecordingSession.session_id == sid)
            .first()
        )
        return int(row[0]) if row and row[0] is not None else None
    finally:
        db.close()


def _token(client, username, password="admin123"):
    resp = client.post(
        "/api/auth/login", data={"username": username, "password": password}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _expect_closed_1008(client, url):
    """Connecting must fail with a 1008 policy-violation close. Starlette
    surfaces a server close-before-frames as WebSocketDisconnect."""
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(url) as ws:
            ws.receive_text()
    assert exc.value.code == WS_CLOSE_POLICY_VIOLATION


def _expect_accepted(client, url):
    """Connecting must be accepted; the transcription socket sends a status
    frame right after accept (no Redis needed)."""
    with client.websocket_connect(url) as ws:
        msg = ws.receive_json()
    assert msg.get("type") == "status"


def test_member_can_open_socket_for_own_org_session(client):
    """(1) Baseline: user is a member of org A and the session's real org is A.
    Then: the socket is accepted."""
    org_a, user_a = _seed_user_in_org("ws-gate-a", "ws_gate_a")
    sid = _create_session(org_a, user_a)

    # Baseline: membership set is exactly [A], and the session resolves to A.
    assert _membership_ids(user_a) == [org_a]
    assert _session_org_id(sid) == org_a

    token = _token(client, "ws_gate_a")
    _expect_accepted(client, f"/ws/transcription/{sid}?token={token}")


def test_member_refused_for_foreign_org_session(client):
    """(2) Baseline: user is a member of org A only, the session's real org is C,
    and C is not in the membership set. Then: the socket is refused (1008)."""
    org_a, user_a = _seed_user_in_org("ws-gate-b", "ws_gate_b")
    org_c = _seed_org("ws-gate-c")
    sid = _create_session(org_c, user_a)

    # Baseline: A != C, membership is [A], session really lives in C, C not a member.
    assert org_c != org_a
    assert _membership_ids(user_a) == [org_a]
    assert _session_org_id(sid) == org_c
    assert org_c not in _membership_ids(user_a)

    token = _token(client, "ws_gate_b")
    _expect_closed_1008(client, f"/ws/transcription/{sid}?token={token}")


def test_superuser_admitted_to_foreign_org_session(client):
    """(3) The code says superusers pass regardless of membership
    (ws_auth.py:166-167: ``if getattr(user, 'is_superuser', False): return True``).

    Baseline: the caller IS a superuser, the session's real org is C, and C is
    NOT in their membership set (so a non-superuser would be refused, as test 2
    shows). Then: the socket is accepted, proving the superuser short-circuit."""
    # Superuser is a member of their home org only; org C is a different org.
    home_org, su_id = _seed_user_in_org(
        "ws-gate-d-home", "ws_gate_su", superuser=True
    )
    org_c = _seed_org("ws-gate-d")
    sid = _create_session(org_c, su_id)

    # Baseline: superuser flag set, session in C, C not in membership set.
    from auth.models import User
    from database.database import SessionLocal

    db = SessionLocal()
    try:
        su = db.query(User).filter(User.id == su_id).first()
        assert su.is_superuser is True
    finally:
        db.close()
    assert home_org != org_c
    assert _membership_ids(su_id) == [home_org]
    assert org_c not in _membership_ids(su_id)
    assert _session_org_id(sid) == org_c

    # Direct rule assertion (not mocked): the real predicate returns True for a
    # superuser on an org they are not a member of (ws_auth.py:166-167).
    from auth.ws_auth import ws_user_can_access_session

    class _DetachedSuper:
        is_superuser = True
        _org_ids = [home_org]

    assert ws_user_can_access_session(_DetachedSuper(), sid) is True

    token = _token(client, "ws_gate_su")
    _expect_accepted(client, f"/ws/transcription/{sid}?token={token}")


def test_org_query_selector_does_not_grant_foreign_org_session(client):
    """(4) The gate reads the session's owning org, never a client ``?org=``
    selector. Baseline: user is a member of org A only, session's real org is C.
    Then: naming org C via ``?org=`` still cannot open the org C session (1008),
    and the same inert selector does not lock the user out of their own org A
    session either."""
    org_a, user_a = _seed_user_in_org("ws-gate-e", "ws_gate_e")
    org_c = _seed_org("ws-gate-f")
    sid_c = _create_session(org_c, user_a)
    sid_a = _create_session(org_a, user_a)

    # Baseline: membership [A]; the C-session resolves to C; the A-session to A.
    assert _membership_ids(user_a) == [org_a]
    assert _session_org_id(sid_c) == org_c
    assert _session_org_id(sid_a) == org_a
    assert org_c not in _membership_ids(user_a)

    token = _token(client, "ws_gate_e")
    # Naming org C in the selector does not open the org C session.
    _expect_closed_1008(
        client, f"/ws/transcription/{sid_c}?token={token}&org={org_c}"
    )
    # The selector is inert: it also does not revoke access to the user's own
    # org A session (proving the gate keys off the session row, not ?org=).
    _expect_accepted(
        client, f"/ws/transcription/{sid_a}?token={token}&org={org_c}"
    )
