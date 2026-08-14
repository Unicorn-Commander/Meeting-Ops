"""STT transient-failure retry behaviour.

Regression cover for: a single transient 500 from the transcription service
permanently failed the session, discarding a multi-hour recording that a retry
seconds later would have transcribed fine.
"""
from __future__ import annotations

import httpx
import pytest

from services.providers import impl_stt


@pytest.fixture()
def audio_file(tmp_path):
    p = tmp_path / "clip.wav"
    p.write_bytes(b"RIFF0000WAVEfmt ")
    return str(p)


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """Keep the backoff logic exercised but the suite fast."""
    async def _instant(_seconds):
        return None
    monkeypatch.setattr(impl_stt.asyncio, "sleep", _instant)


def _mock_transport(monkeypatch, responses):
    """Feed ``responses`` (Response | Exception) to successive POSTs."""
    calls = {"n": 0}

    async def _post(self, url, **kwargs):
        idx = min(calls["n"], len(responses) - 1)
        calls["n"] += 1
        outcome = responses[idx]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(httpx.AsyncClient, "post", _post)
    return calls


def _ok(payload=None):
    return httpx.Response(
        200,
        json=payload or {"text": "hello", "segments": [], "duration": 1.0},
        request=httpx.Request("POST", "http://stt/transcribe"),
    )


def _err(status, body="boom"):
    return httpx.Response(
        status, text=body, request=httpx.Request("POST", "http://stt/transcribe")
    )


@pytest.mark.asyncio
async def test_retries_transient_500_then_succeeds(monkeypatch, audio_file):
    calls = _mock_transport(monkeypatch, [_err(500), _ok()])
    provider = impl_stt.LocalParakeetProvider()

    result = await provider.transcribe(audio_file)

    assert calls["n"] == 2, "should have retried the 500 exactly once"
    assert result["text"] == "hello"
    assert result.get("error") is None


@pytest.mark.asyncio
async def test_gives_up_after_max_attempts_and_reports_reason(monkeypatch, audio_file):
    calls = _mock_transport(monkeypatch, [_err(500, "Internal Server Error")])
    provider = impl_stt.LocalParakeetProvider()

    result = await provider.transcribe(audio_file)

    assert calls["n"] == impl_stt.STT_MAX_ATTEMPTS
    assert result["segments"] == []
    assert "500" in result["error"]
    assert "Internal Server Error" in result["error"]


@pytest.mark.asyncio
async def test_permanent_4xx_is_not_retried(monkeypatch, audio_file):
    """'audio too long' must surface immediately, not after N pointless retries."""
    calls = _mock_transport(monkeypatch, [_err(400, "audio too long")])
    provider = impl_stt.LocalParakeetProvider()

    result = await provider.transcribe(audio_file)

    assert calls["n"] == 1, "4xx is permanent; retrying wastes minutes on a doomed job"
    assert "400" in result["error"]
    assert "audio too long" in result["error"]


@pytest.mark.asyncio
async def test_429_is_treated_as_transient(monkeypatch, audio_file):
    calls = _mock_transport(monkeypatch, [_err(429), _ok()])
    provider = impl_stt.LocalParakeetProvider()

    result = await provider.transcribe(audio_file)

    assert calls["n"] == 2
    assert result["text"] == "hello"


@pytest.mark.asyncio
async def test_timeout_is_retried(monkeypatch, audio_file):
    calls = _mock_transport(monkeypatch, [httpx.TimeoutException("slow"), _ok()])
    provider = impl_stt.LocalParakeetProvider()

    result = await provider.transcribe(audio_file)

    assert calls["n"] == 2
    assert result["text"] == "hello"


@pytest.mark.asyncio
async def test_network_error_is_retried_then_reported(monkeypatch, audio_file):
    calls = _mock_transport(monkeypatch, [httpx.ConnectError("refused")])
    provider = impl_stt.LocalParakeetProvider()

    result = await provider.transcribe(audio_file)

    assert calls["n"] == impl_stt.STT_MAX_ATTEMPTS
    assert "Could not reach the transcription service" in result["error"]


@pytest.mark.asyncio
async def test_file_is_reread_on_each_attempt(monkeypatch, audio_file):
    """httpx consumes the stream on send; a reused handle uploads zero bytes."""
    seen: list[int] = []

    async def _post(self, url, **kwargs):
        handle = kwargs["files"]["audio"][1]
        seen.append(len(handle.read()))
        if len(seen) < 2:
            return _err(503)
        return _ok()

    monkeypatch.setattr(httpx.AsyncClient, "post", _post)

    result = await impl_stt.LocalParakeetProvider().transcribe(audio_file)

    assert len(seen) == 2
    assert seen[0] == seen[1] > 0, "retry must resend the full payload"
    assert result["text"] == "hello"


@pytest.mark.asyncio
async def test_whisper_provider_also_retries(monkeypatch, audio_file):
    calls = _mock_transport(
        monkeypatch,
        [_err(500), _ok({"text": "hi", "segments": [], "duration": 1.0})],
    )

    result = await impl_stt.LocalWhisperProvider().transcribe(audio_file)

    assert calls["n"] == 2
    assert result["text"] == "hi"


@pytest.mark.asyncio
async def test_gateway_provider_also_retries(monkeypatch, audio_file):
    calls = _mock_transport(
        monkeypatch,
        [_err(502), _ok({"text": "yo", "segments": [], "duration": 1.0})],
    )

    result = await impl_stt.OpenAITranscriptionProvider().transcribe(audio_file)

    assert calls["n"] == 2
    assert result["text"] == "yo"


@pytest.mark.asyncio
async def test_missing_file_short_circuits(monkeypatch, tmp_path):
    calls = _mock_transport(monkeypatch, [_ok()])

    result = await impl_stt.LocalParakeetProvider().transcribe(
        str(tmp_path / "nope.wav")
    )

    assert calls["n"] == 0, "a missing file must never hit the network"
    assert result["segments"] == []
