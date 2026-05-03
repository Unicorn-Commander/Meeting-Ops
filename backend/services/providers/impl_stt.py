import logging

from .protocols import STTProvider

logger = logging.getLogger(__name__)


class LocalWhisperProvider:
    def __init__(self, endpoint: str = "http://meet-whisper:8080", model: str = "whisper-large-v3"):
        self.endpoint = endpoint.rstrip("/")
        self.model = model

    async def transcribe(self, audio_path: str, *, language: str | None = None) -> str:
        import httpx
        payload = {"audio_path": audio_path, "model": self.model}
        if language:
            payload["language"] = language
        try:
            async with httpx.AsyncClient(timeout=300) as client:
                response = await client.post(f"{self.endpoint}/transcribe", json=payload)
                if response.status_code == 200:
                    return response.json().get("text", "")
        except Exception as e:
            logger.error(f"Whisper STT error: {e}")
        return ""
