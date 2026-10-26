"""Ordered STT failover uses mocked HTTP and preserves the legacy default."""

# ruff: noqa: S101

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from services.providers import impl_stt

PAYLOAD = {
    "text": "hello there",
    "segments": [{"start": 0.1, "end": 1.0, "text": "hello there"}],
    "words": [{"start": 0.1, "end": 0.5, "word": "hello"}],
    "duration": 1.5,
    "language": "fr",
    "model": "served-model",
}


@pytest.fixture(params=["parakeet", "gateway"])
def stt_case(request, tmp_path, monkeypatch):
    monkeypatch.delenv("MEETING_OPS_STT_FALLBACK_URLS", raising=False)
    monkeypatch.setenv("PARAKEET_SPARSE_RETRY", "0")
    monkeypatch.setattr(impl_stt, "STT_MAX_ATTEMPTS", 2)
    monkeypatch.setattr(impl_stt.asyncio, "sleep", AsyncMock())
    audio = tmp_path / "job-id.wav"
    audio.write_bytes(b"RIFF0000WAVEfmt audio-payload")
    if request.param == "parakeet":
        provider = impl_stt.LocalParakeetProvider(endpoint="http://primary")
        suffix = "/transcribe"
        field = "audio"
    else:
        provider = impl_stt.OpenAITranscriptionProvider(endpoint="http://primary")
        suffix = "/audio/transcriptions"
        field = "file"
    return SimpleNamespace(provider=provider, audio=audio, suffix=suffix, field=field)


@pytest.fixture
def transport(monkeypatch):
    original_client = httpx.AsyncClient
    requests = []
    timeouts = []

    def install(handler):
        def handle(request):
            requests.append(request)
            return handler(request)

        def client(**kwargs):
            timeouts.append(kwargs["timeout"])
            return original_client(transport=httpx.MockTransport(handle), **kwargs)

        monkeypatch.setattr(impl_stt.httpx, "AsyncClient", client)
        return requests, timeouts

    return install


@pytest.mark.asyncio
async def test_primary_success_never_uses_fallback(
    stt_case, transport, monkeypatch, caplog
):
    monkeypatch.setenv("MEETING_OPS_STT_FALLBACK_URLS", "http://backup")
    requests, _ = transport(lambda req: httpx.Response(200, json=PAYLOAD))
    with caplog.at_level(logging.INFO, logger=impl_stt.__name__):
        result = await stt_case.provider.transcribe(str(stt_case.audio), language="fr")
    assert [req.url.host for req in requests] == ["primary"]
    assert result["model"] == "served-model"
    assert "STT served" in caplog.text
    assert "http://primary" in caplog.text
    assert str(stt_case.audio) in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["timeout", "connection", "503", "429"])
async def test_failover_after_primary_retry_budget(
    stt_case, transport, monkeypatch, caplog, failure
):
    monkeypatch.setenv("MEETING_OPS_STT_FALLBACK_URLS", "http://backup")

    def handle(request):
        if request.url.host == "primary":
            if failure == "timeout":
                raise httpx.ReadTimeout("offline", request=request)
            if failure == "connection":
                raise httpx.ConnectError("offline", request=request)
            return httpx.Response(int(failure), text="offline")
        return httpx.Response(200, json=PAYLOAD)

    requests, timeouts = transport(handle)
    with caplog.at_level(logging.INFO, logger=impl_stt.__name__):
        result = await stt_case.provider.transcribe(str(stt_case.audio), language="fr")
    assert [req.url.host for req in requests] == ["primary", "primary", "backup"]
    assert all(req.url.path == stt_case.suffix for req in requests)
    assert all(stt_case.audio.read_bytes() in req.content for req in requests)
    assert all(f'name="{stt_case.field}"'.encode() in req.content for req in requests)
    assert len(set(timeouts)) == 1
    assert timeouts[0] == impl_stt._http_timeout_for_path(
        str(stt_case.audio), base=60.0, per_mb=2.0
    )
    assert result["text"] == "hello there"
    assert result["segments"][0]["start"] == 0.1
    assert result["words"][0]["word"] == "hello"
    assert result["model"] == "served-model"
    assert result["language"] == "fr"
    assert result.get("error") is None
    assert "STT served" in caplog.text
    assert "http://backup" in caplog.text


