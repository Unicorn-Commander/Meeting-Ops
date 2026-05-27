"""v3.0.0 free-tier enforcement tests.

Free tier is browser-only: it must NOT be able to upload audio/text chunks,
trigger the canonical server reprocess, run server-side LLM summaries, or
bulk-import. Pro/Enterprise get the full server stack. Internal service
callers (room_recorder loopback) bypass tier gating entirely.

Two layers:
  1. Unit tests on the gate primitives in auth/tier.py — require_feature
     (dependency factory) + gate_feature_for_caller (inline, internal-caller
     -safe). These use real auth.models.User instances so the isinstance
     check in gate_feature_for_caller is genuinely exercised.
  2. Integration tests that POST to actual gated endpoints as a free vs pro
     user and assert 403 vs not-403, reusing the seeding pattern from
     test_audio_chunks_reprocess.py.
"""
from __future__ import annotations

import asyncio
import uuid as _uuid

import pytest
from fastapi import HTTPException

from auth.utils import get_password_hash


# ---------------------------------------------------------------------------
# Unit: TIER_FEATURES matrix
# ---------------------------------------------------------------------------

NEW_SERVER_FEATURES = [
    "canonical_reprocess",
    "brigade_integration",
    "cross_device_sync",
    "bulk_import",
]


def test_tier_features_matrix_for_new_keys():
    from auth.tier import TIER_FEATURES

    for feat in NEW_SERVER_FEATURES:
        assert TIER_FEATURES["free"][feat] is False, f"free should not have {feat}"
        assert TIER_FEATURES["pro"][feat] is True, f"pro should have {feat}"
        assert TIER_FEATURES["enterprise"][feat] is True, f"enterprise should have {feat}"


def _user(tier: str = "free", is_superuser: bool = False):
    """A real (unpersisted) User instance — enough for tier resolution and
    the isinstance(caller, User) check in gate_feature_for_caller."""
    from auth.models import User

    return User(
        email=f"{tier}@meeting-ops.local",
        username=f"{tier}-user",
        hashed_password="x",
        is_active=True,
        is_superuser=is_superuser,
        tier=tier,
    )


# ---------------------------------------------------------------------------
# Unit: require_feature (dependency factory)
# ---------------------------------------------------------------------------


def test_require_feature_403s_free_user():
    from auth.tier import require_feature

    checker = require_feature("canonical_reprocess")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(checker(current_user=_user("free")))
    assert exc.value.status_code == 403
    assert "canonical_reprocess" in exc.value.detail


def test_require_feature_passes_pro_and_enterprise():
    from auth.tier import require_feature

    checker = require_feature("canonical_reprocess")
    assert asyncio.run(checker(current_user=_user("pro"))).tier == "pro"
    assert asyncio.run(checker(current_user=_user("enterprise"))).tier == "enterprise"


def test_require_feature_superuser_passes():
    from auth.tier import require_feature

    checker = require_feature("canonical_reprocess")
    # is_superuser overrides to enterprise even with tier='free'.
    su = _user("free", is_superuser=True)
    assert asyncio.run(checker(current_user=su)) is su


def test_require_feature_unknown_feature_raises_at_definition():
    from auth.tier import require_feature

    with pytest.raises(ValueError):
        require_feature("does_not_exist")


# ---------------------------------------------------------------------------
# Unit: gate_feature_for_caller (inline, internal-caller-safe)
# ---------------------------------------------------------------------------


def test_gate_feature_for_caller_403s_free_user():
    from auth.tier import gate_feature_for_caller

    with pytest.raises(HTTPException) as exc:
        gate_feature_for_caller(_user("free"), "canonical_reprocess")
    assert exc.value.status_code == 403


def test_gate_feature_for_caller_allows_pro_user():
    from auth.tier import gate_feature_for_caller

    # Should not raise.
    gate_feature_for_caller(_user("pro"), "canonical_reprocess")


def test_gate_feature_for_caller_bypasses_internal_service_caller():
    """A non-User principal (internal loopback like room_recorder) is trusted
    infra and must bypass the tier gate, never 403."""
    from auth.tier import gate_feature_for_caller

    class _FakeInternalCaller:
        # No tier attribute on purpose — must not be treated as free.
        service = "room_recorder"

    # Should not raise even though feature is a paid one.
    gate_feature_for_caller(_FakeInternalCaller(), "canonical_reprocess")


def test_gate_feature_for_caller_unknown_feature_raises():
    from auth.tier import gate_feature_for_caller

    with pytest.raises(ValueError):
        gate_feature_for_caller(_user("pro"), "nope_not_real")


# ---------------------------------------------------------------------------
# Integration: real gated endpoints, free vs pro
# ---------------------------------------------------------------------------


