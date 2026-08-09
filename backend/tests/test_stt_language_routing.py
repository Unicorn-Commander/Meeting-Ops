"""Language-aware STT routing (ProviderRegistry.get_stt).

Parakeet — the default STT — is ENGLISH-ONLY: its `language` request param is
cosmetic, so non-English audio comes back as confidently-garbled English-ish
text (measured 2026-08-09: French at 58% WER with reported confidence 0.97,
while whisper multilingual medium scored 4.2% WER on the same clip). That is
silent data corruption, not a degraded transcript.

These tests pin the routing contract that stops it:

    1. per-upload ``provider_override`` is ALWAYS honored as-is
    2. an explicit non-English ``language`` (per-call arg, else the org stt
       row's ``overrides["language"]``) reroutes English-only providers
       (parakeet + the gateway shim that wraps it) to the multilingual
       whisper endpoint — and FAILS LOUD if none is configured
    3. org Provider Settings row
    4. STT_DEFAULT_PROVIDER env (default parakeet)

English ("en", "en-US", …), "auto", "", and absent languages change nothing.
"""
from __future__ import annotations

import pytest


def _models():
    from auth.models import Organization
    from database.database import SessionLocal
    from database.models import OrgProviderSettings
    return Organization, SessionLocal, OrgProviderSettings


def _seed_org(slug: str) -> int:
    Organization, SessionLocal, _ = _models()
    db = SessionLocal()
    try:
        org = db.query(Organization).filter(Organization.slug == slug).first()
        if not org:
            org = Organization(name=slug.replace("-", " ").title(), slug=slug, is_active=True)
            db.add(org)
            db.commit()
            db.refresh(org)
        return org.id
    finally:
        db.close()


def _set_stt_settings(org_id: int, **kwargs) -> None:
    _, SessionLocal, OrgProviderSettings = _models()
    db = SessionLocal()
    try:
        row = (
            db.query(OrgProviderSettings)
            .filter(
                OrgProviderSettings.organization_id == org_id,
                OrgProviderSettings.service_kind == "stt",
            )
            .first()
        )
        if row is None:
            row = OrgProviderSettings(
                organization_id=org_id,
                service_kind="stt",
                provider_name=kwargs.pop("provider_name", "parakeet"),
            )
            db.add(row)
        for key, value in kwargs.items():
            setattr(row, key, value)
        db.commit()
    finally:
        db.close()


def _get_stt(org_id: int, **kwargs):
    from database.database import SessionLocal
    from services.providers.registry import ProviderRegistry
    db = SessionLocal()
    try:
        return ProviderRegistry(db).get_stt(org_id, **kwargs)
    finally:
        db.close()


@pytest.fixture()
def whisper_env(monkeypatch):
    """A configured multilingual whisper endpoint, like the bigboy compose."""
    monkeypatch.setenv("WHISPER_SERVER_URL", "http://meet-whisper:8178")
    monkeypatch.setenv("WHISPER_MODEL_NAME", "whisper.cpp-medium-q8_0")
    monkeypatch.delenv("STT_DEFAULT_PROVIDER", raising=False)


# ---------------------------------------------------------------------------
# The language predicate
# ---------------------------------------------------------------------------
def test_is_non_english_language_predicate():
    from services.providers.registry import is_non_english_language

    # English/default/auto-ish values must NOT reroute.
    for value in (None, "", "  ", "en", "EN", "en-US", "en_GB", "auto", "AUTO"):
        assert is_non_english_language(value) is False, value

    # Explicit non-English values must.
    for value in ("fr", "FR", "fr-FR", "fr_CA", "de", "es", "pt-BR", "ja"):
        assert is_non_english_language(value) is True, value


# ---------------------------------------------------------------------------
# Default behavior is bit-for-bit unchanged
# ---------------------------------------------------------------------------
def test_default_no_language_routes_parakeet(client, whisper_env):
    from services.providers.impl_stt import LocalParakeetProvider

    org_id = _seed_org("langroute-default")
    provider = _get_stt(org_id)
    assert isinstance(provider, LocalParakeetProvider)


def test_english_and_auto_variants_stay_on_parakeet(client, whisper_env):
    from services.providers.impl_stt import LocalParakeetProvider

    org_id = _seed_org("langroute-english")
    for language in (None, "", "en", "EN", "en-US", "en_GB", "auto"):
        provider = _get_stt(org_id, language=language)
        assert isinstance(provider, LocalParakeetProvider), f"language={language!r}"


# ---------------------------------------------------------------------------
# Explicit non-English reroutes to multilingual whisper
# ---------------------------------------------------------------------------
def test_non_english_language_reroutes_to_whisper(client, whisper_env):
    from services.providers.impl_stt import LocalWhisperProvider

    org_id = _seed_org("langroute-french")
    provider = _get_stt(org_id, language="fr")
    assert isinstance(provider, LocalWhisperProvider)
    assert provider.endpoint == "http://meet-whisper:8178"
    # The truthful model label (stamped into transcription_model) comes from
    # WHISPER_MODEL_NAME, not from the parakeet defaults.
    assert provider.model == "whisper.cpp-medium-q8_0"


def test_non_english_reroutes_gateway_provider_too(client, whisper_env):
    """The gateway shim (provider 'openai') wraps the SAME English-only
    parakeet, so a non-English upload must not stay on it either."""
    from services.providers.impl_stt import (
        LocalWhisperProvider,
        OpenAITranscriptionProvider,
    )

    org_id = _seed_org("langroute-gateway")
    _set_stt_settings(org_id, provider_name="openai")

    # Without a language: existing gateway behavior, untouched.
    assert isinstance(_get_stt(org_id), OpenAITranscriptionProvider)
    # With French: rerouted.
    assert isinstance(_get_stt(org_id, language="fr"), LocalWhisperProvider)


