"""Unit coverage for the opt-in Meeting-Ops org gateway route."""
from __future__ import annotations

import asyncio

import pytest


class _FakeKeyProvider:
    def __init__(self, key: str = "fictional-org-key"):
        self.key = key
        self.calls: list[int] = []

    def get_key(self, org_id: int):
        from services.providers.org_route import OrgGatewayKey

        self.calls.append(org_id)
        return OrgGatewayKey(self.key)


class _FakeUsageReporter:
    def __init__(self):
        self.events: list[dict] = []

    def report(self, **event):
        self.events.append(event)


def _registry(monkeypatch, *, settings=None, key_provider=None, reporter=None):
    from services.providers.registry import ProviderRegistry

    settings = settings or {}
    registry = ProviderRegistry(
        None,
        gateway_key_provider=key_provider or _FakeKeyProvider(),
        usage_reporter=reporter,
    )
    monkeypatch.setattr(
        registry,
        "_get_settings",
        lambda _org_id, service_kind: dict(settings.get(service_kind, {})),
    )
    return registry


def test_flag_off_preserves_old_settings_and_direct_hosts(monkeypatch):
    from services.providers.impl_embeddings import InfinityProvider
    from services.providers.impl_stt import LocalParakeetProvider
    from services.providers.impl_tts import VibeVoiceProvider

    monkeypatch.delenv("MEETING_OPS_USE_ORG_ROUTE", raising=False)
    monkeypatch.setenv("MEETING_OPS_LLM_URL", "http://legacy.example/v1")
    monkeypatch.setenv("MEETING_OPS_LLM_MODEL", "legacy-model")
    registry = _registry(
        monkeypatch,
        settings={
            "llm": {
                "provider_name": "",
                "endpoint_url": "",
                "model_name": "",
                "api_key_encrypted": "",
                "overrides": {},
            },
            "embeddings": {
                "provider_name": "infinity",
                "endpoint_url": "http://legacy-embed.example/v1",
                "model_name": "legacy-embed-model",
            },
            "stt": {
                "provider_name": "parakeet",
                "endpoint_url": "http://legacy-stt.example",
                "model_name": "legacy-parakeet",
            },
            "tts": {
                "provider_name": "vibevoice",
                "endpoint_url": "http://legacy-tts.example",
                "model_name": "alice",
            },
        },
    )

    llm = registry.get_llm(7, task="quality")
    assert llm.endpoint == "http://legacy.example/v1"
    assert llm.model == "legacy-model"
    assert not llm.org_route

    assert isinstance(registry.get_embeddings(7), InfinityProvider)
    assert registry.get_embeddings(7).endpoint == "http://legacy-embed.example/v1"
    assert isinstance(registry.get_stt(7), LocalParakeetProvider)
    assert registry.get_stt(7).endpoint == "http://legacy-stt.example"
    assert isinstance(registry.get_tts(7), VibeVoiceProvider)
    assert registry.get_tts(7).endpoint == "http://legacy-tts.example"


def test_flag_on_uses_bare_routes_and_ignores_org_settings(monkeypatch, caplog):
    from services.providers.impl_embeddings import InfinityProvider
    from services.providers.impl_llm import LiteLLMProvider
    from services.providers.impl_stt import OpenAITranscriptionProvider
    from services.providers.impl_tts import KokoroProvider

    monkeypatch.setenv("MEETING_OPS_USE_ORG_ROUTE", "true")
    monkeypatch.setenv("ORG_GATEWAY_BASE_URL", "https://gateway.example/v1")
    key_provider = _FakeKeyProvider()
    registry = _registry(
        monkeypatch,
        key_provider=key_provider,
        settings={
            "llm": {"provider_name": "openrouter", "endpoint_url": "https://old.example", "model_name": "old"},
            "embeddings": {"provider_name": "infinity", "endpoint_url": "https://old.example/v1", "model_name": "old"},
            "stt": {"provider_name": "parakeet", "endpoint_url": "https://old.example", "model_name": "old"},
            "tts": {"provider_name": "vibevoice", "endpoint_url": "https://old.example", "model_name": "old"},
        },
        reporter=_FakeUsageReporter(),
    )

    with caplog.at_level("WARNING"):
        batch = registry.get_llm(7, task="quality", model_override="old-model", user_id=11)
        concierge = registry.get_llm(7, task="chat")
        embeddings = registry.get_embeddings(7)
        stt = registry.get_stt(7, provider_override="whisper", model_override="old")
        tts = registry.get_tts(7)

    assert isinstance(batch, LiteLLMProvider)
    assert batch.endpoint == "https://gateway.example/v1"
    assert batch.model == "batch"
    assert batch.route == "batch"
    assert batch.feature == "summary"
    assert batch.api_key == "fictional-org-key"
    assert batch.user_id == 11
    assert concierge.model == "concierge"
    assert concierge.route == "concierge"
    assert concierge.feature == "chat"
    assert isinstance(embeddings, InfinityProvider)
    assert embeddings.model == "embed"
    assert embeddings.route == "embed"
    assert isinstance(stt, OpenAITranscriptionProvider)
    assert stt.model == "voice"
    assert stt.route == "voice"
    assert isinstance(tts, KokoroProvider)
    assert tts.model == "voice"
    assert tts.route == "voice"
    assert "OrgProviderSettings ignored" in caplog.text
    assert key_provider.calls == [7, 7, 7, 7, 7]


