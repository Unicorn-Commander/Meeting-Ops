"""Tests for the full-session audio capture + server-side reprocess pipeline.

Covers the endpoints landed alongside the live-summary fix:
  * POST /api/recordings/sessions/{id}/audio-chunks — accepts, persists to
    disk, records arrival metadata under processing_metadata.full_audio.
  * POST /api/recordings/sessions/{id}/audio-chunks — idempotent on
    chunk_index (re-upload overwrites without duplicating state).
  * POST /api/recordings/sessions/{id}/finalize-audio — when no chunks
    were ever uploaded (privacy mode), returns reprocessing_started=False
    and does NOT touch transcript_simple. This pins the privacy guarantee:
    a local-only session that never POSTed audio cannot trigger a
    server-side reprocess.
  * POST /api/recordings/sessions/{id}/finalize-audio — with chunks
    present, queues the reprocess. We monkeypatch the BackgroundTasks
    submission so we can assert the queueing happened without driving
    the full STT/diar/LLM pipeline in unit tests.

These tests are NOT designed to validate the end-to-end pipeline (that
requires the cloud Parakeet + speaker-svc + Qwen providers). They pin
the wire contract + side-effects on the FastAPI surface.
"""
from __future__ import annotations

import uuid as _uuid
from unittest.mock import patch

import pytest

from auth.utils import get_password_hash


def _models():
    from auth.models import Organization, User, UserOrganization
    from database.database import SessionLocal
    from database.models import RecordingSession
    return Organization, User, UserOrganization, SessionLocal, RecordingSession


def _login_headers(client, username: str, password: str, org_slug: str | None = None) -> dict[str, str]:
    response = client.post(
        "/api/auth/login",
        data={"username": username, "password": password},
    )
    assert response.status_code == 200, f"Login failed: {response.text}"
    token = response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    if org_slug:
        headers["X-MeetingOps-Org"] = org_slug
    return headers