@pytest.mark.asyncio
async def test_fallbacks_run_in_order_and_skip_blank_duplicate_urls(
    stt_case, transport, monkeypatch
):
    monkeypatch.setenv(
        "MEETING_OPS_STT_FALLBACK_URLS",
        " , http://primary/, http://backup-1/ ,http://backup-1,http://backup-2,",
    )

    def handle(request):
        if request.url.host != "backup-2":
            return httpx.Response(503, text="offline")
        return httpx.Response(200, json=PAYLOAD)

    requests, _ = transport(handle)
    result = await stt_case.provider.transcribe(str(stt_case.audio))
    assert [req.url.host for req in requests] == [
        "primary",
        "primary",
        "backup-1",
        "backup-1",
        "backup-2",
    ]
    assert result["text"] == "hello there"


@pytest.mark.asyncio
async def test_all_endpoints_fail_with_last_service_error(
    stt_case, transport, monkeypatch
):
    monkeypatch.setenv("MEETING_OPS_STT_FALLBACK_URLS", "http://backup")
    requests, _ = transport(
        lambda req: httpx.Response(503, text=f"{req.url.host} down")
    )
    result = await stt_case.provider.transcribe(str(stt_case.audio))
    assert [req.url.host for req in requests] == [
        "primary",
        "primary",
        "backup",
        "backup",
    ]
    assert result["text"] == ""
    assert result["segments"] == []
    assert result["error"] == "Transcription service error 503: backup down"


@pytest.mark.asyncio
async def test_permanent_request_error_still_fails_fast(
    stt_case, transport, monkeypatch
):
    monkeypatch.setenv("MEETING_OPS_STT_FALLBACK_URLS", "http://backup")
    requests, _ = transport(lambda req: httpx.Response(400, text="audio too long"))
    result = await stt_case.provider.transcribe(str(stt_case.audio))
    assert len(requests) == 1
    assert result["error"] == "Transcription service error 400: audio too long"


@pytest.mark.asyncio
async def test_empty_success_is_not_an_endpoint_failure(
    stt_case, transport, monkeypatch
):
    monkeypatch.setenv("MEETING_OPS_STT_FALLBACK_URLS", "http://backup")
    requests, _ = transport(lambda req: httpx.Response(200, json={"segments": []}))
    result = await stt_case.provider.transcribe(str(stt_case.audio))
    assert len(requests) == 1
    assert result["segments"] == []
    assert result.get("error") is None


@pytest.mark.asyncio
@pytest.mark.parametrize("config", [None, "", " , , "])
async def test_unset_or_empty_config_preserves_failure_result_and_attempts(
    stt_case, transport, monkeypatch, caplog, config
):
    if config is not None:
        monkeypatch.setenv("MEETING_OPS_STT_FALLBACK_URLS", config)
    requests, _ = transport(lambda req: httpx.Response(503, text="offline"))
    with caplog.at_level(logging.INFO, logger=impl_stt.__name__):
        result = await stt_case.provider.transcribe(str(stt_case.audio))
    assert [req.url.host for req in requests] == ["primary", "primary"]
    assert result == {
        "text": "",
        "segments": [],
        "words": [],
        "duration": 0.0,
        "language": "en",
        "confidence": 0.0,
        "model": stt_case.provider.model,
        "rtf": None,
        "error": "Transcription service error 503: offline",
    }
    assert "STT served" not in caplog.text


@pytest.mark.asyncio
async def test_missing_file_never_uses_any_endpoint(stt_case, transport, monkeypatch):
    monkeypatch.setenv("MEETING_OPS_STT_FALLBACK_URLS", "http://backup")
    requests, _ = transport(lambda req: httpx.Response(200, json=PAYLOAD))
    stt_case.audio.unlink()
    result = await stt_case.provider.transcribe(str(stt_case.audio))
    assert requests == []
    assert result == impl_stt._empty_result(stt_case.provider.model, "en")


@pytest.mark.asyncio
async def test_success_log_redacts_url_credentials_and_query(
    stt_case, transport, monkeypatch, caplog
):
    monkeypatch.setenv("MEETING_OPS_STT_FALLBACK_URLS", "http://backup")
    stt_case.provider.endpoint = "http://user:placeholder@primary/v1?token=placeholder"
    transport(lambda req: httpx.Response(200, json=PAYLOAD))
    with caplog.at_level(logging.INFO, logger=impl_stt.__name__):
        await stt_case.provider.transcribe(str(stt_case.audio))
    assert "http://***@primary/v1?token=***" in caplog.text
    assert "placeholder" not in caplog.text
    assert "user:" not in caplog.text
