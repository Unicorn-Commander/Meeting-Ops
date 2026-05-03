import logging

from .protocols import DiarizationProvider

logger = logging.getLogger(__name__)


class LocalDiarizationProvider:
    def __init__(self, endpoint: str = "http://localhost:8881"):
        self.endpoint = endpoint.rstrip("/")

    async def diarize(self, audio_path: str) -> list[dict]:
        import httpx
        try:
            async with httpx.AsyncClient(timeout=300) as client:
                response = await client.post(f"{self.endpoint}/diarize", json={"audio_path": audio_path})
                if response.status_code == 200:
                    return response.json().get("speakers", [])
        except Exception as e:
            logger.error(f"Diarization error: {e}")
        return []
