"""Tests for the additional_recipients (free-form external email) feature
on POST /api/simple/recording-sessions/{id}/email-attendees.

These pin the contract that Aaron asked for: "Can I email this and a link to
people not named as attending this meeting?"

Coverage:
  - Sending with ONLY additional_recipients (no speaker_ids) creates a
    SessionCollaborator row per email + a magic-link token + drives one
    _postmark_send call per address.
  - Combined speaker_ids + additional_recipients sends to both groups (no
    dedupe collisions).
  - Invalid email address in additional_recipients -> 422 from pydantic.
  - Empty speaker_ids + empty additional_recipients on a session with no
    participants -> 400 (no-recipients error).
  - Cross-org safety: the magic-link token grants access to ONLY the one
    session it was minted for. A token from session A in org-A resolves
    to session A and nothing else. The token in org A cannot return data
    from a session in org B.
"""
from __future__ import annotations

import os
import uuid
from typing import Any
from unittest.mock import patch

import pytest

from auth.utils import get_password_hash


def _models():
    from auth.models import Organization, User, UserOrganization
    from database.database import SessionLocal
    from database.models import RecordingSession, SessionCollaborator

    return Organization, User, UserOrganization, SessionLocal, RecordingSession, SessionCollaborator


def _seed_user(db, username: str, password: str, email: str, *, is_superuser: bool = False):
    _, User, _, _, _, _ = _models()
    user = User(
        email=email,
        username=username,
        hashed_password=get_password_hash(password),
        is_active=True,
        is_verified=True,
        is_superuser=is_superuser,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _login(client, username: str, password: str) -> dict[str, str]:
    response = client.post(
        "/api/auth/login",
        data={"username": username, "password": password},
    )
    assert response.status_code == 200, f"Login failed: {response.text}"
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _make_session(db, *, organization_id: int, user_id: int, title: str):
    _, _, _, _, RecordingSession, _ = _models()
    sess = RecordingSession(
        session_id=str(uuid.uuid4()),
        name=title,
        title=title,
        status="completed",
        organization_id=organization_id,
        user_id=user_id,
        transcript_simple="hello world",
        transcript="hello world",
        summary="short summary",
        final_summary={"executive": "short summary"},
        duration=60.0,
        participants=[],
    )
    db.add(sess)
    db.commit()
    db.refresh(sess)
    return sess


@pytest.fixture()
def two_orgs_email(client):
    """Two orgs with one session each + a superuser caller in org A.

    Returns headers + DB ids for the two sessions so cross-org safety
    checks can drive the resolve-access-token endpoint with the right
    inputs.
    """
    Organization, _, UserOrganization, SessionLocal, _, _ = _models()
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:6]

    try:
        org_a = Organization(name=f"Org Alpha {suffix}", slug=f"alpha-{suffix}", is_active=True)
        org_b = Organization(name=f"Org Bravo {suffix}", slug=f"bravo-{suffix}", is_active=True)
        db.add_all([org_a, org_b])
        db.commit()
        db.refresh(org_a)
        db.refresh(org_b)

        # Superuser caller — bypasses the admin/manager/session-creator gate
        # so we can focus on the additional_recipients contract here.
        caller = _seed_user(
            db,
            f"caller_{suffix}",
            "Password123",
            f"caller_{suffix}@example.com",
            is_superuser=True,
        )
        # Make the caller a member of org A so the X-MeetingOps-Org header
        # resolves cleanly.
        db.add(UserOrganization(user_id=caller.id, organization_id=org_a.id, role="admin"))
        db.commit()

        sess_a = _make_session(db, organization_id=org_a.id, user_id=caller.id, title="Alpha planning")
        sess_b = _make_session(db, organization_id=org_b.id, user_id=caller.id, title="Bravo deepdive")

        ctx = {
            "org_a_slug": org_a.slug,
            "org_b_slug": org_b.slug,
            "sess_a_public_id": sess_a.session_id,
            "sess_a_db_id": sess_a.id,
            "sess_b_public_id": sess_b.session_id,
            "sess_b_db_id": sess_b.id,
            "caller_username": caller.username,
        }
    finally:
        db.close()

    ctx["headers"] = _login(client, ctx["caller_username"], "Password123")
    ctx["headers"]["X-MeetingOps-Org"] = ctx["org_a_slug"]
    return ctx


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_external_only_recipients_send(client, two_orgs_email):
    """No speaker_ids + non-empty additional_recipients should succeed and
    drive one Postmark send per external address.
    """
    sends: list[dict[str, Any]] = []

    def fake_postmark(**kwargs):
        sends.append(kwargs)
        return {"ok": True, "message_id": "stub"}

    with patch("api.session_emails._postmark_send", side_effect=fake_postmark):
        res = client.post(
            f"/api/simple/recording-sessions/{two_orgs_email['sess_a_public_id']}/email-attendees",
            json={
                "additional_recipients": ["alice@example.com", "bob@example.com"],
                "include": ["link"],
            },
            headers=two_orgs_email["headers"],
        )

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["sent"] == 2
    assert body["skipped"] == 0
    assert body["failures"] == []
    sent_to = sorted(s["to_email"] for s in sends)
    assert sent_to == ["alice@example.com", "bob@example.com"]

    # Each external address minted a SessionCollaborator row scoped to this
    # session only.
    _, _, _, SessionLocal, _, SessionCollaborator = _models()
    db = SessionLocal()
    try:
        rows = (
            db.query(SessionCollaborator)
            .filter(SessionCollaborator.session_id == two_orgs_email["sess_a_db_id"])
            .all()
        )
        emails = sorted(r.email for r in rows)
        assert emails == ["alice@example.com", "bob@example.com"]
        for r in rows:
            assert r.token is not None
            assert r.access_level == "read"
    finally:
        db.close()


