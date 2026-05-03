from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMProvider(Protocol):
    async def chat(self, system_prompt: str, user_prompt: str, *, max_tokens: int = 500, temperature: float = 0.7) -> str: ...
    async def chat_stream(self, system_prompt: str, user_prompt: str, *, max_tokens: int = 500, temperature: float = 0.7): ...


@runtime_checkable
class EmbeddingsProvider(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...
    def embed_sync(self, texts: list[str]) -> list[list[float]]: ...


@runtime_checkable
class STTProvider(Protocol):
    async def transcribe(self, audio_path: str, *, language: str | None = None) -> str: ...


@runtime_checkable
class TTSProvider(Protocol):
    async def synthesize(self, text: str, *, voice: str | None = None) -> bytes: ...


@runtime_checkable
class RerankingProvider(Protocol):
    async def rerank(self, query: str, documents: list[str], top_n: int = 5) -> list[dict]: ...


@runtime_checkable
class DiarizationProvider(Protocol):
    async def diarize(self, audio_path: str) -> list[dict]: ...