def test_org_llm_request_has_gateway_headers_and_route(monkeypatch):
    from services.providers.impl_llm import LiteLLMProvider

    monkeypatch.setenv("MEETING_OPS_USE_ORG_ROUTE", "true")
    monkeypatch.setenv("ORG_GATEWAY_BASE_URL", "https://gateway.example/v1")
    registry = _registry(monkeypatch, key_provider=_FakeKeyProvider())
    provider = registry.get_llm(12, task="chat", user_id="user-12")
    seen = {}

    class _Response:
        status_code = 200

        def json(self):
            return {"choices": [{"message": {"content": "hello"}}]}

        def raise_for_status(self):
            return None

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, **kwargs):
            seen.update(url=url, **kwargs)
            return _Response()

    monkeypatch.setattr("services.providers.impl_llm.httpx.AsyncClient", _Client)
    assert isinstance(provider, LiteLLMProvider)
    assert asyncio.run(provider.chat("system", "user")) == "hello"
    assert seen["url"] == "https://gateway.example/v1/chat/completions"
    assert seen["headers"] == {
        "Content-Type": "application/json",
        "Authorization": "Bearer fictional-org-key",
        "X-UC-Org-Id": "12",
        "X-UC-App": "meeting-ops",
        "X-UC-Feature": "chat",
        "X-UC-User-Id": "user-12",
    }
    assert seen["json"]["model"] == "concierge"


def test_org_embeddings_request_has_gateway_headers_and_route(monkeypatch):
    from services.providers.impl_embeddings import InfinityProvider

    provider = InfinityProvider(
        endpoint="https://gateway.example/v1",
        api_key="fictional-org-key",
        model="embed",
        route="embed",
        org_id=13,
        user_id="user-13",
    )
    seen = {}

    class _Response:
        status_code = 200

        def json(self):
            return {"data": [{"embedding": [0.1, 0.2]}]}

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, **kwargs):
            seen.update(url=url, **kwargs)
            return _Response()

    monkeypatch.setattr("services.providers.impl_embeddings.httpx.AsyncClient", _Client)
    assert asyncio.run(provider.embed(["fictional text"])) == [[0.1, 0.2]]
    assert seen["url"] == "https://gateway.example/v1/embeddings"
    assert seen["json"]["model"] == "embed"
    assert seen["headers"] == {
        "Content-Type": "application/json",
        "Authorization": "Bearer fictional-org-key",
        "X-UC-Org-Id": "13",
        "X-UC-App": "meeting-ops",
        "X-UC-Feature": "embedding",
        "X-UC-User-Id": "user-13",
    }


def test_org_stt_reports_seconds_and_does_not_use_fallback(monkeypatch, tmp_path):
    from services.providers.impl_stt import OpenAITranscriptionProvider

    audio = tmp_path / "fictional-meeting.wav"
    audio.write_bytes(b"fictional audio")
    reporter = _FakeUsageReporter()
    provider = OpenAITranscriptionProvider(
        endpoint="https://gateway.example/v1",
        model="voice",
        api_key="fictional-org-key",
        route="voice",
        org_id=5,
        usage_reporter=reporter,
        work_id="upload-5",
    )
    seen = {}

    class _Response:
        status_code = 200
        text = ""

        def json(self):
            return {
                "text": "hello",
                "duration": 42.5,
                "segments": [{"start": 0, "end": 42.5, "text": "hello"}],
            }

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, **kwargs):
            seen.update(url=url, **kwargs)
            return _Response()

    monkeypatch.setenv("MEETING_OPS_STT_FALLBACK_URLS", "https://old.example/v1")
    monkeypatch.setattr("services.providers.impl_stt.httpx.AsyncClient", _Client)
    result = asyncio.run(provider.transcribe(str(audio)))

    assert result["duration"] == pytest.approx(42.5)
    assert seen["url"] == "https://gateway.example/v1/audio/transcriptions"
    assert seen["data"]["model"] == "voice"
    assert seen["headers"]["X-UC-Org-Id"] == "5"
    assert seen["headers"]["X-UC-App"] == "meeting-ops"
    assert reporter.events == [{
        "organization_id": 5,
        "metric": "stt_audio_seconds",
        "quantity": 42.5,
        "work_id": "upload-5",
        "feature": "stt",
    }]