def _seed_user_and_org(slug: str, username: str = "audiocap_admin"):
    Organization, User, UserOrganization, SessionLocal, _ = _models()
    db = SessionLocal()
    try:
        org = db.query(Organization).filter(Organization.slug == slug).first()
        if not org:
            org = Organization(name=slug.replace("-", " ").title(), slug=slug, is_active=True)
            db.add(org)
            db.commit()
            db.refresh(org)

        user = db.query(User).filter(User.username == username).first()
        if not user:
            user = User(
                email=f"{username}@meeting-ops.local",
                username=username,
                hashed_password=get_password_hash("admin123"),
                is_active=True,
                is_verified=True,
                is_superuser=False,
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
            db.add(UserOrganization(user_id=user.id, organization_id=org.id, role="admin"))
            db.commit()
        return org.id, org.slug, user.id
    finally:
        db.close()


def _create_always_on_session(org_id: int, user_id: int) -> tuple[int, str]:
    _, _, _, SessionLocal, RecordingSession = _models()
    db = SessionLocal()
    try:
        session_uuid = str(_uuid.uuid4())
        session = RecordingSession(
            session_id=session_uuid,
            name=f"audio-cap-test-{session_uuid[:8]}",
            title=f"audio-cap-test-{session_uuid[:8]}",
            description="audio capture + reprocess test",
            meeting_type="always_on",
            mode="always_on",
            status="recording",
            duration=0.0,
            user_id=user_id,
            organization_id=org_id,
            source_type="browser_always_on",
            processing_metadata={"created_by": "test"},
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        return session.id, session.session_id
    finally:
        db.close()


def _read_full_audio_state(session_pk: int) -> dict:
    _, _, _, SessionLocal, RecordingSession = _models()
    db = SessionLocal()
    try:
        row = db.query(RecordingSession).filter(RecordingSession.id == session_pk).first()
        assert row is not None
        meta = dict(row.processing_metadata or {})
        return dict(meta.get("full_audio") or {})
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 1. Happy path — chunk uploads land on disk + state mirrors arrival
# ---------------------------------------------------------------------------
def test_audio_chunks_upload_records_state(client, tmp_path, monkeypatch):
    """Uploading a chunk persists to disk under the per-session full_audio
    directory and updates processing_metadata.full_audio.chunks to record
    arrival. The chunk count matches the number of distinct chunk_indices."""
    # Redirect the recordings dir into pytest's tmp_path so the test
    # filesystem doesn't pollute the real /app/recordings on the host.
    from api import recording

    monkeypatch.setattr(recording, "RECORDINGS_DIR", tmp_path)
    monkeypatch.setattr(recording, "ALWAYS_ON_DIR", tmp_path / "always_on")

    org_id, org_slug, user_id = _seed_user_and_org("audiocap-happy")
    headers = _login_headers(client, "audiocap_admin", "admin123", org_slug)
    session_pk, session_id = _create_always_on_session(org_id, user_id)

    payload_0 = b"\x1a\x45\xdf\xa3" + b"\x00" * 64  # WebM EBML header bytes + filler
    resp = client.post(
        f"/api/recordings/sessions/{session_id}/audio-chunks",
        headers=headers,
        files={"chunk": ("chunk-0.webm", payload_0, "audio/webm")},
        data={"chunk_index": "0"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["chunk_index"] == 0
    assert body["size"] == len(payload_0)
    assert body["chunks_received"] == 1

    state = _read_full_audio_state(session_pk)
    assert "0" in (state.get("chunks") or {})
    assert state["chunks"]["0"]["size"] == len(payload_0)
    assert state["chunks"]["0"]["content_type"] == "audio/webm"

    # File actually lives on disk under the expected path.
    chunk_dir = tmp_path / "always_on" / org_slug / session_id / "full_audio"
    assert chunk_dir.exists()
    on_disk = sorted(p.name for p in chunk_dir.iterdir() if p.is_file())
    assert on_disk == ["000000.webm"]


# ---------------------------------------------------------------------------
# 2. Idempotent re-upload — same chunk_index overwrites without duplication
# ---------------------------------------------------------------------------
def test_audio_chunks_idempotent_on_index(client, tmp_path, monkeypatch):
    """Re-uploading the same chunk_index overwrites the existing file and
    does NOT create a second entry under chunks[idx]. The retry-on-failure
    path on the frontend depends on this guarantee — without it, a late-ACK
    network blip would double-write the audio."""
    from api import recording

    monkeypatch.setattr(recording, "RECORDINGS_DIR", tmp_path)
    monkeypatch.setattr(recording, "ALWAYS_ON_DIR", tmp_path / "always_on")

    org_id, org_slug, user_id = _seed_user_and_org("audiocap-idem")
    headers = _login_headers(client, "audiocap_admin", "admin123", org_slug)
    session_pk, session_id = _create_always_on_session(org_id, user_id)

    # First send.
    r1 = client.post(
        f"/api/recordings/sessions/{session_id}/audio-chunks",
        headers=headers,
        files={"chunk": ("chunk-2.webm", b"FIRST_VERSION_BYTES", "audio/webm")},
        data={"chunk_index": "2"},
    )
    assert r1.status_code == 200, r1.text

    # Retry — same index, different bytes.
    r2 = client.post(
        f"/api/recordings/sessions/{session_id}/audio-chunks",
        headers=headers,
        files={"chunk": ("chunk-2.webm", b"SECOND_VERSION_BYTES_LONGER", "audio/webm")},
        data={"chunk_index": "2"},
    )
    assert r2.status_code == 200, r2.text

    state = _read_full_audio_state(session_pk)
    chunks = state.get("chunks") or {}
    # Only ONE entry for index 2 — the second write replaced the first.
    assert list(chunks.keys()) == ["2"]
    assert chunks["2"]["size"] == len(b"SECOND_VERSION_BYTES_LONGER")

    # And the on-disk file holds the second-version bytes, not the first.
    chunk_dir = tmp_path / "always_on" / org_slug / session_id / "full_audio"
    files = list(chunk_dir.iterdir())
    assert len(files) == 1, f"Expected exactly one file per index, got {files}"
    assert files[0].read_bytes() == b"SECOND_VERSION_BYTES_LONGER"


# ---------------------------------------------------------------------------
# 3. Privacy mode — finalize without chunks does NOT queue reprocess
# ---------------------------------------------------------------------------
def test_finalize_audio_with_no_chunks_skips_reprocess(client, tmp_path, monkeypatch):
    """When the user recorded in privacy/local-only mode, no audio chunks
    ever leave the device. finalize-audio in that case must return
    reprocessing_started=False and refuse to queue the pipeline — the
    live transcript stays canonical and no server-side STT runs."""
    from api import recording

    monkeypatch.setattr(recording, "RECORDINGS_DIR", tmp_path)
    monkeypatch.setattr(recording, "ALWAYS_ON_DIR", tmp_path / "always_on")

    org_id, org_slug, user_id = _seed_user_and_org("audiocap-nochunks")
    headers = _login_headers(client, "audiocap_admin", "admin123", org_slug)
    session_pk, session_id = _create_always_on_session(org_id, user_id)

    # Make sure the helper would refuse to actually do work — patch the
    # background runner so we get a hard assertion if we accidentally
    # queued anything.
    with patch.object(recording, "_run_session_reprocess") as queued:
        resp = client.post(
            f"/api/recordings/sessions/{session_id}/finalize-audio",
            headers=headers,
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["reprocessing_started"] is False
    assert body["reason"] == "no_chunks_uploaded"

    # Background task must NOT have been scheduled — the runner reference
    # captured by BackgroundTasks would have been our patched mock if so.
    queued.assert_not_called()

    state = _read_full_audio_state(session_pk)
    assert state.get("status") == "skipped"
    assert state.get("skipped_reason") == "no_chunks_uploaded"


# ---------------------------------------------------------------------------
# 4. Finalize after chunk upload sets reprocess_status=queued
# ---------------------------------------------------------------------------
def test_finalize_audio_with_chunks_queues_reprocess(client, tmp_path, monkeypatch):
    """When at least one chunk was uploaded, finalize-audio writes
    reprocess_status='queued' to processing_metadata and returns
    reprocessing_started=True. We patch the background runner so the
    test doesn't try to actually exercise the Parakeet/diar/LLM pipeline."""
    from api import recording

    monkeypatch.setattr(recording, "RECORDINGS_DIR", tmp_path)
    monkeypatch.setattr(recording, "ALWAYS_ON_DIR", tmp_path / "always_on")

    org_id, org_slug, user_id = _seed_user_and_org("audiocap-queue")
    headers = _login_headers(client, "audiocap_admin", "admin123", org_slug)
    session_pk, session_id = _create_always_on_session(org_id, user_id)

    # Drop a single chunk so finalize doesn't skip.
    up = client.post(
        f"/api/recordings/sessions/{session_id}/audio-chunks",
        headers=headers,
        files={"chunk": ("chunk-0.webm", b"\x1a\x45\xdf\xa3" + b"\x00" * 32, "audio/webm")},
        data={"chunk_index": "0"},
    )
    assert up.status_code == 200, up.text

    # Stub out the background pipeline so the test doesn't try to actually
    # run ffmpeg + STT + LLM. We replace the runner before finalize so
    # FastAPI's BackgroundTasks captures the stubbed callable instead.
    async def _noop(_session_pk: int) -> None:  # pragma: no cover — async stub
        return None

    monkeypatch.setattr(recording, "_run_session_reprocess", _noop)

    resp = client.post(
        f"/api/recordings/sessions/{session_id}/finalize-audio",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["reprocessing_started"] is True
    assert body["status"] == "queued"

    state = _read_full_audio_state(session_pk)
    assert state.get("status") == "queued"


# ---------------------------------------------------------------------------
# 5. Sad path — audio-chunks for a wrong-mode session returns 409
# ---------------------------------------------------------------------------
def test_audio_chunks_rejects_non_always_on_session(client, tmp_path, monkeypatch):
    """audio-chunks is scoped to always-on sessions. Posting to an upload-
    mode session returns 409 — same wire contract as the existing
    /chunks-text endpoint, so the frontend's error handling stays uniform."""
    from api import recording

    monkeypatch.setattr(recording, "RECORDINGS_DIR", tmp_path)
    monkeypatch.setattr(recording, "ALWAYS_ON_DIR", tmp_path / "always_on")

    Organization, User, UserOrganization, SessionLocal, RecordingSession = _models()
    org_id, org_slug, user_id = _seed_user_and_org("audiocap-wrongmode")
    headers = _login_headers(client, "audiocap_admin", "admin123", org_slug)

    # Create a session with mode='upload' to assert the guard fires.
    db = SessionLocal()
    try:
        uid = str(_uuid.uuid4())
        bad = RecordingSession(
            session_id=uid,
            name="upload-mode-session",
            title="upload-mode-session",
            mode="upload",
            status="recording",
            duration=0.0,
            user_id=user_id,
            organization_id=org_id,
            source_type="upload",
        )
        db.add(bad)
        db.commit()
        db.refresh(bad)
        session_id = bad.session_id
    finally:
        db.close()

    resp = client.post(
        f"/api/recordings/sessions/{session_id}/audio-chunks",
        headers=headers,
        files={"chunk": ("chunk-0.webm", b"x" * 16, "audio/webm")},
        data={"chunk_index": "0"},
    )
    assert resp.status_code == 409, resp.text
    assert "not an always-on session" in resp.text.lower()
