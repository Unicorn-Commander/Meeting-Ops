"""Focused tests for the server-side MCP recording import."""

from __future__ import annotations

import asyncio
import wave
import uuid
from pathlib import Path

import pytest
from fastapi import HTTPException


def _tiny_wav(path: Path, *, frames: int = 1600) -> None:
    """Write a small valid mono WAV without requiring an audio package."""
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16000)
        output.writeframes(b"\x00\x00" * frames)


@pytest.fixture
def import_context(app, tmp_path, monkeypatch):
    from auth.models import Organization, User, UserOrganization
    from auth.organization import ActiveOrganization
    from auth.utils import get_password_hash
    from database.database import SessionLocal

    suffix = uuid.uuid4().hex[:8]
    db = SessionLocal()
    organization = Organization(
        name=f"MCP import org {suffix}",
        slug=f"mcp-import-{suffix}",
        plan="enterprise",
        is_active=True,
    )
    user = User(
        email=f"mcp-import-{suffix}@example.com",
        username=f"mcp-import-{suffix}",
        hashed_password=get_password_hash("Password123"),
        is_active=True,
        is_verified=True,
        tier="enterprise",
    )
    db.add_all([organization, user])
    db.commit()
    db.refresh(organization)
    db.refresh(user)
    membership = UserOrganization(
        user_id=user.id,
        organization_id=organization.id,
        role="user",
    )
    db.add(membership)
    db.commit()

    root = tmp_path / "allowlisted"
    root.mkdir()
    monkeypatch.setenv("MEETING_OPS_IMPORT_ROOTS", str(root))

    from api import uploads

    monkeypatch.setattr(uploads, "UPLOAD_ROOT", tmp_path / "recordings" / "uploads")
    monkeypatch.setattr(uploads, "_persist_upload_audio_to_garage", lambda *args, **kwargs: None)
    submitted: list[str] = []

    async def fake_enqueue(upload_id: str) -> None:
        submitted.append(upload_id)

    monkeypatch.setattr(uploads.upload_pipeline_queue, "enqueue", fake_enqueue)
    active_org = ActiveOrganization(organization=organization, membership=membership, role="user")
    try:
        yield db, user, active_org, root, submitted
    finally:
        db.close()


def _run_import(context, source: Path, **kwargs):
    from services.mcp_import import import_recording_for_caller

    db, user, active_org, _root, _submitted = context
    return asyncio.run(
        import_recording_for_caller(
            db=db,
            caller=user,
            active_org=active_org,
            local_path=str(source),
            **kwargs,
        )
    )


def test_import_recording_happy_path_uses_upload_job_and_audit(import_context):
    db, _user, _active_org, root, submitted = import_context
    source = root / "meeting.wav"
    _tiny_wav(source)

    result = _run_import(import_context, source, title="Imported sync", tags=["archive", "Archive"])

    assert result["session_id"] > 0
    assert result["status"] == "queued"
    assert len(submitted) == 1

    from auth.models import AuditLog
    from database.models import RecordingSession, UploadJob

    session = db.get(RecordingSession, result["session_id"])
    assert session is not None
    assert session.title == "Imported sync"
    assert session.tags == ["archive"]
    assert session.source_type == "mcp_import"
    assert session.processing_metadata["mcp_import"]["source_kind"] == "local_path"

    job = db.query(UploadJob).filter(UploadJob.session_id == session.id).one()
    assert job.action == "attach"
    assert job.audio_sha256 == session.processing_metadata["mcp_import"]["source_sha256"]
    audit = (
        db.query(AuditLog)
        .filter(AuditLog.resource_id == str(session.id), AuditLog.action == "mcp_import_recording")
        .one()
    )
    assert audit.details["source_sha256"] == job.audio_sha256
    assert "local_path" not in audit.details


def test_import_recording_repeat_returns_same_session(import_context):
    _db, _user, _active_org, root, submitted = import_context
    source = root / "repeat.wav"
    _tiny_wav(source, frames=2400)

    first = _run_import(import_context, source)
    second = _run_import(import_context, source, title="ignored on repeat")

    assert second == first
    assert submitted == [submitted[0]]


def test_import_recording_rejects_path_outside_allowlist(import_context, tmp_path):
    outside = tmp_path / "outside.wav"
    _tiny_wav(outside)

    with pytest.raises(HTTPException) as caught:
        _run_import(import_context, outside)

    assert caught.value.status_code == 403
    assert "allowlisted" in str(caught.value.detail)


def test_import_recording_rejects_oversize_source(import_context, monkeypatch):
    _db, _user, _active_org, root, submitted = import_context
    source = root / "large.wav"
    _tiny_wav(source, frames=1600)
    monkeypatch.setenv("UPLOAD_MAX_FILE_BYTES", "8")

    with pytest.raises(HTTPException) as caught:
        _run_import(import_context, source)

    assert caught.value.status_code == 413
    assert submitted == []


def test_import_recording_rejects_non_https_and_private_url():
    from services.mcp_import import _validate_public_https_url

    with pytest.raises(HTTPException) as non_https:
        _validate_public_https_url("http://example.com/meeting.wav")
    assert non_https.value.status_code == 400

    with pytest.raises(HTTPException) as private:
        _validate_public_https_url("https://127.0.0.1/meeting.wav")
    assert private.value.status_code == 400


def test_import_recording_is_registered_in_mcp_surfaces():
    from services.agent_tools import MEETING_RAG_TOOLS
    from services.mcp_app import mcp

    names = {tool.name for tool in asyncio.run(mcp.list_tools())}
    manifest_names = {
        item["function"]["name"]
        for item in MEETING_RAG_TOOLS
        if item.get("type") == "function"
    }
    assert "import_recording" in names
    assert "import_recording" in manifest_names
