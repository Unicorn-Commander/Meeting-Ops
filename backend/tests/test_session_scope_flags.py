"""Session scope-flag + org-header-fallback regression tests.

Pins the contract of the two scope-widening query flags on
``GET /api/simple/recording-sessions`` (``api/simple_recording_db.py``,
``list_sessions``) and the ``X-MeetingOps-Org`` header fallback in
``auth/organization.py``:

1. ``include_all_my_orgs=true`` widens to the UNION of the caller's own
   memberships and no further - a member of org A + org B never sees org C.
2. ``all_tenants=true`` is silently ignored for non-superusers: the response
   is byte-for-byte the active-org view they would get without the flag.
3. ``all_tenants=true`` for a superuser is the explicit cross-tenant god-view
   and returns every org's sessions.
4. An ``X-MeetingOps-Org`` header naming an org the caller is not a member of
   (or that does not exist) falls back to their default org: never 404/403,
   never widens scope.

The scoping code under test (``list_sessions`` + ``resolve_active_organization``
+ ``services.session_visibility``) is exercised for real through the HTTP
route; nothing in the scoping path is mocked. Fixture pattern follows
``tests/test_cross_org_isolation.py``. Fictional data only (example.com).
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from auth.utils import get_password_hash


def _models():
    """Lazy import - these modules are reloaded by the session app fixture."""
    from auth.models import Organization, User, UserOrganization
    from database.database import SessionLocal
    from database.models import RecordingSession

    return Organization, User, UserOrganization, SessionLocal, RecordingSession


def _seed_user(db, *, username: str, email: str, is_superuser: bool = False):
    _, User, _, _, _ = _models()
    user = User(
        email=email,
        username=username,
        hashed_password=get_password_hash("Password123"),
        is_active=True,
        is_verified=True,
        is_superuser=is_superuser,
        tier="enterprise",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_session(db, *, organization_id: int, user_id: int, title: str) -> Any:
    _, _, _, _, RecordingSession = _models()
    sess = RecordingSession(
        session_id=str(uuid.uuid4()),
        name=title,
        title=title,
        status="completed",
        organization_id=organization_id,
        user_id=user_id,
        transcript=f"{title} transcript body.",
        transcript_simple=f"{title} transcript body.",
        duration=120.0,
    )
    db.add(sess)
    db.commit()
    db.refresh(sess)
    return sess


def _login_headers(client, username: str) -> dict[str, str]:
    response = client.post(
        "/api/auth/login",
        data={"username": username, "password": "Password123"},
    )
    assert response.status_code == 200, f"Login failed: {response.text}"
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture()
def scope_world(client):
    """Three orgs (A/B/C), one session each, plus three users.

    - ``multi``: member of A + B (default org A), never C.
    - ``single``: member of A only (default org A).
    - ``super``: superuser, member of A only (default org A).

    Orgs are on a paid plan and users on a paid tier so no per-workspace tier
    gate can shadow the scope logic under test.
    """
    Organization, _, UserOrganization, SessionLocal, _ = _models()
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    try:
        org_a = Organization(name=f"Scope Alpha {suffix}", slug=f"scope-alpha-{suffix}", is_active=True, plan="enterprise")
        org_b = Organization(name=f"Scope Bravo {suffix}", slug=f"scope-bravo-{suffix}", is_active=True, plan="enterprise")
        org_c = Organization(name=f"Scope Charlie {suffix}", slug=f"scope-charlie-{suffix}", is_active=True, plan="enterprise")
        db.add_all([org_a, org_b, org_c])
        db.commit()
        db.refresh(org_a)
        db.refresh(org_b)
        db.refresh(org_c)

        multi = _seed_user(db, username=f"multi_{suffix}", email=f"multi_{suffix}@example.com")
        single = _seed_user(db, username=f"single_{suffix}", email=f"single_{suffix}@example.com")
        superu = _seed_user(db, username=f"super_{suffix}", email=f"super_{suffix}@example.com", is_superuser=True)

        db.add_all([
            UserOrganization(user_id=multi.id, organization_id=org_a.id, role="user"),
            UserOrganization(user_id=multi.id, organization_id=org_b.id, role="user"),
            UserOrganization(user_id=single.id, organization_id=org_a.id, role="user"),
            UserOrganization(user_id=superu.id, organization_id=org_a.id, role="admin"),
        ])
        db.commit()

        # Pin the default org so header-fallback resolution is deterministic.
        multi.default_organization_id = org_a.id
        single.default_organization_id = org_a.id
        superu.default_organization_id = org_a.id
        db.commit()

        sess_a = _make_session(db, organization_id=org_a.id, user_id=multi.id, title="Alpha Standup")
        sess_b = _make_session(db, organization_id=org_b.id, user_id=multi.id, title="Bravo Retro")
        sess_c = _make_session(db, organization_id=org_c.id, user_id=single.id, title="Charlie Secret")

        ctx = {
            "org_a_id": org_a.id,
            "org_b_id": org_b.id,
            "org_c_id": org_c.id,
            "org_a_slug": org_a.slug,
            "org_b_slug": org_b.slug,
            "org_c_slug": org_c.slug,
            "sess_a_id": sess_a.session_id,
            "sess_b_id": sess_b.session_id,
            "sess_c_id": sess_c.session_id,
        }
    finally:
        db.close()

    ctx["multi_headers"] = _login_headers(client, f"multi_{suffix}")
    ctx["single_headers"] = _login_headers(client, f"single_{suffix}")
    ctx["super_headers"] = _login_headers(client, f"super_{suffix}")
    return ctx


def _listed_ids(client, headers: dict[str, str], params: dict[str, Any] | None = None) -> set[str]:
    response = client.get(
        "/api/simple/recording-sessions",
        params=params or {},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return {row["id"] for row in response.json()["items"]}


def test_include_all_my_orgs_unions_memberships_never_reaches_foreign_org(client, scope_world):
    """(1) A member of A + B with include_all_my_orgs=true sees A and B, never C."""
    ctx = scope_world
    headers = ctx["multi_headers"]

    # Baseline: default view is the active org (A) only - B is NOT included.
    baseline = _listed_ids(client, headers)
    assert ctx["sess_a_id"] in baseline
    assert ctx["sess_b_id"] not in baseline, (
        "Harness broken: default view already spans multiple orgs, so the "
        "include_all_my_orgs assertion below would prove nothing."
    )

    widened = _listed_ids(client, headers, {"include_all_my_orgs": "true"})
    assert ctx["sess_a_id"] in widened, "include_all_my_orgs lost the caller's own org A"
    assert ctx["sess_b_id"] in widened, "include_all_my_orgs did not add org B (a membership)"
    assert ctx["sess_c_id"] not in widened, (
        "Leak: include_all_my_orgs surfaced org C, which the caller is not a "
        "member of. The flag must be a union of the caller's memberships only."
    )


def test_all_tenants_ignored_for_non_superuser(client, scope_world):
    """(2) A non-superuser passing all_tenants=true gets exactly the no-flag view."""
    ctx = scope_world
    headers = ctx["multi_headers"]

    without = _listed_ids(client, headers)
    with_flag = _listed_ids(client, headers, {"all_tenants": "true"})

    assert with_flag == without, (
        "all_tenants=true changed a non-superuser's result. It must be silently "
        f"ignored. without={sorted(without)} with={sorted(with_flag)}"
    )
    # Belt-and-suspenders: the ignored flag must not have widened to a foreign
    # org (C) nor even to the caller's other membership (B), which the
    # active-org default view excludes.
    assert ctx["sess_c_id"] not in with_flag, "Leak: all_tenants widened a non-superuser to org C"
    assert ctx["sess_b_id"] not in with_flag, "all_tenants widened a non-superuser beyond the active org"


def test_all_tenants_superuser_sees_every_org(client, scope_world):
    """(3) A superuser with all_tenants=true sees every org's sessions."""
    ctx = scope_world
    headers = ctx["super_headers"]

    # Contrast: the superuser's default view is member-scoped (org A only), so
    # the god-view flag is what widens it, not superuser status by default.
    default_view = _listed_ids(client, headers)
    assert ctx["sess_a_id"] in default_view
    assert ctx["sess_c_id"] not in default_view, (
        "Superuser's default (no-flag) view already crosses into org C; the "
        "all_tenants assertion below would prove nothing."
    )

    god_view = _listed_ids(client, headers, {"all_tenants": "true"})
    assert ctx["sess_a_id"] in god_view
    assert ctx["sess_b_id"] in god_view
    assert ctx["sess_c_id"] in god_view, (
        "all_tenants=true did not surface org C to a superuser; the explicit "
        "cross-tenant god-view is broken."
    )