def _models():
    from auth.models import Organization, User, UserOrganization
    from database.database import SessionLocal
    from database.models import RecordingSession
    return Organization, User, UserOrganization, SessionLocal, RecordingSession


def _login_headers(client, username, password, org_slug=None):
    resp = client.post("/api/auth/login", data={"username": username, "password": password})
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    if org_slug:
        headers["X-MeetingOps-Org"] = org_slug
    return headers


def _seed_user_and_org(slug, username, tier):
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
                email=f"{username}@meeting-ops.local",
                username=username,
                hashed_password=get_password_hash("admin123"),
                is_active=True, is_verified=True, is_superuser=False,
            )
            db.add(user); db.commit(); db.refresh(user)
        user.tier = tier
        db.commit()
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


def _create_always_on_session(org_id, user_id):
    _, _, _, SessionLocal, RecordingSession = _models()
    db = SessionLocal()
    try:
        sid = str(_uuid.uuid4())
        s = RecordingSession(
            session_id=sid, name=f"tiergate-{sid[:8]}", title=f"tiergate-{sid[:8]}",
            meeting_type="always_on", mode="always_on", status="recording",
            duration=0.0, user_id=user_id, organization_id=org_id,
            source_type="browser_always_on", processing_metadata={"created_by": "test"},
        )
        db.add(s); db.commit(); db.refresh(s)
        return s.id, s.session_id
    finally:
        db.close()


def test_free_tier_blocked_from_audio_chunks(client, tmp_path, monkeypatch):
    from api import recording
    monkeypatch.setattr(recording, "RECORDINGS_DIR", tmp_path)
    monkeypatch.setattr(recording, "ALWAYS_ON_DIR", tmp_path / "always_on")

    org_id, org_slug, user_id = _seed_user_and_org("tiergate-free", "tiergate_free", "free")
    headers = _login_headers(client, "tiergate_free", "admin123", org_slug)
    _, session_id = _create_always_on_session(org_id, user_id)

    resp = client.post(
        f"/api/recordings/sessions/{session_id}/audio-chunks",
        headers=headers,
        files={"chunk": ("c0.webm", b"\x1a\x45\xdf\xa3" + b"\x00" * 32, "audio/webm")},
        data={"chunk_index": "0"},
    )
    assert resp.status_code == 403, resp.text
    assert "canonical_reprocess" in resp.text


def test_free_tier_blocked_from_finalize_audio(client, tmp_path, monkeypatch):
    from api import recording
    monkeypatch.setattr(recording, "RECORDINGS_DIR", tmp_path)
    monkeypatch.setattr(recording, "ALWAYS_ON_DIR", tmp_path / "always_on")

    org_id, org_slug, user_id = _seed_user_and_org("tiergate-free2", "tiergate_free2", "free")
    headers = _login_headers(client, "tiergate_free2", "admin123", org_slug)
    _, session_id = _create_always_on_session(org_id, user_id)

    # No body: `verification` defaults to None (the realistic free-client
    # call). Sending json={} would 422 on the verification schema before the
    # inline gate runs; we want to exercise the gate, so send no body.
    resp = client.post(
        f"/api/recordings/sessions/{session_id}/finalize-audio", headers=headers
    )
    assert resp.status_code == 403, resp.text


def test_pro_tier_allowed_through_audio_chunks_gate(client, tmp_path, monkeypatch):
    """A pro user passes the tier gate. We assert it's NOT a 403 — the
    endpoint proceeds (200 on a valid chunk write)."""
    from api import recording
    monkeypatch.setattr(recording, "RECORDINGS_DIR", tmp_path)
    monkeypatch.setattr(recording, "ALWAYS_ON_DIR", tmp_path / "always_on")

    org_id, org_slug, user_id = _seed_user_and_org("tiergate-pro", "tiergate_pro", "pro")
    headers = _login_headers(client, "tiergate_pro", "admin123", org_slug)
    _, session_id = _create_always_on_session(org_id, user_id)

    resp = client.post(
        f"/api/recordings/sessions/{session_id}/audio-chunks",
        headers=headers,
        files={"chunk": ("c0.webm", b"\x1a\x45\xdf\xa3" + b"\x00" * 32, "audio/webm")},
        data={"chunk_index": "0"},
    )
    assert resp.status_code != 403, resp.text
    assert resp.status_code == 200, resp.text


def test_free_tier_blocked_from_bulk_import(client):
    org_id, org_slug, user_id = _seed_user_and_org("tiergate-bulk", "tiergate_bulk", "free")
    headers = _login_headers(client, "tiergate_bulk", "admin123", org_slug)
    resp = client.post("/api/import/jobs", headers=headers)
    assert resp.status_code == 403, resp.text
    assert "bulk_import" in resp.text
