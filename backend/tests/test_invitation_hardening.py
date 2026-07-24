"""Behavior-level coverage for hashed, manager-only meeting invitations."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import pytest

from auth.utils import get_password_hash


def _models():
    from auth.models import Organization, User, UserOrganization
    from database.database import SessionLocal
    from database.models import RecordingSession, SessionCollaborator

    return (
        Organization,
        User,
        UserOrganization,
        SessionLocal,
        RecordingSession,
        SessionCollaborator,
    )


@pytest.fixture()
def invitation_world(client):
    (
        Organization,
        User,
        UserOrganization,
        SessionLocal,
        RecordingSession,
        SessionCollaborator,
    ) = _models()
    suffix = uuid.uuid4().hex[:8]
    db = SessionLocal()
    try:
        host_org = Organization(
            name=f"Invite Host {suffix}",
            slug=f"invite-host-{suffix}",
            is_active=True,
        )
        outside_org = Organization(
            name=f"Invite Outside {suffix}",
            slug=f"invite-outside-{suffix}",
            is_active=True,
        )
        creator = User(
            email=f"invite-creator-{suffix}@example.com",
            username=f"invite_creator_{suffix}",
            hashed_password=get_password_hash("admin123"),
            is_active=True,
            is_verified=True,
            tier="pro",
        )
        viewer = User(
            email=f"invite-viewer-{suffix}@example.com",
            username=f"invite_viewer_{suffix}",
            hashed_password=get_password_hash("admin123"),
            is_active=True,
            is_verified=True,
            tier="pro",
        )
        commenter = User(
            email=f"invite-commenter-{suffix}@example.com",
            username=f"invite_commenter_{suffix}",
            hashed_password=get_password_hash("admin123"),
            is_active=True,
            is_verified=True,
            tier="pro",
        )
        db.add_all([host_org, outside_org, creator, viewer, commenter])
        db.flush()
        db.add_all(
            [
                UserOrganization(
                    user_id=creator.id,
                    organization_id=host_org.id,
                    role="admin",
                ),
                UserOrganization(
                    user_id=viewer.id,
                    organization_id=host_org.id,
                    role="viewer",
                ),
                UserOrganization(
                    user_id=commenter.id,
                    organization_id=outside_org.id,
                    role="viewer",
                ),
            ]
        )
        meeting = RecordingSession(
            session_id=f"invite-session-{suffix}",
            title="Invitation hardening",
            status="completed",
            user_id=creator.id,
            organization_id=host_org.id,
        )
        db.add(meeting)
        db.flush()
        commenter_grant = SessionCollaborator(
            session_id=meeting.id,
            user_id=commenter.id,
            email=commenter.email,
            access_level="comment",
            invited_by_user_id=creator.id,
            token=uuid.uuid4(),
            token_hash=None,
            token_version=2,
            accepted_at=datetime.now(timezone.utc),
            delivery_state="accepted",
        )
        db.add(commenter_grant)
        db.commit()
        context = {
            "host_slug": host_org.slug,
            "outside_slug": outside_org.slug,
            "creator_username": creator.username,
            "viewer_username": viewer.username,
            "commenter_username": commenter.username,
            "commenter_id": commenter.id,
            "commenter_grant_id": commenter_grant.id,
            "meeting_key": meeting.session_id,
            "meeting_id": meeting.id,
            "external_email": f"invite-external-{suffix}@example.com",
        }
    finally:
        db.close()

    def login(username: str, slug: str) -> dict[str, str]:
        response = client.post(
            "/api/auth/login",
            data={"username": username, "password": "admin123"},
        )
        assert response.status_code == 200, response.text
        return {
            "Authorization": f"Bearer {response.json()['access_token']}",
            "X-MeetingOps-Org": slug,
        }

    context["creator_headers"] = login(
        context["creator_username"],
        context["host_slug"],
    )
    context["viewer_headers"] = login(
        context["viewer_username"],
        context["host_slug"],
    )
    context["commenter_headers"] = login(
        context["commenter_username"],
        context["outside_slug"],
    )
    return context


def _secret_from_url(url: str) -> str:
    fragment = parse_qs(urlsplit(url).fragment)
    assert fragment.get("token")
    return fragment["token"][0]


def _all_keys(value):
    if isinstance(value, dict):
        for key, nested in value.items():
            yield key
            yield from _all_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _all_keys(nested)


def _create_external_invitation(client, world, delivery_result):
    with patch(
        "api.session_permissions._send_invitation_email",
        return_value=delivery_result,
    ) as sender:
        response = client.post(
            (
                f"/api/simple/recording-sessions/{world['meeting_key']}"
                "/permissions/collaborators"
            ),
            headers=world["creator_headers"],
            json={
                "email": world["external_email"],
                "access_level": "read",
            },
        )
    assert response.status_code == 200, response.text
    return response, sender


def test_secret_is_copy_once_hashed_and_a_leaked_row_cannot_redeem(
    client,
    invitation_world,
):
    from api.session_permissions import InvitationDeliveryResult
    from services.invitation_tokens import hash_invitation_secret

    response, sender = _create_external_invitation(
        client,
        invitation_world,
        InvitationDeliveryResult(sent=True),
    )
    body = response.json()
    assert body["created"] is True
    assert body["delivered"] is True
    assert body["invite_url_once"]
    assert "/invite-bootstrap.html#token=" in body["invite_url_once"]
    assert "?token=" not in body["invite_url_once"]
    secret = _secret_from_url(body["invite_url_once"])
    assert sender.call_count == 1

    _, _, _, SessionLocal, _, SessionCollaborator = _models()
    db = SessionLocal()
    try:
        row = (
            db.query(SessionCollaborator)
            .filter(
                SessionCollaborator.session_id == invitation_world["meeting_id"],
                SessionCollaborator.email == invitation_world["external_email"],
            )
            .one()
        )
        assert row.token is not None
        compatibility_uuid = str(row.token)
        assert row.token_hash == hash_invitation_secret(secret)
        assert secret not in row.token_hash
        leaked_hash = row.token_hash
    finally:
        db.close()

    valid = client.post(
        "/api/simple/recording-sessions/permissions/access",
        json={"token": secret},
    )
    assert valid.status_code == 200
    assert valid.json()["valid"] is True
    assert valid.json()["session_db_id"] == invitation_world["meeting_id"]

    leaked = client.post(
        "/api/simple/recording-sessions/permissions/access",
        json={"token": leaked_hash},
    )
    assert leaked.status_code == 200
    assert leaked.json()["valid"] is False
    leaked_compatibility = client.post(
        "/api/simple/recording-sessions/permissions/access",
        json={"token": compatibility_uuid},
    )
    assert leaked_compatibility.status_code == 200
    assert leaked_compatibility.json()["valid"] is False

    listed = client.get(
        (
            f"/api/simple/recording-sessions/{invitation_world['meeting_key']}"
            "/permissions"
        ),
        headers=invitation_world["creator_headers"],
    )
    assert listed.status_code == 200, listed.text
    keys = set(_all_keys(listed.json()))
    assert {"token", "token_hash", "invite_url", "invite_url_once"}.isdisjoint(keys)
    assert secret not in listed.text
    assert leaked_hash not in listed.text

    # Repeating POST updates the existing grant but neither sends nor reveals
    # a fresh secret.
    duplicate, duplicate_sender = _create_external_invitation(
        client,
        invitation_world,
        InvitationDeliveryResult(sent=True),
    )
    assert duplicate.json()["created"] is False
    assert duplicate.json()["invite_url_once"] is None
    assert duplicate_sender.call_count == 0
    db = SessionLocal()
    try:
        assert (
            db.query(SessionCollaborator)
            .filter(
                SessionCollaborator.session_id == invitation_world["meeting_id"],
                SessionCollaborator.email == invitation_world["external_email"],
            )
            .count()
            == 1
        )
    finally:
        db.close()


@pytest.mark.parametrize("actor", ["viewer", "commenter"])
def test_read_and_comment_collaborators_cannot_manage_or_inspect_roster(
    client,
    invitation_world,
    actor,
):
    from api.session_permissions import InvitationDeliveryResult

    created, _ = _create_external_invitation(
        client,
        invitation_world,
        InvitationDeliveryResult(sent=True),
    )
    collaborator_id = created.json()["id"]
    headers = invitation_world[f"{actor}_headers"]
    base = (
        f"/api/simple/recording-sessions/{invitation_world['meeting_key']}"
        "/permissions"
    )

    requests = [
        client.get(base, headers=headers),
        client.post(
            f"{base}/collaborators",
            headers=headers,
            json={"email": "other-private@example.com", "access_level": "read"},
        ),
        client.patch(
            f"{base}/collaborators/{collaborator_id}",
            headers=headers,
            json={"access_level": "edit"},
        ),
        client.post(
            f"{base}/collaborators/{collaborator_id}/resend",
            headers=headers,
        ),
        client.delete(
            f"{base}/collaborators/{collaborator_id}",
            headers=headers,
        ),
    ]
    assert [response.status_code for response in requests] == [403] * 5
    for response in requests:
        assert invitation_world["external_email"] not in response.text
        assert "token_hash" not in response.text
        assert "provider" not in response.text.lower()

    # Both actors may read the meeting itself, but that payload does not carry
    # the private invitation roster.
    meeting = client.get(
        f"/api/simple/recording-sessions/{invitation_world['meeting_key']}",
        headers=headers,
    )
    assert meeting.status_code == 200, meeting.text
    assert invitation_world["external_email"] not in meeting.text


def test_resend_rotates_once_is_rate_limited_and_never_duplicates_grant(
    client,
    invitation_world,
):
    from api.session_permissions import InvitationDeliveryResult

    created, _ = _create_external_invitation(
        client,
        invitation_world,
        InvitationDeliveryResult(
            sent=False,
            failure_reason="delivery_failed",
        ),
    )
    old_secret = _secret_from_url(created.json()["invite_url_once"])
    collaborator_id = created.json()["id"]

    _, _, _, SessionLocal, _, SessionCollaborator = _models()
    db = SessionLocal()
    try:
        row = db.query(SessionCollaborator).filter(
            SessionCollaborator.id == collaborator_id
        ).one()
        assert row.delivery_state == "failed"
        assert row.delivery_attempt_count == 1
        row.last_delivery_attempt_at = (
            datetime.now(timezone.utc) - timedelta(minutes=2)
        )
        db.commit()
    finally:
        db.close()

    with patch(
        "api.session_permissions._send_invitation_email",
        return_value=InvitationDeliveryResult(
            sent=False,
            failure_reason="delivery_failed",
        ),
    ) as sender:
        resent = client.post(
            (
                f"/api/simple/recording-sessions/{invitation_world['meeting_key']}"
                f"/permissions/collaborators/{collaborator_id}/resend"
            ),
            headers=invitation_world["creator_headers"],
        )
        repeated = client.post(
            (
                f"/api/simple/recording-sessions/{invitation_world['meeting_key']}"
                f"/permissions/collaborators/{collaborator_id}/resend"
            ),
            headers=invitation_world["creator_headers"],
        )
    assert resent.status_code == 200, resent.text
    assert resent.json()["delivered"] is False
    new_secret = _secret_from_url(resent.json()["invite_url_once"])
    assert new_secret != old_secret
    assert repeated.status_code == 429
    assert int(repeated.headers["Retry-After"]) >= 1
    assert sender.call_count == 1

    old = client.post(
        "/api/simple/recording-sessions/permissions/access",
        json={"token": old_secret},
    )
    new = client.post(
        "/api/simple/recording-sessions/permissions/access",
        json={"token": new_secret},
    )
    assert old.json()["valid"] is False
    assert new.json()["valid"] is True

    db = SessionLocal()
    try:
        rows = (
            db.query(SessionCollaborator)
            .filter(
                SessionCollaborator.session_id == invitation_world["meeting_id"],
                SessionCollaborator.email == invitation_world["external_email"],
            )
            .all()
        )
        assert len(rows) == 1
        assert rows[0].delivery_attempt_count == 2
        assert rows[0].delivery_state == "failed"
        assert rows[0].delivery_failure_reason == "delivery_failed"
    finally:
        db.close()


def test_revocation_is_immediate_and_preserves_unrelated_membership(
    client,
    invitation_world,
):
    before = client.get(
        f"/api/simple/recording-sessions/{invitation_world['meeting_key']}",
        headers=invitation_world["commenter_headers"],
    )
    assert before.status_code == 200, before.text

    revoked = client.delete(
        (
            f"/api/simple/recording-sessions/{invitation_world['meeting_key']}"
            "/permissions/collaborators/"
            f"{invitation_world['commenter_grant_id']}"
        ),
        headers=invitation_world["creator_headers"],
    )
    assert revoked.status_code == 200, revoked.text

    after = client.get(
        f"/api/simple/recording-sessions/{invitation_world['meeting_key']}",
        headers=invitation_world["commenter_headers"],
    )
    assert after.status_code == 404

    _, _, UserOrganization, SessionLocal, _, SessionCollaborator = _models()
    db = SessionLocal()
    try:
        grant = db.query(SessionCollaborator).filter(
            SessionCollaborator.id == invitation_world["commenter_grant_id"]
        ).one()
        assert grant.revoked_at is not None
        assert grant.delivery_state == "revoked"
        assert grant.token is not None
        assert (
            db.query(UserOrganization)
            .filter(UserOrganization.user_id == invitation_world["commenter_id"])
            .count()
            == 1
        )
    finally:
        db.close()


def test_migrated_legacy_hash_survives_plaintext_scrub_until_cutoff(
    client,
    invitation_world,
    monkeypatch,
):
    from services.invitation_tokens import hash_invitation_secret

    legacy_secret = str(uuid.uuid4())
    _, _, _, SessionLocal, _, SessionCollaborator = _models()
    db = SessionLocal()
    try:
        row = SessionCollaborator(
            session_id=invitation_world["meeting_id"],
            email=f"legacy-{uuid.uuid4().hex[:6]}@example.com",
            access_level="read",
            token=uuid.UUID(legacy_secret),
            token_hash=hash_invitation_secret(legacy_secret),
            token_version=1,
            delivery_state="sent",
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        legacy_row_id = row.id
    finally:
        db.close()

    during_transition = client.post(
        "/api/simple/recording-sessions/permissions/access",
        json={"token": legacy_secret},
    )
    assert during_transition.status_code == 200
    assert during_transition.json()["valid"] is True

    # This mirrors the separately approved SQL scrub: only the legacy
    # plaintext column is cleared. The v1 UUID still resolves through its
    # digest while the bounded legacy transport window remains open.
    db = SessionLocal()
    try:
        row = db.query(SessionCollaborator).filter(
            SessionCollaborator.id == legacy_row_id
        ).one()
        row.token = None
        db.commit()
    finally:
        db.close()
    after_plaintext_scrub = client.post(
        "/api/simple/recording-sessions/permissions/access",
        json={"token": legacy_secret},
    )
    assert after_plaintext_scrub.status_code == 200
    assert after_plaintext_scrub.json()["valid"] is True

    monkeypatch.setenv(
        "MEETING_INVITE_LEGACY_TOKEN_CUTOFF",
        "2020-01-01T00:00:00Z",
    )
    after_cutoff = client.post(
        "/api/simple/recording-sessions/permissions/access",
        json={"token": legacy_secret},
    )
    assert after_cutoff.status_code == 200
    assert after_cutoff.json()["valid"] is False


def test_redeem_fails_closed_when_an_email_bound_account_has_no_email(
    client,
    invitation_world,
):
    """An empty account email must not bypass an email-bound invitation."""
    from api.session_permissions import InvitationDeliveryResult

    created, _ = _create_external_invitation(
        client,
        invitation_world,
        InvitationDeliveryResult(sent=True),
    )
    secret = _secret_from_url(created.json()["invite_url_once"])
    collaborator_id = created.json()["id"]

    _, User, _, SessionLocal, _, SessionCollaborator = _models()
    db = SessionLocal()
    try:
        user = db.query(User).filter(
            User.id == invitation_world["commenter_id"]
        ).one()
        user.email = ""
        db.commit()
    finally:
        db.close()

    redeemed = client.post(
        "/api/simple/recording-sessions/permissions/redeem",
        headers=invitation_world["commenter_headers"],
        json={"token": secret},
    )
    assert redeemed.status_code == 200, redeemed.text
    assert redeemed.json()["valid"] is False
    assert redeemed.json()["reason"] == (
        "this invitation was sent to a different email address"
    )

    db = SessionLocal()
    try:
        row = db.query(SessionCollaborator).filter(
            SessionCollaborator.id == collaborator_id
        ).one()
        assert row.user_id is None
        assert row.accepted_at is None
    finally:
        db.close()


@pytest.mark.parametrize(
    ("terminal_state", "expected_reason"),
    [
        ("invalid", "invitation not found"),
        ("expired", "expired"),
        ("revoked", "revoked"),
    ],
)
def test_terminal_invitation_states_are_controlled_and_secret_free(
    client,
    invitation_world,
    terminal_state,
    expected_reason,
):
    """Bearer holders get a safe terminal state; API errors never echo it."""
    from services.invitation_tokens import (
        generate_invitation_secret,
        hash_invitation_secret,
    )

    secret = generate_invitation_secret()
    collaborator_id = None
    if terminal_state != "invalid":
        _, _, _, SessionLocal, _, SessionCollaborator = _models()
        db = SessionLocal()
        try:
            row = SessionCollaborator(
                session_id=invitation_world["meeting_id"],
                email=f"terminal-{uuid.uuid4().hex[:8]}@example.com",
                access_level="read",
                token=uuid.uuid4(),
                token_hash=hash_invitation_secret(secret),
                token_version=2,
                delivery_state="sent",
                expires_at=(
                    datetime.now(timezone.utc) - timedelta(minutes=1)
                    if terminal_state == "expired"
                    else None
                ),
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            collaborator_id = row.id
        finally:
            db.close()

    if terminal_state == "revoked":
        revoked = client.delete(
            (
                f"/api/simple/recording-sessions/{invitation_world['meeting_key']}"
                f"/permissions/collaborators/{collaborator_id}"
            ),
            headers=invitation_world["creator_headers"],
        )
        assert revoked.status_code == 200, revoked.text

    response = client.post(
        "/api/simple/recording-sessions/permissions/access",
        json={"token": secret},
    )
    assert response.status_code == 200
    assert response.json()["valid"] is False
    assert response.json()["reason"] == expected_reason
    assert secret not in response.text
    assert "token_hash" not in response.text


def test_secret_in_a_query_string_is_not_an_invitation_api_contract(
    client,
    invitation_world,
):
    """The public resolver accepts only a JSON body, never a request URL."""
    from services.invitation_tokens import generate_invitation_secret

    secret = generate_invitation_secret()
    response = client.get(
        "/api/simple/recording-sessions/permissions/access",
        params={"token": secret},
    )
    assert response.status_code in {404, 405}
    assert secret not in response.text


def test_native_oidc_return_path_rejects_open_redirect_targets():
    """The bootstrap's fixed native return path cannot be widened by input."""
    from auth.oidc_sso import _safe_return_to

    assert _safe_return_to("/shared/sessions") == "/shared/sessions"
    assert _safe_return_to("https://attacker.example/invite") == "/"
    assert _safe_return_to("//attacker.example/invite") == "/"
    assert _safe_return_to(None) == "/"
