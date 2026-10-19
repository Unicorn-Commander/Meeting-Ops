"""Agent imports of files staged through the existing HTTP upload API."""

# Ruff's security rules permit assertions in this test module.
# ruff: noqa: S101

import asyncio
import io
import uuid
import wave
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient


@pytest.fixture
def staged_upload(app, tmp_path, monkeypatch):
    from api import uploads
    from auth.dependencies import get_current_organization, get_current_user
    from auth.models import Organization, User, UserOrganization
    from auth.organization import ActiveOrganization
    from database.database import SessionLocal, get_db

    suffix = uuid.uuid4().hex
    db = SessionLocal()
    org = Organization(
        name=suffix, slug=suffix, plan="enterprise", max_concurrent_uploads=1
    )
    user = User(
        username=suffix,
        email=f"{suffix}@example.com",
        hashed_password="unused",  # noqa: S106 - no authentication in this fixture
        tier="enterprise",
        is_active=True,
    )
    db.add_all([org, user])
    db.flush()
    membership = UserOrganization(user_id=user.id, organization_id=org.id, role="user")
    db.add(membership)
    db.commit()
    active_org = ActiveOrganization(org, membership, "user")
    monkeypatch.delenv("MEETING_OPS_IMPORT_ROOTS", raising=False)
    monkeypatch.setattr(uploads, "UPLOAD_ROOT", tmp_path / "uploads")
    monkeypatch.setattr(uploads, "_persist_upload_audio_to_garage", lambda *a: None)
    enqueue = AsyncMock()
    monkeypatch.setattr(uploads.upload_pipeline_queue, "enqueue", enqueue)

    api = FastAPI()
    api.include_router(uploads.router)
    api.dependency_overrides[get_db] = lambda: db
    api.dependency_overrides[get_current_user] = lambda: user
    api.dependency_overrides[get_current_organization] = lambda: active_org
    audio = io.BytesIO()
    with wave.open(audio, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\x00\x00" * 1600)
    content = audio.getvalue()
    try:
        with TestClient(api) as client:
            response = client.post(
                "/api/uploads/start",
                json={
                    "filename": "one-off.wav",
                    "total_size": len(content),
                    "content_type": "audio/wav",
                    "action": "transcribe",
                    "transcription_options": {"language": "fr"},
                },
            )
            assert response.status_code == 200, response.text
            upload_id = response.json()["upload_id"]
            response = client.post(
                f"/api/uploads/{upload_id}/chunk",
                data={"chunk_index": "0"},
                files={"data": ("chunk.part", content, "application/octet-stream")},
            )
            assert response.status_code == 200, response.text
            yield SimpleNamespace(
                db=db,
                user=user,
                org=active_org,
                upload_id=upload_id,
                job=uploads._get_job(db, upload_id, org.id),
                path=uploads._job_dir(org.slug, upload_id),
                enqueue=enqueue,
                client=client,
                content=content,
            )
    finally:
        db.close()


def _import(context, **kwargs):
    from services.mcp_import import import_recording_for_caller

    return asyncio.run(
        import_recording_for_caller(
            db=context.db,
            caller=context.user,
            active_org=context.org,
            upload_id=context.upload_id,
            **kwargs,
        )
    )


def test_import_uploaded_file_uses_reserved_job_and_normal_pipeline(staged_upload):
    from auth.models import AuditLog
    from database.models import RecordingSession, UploadJob

    ctx = staged_upload
    jobs_before = ctx.db.query(UploadJob).count()
    result = _import(ctx, title="Agent upload", tags=["sync", "Sync"])

    session = ctx.db.get(RecordingSession, result["session_id"])
    assert result["status"] == "queued"
    assert session.user_id == ctx.user.id
    assert session.organization_id == ctx.org.organization.id
    assert session.title == session.name == "Agent upload"
    assert session.title_user_set
    assert session.tags == ["sync"]
    assert session.source_type == "mcp_import"
    assert session.processing_metadata["mcp_import"]["source_kind"] == "upload"
    assert ctx.job.action == "attach"
    assert ctx.job.session_id == session.id
    assert ctx.job.transcription_options["language"] == "fr"
    assert ctx.job.audio_sha256
    assert ctx.db.query(UploadJob).count() == jobs_before
    assert (ctx.path / ctx.job.filename).read_bytes() == ctx.content
    ctx.enqueue.assert_awaited_once_with(ctx.upload_id)
    audit = (
        ctx.db.query(AuditLog)
        .filter_by(resource_id=str(session.id), action="mcp_import_recording")
        .one()
    )
    assert audit.details["upload_id"] == ctx.upload_id


@pytest.mark.parametrize("stage", ["queued", "transcribing", "done", "failed"])
def test_repeated_upload_import_returns_same_session_without_requeue(
    staged_upload, stage
):
    ctx = staged_upload
    first = _import(ctx, title="Original")
    ctx.job.stage = stage
    ctx.db.commit()
    second = _import(ctx, title="Ignored")
    assert second == {"session_id": first["session_id"], "status": stage}
    ctx.enqueue.assert_awaited_once_with(ctx.upload_id)


def test_queue_outage_leaves_recoverable_upload_and_stable_session(staged_upload):
    ctx = staged_upload
    ctx.enqueue.side_effect = RuntimeError("queue unavailable")
    result = _import(ctx)
    assert result == {"session_id": ctx.job.session_id, "status": "queued"}
    assert ctx.job.session_id is not None
    assert (ctx.path / ctx.job.filename).is_file()


def test_invalid_tags_do_not_finish_upload(staged_upload):
    ctx = staged_upload
    with pytest.raises(HTTPException) as exc:
        _import(ctx, tags=["valid", 7])
    assert exc.value.status_code == 400
    assert ctx.job.session_id is None
    assert ctx.job.stage == "uploading"
    ctx.enqueue.assert_not_awaited()


@pytest.mark.parametrize("boundary", ["user", "organization"])
def test_upload_import_rejects_other_owner_or_org(staged_upload, boundary):
    ctx = staged_upload
    if boundary == "user":
        ctx.job.user_id = ctx.user.id + 10000
    else:
        ctx.job.organization_id = ctx.org.organization.id + 10000
    ctx.db.commit()

    with pytest.raises(HTTPException) as exc:
        _import(ctx)
    assert exc.value.status_code == (403 if boundary == "user" else 404)
    ctx.enqueue.assert_not_awaited()
    assert ctx.job.session_id is None


@pytest.mark.parametrize("upload_id", ["not-a-uuid", str(uuid.uuid4())])
def test_unknown_upload_does_not_create_session(staged_upload, upload_id):
    ctx = staged_upload
    ctx.upload_id = upload_id
    with pytest.raises(HTTPException) as exc:
        _import(ctx)
    assert exc.value.status_code == 404
    ctx.enqueue.assert_not_awaited()


@pytest.mark.parametrize("failure", ["incomplete", "missing", "size"])
def test_upload_must_contain_all_declared_bytes(staged_upload, failure):
    ctx = staged_upload
    chunk = ctx.path / "chunks" / "00000000.part"
    if failure == "incomplete":
        ctx.job.chunks_received = 0
        ctx.db.commit()
    elif failure == "missing":
        chunk.unlink()
    else:
        chunk.write_bytes(b"truncated")
    with pytest.raises(HTTPException) as exc:
        _import(ctx)
    assert exc.value.status_code == 400
    assert ctx.job.session_id is None
    assert ctx.job.stage == "uploading"
    ctx.enqueue.assert_not_awaited()


@pytest.mark.parametrize("action", ["attach", "ingest"])
def test_import_does_not_reinterpret_other_upload_protocols(staged_upload, action):
    ctx = staged_upload
    ctx.job.action = action
    ctx.db.commit()
    with pytest.raises(HTTPException) as exc:
        _import(ctx)
    assert exc.value.status_code == 409
    assert ctx.job.session_id is None
    ctx.enqueue.assert_not_awaited()


@pytest.mark.parametrize("stage", ["queued", "transcribing", "failed", "cancelled"])
def test_import_does_not_restart_a_job(staged_upload, stage):
    ctx = staged_upload
    ctx.job.stage = stage
    ctx.db.commit()
    with pytest.raises(HTTPException) as exc:
        _import(ctx)
    assert exc.value.status_code == 409
    ctx.enqueue.assert_not_awaited()


def test_upload_import_still_checks_feature_gate(staged_upload):
    ctx = staged_upload
    ctx.user.tier = "free"
    ctx.org.organization.plan = "free"
    ctx.db.commit()
    with pytest.raises(HTTPException) as exc:
        _import(ctx)
    assert exc.value.status_code == 403
    assert ctx.job.session_id is None
    ctx.enqueue.assert_not_awaited()


def test_upload_import_checks_current_size_limit(staged_upload, monkeypatch):
    monkeypatch.setenv("UPLOAD_MAX_FILE_BYTES", "8")
    with pytest.raises(HTTPException) as exc:
        _import(staged_upload)
    assert exc.value.status_code == 413
    staged_upload.enqueue.assert_not_awaited()


@pytest.mark.parametrize(
    "sources",
    [
        {},
        {"source_url": "https://example.com/a.wav", "local_path": "/a.wav"},
        {"source_url": "https://example.com/a.wav", "upload_id": "id"},
        {"local_path": "/a.wav", "upload_id": "id"},
        {
            "source_url": "https://example.com/a.wav",
            "local_path": "/a.wav",
            "upload_id": "id",
        },
    ],
)
def test_exactly_one_source_is_required(sources):
    from services.mcp_import import import_recording_for_caller

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            import_recording_for_caller(
                db=None, caller=None, active_org=None, **sources
            )
        )
    assert exc.value.status_code == 400


