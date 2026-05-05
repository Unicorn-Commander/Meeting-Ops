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
# Honor either LITELLM_API_KEY (preferred) or OPENAI_API_KEY (the env var the
# legacy unified_llm_service reads). This keeps the registry compatible with
# existing deploys that only set OPENAI_API_KEY.
DEFAULT_LITELLM_API_KEY = os.getenv("LITELLM_API_KEY") or os.getenv("OPENAI_API_KEY", "")
DEFAULT_INFINITY_ENDPOINT = os.getenv("INFINITY_ENDPOINT") or "http://unicorn-infinity-proxy:8086/v1"
DEFAULT_WHISPER_ENDPOINT = os.getenv("WHISPER_SERVER_URL", "http://meet-whisper:8178")
DEFAULT_PARAKEET_ENDPOINT = os.getenv("PARAKEET_SERVER_URL", "http://meet-parakeet-svc:8881")


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

    def get_llm(self, org_id: int, task: str = "quality") -> Any:
        settings = self._get_settings(org_id, "llm")
        provider_name = settings.get("provider_name") or "litellm"
        endpoint = settings.get("endpoint_url") or DEFAULT_LITELLM_ENDPOINT
        api_key = self.get_api_key(org_id, "llm")
        model = settings.get("model_name", "")

        if not model:
            env_keys = {
                "fast": "LLM_MODEL_FAST",
                "quality": "LLM_MODEL_QUALITY",
                "chat": "LLM_MODEL_CHAT",
            }.get(task, "LLM_MODEL_QUALITY")
            model = os.getenv(env_keys, "gemma-4-26b-moe")

        overrides = settings.get("overrides", {})
        task_override = overrides.get(task, {})
        model = task_override.get("model", model)

        if provider_name == "litellm" or provider_name == "openai":
            from .impl_llm import LiteLLMProvider
            return LiteLLMProvider(api_key=api_key, endpoint=endpoint, model=model)
        elif provider_name == "openrouter":
            from .impl_llm import LiteLLMProvider
            return LiteLLMProvider(api_key=api_key, endpoint=endpoint or "https://openrouter.ai/api/v1", model=model)
        elif provider_name == "lambda":
            from .impl_llm import LiteLLMProvider
            return LiteLLMProvider(api_key=api_key, endpoint=endpoint or "https://api.lambdalabs.com/v1", model=model)
        elif provider_name == "bedrock":
            from .impl_llm import LiteLLMProvider
            return LiteLLMProvider(api_key=api_key, endpoint=endpoint or "https://bedrock-runtime.us-east-1.amazonaws.com", model=model)
        else:
            from .impl_llm import LiteLLMProvider
            logger.warning(f"Unknown LLM provider '{provider_name}', falling back to LiteLLM")
            return LiteLLMProvider(api_key=api_key, endpoint=endpoint, model=model)

    def get_embeddings(self, org_id: int) -> Any:
        settings = self._get_settings(org_id, "embeddings")
        provider_name = settings.get("provider_name") or "infinity"
        endpoint = settings.get("endpoint_url") or DEFAULT_INFINITY_ENDPOINT
        api_key = self.get_api_key(org_id, "embeddings")
        model = settings.get("model_name") or "BAAI/bge-large-en-v1.5"

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
        endpoint = settings.get("endpoint_url") or DEFAULT_INFINITY_ENDPOINT
        api_key = self.get_api_key(org_id, "reranking")
        model = settings.get("model_name") or "BAAI/bge-reranker-v2-m3"

        from .impl_reranking import InfinityRerankingProvider
        return InfinityRerankingProvider(api_key=api_key, endpoint=endpoint, model=model)

    def get_stt(self, org_id: int) -> Any:
        """Resolve the STT provider for the given org.

        Recognized provider_name values:
            - "local_whisper" (default) -> in-cluster whisper.cpp on :8178
            - "parakeet"                -> in-cluster Parakeet-TDT on :8881
            - "local_parakeet"          -> alias of "parakeet"
        Cloud STT (deepgram / assemblyai / openai) is reserved for future
        provider impls; for now we fall back to whisper for unknown values
        so an org can't accidentally lose transcription by picking a
        provider that hasn't shipped yet.
        """
        settings = self._get_settings(org_id, "stt")
        provider_name = (settings.get("provider_name") or "local_whisper").lower()
        endpoint = settings.get("endpoint_url") or ""
        model = settings.get("model_name") or ""

        if provider_name in ("parakeet", "local_parakeet"):
            from .impl_stt import LocalParakeetProvider
            return LocalParakeetProvider(
                endpoint=endpoint or DEFAULT_PARAKEET_ENDPOINT,
                model=model or "parakeet-tdt-1.1b",
            )
        if provider_name in ("local_whisper", "whisper", ""):
            from .impl_stt import LocalWhisperProvider
            return LocalWhisperProvider(
                endpoint=endpoint or DEFAULT_WHISPER_ENDPOINT,
                model=model or "whisper.cpp-large-v3-turbo",
            )

        # Unknown provider — log and fall back to whisper so the pipeline still
        # works.
        logger.warning("Unknown STT provider '%s' for org %s; falling back to local_whisper",
                       provider_name, org_id)
        from .impl_stt import LocalWhisperProvider
        return LocalWhisperProvider(
            endpoint=endpoint or DEFAULT_WHISPER_ENDPOINT,
            model=model or "whisper.cpp-large-v3-turbo",
        )

    def get_tts(self, org_id: int) -> Any:
        settings = self._get_settings(org_id, "tts")
        provider_name = settings.get("provider_name") or "kokoro"

        if provider_name == "vibevoice":
            from .impl_tts import VibeVoiceProvider
            return VibeVoiceProvider(endpoint=settings.get("endpoint_url", ""))
        else:
            from .impl_tts import KokoroProvider
            return KokoroProvider(endpoint=settings.get("endpoint_url", "http://localhost:8880"))

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