def test_combined_speakers_and_externals(client, two_orgs_email):
    """speaker_ids + additional_recipients should fan out to both groups.

    Speakers without a stored email get skipped (no email on file) but the
    external addresses still go out.
    """
    # Seed a speaker without an email so the speaker-fanout has something
    # legitimate to skip on (we don't want a hard 404 here).
    from database.database import SessionLocal
    from database.models import SpeakerProfile

    db = SessionLocal()
    try:
        # Pull the org_a id from the session row to associate the speaker
        # with the same organization that the caller is operating in.
        from database.models import RecordingSession

        sess = db.query(RecordingSession).filter(
            RecordingSession.session_id == two_orgs_email["sess_a_public_id"]
        ).one()
        speaker = SpeakerProfile(
            display_name="No-email Speaker",
            email=None,
            organization_id=sess.organization_id,
        )
        db.add(speaker)
        db.commit()
        db.refresh(speaker)
        speaker_id = speaker.id
    finally:
        db.close()

    sends: list[dict[str, Any]] = []

    def fake_postmark(**kwargs):
        sends.append(kwargs)
        return {"ok": True, "message_id": "stub"}

    with patch("api.session_emails._postmark_send", side_effect=fake_postmark):
        res = client.post(
            f"/api/simple/recording-sessions/{two_orgs_email['sess_a_public_id']}/email-attendees",
            json={
                "speaker_ids": [speaker_id],
                "additional_recipients": ["charlie@example.com"],
                "include": ["link"],
            },
            headers=two_orgs_email["headers"],
        )

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["sent"] == 1  # only charlie
    assert body["skipped"] == 1  # the no-email speaker
    assert any(f.get("speaker_id") == speaker_id for f in body["failures"])
    assert [s["to_email"] for s in sends] == ["charlie@example.com"]


def test_invalid_email_returns_422(client, two_orgs_email):
    """pydantic EmailStr catches obvious garbage before we hit the handler."""
    res = client.post(
        f"/api/simple/recording-sessions/{two_orgs_email['sess_a_public_id']}/email-attendees",
        json={
            "additional_recipients": ["not-an-email"],
            "include": ["link"],
        },
        headers=two_orgs_email["headers"],
    )
    assert res.status_code == 422, res.text


def test_no_recipients_at_all_returns_400(client, two_orgs_email):
    """Empty speaker_ids + empty additional_recipients on a session with no
    participants should refuse cleanly with a 400."""
    res = client.post(
        f"/api/simple/recording-sessions/{two_orgs_email['sess_a_public_id']}/email-attendees",
        json={
            "additional_recipients": [],
            "include": ["link"],
        },
        headers=two_orgs_email["headers"],
    )
    assert res.status_code == 400, res.text
    assert "no recipients" in res.json()["detail"].lower()


def test_external_token_only_grants_one_session(client, two_orgs_email):
    """The magic-link token an external recipient receives must resolve to
    EXACTLY the one session it was minted for, regardless of org. A token
    minted for session A in org A cannot be used to view session B in
    org B."""
    sends: list[dict[str, Any]] = []

    def fake_postmark(**kwargs):
        sends.append(kwargs)
        return {"ok": True, "message_id": "stub"}

    with patch("api.session_emails._postmark_send", side_effect=fake_postmark):
        res = client.post(
            f"/api/simple/recording-sessions/{two_orgs_email['sess_a_public_id']}/email-attendees",
            json={
                "additional_recipients": ["external@example.com"],
                "include": ["link"],
            },
            headers=two_orgs_email["headers"],
        )
    assert res.status_code == 200, res.text

    # Pull the freshly-minted token out of the database.
    _, _, _, SessionLocal, _, SessionCollaborator = _models()
    db = SessionLocal()
    try:
        row = (
            db.query(SessionCollaborator)
            .filter(
                SessionCollaborator.session_id == two_orgs_email["sess_a_db_id"],
                SessionCollaborator.email == "external@example.com",
            )
            .one()
        )
        token = str(row.token)
    finally:
        db.close()

    # The token resolves — but ONLY to session A. We hit the public
    # resolve endpoint (no auth) and check the bound session_id matches A
    # and is NOT session B.
    resolve = client.get(
        f"/api/simple/recording-sessions/permissions/access?token={token}"
    )
    assert resolve.status_code == 200, resolve.text
    body = resolve.json()
    assert body["valid"] is True
    assert body["session_db_id"] == two_orgs_email["sess_a_db_id"]
    assert body["session_db_id"] != two_orgs_email["sess_b_db_id"]
    # session_id is the public string id and must match A's, not B's
    assert body["session_id"] == two_orgs_email["sess_a_public_id"]
    assert body["session_id"] != two_orgs_email["sess_b_public_id"]
