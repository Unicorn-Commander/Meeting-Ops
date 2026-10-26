"""Status responses never expose configured URL credentials or query secrets."""

from __future__ import annotations

import json
from unittest.mock import patch

import httpx
import pytest

from utils.url_redaction import URL_REDACTION_PLACEHOLDER, redact_url


FIXTURE_PASS = "fixture-pass"
FIXTURE_USER = "fixture-user"
FIXTURE_QUERY_SECRETS = (
    "fixture-token",
    "fixture-key",
    "fixture-secret",
    "fixture-password",
    "fixture-signature",
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "https://fixture-user:fixture-pass@voice.example.test:443/v1/health"
            "?token=fixture-token&mode=fixture-mode",
            "https://***@voice.example.test:443/v1/health"
            "?token=***&mode=fixture-mode",
        ),
        (
            "redis://:fixture-pass@cache.example.test:6379/4"
            "?api_key=fixture-key&db=4",
            "redis://***@cache.example.test:6379/4?api_key=***&db=4",
        ),
        (
            "postgresql://fixture-user:REMOVED@db.example.test:5432/meetings"
            "?sslmode=require&password=fixture-password",
            "postgresql://***@db.example.test:5432/meetings"
            "?sslmode=require&password=***",
        ),
    ],
)
def test_redact_url_preserves_routing_data_and_masks_secrets(raw, expected):
    assert redact_url(raw) == expected


@pytest.mark.parametrize("raw", ["", None, "not a URL", "https://[invalid"])
def test_redact_url_never_raises_for_malformed_values(raw):
    result = redact_url(raw)
    assert result in ("", URL_REDACTION_PLACEHOLDER)
    assert FIXTURE_PASS not in result


def _fixture_urls() -> dict[str, str]:
    return {
        "SPEAKER_SVC_URL": (
            "https://fixture-user:fixture-pass@voice.example.test:443/?"
            "token=fixture-token&mode=fixture-mode"
        ),
        "PARAKEET_SERVER_URL": (
            "https://fixture-user:fixture-pass@stt.example.test:443/?"
            "api_key=fixture-key"
        ),
        "SORTFORMER_URL": (
            "https://fixture-user:fixture-pass@sortformer.example.test:8896/?"
            "secret=fixture-secret"
        ),
        "WHISPER_SERVER_URL": (
            "https://fixture-user:fixture-pass@whisper.example.test:8178/?"
            "password=fixture-password"
        ),
        "KOKORO_ENDPOINT": (
            "https://fixture-user:fixture-pass@tts.example.test:8880/?"
            "signature=fixture-signature"
        ),
        "INFINITY_ENDPOINT": (
            "https://fixture-user:fixture-pass@infinity.example.test:8086/v1?"
            "access_token=fixture-token"
        ),
        "INFINITY_EMBEDDING_ENDPOINT": (
            "https://fixture-user:fixture-pass@embed.example.test:8086/v1?"
            "key=fixture-key"
        ),
        "OPENAI_API_BASE": (
            "https://fixture-user:fixture-pass@llm.example.test:4000/v1?"
            "auth=fixture-secret"
        ),
        "MEETING_OPS_SUMMARIZER_URL": (
            "https://fixture-user:fixture-pass@summarizer.example.test:8080/v1?"
            "sig=fixture-signature"
        ),
        "MEETING_OPS_LLM_URL": (
            "https://fixture-user:fixture-pass@direct-llm.example.test:8080/v1?"
            "token=fixture-token"
        ),
        "STT_OPENAI_URL": (
            "https://fixture-user:fixture-pass@stt-openai.example.test:8080/v1?"
            "password=fixture-password"
        ),
        "VIBEVOICE_ENDPOINT": (
            "https://fixture-user:fixture-pass@vibevoice.example.test:8882/?"
            "api_key=fixture-key"
        ),
        "GARAGE_ENDPOINT_URL": (
            "https://fixture-user:fixture-pass@garage.example.test:3900/?"
            "secret=fixture-secret"
        ),
        "QDRANT_URL": (
            "https://fixture-user:fixture-pass@qdrant.example.test:6333/?"
            "token=fixture-token"
        ),
        "REDIS_URL": (
            "redis://fixture-user:fixture-pass@redis.example.test:6379/4?"
            "password=fixture-password"
        ),
        "DATABASE_URL": (
            "postgresql://fixture-user:REMOVED@db.example.test:5432/meetings?"
            "password=fixture-password"
        ),
    }


@pytest.mark.parametrize("path", ["/api/ready", "/api/status", "/api/system/pipeline"])
def test_public_status_endpoints_mask_fixture_url_secrets(client, monkeypatch, path):
    for name, value in _fixture_urls().items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("MEETING_OPS_SUMMARIZER_MODEL", "fixture-model")
    monkeypatch.setenv("KOKORO_API_KEY", "fixture-api-key")
    monkeypatch.setenv("INFINITY_API_KEY", "fixture-api-key")

    async def successful_probe():
        return {"ok": True}

    async def successful_llm_probe():
        return {"ok": True, "model": "fixture-model"}

    async def successful_pipeline_probe(_url: str):
        return {
            "model": "fixture-model",
            "model_loaded": True,
            "diarizer_available": True,
            "gpu_name": "fixture-gpu",
        }

    from services import readiness
    from api import system_caps

    # The four non-HTTP probes are replaced directly. HTTP probes use a
    # MockTransport below, so this test cannot contact any configured host.
    fake_probes = {
        "database": successful_probe,
        "redis": successful_probe,
        "qdrant": successful_probe,
        "llm": successful_llm_probe,
    }
    real_async_client = httpx.AsyncClient

    def mock_async_client(**kwargs):
        return real_async_client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json={"status": "ok"})
            ),
            **kwargs,
        )

    monkeypatch.setattr(readiness.httpx, "AsyncClient", mock_async_client)

    with (
        patch.dict(readiness._PROBES, fake_probes),
        patch.object(system_caps, "_probe_json", successful_pipeline_probe),
    ):
        response = client.get(path)

    assert response.status_code == 200, response.text
    payload_text = json.dumps(response.json(), sort_keys=True)
    assert f"{FIXTURE_USER}:" not in payload_text
    assert FIXTURE_PASS not in payload_text
    for secret in FIXTURE_QUERY_SECRETS:
        assert secret not in payload_text
