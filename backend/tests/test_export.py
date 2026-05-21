"""Tests for export/download endpoints"""
import uuid

import pytest

from auth.utils import get_password_hash


def _admin_headers(client):
    """The conftest seeds an admin user; we use it for the simple legacy
    smoke tests below. These three tests were authored before auth was
    enforced on the POST /recording-sessions endpoint and silently failed
    with 401; logging in restores the original intent."""
    response = client.post(
        "/api/auth/login",
        data={"username": "admin", "password": "admin123"},
    )
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _create_session(client, name="Export Test Session"):
    """Helper to create a session and return its id."""
    response = client.post(
        "/api/simple/recording-sessions",
        json={"name": name, "description": "Session for export tests"},
        headers=_admin_headers(client),
    )
    assert response.status_code == 200, response.text
    return response.json()["id"]


def test_export_txt(client):
    """GET /download/transcript returns text content for an existing session."""
    session_id = _create_session(client)
    response = client.get(
        f"/api/simple/recording-sessions/{session_id}/download/transcript",
        headers=_admin_headers(client),
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    # The transcript should contain the session name
    assert "Export Test Session" in response.text


def test_export_transcript_simple(client):
    """GET /download/transcript/simple returns simple text for an existing session."""
    session_id = _create_session(client, name="Simple Export Session")
    response = client.get(
        f"/api/simple/recording-sessions/{session_id}/download/transcript/simple",
        headers=_admin_headers(client),
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "Simple Export Session" in response.text


def test_export_session_not_found(client):
    """GET /download/transcript returns 404 for a nonexistent session."""
    fake_id = str(uuid.uuid4())
    response = client.get(
        f"/api/simple/recording-sessions/{fake_id}/download/transcript",
        headers=_admin_headers(client),
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# /api/recording-sessions/{id}/export — meeting_management endpoint
#
# Regression coverage for two long-standing bugs (fixed 2026-05-20):
#   1. Markdown was missing from the Query() regex, so any caller asking for
#      ?format=md|markdown got an FastAPI-422 before the handler ran.
#   2. The handler filtered by ``RecordingSession.user_id`` which is legacy
#      pre-multi-org state; the canonical filter is ``organization_id``. The
#      result was 404 for every valid session on freshly-created data.
# ---------------------------------------------------------------------------


def _seed_org_and_user(suffix: str):
    """Create a fresh org + user + membership.

    Returns plain ints/strings (``org_id``, ``user_id``, ``username``) so the
    caller never touches detached ORM instances after the session closes —
    SQLAlchemy raises DetachedInstanceError on lazy-loaded attrs once a
    Session is closed, which is exactly what happens in this helper.
    """
    from auth.models import Organization, User, UserOrganization
    from database.database import SessionLocal

    db = SessionLocal()
    try:
        org = Organization(
            name=f"Export Org {suffix}",
            slug=f"export-{suffix}",
            is_active=True,
        )
        user = User(
            email=f"export_{suffix}@example.com",
            username=f"export_user_{suffix}",
            hashed_password=get_password_hash("Password123"),
            is_active=True,
            is_verified=True,
        )
        db.add_all([org, user])
        db.commit()
        db.refresh(org)
        db.refresh(user)
        db.add(UserOrganization(
            user_id=user.id, organization_id=org.id, role="user",
        ))
        db.commit()
        # Snapshot the values before the session closes — afterwards the
        # ORM instances are detached and attribute access raises.
        return {
            "org_id": org.id,
            "user_id": user.id,
            "username": user.username,
        }
    finally:
        db.close()


def _seed_session(*, organization_id: int, user_id: int, title: str):
    """Drop a populated RecordingSession into the DB and return its public
    ``session_id`` (UUID string) and integer PK."""
    from database.database import SessionLocal
    from database.models import RecordingSession

    db = SessionLocal()
    try:
        sess = RecordingSession(
            session_id=str(uuid.uuid4()),
            name=title,
            title=title,
            status="completed",
            organization_id=organization_id,
            user_id=user_id,
            transcript_simple=f"{title} transcript body.",
            transcript=f"{title} transcript body.",
            summary=f"{title} summary.",
            final_summary={
                "executive": f"{title} executive summary line.",
                "bullets": [f"{title} bullet one", f"{title} bullet two"],
                "actions": [{"action": f"{title} action item", "owner": "alice"}],
                "decisions": [f"{title} decision."],
            },
            duration=180.0,
        )
        db.add(sess)
        db.commit()
        db.refresh(sess)
        return {"public_id": sess.session_id, "db_id": sess.id}
    finally:
        db.close()


def _login_headers(client, username: str, password: str = "Password123") -> dict:
    response = client.post(
        "/api/auth/login",
        data={"username": username, "password": password},
    )
    assert response.status_code == 200, f"Login failed: {response.text}"
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture()
def two_orgs_with_sessions(client):
    """Seed org A + org B, one user + one session each. Return a dict with
    auth headers for org A and the public session_ids for both orgs."""
    suffix_a = uuid.uuid4().hex[:6]
    suffix_b = uuid.uuid4().hex[:6]
    a = _seed_org_and_user(suffix_a)
    b = _seed_org_and_user(suffix_b)
    sess_a = _seed_session(
        organization_id=a["org_id"], user_id=a["user_id"], title="Alpha Export Meeting",
    )
    sess_b = _seed_session(
        organization_id=b["org_id"], user_id=b["user_id"], title="Bravo Export Meeting",
    )
    return {
        "headers_a": _login_headers(client, a["username"]),
        "sess_a_id": sess_a["public_id"],
        "sess_b_id": sess_b["public_id"],
    }


@pytest.mark.parametrize("fmt", ["md", "markdown"])
def test_export_markdown_accepted(client, two_orgs_with_sessions, fmt):
    """GET /api/recording-sessions/{id}/export?format=md|markdown returns 200
    with text/markdown content. Pre-fix this 422'd at the Query() regex."""
    response = client.get(
        f"/api/recording-sessions/{two_orgs_with_sessions['sess_a_id']}/export",
        params={"format": fmt},
        headers=two_orgs_with_sessions["headers_a"],
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/markdown")
    body = response.text
    # Markdown rendering must surface the title + executive summary.
    assert "Alpha Export Meeting" in body
    assert "executive summary line" in body.lower()


def test_export_markdown_cross_org_returns_404(client, two_orgs_with_sessions):
    """Exporting org B's session as org A must 404 — not return org B's data."""
    response = client.get(
        f"/api/recording-sessions/{two_orgs_with_sessions['sess_b_id']}/export",
        params={"format": "markdown"},
        headers=two_orgs_with_sessions["headers_a"],
    )
    assert response.status_code == 404, (
        f"Leak: org A got status {response.status_code} for org B's session. "
        f"Body: {response.text[:300]}"
    )


@pytest.mark.parametrize("fmt,expected_ct", [
    ("txt", "text/plain"),
    ("json", "application/json"),
    ("srt", "text/plain"),
])
def test_export_other_formats_still_work(client, two_orgs_with_sessions, fmt, expected_ct):
    """Regression: txt/json/srt must keep working after the markdown +
    org-scoping rewrite."""
    response = client.get(
        f"/api/recording-sessions/{two_orgs_with_sessions['sess_a_id']}/export",
        params={"format": fmt},
        headers=two_orgs_with_sessions["headers_a"],
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith(expected_ct), (
        f"Format {fmt} returned content-type "
        f"{response.headers['content-type']!r}; expected {expected_ct!r}"
    )


def test_export_invalid_format_rejected(client, two_orgs_with_sessions):
    """Unknown formats (e.g. ?format=html) must 422 at the Query() regex."""
    response = client.get(
        f"/api/recording-sessions/{two_orgs_with_sessions['sess_a_id']}/export",
        params={"format": "html"},
        headers=two_orgs_with_sessions["headers_a"],
    )
    assert response.status_code == 422, (
        f"Expected 422 for unknown format, got {response.status_code}: {response.text}"
    )


def test_download_summary_md_includes_transcript_option(client, two_orgs_with_sessions):
    """Regression: ``ExportOptions(includeTranscript=...)`` used to silently
    drop the kwarg (pydantic v2 ignores unknown fields), then crash with
    AttributeError when ``export_to_markdown`` read it. Confirms the
    /download/summary/md path now resolves cleanly with both defaults and
    explicit include_transcript=true."""
    # Default (include_transcript=False) — must succeed.
    response = client.get(
        f"/api/simple/recording-sessions/{two_orgs_with_sessions['sess_a_id']}/download/summary/md",
        headers=two_orgs_with_sessions["headers_a"],
    )
    assert response.status_code == 200, response.text
    assert "Alpha Export Meeting" in response.text

    # Explicit include_transcript=true — must also succeed and include the
    # transcript body line ("Alpha Export Meeting transcript body.").
    response = client.get(
        f"/api/simple/recording-sessions/{two_orgs_with_sessions['sess_a_id']}/download/summary/md",
        params={"include_transcript": "true"},
        headers=two_orgs_with_sessions["headers_a"],
    )
    assert response.status_code == 200, response.text
    assert "Alpha Export Meeting transcript body." in response.text
