"""Focused tests for the server-side MCP recording import."""

from __future__ import annotations

import asyncio
import socket
import uuid
import wave
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


def test_import_recording_requires_session_create_before_creating_rows(import_context):
    db, _user, active_org, root, submitted = import_context
    source = root / "role-gated.wav"
    _tiny_wav(source)

    from database.models import RecordingSession, UploadJob

    active_org.membership.role = "viewer"
    active_org.role = "viewer"
    db.commit()
    sessions_before = db.query(RecordingSession).count()
    jobs_before = db.query(UploadJob).count()

    with pytest.raises(HTTPException) as caught:
        _run_import(import_context, source)

    assert caught.value.status_code == 403
    assert caught.value.detail == "Insufficient permissions. Required: session.create"
    assert db.query(RecordingSession).count() == sessions_before
    assert db.query(UploadJob).count() == jobs_before
    assert submitted == []

    active_org.membership.role = "user"
    active_org.role = "user"
    db.commit()
    result = _run_import(import_context, source)

    assert result["session_id"] > 0
    assert result["status"] == "queued"
    assert db.query(RecordingSession).count() == sessions_before + 1
    assert db.query(UploadJob).count() == jobs_before + 1
    assert len(submitted) == 1


def test_import_recording_rejects_invalid_tags_before_creating_session(import_context):
    db, _user, _active_org, root, submitted = import_context
    source = root / "invalid-tags.wav"
    _tiny_wav(source)

    from database.models import RecordingSession, UploadJob

    sessions_before = db.query(RecordingSession).count()
    jobs_before = db.query(UploadJob).count()
    with pytest.raises(HTTPException) as caught:
        _run_import(import_context, source, tags=["ok", 1])  # type: ignore[list-item]

    assert caught.value.status_code == 400
    assert db.query(RecordingSession).count() == sessions_before
    assert db.query(UploadJob).count() == jobs_before
    assert submitted == []


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


@pytest.mark.parametrize(
    "raw_url",
    [
        "https://100.64.0.1/meeting.wav",
        "https://224.0.0.1/meeting.wav",
        "https://[ff02::1]/meeting.wav",
        "https://[::ffff:127.0.0.1]/meeting.wav",
    ],
)
def test_import_recording_rejects_special_use_url_addresses(raw_url):
    from services.mcp_import import _validate_public_https_url

    with pytest.raises(HTTPException) as caught:
        _validate_public_https_url(raw_url)

    assert caught.value.status_code == 400


def test_download_url_uses_one_validated_dns_answer(monkeypatch, tmp_path):
    import httpx
    from services import mcp_import

    resolver_calls: list[tuple[str, int]] = []
    transport_addresses: list[tuple[str, str]] = []

    def resolve(host, port, *args, **kwargs):
        resolver_calls.append((host, port))
        address = "8.8.8.8" if len(resolver_calls) == 1 else "10.0.0.1"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port))]

    def transport_factory(hostname, address):
        transport_addresses.append((hostname, address))

        def respond(request):
            return httpx.Response(
                200,
                headers={"content-type": "audio/wav"},
                content=b"wav",
                request=request,
            )

        return httpx.MockTransport(respond)

    monkeypatch.setattr(mcp_import.socket, "getaddrinfo", resolve)
    monkeypatch.setattr(mcp_import, "_url_import_transport", transport_factory)
    destination = tmp_path / "download.part"

    result = asyncio.run(
        mcp_import._download_url(
            "https://recordings.example/meeting.wav", destination, max_bytes=1024
        )
    )

    assert result == ("meeting.wav", "audio/wav", 3)
    assert destination.read_bytes() == b"wav"
    assert resolver_calls == [("recordings.example", 443)]
    assert transport_addresses == [("recordings.example", "8.8.8.8")]


def test_download_url_rejects_private_redirect_before_connecting(monkeypatch, tmp_path):
    import httpx
    from services import mcp_import

    dns_answers = {
        "public.example": "8.8.8.8",
        "private.example": "127.0.0.1",
    }
    requested_urls: list[str] = []
    transport_addresses: list[tuple[str, str]] = []

    def resolve(host, port, *args, **kwargs):
        address = dns_answers[host]
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port))]

    def respond(request):
        requested_urls.append(str(request.url))
        return httpx.Response(
            302,
            headers={"location": "https://private.example/internal.wav"},
            request=request,
        )

    def transport_factory(hostname, address):
        transport_addresses.append((hostname, address))
        return httpx.MockTransport(respond)

    monkeypatch.setattr(mcp_import.socket, "getaddrinfo", resolve)
    monkeypatch.setattr(mcp_import, "_url_import_transport", transport_factory)

    with pytest.raises(HTTPException) as caught:
        asyncio.run(
            mcp_import._download_url(
                "https://public.example/redirect", tmp_path / "redirect.part", 1024
            )
        )

    assert caught.value.status_code == 400
    assert requested_urls == ["https://public.example/redirect"]
    assert transport_addresses == [("public.example", "8.8.8.8")]


def test_download_url_uses_original_host_with_mocked_https_transport(
    monkeypatch, tmp_path
):
    import httpx
    from services import mcp_import

    def resolve(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", port))]

    seen: dict[str, str] = {}

    def respond(request):
        seen["url"] = str(request.url)
        seen["host"] = request.headers["host"]
        return httpx.Response(
            200,
            headers={"content-type": "audio/wav"},
            content=b"normal",
            request=request,
        )

    monkeypatch.setattr(mcp_import.socket, "getaddrinfo", resolve)
    monkeypatch.setattr(
        mcp_import,
        "_url_import_transport",
        lambda hostname, address: httpx.MockTransport(respond),
    )
    destination = tmp_path / "normal.part"

    result = asyncio.run(
        mcp_import._download_url(
            "https://media.example/normal.wav", destination, max_bytes=1024
        )
    )

    assert result == ("normal.wav", "audio/wav", 6)
    assert destination.read_bytes() == b"normal"
    assert seen == {
        "url": "https://media.example/normal.wav",
        "host": "media.example",
    }


def test_pinned_transport_connects_to_validated_ip_with_original_sni():
    import httpcore
    import httpx
    from services import mcp_import

    class RecordingStream(httpcore.AsyncMockStream):
        def __init__(self):
            super().__init__(
                [b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok"]
            )
            self.sni = None

        async def start_tls(self, ssl_context, server_hostname=None, timeout=None):
            self.sni = server_hostname
            return self

    class RecordingBackend(httpcore.AsyncNetworkBackend):
        def __init__(self):
            self.destination = None
            self.stream = RecordingStream()

        async def connect_tcp(self, host, port, **kwargs):
            self.destination = (host, port)
            return self.stream

        async def connect_unix_socket(self, path, **kwargs):
            return self.stream

        async def sleep(self, seconds):
            return None

    transport = mcp_import._PinnedHTTPTransport(
        hostname="media.example", address="8.8.8.8"
    )
    backend = RecordingBackend()
    transport._pool._network_backend._delegate = backend

    async def request():
        async with httpx.AsyncClient(transport=transport) as client:
            return await client.get("https://media.example/meeting.wav")

    response = asyncio.run(request())

    assert response.status_code == 200
    assert response.text == "ok"
    assert backend.destination == ("8.8.8.8", 443)
    assert backend.stream.sni == "media.example"
    assert response.request.headers["host"] == "media.example"


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
