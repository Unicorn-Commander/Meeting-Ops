"""Tests for ``LocalSpeakerSvcProvider.diarize`` — the canonical production
diarizer (pyannote 3.1 + wespeaker embeddings on meet-speaker-svc).

The reprocess + upload pipelines both call this provider's ``diarize`` to
draw speaker boundaries and pull per-turn voice embeddings. It was the only
shipped diarizer without direct test coverage, so this pins its contract:

  1. A 200 response from speaker-svc /diarize parses each segment's speaker
     + embedding (and stamps the ``backend`` from the payload).
  2. A missing audio path short-circuits to [] before any HTTP call (the
     cross-host topology guard — the file may not exist on the svc host).
  3. An HTTP 500 is swallowed and yields [] — diarization is non-fatal to
     the pipeline; we keep the un-diarized transcript rather than 500.

httpx is mocked with httpx.MockTransport (no network), mirroring
test_sortformer_hybrid.py's approach.
"""
from __future__ import annotations

import asyncio

import httpx
import pytest


def _patch_mock_transport(monkeypatch, handler):
    """Route impl_diarization.httpx.AsyncClient(...) through a MockTransport
    handler instead of the network. Drops the timeout kwarg the provider
    passes (MockTransport ignores it)."""
    import services.providers.impl_diarization as impl

    real_async_client = httpx.AsyncClient

    def _factory(*_args, **_kwargs):
        return real_async_client(transport=httpx.MockTransport(handler))

    monkeypatch.setattr(impl.httpx, "AsyncClient", _factory)


def _provider():
    from services.providers.impl_diarization import LocalSpeakerSvcProvider

    return LocalSpeakerSvcProvider(endpoint="http://sp:8889")


def test_diarize_parses_segments_speaker_and_embedding(monkeypatch, tmp_path):
    wav = tmp_path / "session.wav"
    wav.write_bytes(b"RIFF....WAVE")  # content irrelevant; transport mocked

    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["method"] = request.method
        captured["content_type"] = request.headers.get("content-type", "")
        return httpx.Response(
            200,
            json={
                "segments": [
                    {"start": 0.0, "end": 2.5, "speaker": "SPEAKER_00", "embedding": [0.1, 0.2]},
                    {"start": 2.5, "end": 4.0, "speaker": "SPEAKER_01", "embedding": [0.3, 0.4]},
                ],
                "num_speakers": 2,
                "backend": "pyannote",
            },
        )

    _patch_mock_transport(monkeypatch, handler)
    segs = asyncio.run(_provider().diarize(str(wav)))

    assert captured["method"] == "POST"
    assert captured["url"].endswith("/diarize")
    # Audio is streamed as a multipart upload (host-topology-proof).
    assert captured["content_type"].startswith("multipart/form-data")
    assert len(segs) == 2
    assert segs[0]["speaker"] == "SPEAKER_00"
    assert segs[0]["embedding"] == [0.1, 0.2]
    assert segs[1]["speaker"] == "SPEAKER_01"
    # backend is stamped onto every segment from the payload.
    assert segs[0]["backend"] == "pyannote"
    assert segs[1]["backend"] == "pyannote"


def test_diarize_missing_file_returns_empty(tmp_path):
    missing = tmp_path / "nope.wav"
    # No transport patch needed — the provider must short-circuit before any
    # HTTP call when the audio path doesn't exist on disk.
    assert asyncio.run(_provider().diarize(str(missing))) == []


def test_diarize_http_error_returns_empty(monkeypatch, tmp_path):
    wav = tmp_path / "session.wav"
    wav.write_bytes(b"RIFF")

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="speaker-svc exploded")

    _patch_mock_transport(monkeypatch, handler)
    # 500 raises HTTPStatusError internally; the provider swallows it and
    # returns [] so a transient svc outage never fails the pipeline.
    assert asyncio.run(_provider().diarize(str(wav))) == []
