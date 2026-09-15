"""security-3 regression: POST /api/auth/register must not take org or role off the wire.

The bug (found 2026-09-15, live on the centerdeep ring): ``UserCreate`` carried
``organization_id`` and ``role``, and ``register`` passed both straight to
``AuthService.create_user``, where "an explicit organization_id always wins"
and ``role`` is written verbatim into ``user_organizations``. The route serves
anonymous callers whenever ALLOW_REGISTRATION is on, and its dependency is
``get_current_user_optional`` rather than ``require_admin``, so there were two
ways into a populated tenant at a self-chosen role:

  1. an anonymous POST carrying ``{organization_id: <victim org>, role: ...}``;
  2. sign up self-serve, log in, POST again as that unprivileged user --
     ``organization_id=None`` then fell through to
     ``ensure_default_organization()`` with the wire role.

``role`` was never whitelisted, and ``ROLE_HIERARCHY`` accepts ``"superuser"``.

These tests pin the closed behaviour. The seeded fixture org is
``magic-unicorn`` -- the same slug as the real prod org 1 that holds the
third-party conversations -- so a regression reads unmistakably.
"""
from __future__ import annotations

import uuid

import pytest


def _models():
    from auth.models import Organization, User, UserOrganization
    from database.database import SessionLocal
    return Organization, User, UserOrganization, SessionLocal


@pytest.fixture(autouse=True)
def _registration_env(monkeypatch):
    """Self-serve register needs ALLOW_REGISTRATION on and no invite gate."""
    from auth.config import auth_config
    from auth import routes as routes_mod

    monkeypatch.setattr(auth_config, "ALLOW_REGISTRATION", True)
    monkeypatch.setattr(auth_config, "REQUIRE_INVITE_CODE", False)
    monkeypatch.setattr(routes_mod, "send_verification_email", lambda to, url: True)
    yield


def _uname() -> str:
    return "sec3" + uuid.uuid4().hex[:8]


def _body(username: str, **extra) -> dict:
    body = {
        "email": f"{username}@example.com",
        "username": username,
        "password": "Passw0rdSec3",
    }
    body.update(extra)
    return body


def _victim_org_id() -> int:
    Organization, _User, _UO, SessionLocal = _models()
    db = SessionLocal()
    try:
        org = db.query(Organization).filter(Organization.slug == "magic-unicorn").first()
        assert org is not None, "fixture org missing"
        return org.id
    finally:
        db.close()


def _user_row(username: str):
    _Org, User, _UO, SessionLocal = _models()
    db = SessionLocal()
    try:
        return db.query(User).filter(User.username == username).first()
    finally:
        db.close()


def _memberships(username: str) -> list[tuple[int, str]]:
    _Org, User, UserOrganization, SessionLocal = _models()
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username).first()
        if user is None:
            return []
        rows = (
            db.query(UserOrganization)
            .filter(UserOrganization.user_id == user.id)
            .all()
        )
        return [(r.organization_id, r.role) for r in rows]
    finally:
        db.close()