def test_org_header_not_a_member_falls_back_to_default_org(client, scope_world):
    """(4) X-MeetingOps-Org naming a non-member org falls back to the default."""
    ctx = scope_world
    headers = {**ctx["single_headers"], "X-MeetingOps-Org": ctx["org_c_slug"]}

    response = client.get("/api/simple/recording-sessions", headers=headers)
    assert response.status_code == 200, (
        f"Forged/foreign org header must fall back, not error. "
        f"status={response.status_code} body={response.text[:300]}"
    )
    ids = {row["id"] for row in response.json()["items"]}
    # Falls back to the caller's default org (A): their own session is visible.
    assert ctx["sess_a_id"] in ids, "Header fallback lost the caller's default org A"
    # Never widens: org C (the header target) and org B (not a membership) stay out.
    assert ctx["sess_c_id"] not in ids, (
        "Leak: X-MeetingOps-Org header widened scope into an org the caller is "
        "not a member of."
    )
    assert ctx["sess_b_id"] not in ids, "Header fallback widened beyond the default org"


def test_org_header_unknown_slug_falls_back_to_default_org(client, scope_world):
    """(4b) An X-MeetingOps-Org header naming a nonexistent org also falls back."""
    ctx = scope_world
    headers = {**ctx["single_headers"], "X-MeetingOps-Org": f"ghost-org-{uuid.uuid4().hex[:8]}"}

    response = client.get("/api/simple/recording-sessions", headers=headers)
    assert response.status_code == 200, (
        f"Unknown org slug must fall back to the default org, not 404. "
        f"status={response.status_code} body={response.text[:300]}"
    )
    ids = {row["id"] for row in response.json()["items"]}
    assert ctx["sess_a_id"] in ids
    assert ctx["sess_c_id"] not in ids