def test_org_tts_reports_characters_and_uses_voice_route(monkeypatch):
    from services.providers.impl_tts import KokoroProvider

    reporter = _FakeUsageReporter()
    provider = KokoroProvider(
        endpoint="https://gateway.example/v1",
        api_key="fictional-org-key",
        route="voice",
        org_id=9,
        usage_reporter=reporter,
        work_id="tts-9",
    )
    seen = {}

    class _Response:
        status_code = 200
        content = b"audio"
        text = ""

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, **kwargs):
            seen.update(url=url, **kwargs)
            return _Response()

    monkeypatch.setattr("httpx.AsyncClient", _Client)
    assert asyncio.run(provider.synthesize("hello world")) == b"audio"
    assert seen["url"] == "https://gateway.example/v1/audio/speech"
    assert seen["json"]["model"] == "voice"
    assert seen["headers"]["X-UC-Org-Id"] == "9"
    assert reporter.events == [{
        "organization_id": 9,
        "metric": "tts_characters",
        "quantity": 11.0,
        "work_id": "tts-9",
        "feature": "tts",
    }]


def test_gateway_failure_is_visible_and_names_gateway(monkeypatch):
    from services.providers.impl_llm import LLMUnavailable

    monkeypatch.setenv("MEETING_OPS_USE_ORG_ROUTE", "true")
    monkeypatch.setenv("ORG_GATEWAY_BASE_URL", "https://gateway.example/v1")
    provider = _registry(monkeypatch, key_provider=_FakeKeyProvider()).get_llm(3, task="quality")

    class _Response:
        status_code = 503
        text = "gateway unavailable"

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, **kwargs):
            assert url.startswith("https://gateway.example/")
            return _Response()

    monkeypatch.setattr("services.providers.impl_llm.httpx.Client", _Client)
    with pytest.raises(LLMUnavailable, match="Gateway"):
        provider.chat_sync("system", "user")


def test_org_gateway_key_provider_caches_for_ten_minutes(monkeypatch):
    from services.providers import org_route

    monkeypatch.setenv("OPS_CENTER_INTERNAL_URL", "https://ops.example")
    monkeypatch.setenv("OPS_CENTER_SERVICE_TOKEN", "fictional-service-token")
    calls = []

    class _Response:
        status_code = 200

        def json(self):
            return {"key": "fictional-org-key", "expiresAt": "2099-01-01T00:00:00Z"}

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url, **kwargs):
            calls.append((url, kwargs))
            return _Response()

    monkeypatch.setattr(org_route.httpx, "Client", _Client)
    provider = org_route.OpsCenterOrgGatewayKeyProvider()
    assert provider.get_key(14).key == "fictional-org-key"
    assert provider.get_key(14).key == "fictional-org-key"
    assert len(calls) == 1
    assert calls[0][0] == "https://ops.example/api/v1/internal/orgs/14/gateway-key"


def test_quota_hours_report_is_idempotent_per_recording(monkeypatch):
    from services import quotas

    class _Query:
        def __init__(self, *, scalar_value=None, rows=()):
            self.scalar_value = scalar_value
            self.rows = rows

        def filter(self, *args):
            return self

        def scalar(self):
            return self.scalar_value

        def all(self):
            return list(self.rows)

    class _DB:
        def __init__(self):
            self.calls = 0

        def query(self, *args):
            self.calls += 1
            if self.calls == 1:
                return _Query(scalar_value=7200.0)
            return _Query(rows=[(44, 7200.0)])

    reporter = _FakeUsageReporter()
    monkeypatch.setenv("MEETING_OPS_USE_ORG_ROUTE", "true")
    monkeypatch.setattr("services.providers.usage.get_usage_reporter", lambda: reporter)
    assert quotas.sum_monthly_audio_seconds(_DB(), 21) == 7200.0
    assert reporter.events == [{
        "organization_id": 21,
        "metric": "upload_audio_hours",
        "quantity": 2.0,
        "work_id": "upload-audio:21:44",
        "feature": "upload",
    }]