def test_non_english_without_endpoint_fails_loud(client, monkeypatch):
    """No whisper endpoint + explicit non-English must ERROR, not silently
    hand the audio to parakeet for high-confidence garbage."""
    monkeypatch.delenv("WHISPER_SERVER_URL", raising=False)
    monkeypatch.delenv("STT_DEFAULT_PROVIDER", raising=False)

    org_id = _seed_org("langroute-noendpoint")
    with pytest.raises(RuntimeError, match="fr"):
        _get_stt(org_id, language="fr")

    # The compose files export the var as an EMPTY string when unset — that
    # must behave identically to absent.
    monkeypatch.setenv("WHISPER_SERVER_URL", "")
    with pytest.raises(RuntimeError, match="multilingual"):
        _get_stt(org_id, language="de")


# ---------------------------------------------------------------------------
# Precedence
# ---------------------------------------------------------------------------
def test_per_upload_provider_override_beats_language(client, whisper_env):
    """An explicit per-upload engine pick is the user's most specific intent
    and always wins — even combined with a non-English language."""
    from services.providers.impl_stt import LocalParakeetProvider, LocalWhisperProvider

    org_id = _seed_org("langroute-override")
    provider = _get_stt(org_id, provider_override="parakeet", language="fr")
    assert isinstance(provider, LocalParakeetProvider)

    # And the explicit whisper pick keeps working (legacy escape hatch).
    provider = _get_stt(org_id, provider_override="local_whisper")
    assert isinstance(provider, LocalWhisperProvider)
    assert provider.endpoint == "http://meet-whisper:8178"


def test_org_level_language_override_reroutes(client, whisper_env):
    """An org whose stt row carries overrides={'language': 'fr'} transcribes
    non-English by default — without per-upload options."""
    from services.providers.impl_stt import LocalParakeetProvider, LocalWhisperProvider

    org_id = _seed_org("langroute-orglang")
    _set_stt_settings(org_id, provider_name="parakeet", overrides={"language": "fr"})

    assert isinstance(_get_stt(org_id), LocalWhisperProvider)
    # Per-call language wins over the org default — an explicit English
    # upload in a French org goes back to parakeet.
    assert isinstance(_get_stt(org_id, language="en"), LocalParakeetProvider)


def test_model_override_is_ignored_on_rerouted_path(client, whisper_env):
    """A per-upload stt_model names a model for the engine the org would have
    used (parakeet); carrying it onto the forced whisper route would stamp a
    lying transcription_model. The whisper label wins."""
    from services.providers.impl_stt import LocalWhisperProvider

    org_id = _seed_org("langroute-modeloverride")
    provider = _get_stt(org_id, model_override="parakeet-tdt-0.6b", language="fr")
    assert isinstance(provider, LocalWhisperProvider)
    assert provider.model == "whisper.cpp-medium-q8_0"


def test_org_whisper_escape_hatch_unchanged(client, whisper_env):
    """Orgs that explicitly stored a whisper provider + their own endpoint
    keep exactly that endpoint (bring-your-own-whisper customers)."""
    from services.providers.impl_stt import LocalWhisperProvider

    org_id = _seed_org("langroute-byow")
    _set_stt_settings(
        org_id, provider_name="whisper", endpoint_url="http://byo-whisper:9999"
    )
    provider = _get_stt(org_id)
    assert isinstance(provider, LocalWhisperProvider)
    assert provider.endpoint == "http://byo-whisper:9999"


# ---------------------------------------------------------------------------
# The pipeline seam: _transcribe_audio forwards the raw language
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_transcribe_audio_forwards_language_to_registry(client, whisper_env, tmp_path, monkeypatch):
    """api.uploads._transcribe_audio must hand get_stt the RAW language (None
    when unset) — coercing to 'en' there would erase the routing signal — and
    still default the provider CALL language to 'en'."""
    import api.uploads as uploads_mod
    import services.providers.registry as registry_mod

    captured: dict = {}

    class _FakeProvider:
        async def transcribe(self, audio_path, *, language=None):
            captured["call_language"] = language
            return {
                "text": "bonjour tout le monde",
                "segments": [
                    {"text": "bonjour tout le monde", "start": 0.0, "end": 2.0,
                     "confidence": 0.9, "speaker": None}
                ],
                "words": [],
                "duration": 2.0,
                "language": language,
                "confidence": 0.9,
                "model": "fake-stt",
                "rtf": None,
            }

    class _FakeRegistry:
        def get_stt(self, org_id, *, provider_override=None, model_override=None, language=None):
            captured["registry_language"] = language
            captured["provider_override"] = provider_override
            return _FakeProvider()

    monkeypatch.setattr(uploads_mod, "get_provider_registry", lambda db: _FakeRegistry(), raising=False)
    monkeypatch.setattr(registry_mod, "get_provider_registry", lambda db: _FakeRegistry())

    wav = tmp_path / "clip.wav"
    wav.write_bytes(b"RIFF0000WAVE")

    org_id = _seed_org("langroute-seam")

    # Explicit French reaches the registry as-is.
    await uploads_mod._transcribe_audio(wav, org_id, db=None, language="fr")
    assert captured["registry_language"] == "fr"
    assert captured["call_language"] == "fr"

    # Absent language reaches the registry as None (NOT 'en'), while the
    # provider call itself still defaults to 'en'.
    await uploads_mod._transcribe_audio(wav, org_id, db=None)
    assert captured["registry_language"] is None
    assert captured["call_language"] == "en"
