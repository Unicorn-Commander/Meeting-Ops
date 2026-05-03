import logging

from .protocols import TTSProvider

logger = logging.getLogger(__name__)


class KokoroProvider:
    def __init__(self, endpoint: str = "http://localhost:8880", voice: str = "af_bella"):
        self.endpoint = endpoint.rstrip("/")
        self.voice = voice

    async def synthesize(self, text: str, *, voice: str | None = None) -> bytes:
        import httpx
        payload = {"text": text, "voice": voice or self.voice}
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(f"{self.endpoint}/v1/audio/speech", json=payload)
                if response.status_code == 200:
                    return response.content
        except Exception as e:
            logger.error(f"Kokoro TTS error: {e}")
        return b""


class VibeVoiceProvider:
    def __init__(self, endpoint: str = "", voice: str = "default"):
        self.endpoint = endpoint.rstrip("/")
        self.voice = voice

    async def synthesize(self, text: str, *, voice: str | None = None) -> bytes:
        import httpx
        payload = {"text": text, "voice": voice or self.voice}
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(f"{self.endpoint}/synthesize", json=payload)
                if response.status_code == 200:
                    return response.content
        except Exception as e:
            logger.error(f"VibeVoice TTS error: {e}")
        return b""
