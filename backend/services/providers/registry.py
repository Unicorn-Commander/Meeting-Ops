import logging
import os
from typing import Any, Optional

from sqlalchemy.orm import Session

from .crypto import decrypt_api_key
from .protocols import LLMProvider, EmbeddingsProvider, STTProvider, TTSProvider, RerankingProvider, DiarizationProvider

logger = logging.getLogger(__name__)

_SERVICE_KINDS = ("llm", "stt", "tts", "embeddings", "reranking", "diarization")
_TASKS = {"llm": ("fast", "quality", "chat")}

DEFAULT_LITELLM_ENDPOINT = "http://unicorn-litellm:4000/v1"
# Honor either LITELLM_API_KEY (preferred) or OPENAI_API_KEY for compat with
# deploys that historically only set OPENAI_API_KEY.
DEFAULT_LITELLM_API_KEY = os.getenv("LITELLM_API_KEY") or os.getenv("OPENAI_API_KEY", "")
DEFAULT_INFINITY_ENDPOINT = os.getenv("INFINITY_ENDPOINT") or "http://unicorn-infinity-proxy:8086/v1"
# midboy2 runs embed (8082) and rerank (8083) as separate containers; the
# old single-proxy "INFINITY_ENDPOINT" can't address both, so allow per-service
# overrides. Falls back to INFINITY_ENDPOINT for legacy single-proxy deploys.
DEFAULT_INFINITY_EMBEDDING_ENDPOINT = (
    os.getenv("INFINITY_EMBEDDING_ENDPOINT")
    or os.getenv("INFINITY_ENDPOINT")
    or "http://unicorn-infinity-proxy:8086/v1"
)
DEFAULT_INFINITY_RERANKER_ENDPOINT = (
    os.getenv("INFINITY_RERANKER_ENDPOINT")
    or os.getenv("INFINITY_ENDPOINT")
    or "http://unicorn-infinity-proxy:8086/v1"
)
DEFAULT_EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL") or "BAAI/bge-m3"
DEFAULT_RERANKER_MODEL = os.getenv("RERANKER_MODEL") or "BAAI/bge-reranker-v2-m3"


