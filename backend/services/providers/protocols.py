from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LLMProvider(Protocol):
    async def chat(self, system_prompt: str, user_prompt: str, *, max_tokens: int = 500, temperature: float = 0.7) -> str: ...
    def chat_sync(self, system_prompt: str, user_prompt: str, *, max_tokens: int = 500, temperature: float = 0.7) -> str: ...
    async def chat_stream(self, system_prompt: str, user_prompt: str, *, max_tokens: int = 500, temperature: float = 0.7): ...


@runtime_checkable
class EmbeddingsProvider(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...
    def embed_sync(self, texts: list[str]) -> list[list[float]]: ...


@runtime_checkable
class STTProvider(Protocol):
    async def transcribe(self, audio_path: str, *, language: str | None = None) -> dict[str, Any]:
        """Transcribe an audio file. Returns a normalized dict with at least:

            text:       str
            segments:   list[dict]   # each {start, end, text, confidence, speaker?}
            words:      list[dict]   # optional word-level (parakeet only)
            duration:   float
            language:   str
            model:      str          # used to populate processing_metadata.transcription_model
            confidence: float
            rtf:        float | None # realtime factor when the engine reports it
        """
        ...


@runtime_checkable
class TTSProvider(Protocol):
    async def synthesize(self, text: str, *, voice: str | None = None) -> bytes: ...


@runtime_checkable
class RerankingProvider(Protocol):
    async def rerank(self, query: str, documents: list[str], top_n: int = 5) -> list[dict]: ...


@runtime_checkable
class DiarizationProvider(Protocol):
    async def diarize(self, audio_path: str) -> list[dict]: ...

    async def embed(self, audio_path: str) -> dict: ...
    """Return {"embedding": list[float], "embedding_dim": int, "duration_seconds": float, "model": str}."""

    async def identify(self, embedding: list[float], candidates: list[dict], threshold: float = 0.55) -> dict: ...
    """candidates: [{"speaker_id": int, "embedding": list[float]}, ...]
    Returns {"matches": [{"speaker_id": int, "similarity": float, "matched": bool}, ...],
             "best_match": {...} | None}."""