def test_disabled_local_import_explains_supported_upload_path(monkeypatch):
    from services.mcp_import import _resolve_local_source

    monkeypatch.delenv("MEETING_OPS_IMPORT_ROOTS", raising=False)
    with pytest.raises(HTTPException) as exc:
        _resolve_local_source("/unavailable/meeting.wav")
    assert exc.value.status_code == 403
    assert "/api/uploads/start" in exc.value.detail
    assert "upload_id" in exc.value.detail


def test_allowlist_still_rejects_symlink_escape(tmp_path, monkeypatch):
    from services.mcp_import import _resolve_local_source

    root = tmp_path / "allowed"
    root.mkdir()
    outside = tmp_path / "outside.wav"
    outside.write_bytes(b"audio")
    link = root / "escape.wav"
    link.symlink_to(outside)
    monkeypatch.setenv("MEETING_OPS_IMPORT_ROOTS", str(root))
    with pytest.raises(HTTPException) as exc:
        _resolve_local_source(str(link))
    assert exc.value.status_code == 403


def test_upload_id_is_advertised_by_both_agent_surfaces():
    from services.agent_tools import MEETING_RAG_TOOLS
    from services.mcp_app import mcp

    tool = next(
        t for t in asyncio.run(mcp.list_tools()) if t.name == "import_recording"
    )
    manifest = next(
        t["function"]
        for t in MEETING_RAG_TOOLS
        if t.get("function", {}).get("name") == "import_recording"
    )
    assert "upload_id" in tool.inputSchema["properties"]
    assert "upload_id" in manifest["parameters"]["properties"]