class ProviderRegistry:
    def __init__(self, db: Session):
        self._db = db
        self._settings_cache: dict[tuple[int, str], Optional[dict]] = {}

    def _get_settings(self, org_id: int, service_kind: str) -> dict:
        cache_key = (org_id, service_kind)
        if cache_key in self._settings_cache:
            return self._settings_cache[cache_key] or {}

        from database.models import OrgProviderSettings

        row = (
            self._db.query(OrgProviderSettings)
            .filter(
                OrgProviderSettings.organization_id == org_id,
                OrgProviderSettings.service_kind == service_kind,
            )
            .first()
        )

        if not row:
            self._settings_cache[cache_key] = None
            return {}

        settings = {
            "provider_name": row.provider_name,
            "endpoint_url": row.endpoint_url or "",
            "api_key_encrypted": row.api_key_encrypted or "",
            "model_name": row.model_name or "",
            "overrides": row.overrides or {},
        }
        self._settings_cache[cache_key] = settings
        return settings

    def get_api_key(self, org_id: int, service_kind: str) -> str:
        settings = self._get_settings(org_id, service_kind)
        encrypted = settings.get("api_key_encrypted", "")
        if encrypted:
            try:
                return decrypt_api_key(encrypted)
            except Exception:
                pass
        if service_kind == "llm":
            return DEFAULT_LITELLM_API_KEY
        return ""

    def default_llm(self, task: str = "quality") -> Any:
        """Return the system default LiteLLM provider with no org overlay.

        For status endpoints / unauthenticated callers / background jobs that
        cannot resolve an org context but still need to probe upstream
        availability. Honors LLM_MODEL_{FAST,QUALITY,CHAT} env vars.
        """
        env_key = {
            "fast": "LLM_MODEL_FAST",
            "quality": "LLM_MODEL_QUALITY",
            "chat": "LLM_MODEL_CHAT",
        }.get(task, "LLM_MODEL_QUALITY")
        model = os.getenv(env_key, "gemma-4-26b-moe")
        from .impl_llm import LiteLLMProvider
        return LiteLLMProvider(
            api_key=DEFAULT_LITELLM_API_KEY,
            endpoint=DEFAULT_LITELLM_ENDPOINT,
            model=model,
        )

    def get_llm(
        self,
        org_id: int,
        task: str = "quality",
        *,
        model_override: Optional[str] = None,
        thinking_override: Optional[bool] = None,
    ) -> Any:
        """Resolve the active LLM provider for an org+task.

        Precedence (highest to lowest):
            1. caller model_override
            2. per-org provider_settings (DB row) — explicit choice from the
               AI Providers settings panel
            3. MEETING_OPS_LLM_URL + MEETING_OPS_LLM_MODEL — host-level
               direct-route override (used by the cloud build to send all
               meeting-ops LLM traffic at the dedicated Qwen on midboy1
               P40 #0, bypassing the bigboy LiteLLM gateway entirely)
            4. LLM_MODEL_{FAST,QUALITY,CHAT} env
            5. hardcoded gemma-4-26b-moe fallback

        Layer 3 is intentional: without it, every meeting-ops LLM call
        path (ai_insights / ai_chat / digests / summary)
        defaults back to ProviderRegistry's LiteLLM endpoint regardless
        of what the upload pipeline's _direct_summarizer_provider does.
        Adding the override here means flipping the env once routes ALL
        meeting-ops LLM workload to the same direct upstream.

        thinking_override flips chat_template_kwargs.enable_thinking;
        None defaults to False (suppress <think> tags).
        """
        settings = self._get_settings(org_id, "llm")
        per_org_provider = settings.get("provider_name")
        per_org_endpoint = settings.get("endpoint_url")
        per_org_model = settings.get("model_name", "")

        # Host-level direct route (layer 3). Only kicks in when the org
        # hasn't explicitly chosen a provider in Provider Settings, so
        # paying customers can still pick OpenAI/Anthropic/etc.
        direct_url = os.getenv("MEETING_OPS_LLM_URL", "").strip()
        direct_model = os.getenv("MEETING_OPS_LLM_MODEL", "").strip()
        # Backwards-compat: if MEETING_OPS_LLM_URL isn't set but the
        # legacy summarizer-specific env is, treat that as the direct route.
        if not direct_url:
            direct_url = os.getenv("MEETING_OPS_SUMMARIZER_URL", "").strip()
            direct_model = direct_model or os.getenv("MEETING_OPS_SUMMARIZER_MODEL", "").strip()

        provider_name = per_org_provider or "litellm"
        endpoint = per_org_endpoint or DEFAULT_LITELLM_ENDPOINT
        api_key = self.get_api_key(org_id, "llm")
        model = per_org_model

        # If the org hasn't customized provider AND a host-level direct
        # route is configured, use it. The model_override (caller) still
        # wins to keep per-upload picks honored.
        use_direct = (
            not per_org_provider
            and not per_org_model
            and direct_url
            and direct_model
            and not model_override
        )
        if use_direct:
            endpoint = direct_url
            model = direct_model
        elif not model:
            env_keys = {
                "fast": "LLM_MODEL_FAST",
                "quality": "LLM_MODEL_QUALITY",
                "chat": "LLM_MODEL_CHAT",
            }.get(task, "LLM_MODEL_QUALITY")
            model = os.getenv(env_keys, "gemma-4-26b-moe")

        overrides = settings.get("overrides", {})
        task_override = overrides.get(task, {})
        model = task_override.get("model", model)

        # Per-call overrides win over everything above.
        if model_override:
            model = model_override
        thinking = False if thinking_override is None else bool(thinking_override)

        if provider_name == "litellm" or provider_name == "openai":
            from .impl_llm import LiteLLMProvider
            return LiteLLMProvider(api_key=api_key, endpoint=endpoint, model=model, thinking=thinking)
        elif provider_name == "openrouter":
            from .impl_llm import LiteLLMProvider
            return LiteLLMProvider(api_key=api_key, endpoint=endpoint or "https://openrouter.ai/api/v1", model=model, thinking=thinking)
        elif provider_name == "lambda":
            from .impl_llm import LiteLLMProvider
            return LiteLLMProvider(api_key=api_key, endpoint=endpoint or "https://api.lambdalabs.com/v1", model=model, thinking=thinking)
        elif provider_name == "bedrock":
            from .impl_llm import LiteLLMProvider
            return LiteLLMProvider(api_key=api_key, endpoint=endpoint or "https://bedrock-runtime.us-east-1.amazonaws.com", model=model, thinking=thinking)
        else:
            from .impl_llm import LiteLLMProvider
            logger.warning(f"Unknown LLM provider '{provider_name}', falling back to LiteLLM")
            return LiteLLMProvider(api_key=api_key, endpoint=endpoint, model=model, thinking=thinking)

    def get_embeddings(self, org_id: int) -> Any:
        settings = self._get_settings(org_id, "embeddings")
        provider_name = settings.get("provider_name") or "infinity"
        endpoint = settings.get("endpoint_url") or DEFAULT_INFINITY_EMBEDDING_ENDPOINT
        api_key = self.get_api_key(org_id, "embeddings")
        model = settings.get("model_name") or DEFAULT_EMBEDDING_MODEL

        if provider_name in ("infinity", "openai"):
            from .impl_embeddings import InfinityProvider
            return InfinityProvider(api_key=api_key, endpoint=endpoint, model=model)
        elif provider_name == "voyage":
            from .impl_embeddings import InfinityProvider
            return InfinityProvider(api_key=api_key, endpoint=endpoint or "https://api.voyageai.com/v1", model=model or "voyage-2")
        elif provider_name == "cohere":
            from .impl_embeddings import InfinityProvider
            return InfinityProvider(api_key=api_key, endpoint=endpoint or "https://api.cohere.ai/v1", model=model or "embed-english-v3.0")
        else:
            from .impl_embeddings import InfinityProvider
            return InfinityProvider(api_key=api_key, endpoint=endpoint, model=model)

    def get_reranking(self, org_id: int) -> Any:
        settings = self._get_settings(org_id, "reranking")
        provider_name = settings.get("provider_name") or "infinity"
        endpoint = settings.get("endpoint_url") or DEFAULT_INFINITY_RERANKER_ENDPOINT
        api_key = self.get_api_key(org_id, "reranking")
        model = settings.get("model_name") or DEFAULT_RERANKER_MODEL

        from .impl_reranking import InfinityRerankingProvider
        return InfinityRerankingProvider(api_key=api_key, endpoint=endpoint, model=model)

    def get_stt(
        self,
        org_id: int,
        *,
        provider_override: Optional[str] = None,
        model_override: Optional[str] = None,
    ) -> Any:
        """Resolve the org's configured STT provider.

        Defaults to whisper.cpp at meet-whisper:8178; orgs that prefer
        Parakeet flip provider_name="parakeet" in Provider Settings and we
        route to meet-parakeet-svc instead. Endpoint env vars
        (WHISPER_SERVER_URL, PARAKEET_SERVER_URL) override per deployment.

        Per-upload overrides win over org-level settings — the upload
        pipeline reads UploadJob.transcription_options and passes
        provider_override / model_override here so a single recording can
        route through Parakeet while the org default stays Whisper (or
        vice versa).
        """
        # Default to Parakeet on the cloud build: it runs ~3x faster than
        # whisper-large-v3-turbo on the same hardware, returns word-level
        # timestamps natively (whisper.cpp only does segment-level), and
        # gives the upload pipeline a cleaner shape for the diarization
        # merge. Orgs can flip back to whisper in Provider Settings.
        settings = self._get_settings(org_id, "stt")
        provider_name = (
            provider_override
            or settings.get("provider_name")
            or os.getenv("STT_DEFAULT_PROVIDER", "parakeet")
        ).lower()
        endpoint_override = settings.get("endpoint_url") or ""
        model = model_override or settings.get("model_name") or ""

        if provider_name in ("parakeet", "nemo", "parakeet-tdt"):
            from .impl_stt import LocalParakeetProvider
            endpoint = endpoint_override or os.getenv(
                "PARAKEET_SERVER_URL", "http://meet-parakeet-svc:8881"
            )
            return LocalParakeetProvider(
                endpoint=endpoint,
                model=model or "parakeet-tdt-1.1b",
            )

        from .impl_stt import LocalWhisperProvider
        endpoint = endpoint_override or os.getenv(
            "WHISPER_SERVER_URL", "http://meet-whisper:8178"
        )
        return LocalWhisperProvider(
            endpoint=endpoint,
            model=model or "whisper.cpp-large-v3-turbo",
        )

    def get_tts(self, org_id: int) -> Any:
        settings = self._get_settings(org_id, "tts")
        provider_name = settings.get("provider_name") or "kokoro"
        api_key = self.get_api_key(org_id, "tts")
        endpoint_override = settings.get("endpoint_url") or ""
        model_override = settings.get("model_name") or ""

        if provider_name == "vibevoice":
            from .impl_tts import VibeVoiceProvider
            endpoint = endpoint_override or os.getenv(
                "VIBEVOICE_ENDPOINT", "http://192.168.10.68:8882"
            )
            return VibeVoiceProvider(
                endpoint=endpoint,
                voice=model_override or "alice",
                api_key=api_key,
            )
        elif provider_name == "openai":
            # Treat the generic OpenAI TTS as a Kokoro-shaped client (same
            # /v1/audio/speech endpoint). API key required; endpoint should be
            # https://api.openai.com/v1.
            from .impl_tts import KokoroProvider
            return KokoroProvider(
                endpoint=endpoint_override or "https://api.openai.com/v1",
                voice=model_override or "alloy",
                api_key=api_key,
            )
        else:
            # Kokoro default.
            from .impl_tts import KokoroProvider
            return KokoroProvider(
                endpoint=endpoint_override
                or os.getenv("KOKORO_ENDPOINT", "http://unicorn-kokoro:8880"),
                voice=model_override or "af_bella",
                api_key=api_key,
            )

    def get_diarization(self, org_id: int) -> Any:
        """Returns a DiarizationProvider that also exposes embed() and identify().
        Configurable per-org via OrgProviderSettings; defaults to the internal
        speaker-svc container on bigboy GPU 1."""
        settings = self._get_settings(org_id, "diarization")
        endpoint = settings.get("endpoint_url") or os.getenv("SPEAKER_SVC_URL", "http://meet-speaker-svc:8889")
        from .impl_diarization import LocalSpeakerSvcProvider
        return LocalSpeakerSvcProvider(endpoint=endpoint)

    def get_speaker_svc(self, org_id: int) -> Any:
        """Convenience alias — same provider as get_diarization but reads as
        intent in code that only needs embed/identify (e.g. enrollment)."""
        return self.get_diarization(org_id)

    def clear_cache(self):
        self._settings_cache.clear()


_registry_instance: Optional[ProviderRegistry] = None


def get_provider_registry(db=None) -> ProviderRegistry:
    return ProviderRegistry(db)


# FastAPI dependency — use as: Depends(get_provider_registry_dep)
async def get_provider_registry_dep(db=None):
    from database.database import SessionLocal
    dbi = db or SessionLocal()
    registry = ProviderRegistry(dbi)
    try:
        yield registry
    finally:
        if not db:
            dbi.close()