def _login(client, username: str, password: str = "Passw0rdSec3") -> dict:
    r = client.post("/api/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# ---------------------------------------------------------------------------
# 1. anonymous caller cannot name an org
# ---------------------------------------------------------------------------


def test_anonymous_register_cannot_join_an_existing_org(client):
    victim = _victim_org_id()
    username = _uname()

    resp = client.post(
        "/api/auth/register", json=_body(username, organization_id=victim)
    )

    assert resp.status_code == 403, resp.text
    # and, crucially, nothing was created on the way to the 403
    assert _user_row(username) is None
    assert _memberships(username) == []


# ---------------------------------------------------------------------------
# 2. anonymous caller cannot name a role (superuser least of all)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("role", ["superuser", "admin", "manager", "viewer"])
def test_anonymous_register_cannot_choose_a_role(client, role):
    username = _uname()

    resp = client.post("/api/auth/register", json=_body(username, role=role))

    assert resp.status_code == 403, resp.text
    assert _user_row(username) is None


def test_anonymous_register_cannot_combine_org_and_superuser(client):
    victim = _victim_org_id()
    username = _uname()

    resp = client.post(
        "/api/auth/register",
        json=_body(username, organization_id=victim, role="superuser"),
    )

    assert resp.status_code == 403, resp.text
    assert _user_row(username) is None


# ---------------------------------------------------------------------------
# 3. the real signup flow still works, and lands in a NEW private org
# ---------------------------------------------------------------------------


def test_legitimate_self_serve_signup_still_works(client):
    """Exactly the body frontend/src/pages/Signup.tsx sends."""
    victim = _victim_org_id()
    username = _uname()

    resp = client.post(
        "/api/auth/register",
        json={
            "email": f"{username}@example.com",
            "username": username,
            "password": "Passw0rdSec3",
            "full_name": "Sec Three",
        },
    )

    assert resp.status_code == 200, resp.text
    memberships = _memberships(username)
    assert len(memberships) == 1
    org_id, role = memberships[0]
    assert org_id != victim, "self-serve signup must never land in an existing tenant"
    assert role == "admin"  # admin OF THEIR OWN new personal org

    _Org, _User, _UO, SessionLocal = _models()
    db = SessionLocal()
    try:
        org = db.query(_Org).filter(_Org.id == org_id).first()
        assert org.slug == f"{username}-personal"
    finally:
        db.close()

    # ... and they can log in afterwards
    _login(client, username)


# ---------------------------------------------------------------------------
# 4. an authenticated but unprivileged user cannot create into another org
# ---------------------------------------------------------------------------


def test_authenticated_nonadmin_cannot_create_into_another_org(client):
    """The second escalation path: self-serve, log in, then POST again."""
    victim = _victim_org_id()
    attacker = _uname()
    assert client.post("/api/auth/register", json=_body(attacker)).status_code == 200
    headers = _login(client, attacker)

    target = _uname()
    resp = client.post(
        "/api/auth/register",
        json=_body(target, organization_id=victim, role="admin"),
        headers=headers,
    )

    assert resp.status_code == 403, resp.text
    assert _user_row(target) is None


def test_authenticated_nonadmin_cannot_fall_through_to_default_org(client):
    """organization_id omitted used to mean ensure_default_organization()."""
    attacker = _uname()
    assert client.post("/api/auth/register", json=_body(attacker)).status_code == 200
    headers = _login(client, attacker)

    target = _uname()
    resp = client.post(
        "/api/auth/register",
        json=_body(target, role="admin"),
        headers=headers,
    )

    assert resp.status_code == 400, resp.text
    assert _user_row(target) is None


# ---------------------------------------------------------------------------
# 5. the admin path still works, and still refuses superuser
# ---------------------------------------------------------------------------


def _admin_headers(client) -> dict:
    r = client.post("/api/auth/login", data={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_admin_can_still_create_a_member_in_their_own_org(client):
    victim = _victim_org_id()
    target = _uname()

    resp = client.post(
        "/api/auth/register",
        json=_body(target, organization_id=victim, role="manager"),
        headers=_admin_headers(client),
    )

    assert resp.status_code == 200, resp.text
    assert _memberships(target) == [(victim, "manager")]


def test_admin_cannot_assign_superuser(client):
    victim = _victim_org_id()
    target = _uname()

    resp = client.post(
        "/api/auth/register",
        json=_body(target, organization_id=victim, role="superuser"),
        headers=_admin_headers(client),
    )

    assert resp.status_code == 400, resp.text
    assert _user_row(target) is None


def test_admin_cannot_assign_a_made_up_role(client):
    victim = _victim_org_id()
    target = _uname()

    resp = client.post(
        "/api/auth/register",
        json=_body(target, organization_id=victim, role="root"),
        headers=_admin_headers(client),
    )

    assert resp.status_code == 400, resp.text
    assert _user_row(target) is None


# ---------------------------------------------------------------------------
# 6. service layer refuses a bad role even without the route gate
# ---------------------------------------------------------------------------


def test_create_user_service_rejects_unwhitelisted_role(client):
    from auth.service import AuthService
    from database.database import SessionLocal

    db = SessionLocal()
    try:
        with pytest.raises(ValueError):
            AuthService.create_user(
                db,
                email=f"{_uname()}@example.com",
                username=_uname(),
                password="Passw0rdSec3",
                role="superuser",
            )
    finally:
        db.close()
