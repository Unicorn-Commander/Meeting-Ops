"""Contract tests for the desktop recording-ingest API."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import pytest


def _login(client):
    response = client.post(
        "/api/auth/login",
        data={"username": "admin", "password": "admin123"},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def _mint_pat(client, *, scope="recordings.ingest", org="magic-unicorn", expires=90):
    response = client.post(
        "/api/auth/pats",
        headers={"Authorization": f"Bearer {_login(client)}"},
        json={
            "name": f"desktop-test-{uuid.uuid4()}",
            "scope": scope,
            **({"organization_slug": org} if scope != "user" else {}),
            **({"expires_in_days": expires} if expires is not None else {}),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _headers(plaintext: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {plaintext}",
        "User-Agent": "MeetingMinutesTest/1.0",
    }


def _post_recording(client, plaintext: str, *, external_id=None, **overrides):
    files = overrides.pop("files", None) or {
        "file": ("meeting.wav", b"synthetic audio", "audio/wav"),
    }
    data = {
        "external_source": "meeting-minutes",
        "external_id": external_id or f"recording-{uuid.uuid4()}",
        "recorded_at": "2026-10-08T01:30:00Z",
        "timezone": "America/New_York",
        "title": "Desktop test meeting",
    }
    data.update(overrides)
    if isinstance(data.get("metadata"), dict):
        data["metadata"] = json.dumps(data["metadata"])
    return client.post(
        "/api/ingest/recordings",
        headers=_headers(plaintext),
        data=data,
        files=files,
    )


@pytest.fixture(autouse=True)
def generous_test_quota(app):
    """Keep unrelated queued jobs from masking route behavior in this module."""
    from auth.models import Organization
    from database.database import SessionLocal

    db = SessionLocal()
    try:
        org = db.query(Organization).filter(Organization.slug == "magic-unicorn").one()
        org.max_concurrent_uploads = 1000
        db.commit()
    finally:
        db.close()


def test_scope_creation_requires_org_and_expiry_and_whoami_never_returns_token(client):
    jwt = _login(client)
    missing_org = client.post(
        "/api/auth/pats",
        headers={"Authorization": f"Bearer {jwt}"},
        json={"name": "missing org", "scope": "recordings.ingest", "expires_in_days": 90},
    )
    assert missing_org.status_code == 400

    missing_expiry = client.post(
        "/api/auth/pats",
        headers={"Authorization": f"Bearer {jwt}"},
        json={
            "name": "missing expiry",
            "scope": "recordings.ingest",
            "organization_slug": "magic-unicorn",
        },
    )
    assert missing_expiry.status_code == 400

    created = _mint_pat(client)
    response = client.get("/api/ingest/whoami", headers=_headers(created["plaintext"]))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["organization_slug"] == "magic-unicorn"
    assert body["scope"] == "recordings.ingest"
    assert body["token_prefix"] == created["token_prefix"]
    assert created["plaintext"] not in response.text


def test_auth_is_pat_only_and_membership_is_rechecked(client):
    generic = _mint_pat(client, scope="user", org=None, expires=None)
    response = client.get("/api/ingest/whoami", headers=_headers(generic["plaintext"]))
    assert response.status_code == 403

    expired = _mint_pat(client)
    from auth.models import PersonalAccessToken
    from database.database import SessionLocal

    db = SessionLocal()
    try:
        row = db.query(PersonalAccessToken).filter(PersonalAccessToken.id == expired["id"]).one()
        row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()
    finally:
        db.close()
    assert client.get("/api/ingest/whoami", headers=_headers(expired["plaintext"])).status_code == 401

    revoked = _mint_pat(client)
    revoke = client.delete(
        f"/api/auth/pats/{revoked['id']}",
        headers={"Authorization": f"Bearer {_login(client)}"},
    )
    assert revoke.status_code == 204
    assert client.get("/api/ingest/whoami", headers=_headers(revoked["plaintext"])).status_code == 401

    assert client.get("/api/ingest/whoami", headers=_headers("mops_pat_not-a-real-token")).status_code == 401
    assert client.get("/api/ingest/whoami").status_code == 401

    member_removed = _mint_pat(client)
    from auth.models import UserOrganization

    db = SessionLocal()
    try:
        row = db.query(PersonalAccessToken).filter(PersonalAccessToken.id == member_removed["id"]).one()
        user_id = row.user_id
        organization_id = row.organization_id
        membership = (
            db.query(UserOrganization)
            .filter(
                UserOrganization.user_id == row.user_id,
                UserOrganization.organization_id == row.organization_id,
            )
            .one()
        )
        db.delete(membership)
        db.commit()
    finally:
        db.close()
    assert client.get("/api/ingest/whoami", headers=_headers(member_removed["plaintext"])).status_code == 403

    db = SessionLocal()
    try:
        db.add(UserOrganization(user_id=user_id, organization_id=organization_id, role="admin"))
        db.commit()
    finally:
        db.close()


def test_first_post_is_idempotent_and_does_not_store_or_enqueue_twice(client, monkeypatch):
    from api import ingest_recordings
    from api import uploads
    from auth.models import Organization
    from database.database import SessionLocal
    from database.models import RecordingSession, UploadJob

    enqueue = AsyncMock()
    monkeypatch.setattr(ingest_recordings.upload_api.upload_pipeline_queue, "enqueue", enqueue)
    pat = _mint_pat(client)

    first = _post_recording(client, pat["plaintext"], external_id="idempotent-1")
    assert first.status_code == 201, first.text
    first_body = first.json()
    assert first_body["created"] is True
    assert first_body["status"] == "processing"
    assert first_body["meeting_date"] == "2026-10-07"
    assert first_body["meeting_time"] == "21:30:00"
    assert enqueue.await_count == 1

    db = SessionLocal()
    try:
        org = db.query(Organization).filter(Organization.slug == "magic-unicorn").one()
        rows = (
            db.query(RecordingSession)
            .filter(
                RecordingSession.organization_id == org.id,
                RecordingSession.external_source == "meeting-minutes",
                RecordingSession.external_id == "idempotent-1",
            )
            .all()
        )
        assert len(rows) == 1
        job = db.query(UploadJob).filter(UploadJob.upload_id == uuid.UUID(first_body["upload_id"])).one()
        assert job.session_id == rows[0].id
        assert Path(rows[0].audio_file).is_file()
        upload_dirs = list((uploads.UPLOAD_ROOT / org.slug).iterdir())
    finally:
        db.close()

    duplicate = _post_recording(client, pat["plaintext"], external_id="idempotent-1")
    assert duplicate.status_code == 200, duplicate.text
    assert duplicate.json()["created"] is False
    assert duplicate.json()["session_id"] == first_body["session_id"]
    assert enqueue.await_count == 1
    assert len(list((uploads.UPLOAD_ROOT / "magic-unicorn").iterdir())) == len(upload_dirs)


def test_integrity_error_race_returns_existing_session_and_cleans_loser_file(client, monkeypatch):
    from api import ingest_recordings
    from auth.models import Organization, User
    from database.database import SessionLocal
    from database.models import RecordingSession

    pat = _mint_pat(client)
    db = SessionLocal()
    try:
        org = db.query(Organization).filter(Organization.slug == "magic-unicorn").one()
        user = db.query(User).filter(User.username == "admin").one()
        existing = RecordingSession(
            session_id=str(uuid.uuid4()),
            name="race winner",
            title="race winner",
            status="processing",
            user_id=user.id,
            organization_id=org.id,
            external_source="meeting-minutes",
            external_id="race-1",
        )
        db.add(existing)
        db.commit()
        existing_id = existing.session_id
        upload_root = ingest_recordings.upload_api.UPLOAD_ROOT / org.slug
        before_dirs = {path.name for path in upload_root.iterdir()} if upload_root.exists() else set()
    finally:
        db.close()

    real_find = ingest_recordings._find_session
    calls = 0

    def hide_once(*args, **kwargs):
        nonlocal calls
        calls += 1
        return None if calls == 1 else real_find(*args, **kwargs)

    monkeypatch.setattr(ingest_recordings, "_find_session", hide_once)
    enqueue = AsyncMock()
    monkeypatch.setattr(ingest_recordings.upload_api.upload_pipeline_queue, "enqueue", enqueue)

    response = _post_recording(client, pat["plaintext"], external_id="race-1")
    assert response.status_code == 200, response.text
    assert response.json()["created"] is False
    assert response.json()["session_id"] == existing_id
    assert enqueue.await_count == 0
    after_dirs = {path.name for path in upload_root.iterdir()} if upload_root.exists() else set()
    assert after_dirs == before_dirs


def test_status_mapping_and_retry_reuses_shared_upload_retry(client, monkeypatch):
    from api import ingest_recordings
    from api import uploads
    from database.database import SessionLocal
    from database.models import RecordingSession, UploadJob

    enqueue = AsyncMock()
    monkeypatch.setattr(ingest_recordings.upload_api.upload_pipeline_queue, "enqueue", enqueue)
    pat = _mint_pat(client)
    created = _post_recording(client, pat["plaintext"], external_id="retry-1")
    assert created.status_code == 201
    body = created.json()

    status_response = client.get(
        "/api/ingest/recordings/meeting-minutes/retry-1",
        headers=_headers(pat["plaintext"]),
    )
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "processing"

    not_failed = client.post(
        "/api/ingest/recordings/meeting-minutes/retry-1/retry",
        headers=_headers(pat["plaintext"]),
    )
    assert not_failed.status_code == 409

    db = SessionLocal()
    try:
        session = db.query(RecordingSession).filter(RecordingSession.session_id == body["session_id"]).one()
        job = db.query(UploadJob).filter(UploadJob.upload_id == uuid.UUID(body["upload_id"])).one()
        session.status = "failed"
        job.stage = "failed"
        job.error_message = "synthetic failure"
        db.commit()
    finally:
        db.close()

    retry = client.post(
        "/api/ingest/recordings/meeting-minutes/retry-1/retry",
        headers=_headers(pat["plaintext"]),
    )
    assert retry.status_code == 202, retry.text
    assert retry.json() == {"session_id": body["session_id"], "status": "processing"}
    assert enqueue.await_count == 2
    after = client.get(
        "/api/ingest/recordings/meeting-minutes/retry-1",
        headers=_headers(pat["plaintext"]),
    )
    assert after.json()["status"] == "processing"


def test_validation_rejects_bad_identity_time_zone_metadata_and_hash(client, monkeypatch):
    enqueue = AsyncMock()
    from api import ingest_recordings
    from api import uploads

    monkeypatch.setattr(ingest_recordings.upload_api.upload_pipeline_queue, "enqueue", enqueue)
    pat = _mint_pat(client)
    cases = [
        {"external_source": "Bad Source", "external_id": "bad-source"},
        {"external_id": "contains/slash"},
        {"external_id": "naive-time", "recorded_at": "2026-10-08T01:30:00"},
        {"external_id": "bad-zone", "timezone": "Not/IANA"},
        {"external_id": "big-metadata", "metadata": {"x": "a" * (16 * 1024)}},
        {"external_id": "bad-hash", "sha256": "0" * 64},
    ]
    for case in cases:
        response = _post_recording(client, pat["plaintext"], **case)
        assert response.status_code == 422, (case, response.text)
    assert enqueue.await_count == 0


def test_org_scope_hides_another_org_session(client):
    from auth.models import Organization, User, UserOrganization
    from database.database import SessionLocal
    from database.models import RecordingSession

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == "admin").one()
        org_b = Organization(
            name=f"Other ingest org {uuid.uuid4()}",
            slug=f"other-ingest-{uuid.uuid4().hex[:12]}",
            is_active=True,
            max_concurrent_uploads=1000,
        )
        db.add(org_b)
        db.flush()
        db.add(UserOrganization(user_id=user.id, organization_id=org_b.id, role="admin"))
        db.add(
            RecordingSession(
                session_id=str(uuid.uuid4()),
                name="other org meeting",
                title="other org meeting",
                status="failed",
                user_id=user.id,
                organization_id=org_b.id,
                external_source="meeting-minutes",
                external_id="shared-key",
            )
        )
        db.commit()
    finally:
        db.close()

    pat = _mint_pat(client)
    status_response = client.get(
        "/api/ingest/recordings/meeting-minutes/shared-key",
        headers=_headers(pat["plaintext"]),
    )
    retry_response = client.post(
        "/api/ingest/recordings/meeting-minutes/shared-key/retry",
        headers=_headers(pat["plaintext"]),
    )
    assert status_response.status_code == 404
    assert retry_response.status_code == 404


@pytest.mark.asyncio
async def test_ingest_dates_survive_the_real_upload_pipeline(app, client, monkeypatch):
    from api import ingest_recordings
    from api import uploads
    from database.database import SessionLocal
    from database.models import RecordingSession, UploadJob

    enqueue = AsyncMock()
    monkeypatch.setattr(ingest_recordings.upload_api.upload_pipeline_queue, "enqueue", enqueue)
    pat = _mint_pat(client)
    created = _post_recording(
        client,
        pat["plaintext"],
        external_id="pipeline-dates-1",
        duration_seconds="42.0",
    )
    assert created.status_code == 201, created.text
    body = created.json()

    db = SessionLocal()
    try:
        job = db.query(UploadJob).filter(UploadJob.upload_id == uuid.UUID(body["upload_id"])).one()
        job.transcription_options = {"diarization_mode": "off"}
        db.commit()
    finally:
        db.close()

    async def fake_extract(_source, audio, *_args):
        audio.write_bytes(b"RIFF synthetic wav")

    async def fake_transcribe(*_args, **_kwargs):
        return {
            "segments": [{"text": "hello from mocked STT", "start": 0.0, "end": 900.0}],
            "audio_duration": 900.0,
            "language": "en",
            "model": "test-stt",
        }

    async def fake_summary(*_args, **_kwargs):
        return None

    async def fake_insights(*_args, **_kwargs):
        class Insights:
            def model_dump(self):
                return {}

        return Insights()

    async def fake_autostamp(*_args, **_kwargs):
        return None

    monkeypatch.setattr(uploads, "_extract_audio", fake_extract)
    monkeypatch.setattr(uploads, "_transcribe_audio", fake_transcribe)
    monkeypatch.setattr(uploads, "_summarize_session", fake_summary)
    monkeypatch.setattr("api.ai_insights._generate_ai_insights", fake_insights)
    monkeypatch.setattr("services.semantic_search_service.semantic_search.index_session", lambda **_kwargs: None)
    monkeypatch.setattr("api.recording._autostamp_recorder_participant", fake_autostamp)
    monkeypatch.setattr(uploads, "_stamp_speaker_contacts_fresh", lambda *_args, **_kwargs: None)

    from services.projectops_writer import ProjectOpsWriteResult

    monkeypatch.setattr(
        "services.projectops_writer.submit_action_items_to_triage",
        AsyncMock(return_value=ProjectOpsWriteResult(ok=True, mode="test")),
    )

    await uploads.run_upload_pipeline(body["upload_id"])

    db = SessionLocal()
    try:
        job = db.query(UploadJob).filter(UploadJob.upload_id == uuid.UUID(body["upload_id"])).one()
        session = db.query(RecordingSession).filter(RecordingSession.id == job.session_id).one()
        assert job.stage == "done"
        assert session.status == "completed"
        assert session.meeting_date.isoformat() == "2026-10-07"
        assert session.meeting_time.isoformat() == "21:30:00"
        assert session.started_at.replace(tzinfo=timezone.utc) == datetime(2026, 10, 8, 1, 30, tzinfo=timezone.utc)
        assert session.ended_at.replace(tzinfo=timezone.utc) == datetime(2026, 10, 8, 1, 30, 42, tzinfo=timezone.utc)
        assert session.duration == 42.0
        provenance = session.processing_metadata["meeting_provenance"]
        assert provenance["when"]["recorded_at"]["source"] == "ingest.recorded_at"
        assert provenance["when"]["recorded_at"]["confidence"] == 1.0
        assert session.processing_metadata["ingest"]["pat_id"] == pat["id"]
        assert "mops_pat_" not in json.dumps(session.processing_metadata)
    finally:
        db.close()
