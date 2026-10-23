"""Contract tests for the desktop recording-ingest API."""

from __future__ import annotations

import json
import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import pytest


def _login(client, *, username="admin", password="admin123"):
    response = client.post(
        "/api/auth/login",
        data={"username": username, "password": password},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def _mint_pat(
    client,
    *,
    scope="recordings.ingest",
    org="magic-unicorn",
    expires=90,
    username="admin",
    password="admin123",
):
    response = client.post(
        "/api/auth/pats",
        headers={"Authorization": f"Bearer {_login(client, username=username, password=password)}"},
        json={
            "name": f"desktop-test-{uuid.uuid4()}",
            "scope": scope,
            **({"organization_slug": org} if scope != "user" else {}),
            **({"expires_in_days": expires} if expires is not None else {}),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _headers(plaintext: str, *, org: str | None = None) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {plaintext}",
        "User-Agent": "MeetingMinutesTest/1.0",
    }
    if org is not None:
        headers["X-MeetingOps-Org"] = org
    return headers


def _seed_member(*, role="user"):
    from auth.models import Organization, User, UserOrganization
    from auth.utils import get_password_hash
    from database.database import SessionLocal

    suffix = uuid.uuid4().hex[:12]
    username = f"ingest_member_{suffix}"
    password = "Member123!"
    db = SessionLocal()
    try:
        user = User(
            email=f"{username}@example.com",
            username=username,
            hashed_password=get_password_hash(password),
            is_active=True,
            is_verified=True,
            is_superuser=False,
        )
        organization = Organization(
            name=f"Ingest org {suffix}",
            slug=f"ingest-org-{suffix}",
            is_active=True,
            max_concurrent_uploads=1000,
        )
        db.add_all([user, organization])
        db.flush()
        db.add(
            UserOrganization(
                user_id=user.id,
                organization_id=organization.id,
                role=role,
            )
        )
        db.commit()
        return {
            "username": username,
            "password": password,
            "user_id": user.id,
            "org_id": organization.id,
            "org_slug": organization.slug,
        }
    finally:
        db.close()


def _post_recording(client, plaintext: str, *, external_id=None, org=None, **overrides):
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
        headers=_headers(plaintext, org=org),
        data=data,
        files=files,
    )


def _init_chunked(client, plaintext: str, *, external_id=None, **overrides):
    payload = {
        "external_source": "meeting-minutes",
        "external_id": external_id or f"chunked-{uuid.uuid4()}",
        "recorded_at": "2026-10-08T01:30:00Z",
        "sha256": hashlib.sha256(b"chunked-test").hexdigest(),
        "total_size": len(b"chunked-test"),
        "filename": "meeting.wav",
        "content_type": "audio/wav",
        "timezone": "America/New_York",
        "title": "Chunked test meeting",
    }
    payload.update(overrides)
    return client.post(
        "/api/ingest/uploads",
        headers=_headers(plaintext),
        json=payload,
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


def test_pat_auth_is_rechecked_and_session_tokens_need_an_org(client):
    generic = _mint_pat(client, scope="user", org=None, expires=None)
    response = client.get("/api/ingest/whoami", headers=_headers(generic["plaintext"]))
    assert response.status_code == 400

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


def test_signed_in_member_ingest_is_org_bound_and_replay_does_not_enqueue_twice(client, monkeypatch):
    from api import ingest_recordings
    from auth.models import Organization
    from database.database import SessionLocal
    from database.models import RecordingSession

    member = _seed_member()
    access_token = _login(
        client,
        username=member["username"],
        password=member["password"],
    )
    enqueue = AsyncMock()
    monkeypatch.setattr(ingest_recordings.upload_api.upload_pipeline_queue, "enqueue", enqueue)

    first = _post_recording(
        client,
        access_token,
        external_id="member-replay-1",
        org=member["org_slug"],
    )
    assert first.status_code == 201, first.text
    first_body = first.json()
    assert first_body["created"] is True

    replay = _post_recording(
        client,
        access_token,
        external_id="member-replay-1",
        org=member["org_slug"],
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["created"] is False
    assert replay.json()["session_id"] == first_body["session_id"]
    assert enqueue.await_count == 1

    db = SessionLocal()
    try:
        organization = db.query(Organization).filter(Organization.id == member["org_id"]).one()
        session = (
            db.query(RecordingSession)
            .filter(
                RecordingSession.organization_id == organization.id,
                RecordingSession.external_source == "meeting-minutes",
                RecordingSession.external_id == "member-replay-1",
            )
            .one()
        )
        assert session.user_id == member["user_id"]
        assert session.organization_id == member["org_id"]
    finally:
        db.close()


def test_member_of_org_a_cannot_ingest_into_org_b(client):
    from auth.models import Organization
    from database.database import SessionLocal
    from database.models import RecordingSession

    member = _seed_member()
    db = SessionLocal()
    try:
        org_b = Organization(
            name=f"Ingest foreign org {uuid.uuid4().hex[:12]}",
            slug=f"ingest-foreign-{uuid.uuid4().hex[:12]}",
            is_active=True,
            max_concurrent_uploads=1000,
        )
        db.add(org_b)
        db.commit()
        org_b_slug = org_b.slug
        org_b_id = org_b.id
    finally:
        db.close()

    access_token = _login(
        client,
        username=member["username"],
        password=member["password"],
    )
    response = _post_recording(
        client,
        access_token,
        external_id="cross-tenant-ingest-1",
        org=org_b_slug,
    )
    assert response.status_code == 403, response.text

    db = SessionLocal()
    try:
        assert (
            db.query(RecordingSession)
            .filter(
                RecordingSession.organization_id == org_b_id,
                RecordingSession.external_id == "cross-tenant-ingest-1",
            )
            .count()
            == 0
        )
    finally:
        db.close()


def test_viewer_role_cannot_ingest_when_session_create_is_not_allowed(client):
    viewer = _seed_member(role="viewer")
    access_token = _login(
        client,
        username=viewer["username"],
        password=viewer["password"],
    )
    response = client.get(
        "/api/ingest/whoami",
        headers=_headers(access_token, org=viewer["org_slug"]),
    )
    assert response.status_code == 403, response.text
    assert "session.create" in response.text


def test_session_ingest_requires_a_known_org_header(client):
    member = _seed_member()
    access_token = _login(
        client,
        username=member["username"],
        password=member["password"],
    )
    missing = client.get(
        "/api/ingest/whoami",
        headers=_headers(access_token),
    )
    assert missing.status_code == 400, missing.text

    unknown = client.get(
        "/api/ingest/whoami",
        headers=_headers(access_token, org="does-not-exist"),
    )
    assert unknown.status_code == 404, unknown.text


def test_user_pat_uses_member_session_branch_and_requires_membership(client):
    member = _seed_member()
    member_pat = _mint_pat(
        client,
        scope="user",
        org=None,
        expires=None,
        username=member["username"],
        password=member["password"],
    )
    allowed = client.get(
        "/api/ingest/whoami",
        headers=_headers(member_pat["plaintext"], org=member["org_slug"]),
    )
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["organization_slug"] == member["org_slug"]

    from auth.models import UserOrganization
    from database.database import SessionLocal

    db = SessionLocal()
    try:
        db.query(UserOrganization).filter(
            UserOrganization.user_id == member["user_id"],
            UserOrganization.organization_id == member["org_id"],
        ).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()

    refused = client.get(
        "/api/ingest/whoami",
        headers=_headers(member_pat["plaintext"], org=member["org_slug"]),
    )
    assert refused.status_code == 403, refused.text


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


def test_chunked_happy_path_assembles_three_chunks_and_enqueues_once(client, monkeypatch):
    from api import ingest_recordings, uploads
    from database.database import SessionLocal
    from database.models import RecordingSession, UploadJob

    enqueue = AsyncMock()
    monkeypatch.setattr(ingest_recordings.upload_api.upload_pipeline_queue, "enqueue", enqueue)
    pat = _mint_pat(client)
    chunk_size = uploads.DEFAULT_CHUNK_SIZE
    payload = b"a" * (chunk_size * 2 + 17)
    digest = hashlib.sha256(payload).hexdigest()
    initialized = _init_chunked(
        client,
        pat["plaintext"],
        external_id="chunk-happy-1",
        sha256=digest,
        total_size=len(payload),
        duration_seconds=42.0,
        source_app="MeetingMinutesTest",
        metadata={"kind": "happy"},
    )
    assert initialized.status_code == 201, initialized.text
    init_body = initialized.json()
    assert init_body["chunk_size"] == chunk_size
    assert init_body["total_chunks"] == 3
    assert init_body["received"] == []

    for index in range(3):
        start = index * chunk_size
        chunk_response = client.put(
            f"/api/ingest/uploads/{init_body['upload_id']}/chunks/{index}",
            headers=_headers(pat["plaintext"]),
            content=payload[start:start + chunk_size],
        )
        assert chunk_response.status_code == 200, chunk_response.text

    status_response = client.get(
        f"/api/ingest/uploads/{init_body['upload_id']}",
        headers=_headers(pat["plaintext"]),
    )
    assert status_response.status_code == 200
    assert status_response.json()["received"] == [0, 1, 2]

    completed = client.post(
        f"/api/ingest/uploads/{init_body['upload_id']}/complete",
        headers=_headers(pat["plaintext"]),
    )
    assert completed.status_code == 201, completed.text
    body = completed.json()
    assert body["created"] is True
    assert body["meeting_date"] == "2026-10-07"
    assert body["meeting_time"] == "21:30:00"
    assert enqueue.await_count == 1

    db = SessionLocal()
    try:
        session = db.query(RecordingSession).filter(RecordingSession.id == body["session_id"]).one()
        job = db.query(UploadJob).filter(UploadJob.upload_id == uuid.UUID(body["upload_id"])).one()
        assert job.stage == "queued"
        assert job.session_id == session.id
        assert session.started_at.replace(tzinfo=timezone.utc) == datetime(2026, 10, 8, 1, 30, tzinfo=timezone.utc)
        assert session.ended_at.replace(tzinfo=timezone.utc) == datetime(2026, 10, 8, 1, 30, 42, tzinfo=timezone.utc)
        assert session.processing_metadata["ingest"]["metadata"] == {"kind": "happy"}
        assert session.processing_metadata["ingest"]["source_app"] == "MeetingMinutesTest"
        assert Path(session.audio_file).read_bytes() == payload
    finally:
        db.close()


def test_chunked_init_existing_key_returns_existing_without_new_job_or_file(client, monkeypatch):
    from api import ingest_recordings, uploads
    from database.database import SessionLocal
    from database.models import UploadJob

    enqueue = AsyncMock()
    monkeypatch.setattr(ingest_recordings.upload_api.upload_pipeline_queue, "enqueue", enqueue)
    pat = _mint_pat(client)
    created = _post_recording(client, pat["plaintext"], external_id="chunk-existing-1")
    assert created.status_code == 201

    db = SessionLocal()
    try:
        before_jobs = db.query(UploadJob).count()
        before_dirs = {
            path.name
            for path in (uploads.UPLOAD_ROOT / "magic-unicorn").iterdir()
        }
    finally:
        db.close()

    init = _init_chunked(
        client,
        pat["plaintext"],
        external_id="chunk-existing-1",
        sha256="0" * 64,
        total_size=123,
    )
    assert init.status_code == 200, init.text
    assert init.json()["created"] is False
    db = SessionLocal()
    try:
        assert db.query(UploadJob).count() == before_jobs
    finally:
        db.close()
    after_dirs = {
        path.name
        for path in (uploads.UPLOAD_ROOT / "magic-unicorn").iterdir()
    }
    assert after_dirs == before_dirs


def test_no_speech_is_skipped_terminal_and_repeat_init_returns_existing_session(client, monkeypatch):
    from api import ingest_recordings, uploads
    from database.database import SessionLocal
    from database.models import RecordingSession, UploadJob

    enqueue = AsyncMock()
    monkeypatch.setattr(ingest_recordings.upload_api.upload_pipeline_queue, "enqueue", enqueue)
    pat = _mint_pat(client)
    created = _post_recording(client, pat["plaintext"], external_id="skipped-1")
    assert created.status_code == 201, created.text
    body = created.json()

    db = SessionLocal()
    try:
        session = db.query(RecordingSession).filter(RecordingSession.id == body["session_id"]).one()
        job = db.query(UploadJob).filter(UploadJob.upload_id == uuid.UUID(body["upload_id"])).one()
        session.status = "failed"
        metadata = dict(session.processing_metadata or {})
        metadata.update({
            "no_speech": True,
            "skip_reason": "no_speech",
            "upload_error": "No speech detected in this recording.",
        })
        session.processing_metadata = metadata
        job.stage = "failed"
        job.error_message = "No speech detected in this recording."
        db.commit()
        before_jobs = db.query(UploadJob).count()
        before_dirs = {
            path.name
            for path in (uploads.UPLOAD_ROOT / "magic-unicorn").iterdir()
        }
    finally:
        db.close()

    status_response = client.get(
        "/api/ingest/recordings/meeting-minutes/skipped-1",
        headers=_headers(pat["plaintext"]),
    )
    assert status_response.status_code == 200, status_response.text
    assert status_response.json()["status"] == "skipped"
    assert status_response.json()["skip_reason"] == "no_speech"

    retry = client.post(
        "/api/ingest/recordings/meeting-minutes/skipped-1/retry",
        headers=_headers(pat["plaintext"]),
    )
    assert retry.status_code == 409, retry.text
    assert retry.json() == {"detail": "skipped: no_speech"}

    repeat_init = _init_chunked(
        client,
        pat["plaintext"],
        external_id="skipped-1",
        sha256="0" * 64,
        total_size=123,
    )
    assert repeat_init.status_code == 200, repeat_init.text
    assert repeat_init.json()["created"] is False
    assert repeat_init.json()["session_id"] == body["session_id"]
    assert repeat_init.json()["status"] == "skipped"
    assert repeat_init.json()["skip_reason"] == "no_speech"
    assert enqueue.await_count == 1

    db = SessionLocal()
    try:
        assert db.query(UploadJob).count() == before_jobs
    finally:
        db.close()
    after_dirs = {
        path.name
        for path in (uploads.UPLOAD_ROOT / "magic-unicorn").iterdir()
    }
    assert after_dirs == before_dirs


def test_chunked_init_resumes_same_upload_and_received_indices(client):
    from api import uploads

    pat = _mint_pat(client)
    payload = b"resume-test"
    init = _init_chunked(
        client,
        pat["plaintext"],
        external_id="chunk-resume-1",
        sha256=hashlib.sha256(payload).hexdigest(),
        total_size=len(payload),
    )
    assert init.status_code == 201, init.text
    upload_id = init.json()["upload_id"]
    chunk = client.put(
        f"/api/ingest/uploads/{upload_id}/chunks/0",
        headers=_headers(pat["plaintext"]),
        content=payload,
    )
    assert chunk.status_code == 200
    resumed = _init_chunked(
        client,
        pat["plaintext"],
        external_id="chunk-resume-1",
        sha256=hashlib.sha256(payload).hexdigest(),
        total_size=len(payload),
    )
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["upload_id"] == upload_id
    assert resumed.json()["received"] == [0]
    assert resumed.json()["chunk_size"] == uploads.DEFAULT_CHUNK_SIZE


def test_chunked_rejects_wrong_size_and_out_of_range_chunk(client):
    pat = _mint_pat(client)
    init = _init_chunked(
        client,
        pat["plaintext"],
        external_id="chunk-invalid-1",
        sha256="1" * 64,
        total_size=10,
    )
    assert init.status_code == 201, init.text
    upload_id = init.json()["upload_id"]
    wrong_size = client.put(
        f"/api/ingest/uploads/{upload_id}/chunks/0",
        headers=_headers(pat["plaintext"]),
        content=b"short",
    )
    assert wrong_size.status_code == 422
    out_of_range = client.put(
        f"/api/ingest/uploads/{upload_id}/chunks/1",
        headers=_headers(pat["plaintext"]),
        content=b"0123456789",
    )
    assert out_of_range.status_code == 422


def test_chunked_complete_reports_missing_chunks(client):
    from api import uploads

    pat = _mint_pat(client)
    payload = b"b" * (uploads.DEFAULT_CHUNK_SIZE + 1)
    init = _init_chunked(
        client,
        pat["plaintext"],
        external_id="chunk-missing-1",
        sha256=hashlib.sha256(payload).hexdigest(),
        total_size=len(payload),
    )
    assert init.status_code == 201
    upload_id = init.json()["upload_id"]
    sent = client.put(
        f"/api/ingest/uploads/{upload_id}/chunks/0",
        headers=_headers(pat["plaintext"]),
        content=payload[:uploads.DEFAULT_CHUNK_SIZE],
    )
    assert sent.status_code == 200
    complete = client.post(
        f"/api/ingest/uploads/{upload_id}/complete",
        headers=_headers(pat["plaintext"]),
    )
    assert complete.status_code == 409
    assert complete.json() == {"missing": [1]}


def test_chunked_complete_rejects_sha256_mismatch(client):
    pat = _mint_pat(client)
    payload = b"sha-mismatch"
    init = _init_chunked(
        client,
        pat["plaintext"],
        external_id="chunk-sha-1",
        sha256="2" * 64,
        total_size=len(payload),
    )
    assert init.status_code == 201
    upload_id = init.json()["upload_id"]
    sent = client.put(
        f"/api/ingest/uploads/{upload_id}/chunks/0",
        headers=_headers(pat["plaintext"]),
        content=payload,
    )
    assert sent.status_code == 200
    complete = client.post(
        f"/api/ingest/uploads/{upload_id}/complete",
        headers=_headers(pat["plaintext"]),
    )
    assert complete.status_code == 422


def test_chunked_upload_is_org_scoped_on_get_put_and_complete(client):
    from auth.models import Organization, User, UserOrganization
    from database.database import SessionLocal

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == "admin").one()
        other = Organization(
            name=f"Chunk other {uuid.uuid4()}",
            slug=f"chunk-other-{uuid.uuid4().hex[:10]}",
            is_active=True,
            max_concurrent_uploads=1000,
        )
        db.add(other)
        db.flush()
        db.add(UserOrganization(user_id=user.id, organization_id=other.id, role="admin"))
        db.commit()
        other_slug = other.slug
    finally:
        db.close()

    pat_a = _mint_pat(client)
    pat_b = _mint_pat(client, org=other_slug)
    init = _init_chunked(client, pat_a["plaintext"], external_id="chunk-org-1")
    assert init.status_code == 201
    upload_id = init.json()["upload_id"]
    path = f"/api/ingest/uploads/{upload_id}"
    assert client.get(path, headers=_headers(pat_b["plaintext"])).status_code == 404
    assert client.put(
        f"{path}/chunks/0",
        headers=_headers(pat_b["plaintext"]),
        content=b"chunked-test",
    ).status_code == 404
    assert client.post(
        f"{path}/complete",
        headers=_headers(pat_b["plaintext"]),
    ).status_code == 404


def test_chunked_complete_race_returns_existing_and_cleans_upload(client, monkeypatch):
    from api import ingest_recordings, uploads
    from auth.models import Organization, User
    from database.database import SessionLocal
    from database.models import RecordingSession, UploadJob

    enqueue = AsyncMock()
    monkeypatch.setattr(ingest_recordings.upload_api.upload_pipeline_queue, "enqueue", enqueue)
    pat = _mint_pat(client)
    payload = b"race-complete"
    init = _init_chunked(
        client,
        pat["plaintext"],
        external_id="chunk-race-1",
        sha256=hashlib.sha256(payload).hexdigest(),
        total_size=len(payload),
    )
    assert init.status_code == 201
    upload_id = init.json()["upload_id"]
    assert client.put(
        f"/api/ingest/uploads/{upload_id}/chunks/0",
        headers=_headers(pat["plaintext"]),
        content=payload,
    ).status_code == 200

    db = SessionLocal()
    try:
        org = db.query(Organization).filter(Organization.slug == "magic-unicorn").one()
        user = db.query(User).filter(User.username == "admin").one()
        winner = RecordingSession(
            session_id=str(uuid.uuid4()),
            name="race winner",
            title="race winner",
            status="processing",
            user_id=user.id,
            organization_id=org.id,
            external_source="meeting-minutes",
            external_id="chunk-race-1",
        )
        db.add(winner)
        db.commit()
        winner_id = winner.id
        upload_dir = uploads._job_dir(org.slug, upload_id)
    finally:
        db.close()

    real_find = ingest_recordings._find_session
    calls = 0

    def hide_first(*args, **kwargs):
        nonlocal calls
        calls += 1
        return None if calls == 1 else real_find(*args, **kwargs)

    monkeypatch.setattr(ingest_recordings, "_find_session", hide_first)
    complete = client.post(
        f"/api/ingest/uploads/{upload_id}/complete",
        headers=_headers(pat["plaintext"]),
    )
    assert complete.status_code == 200, complete.text
    assert complete.json()["session_id"] == winner_id
    assert enqueue.await_count == 0
    assert not upload_dir.exists()
    db = SessionLocal()
    try:
        assert db.query(UploadJob).filter(UploadJob.upload_id == uuid.UUID(upload_id)).count() == 0
    finally:
        db.close()


def test_chunked_routes_require_recording_ingest_pat(client):
    valid = _mint_pat(client)
    init = _init_chunked(client, valid["plaintext"], external_id="chunk-auth-1")
    assert init.status_code == 201
    upload_id = init.json()["upload_id"]
    generic = _mint_pat(client, scope="stable.transcript.ingest", org="magic-unicorn")
    paths = [
        ("post", "/api/ingest/uploads", {"json": {
            "external_source": "meeting-minutes",
            "external_id": "chunk-auth-nope",
            "recorded_at": "2026-10-08T01:30:00Z",
            "sha256": "3" * 64,
            "total_size": 1,
        }}),
        ("get", f"/api/ingest/uploads/{upload_id}", {}),
        ("put", f"/api/ingest/uploads/{upload_id}/chunks/0", {"content": b"x"}),
        ("post", f"/api/ingest/uploads/{upload_id}/complete", {}),
    ]
    for method, path, kwargs in paths:
        assert getattr(client, method)(path, headers=_headers(generic["plaintext"]), **kwargs).status_code == 403
        no_token_headers = {"User-Agent": "MeetingMinutesTest/1.0"}
        assert getattr(client, method)(path, headers=no_token_headers, **kwargs).status_code == 401


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
        existing_id = existing.id
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
        session = db.query(RecordingSession).filter(RecordingSession.id == body["session_id"]).one()
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
        title="Call with Diesal",
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

    async def fake_summary(_db, session, *_args, **_kwargs):
        session.title = "Summary retitle"
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
        # The measured audio duration (900 s from STT) wins over the client's 42 s.
        assert session.ended_at.replace(tzinfo=timezone.utc) == datetime(2026, 10, 8, 1, 45, tzinfo=timezone.utc)
        assert session.duration == 900.0
        assert session.title == "Diesal · Summary retitle"
        assert session.processing_metadata["ingest"]["title"] == "Call with Diesal"
        provenance = session.processing_metadata["meeting_provenance"]
        assert provenance["when"]["recorded_at"]["source"] == "ingest.recorded_at"
        assert provenance["when"]["recorded_at"]["confidence"] == 1.0
        assert session.processing_metadata["ingest"]["pat_id"] == pat["id"]
        assert "mops_pat_" not in json.dumps(session.processing_metadata)
    finally:
        db.close()