def test_mcp_tool_forwards_upload_id_with_authenticated_context(monkeypatch):
    from auth import pat
    from database import database
    from services import mcp_app, mcp_import

    db = SimpleNamespace(close=lambda: None)
    user = object()
    active_org = object()
    token = SimpleNamespace(scope="user", user=user, organization_id=7)
    importer = AsyncMock(return_value={"session_id": 42, "status": "queued"})
    monkeypatch.setattr(database, "SessionLocal", lambda: db)
    monkeypatch.setattr(mcp_app, "_require_pat", lambda: "fixture")
    monkeypatch.setattr(pat, "resolve_pat_record", lambda *a, **kw: token)
    monkeypatch.setattr(
        mcp_app, "_resolve_mcp_active_organization", lambda *a: active_org
    )
    monkeypatch.setattr(mcp_import, "import_recording_for_caller", importer)

    result = asyncio.run(mcp_app.import_recording(upload_id="staged-upload"))

    assert result == {"session_id": 42, "status": "queued"}
    importer.assert_awaited_once_with(
        db=db,
        caller=user,
        active_org=active_org,
        upload_id="staged-upload",
        source_url=None,
        local_path=None,
        title=None,
        tags=None,
    )


def test_in_process_agent_can_import_uploaded_file(staged_upload):
    from services.agent_tools import execute_tool

    ctx = staged_upload
    result = asyncio.run(
        execute_tool(
            "import_recording",
            {"upload_id": ctx.upload_id},
            db=ctx.db,
            org_id=ctx.org.organization.id,
            current_user=ctx.user,
            llm_provider=None,
        )
    )
    assert result == {"session_id": ctx.job.session_id, "status": "queued"}
    ctx.enqueue.assert_awaited_once_with(ctx.upload_id)
