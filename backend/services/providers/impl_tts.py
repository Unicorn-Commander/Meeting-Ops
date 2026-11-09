"""TTS provider implementations.

Two providers are supported:

* `KokoroProvider` — small, fast, OpenAI-compatible TTS for short snippets.
  Default for new orgs; lives at `unicorn-kokoro:8880` on bigboy.
* `VibeVoiceProvider` — long-form, multi-speaker TTS for podcast-style outputs.
  Lives at `meet-vibevoice` on midboy1 P40 #1, reached over the LAN at
  `http://192.168.10.68:8882` (no shared docker network with bigboy).

Both implement the same `synthesize()` shape. `synthesize_podcast()` is a
VibeVoice-only feature; KokoroProvider declines with `NotImplementedError`
so callers can fall back gracefully.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from .usage import UsageReporter, get_usage_reporter, text_work_id
from utils.url_redaction import redact_text

logger = logging.getLogger(__name__)


class KokoroProvider:
    """OpenAI-compatible TTS via Kokoro-FastAPI on bigboy."""

    name = "kokoro"
    supports_podcast = False

    def __init__(
        self,
        endpoint: str = "http://unicorn-kokoro:8880",
        voice: str = "af_bella",
        api_key: str = "",
        *,
        route: str | None = None,
        org_id: int | None = None,
        feature: str | None = None,
        user_id: int | str | None = None,
        usage_reporter: UsageReporter | None = None,
        work_id: str | None = None,
    ):
        self.endpoint = (endpoint or "http://unicorn-kokoro:8880").rstrip("/")
        self.voice = voice or "af_bella"
        self.api_key = api_key or ""
        self.route = route
        self.model = route or "kokoro"
        self.org_id = org_id
        self.feature = feature or ("tts" if route == "voice" else route or "tts")
        self.user_id = user_id
        self.org_route = bool(route and org_id is not None)
        self.usage_reporter = usage_reporter or (
            get_usage_reporter() if self.org_route else None
        )
        self.work_id = work_id

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if self.org_route:
            headers.update(
                {
                    "X-UC-Org-Id": str(self.org_id),
                    "X-UC-App": "meeting-ops",
                    "X-UC-Feature": self.feature,
                }
            )
            if self.user_id is not None:
                headers["X-UC-User-Id"] = str(self.user_id)
        return headers

    def _speech_url(self) -> str:
        if self.org_route:
            return f"{self.endpoint}/audio/speech"
        return f"{self.endpoint}/v1/audio/speech"

    def _report_characters(self, text: str) -> None:
        if not self.org_route or not self.usage_reporter or not text:
            return
        try:
            self.usage_reporter.report(
                organization_id=int(self.org_id),
                metric="tts_characters",
                quantity=float(len(text)),
                work_id=self.work_id or text_work_id(text),
                feature=self.feature,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("TTS usage report failed for org_id=%s: %s", self.org_id, exc)

    async def synthesize(
        self,
        text: str,
        *,
        voice: Optional[str] = None,
        format: str = "mp3",
    ) -> bytes:
        import httpx

        payload = {
            "input": text,
            "voice": voice or self.voice,
            "response_format": format,
            "model": self.model,
        }

        try:
            async with httpx.AsyncClient(timeout=180) as client:
                response = await client.post(
                    self._speech_url(),
                    headers=self._headers(),
                    json=payload,
                )
                if response.status_code == 200:
                    self._report_characters(text)
                    return response.content
                logger.error(
                    "Kokoro TTS error %s: %s",
                    response.status_code,
                    redact_text(response.text[:200]),
                )
                if self.org_route:
                    raise RuntimeError(
                        f"Gateway TTS request failed: HTTP {response.status_code}"
                    )
        except Exception as exc:  # noqa: BLE001
            if self.org_route:
                if isinstance(exc, RuntimeError) and "Gateway TTS" in str(exc):
                    raise
                raise RuntimeError(
                    f"Gateway TTS request failed: {redact_text(str(exc))}"
                ) from exc
            logger.error("Kokoro TTS failed: %s", redact_text(str(exc)))
        return b""

    async def synthesize_podcast(
        self,
        script: list[dict],
        voices: dict[str, str],
        *,
        format: str = "mp3",
    ) -> bytes:
        # Kokoro is single-voice; the API endpoint should return 501 instead
        # of pretending to support multi-voice.
        raise NotImplementedError("Kokoro TTS does not support multi-speaker podcasts")

    async def list_voices(self) -> list[dict]:
        import httpx

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                voices_url = (
                    f"{self.endpoint}/audio/voices"
                    if self.org_route
                    else f"{self.endpoint}/v1/audio/voices"
                )
                if self.org_route:
                    response = await client.get(voices_url, headers=self._headers())
                else:
                    response = await client.get(voices_url)
                if response.status_code == 200:
                    payload = response.json()
                    voices = payload.get("voices", [])
                    return [{"voice_id": v, "label": v} for v in voices]
        except Exception as exc:  # noqa: BLE001
            logger.warning("Kokoro voices listing failed: %s", redact_text(str(exc)))
        return [{"voice_id": "af_bella", "label": "af_bella"}]

    async def health(self) -> dict:
        import httpx

        try:
            async with httpx.AsyncClient(timeout=5) as client:
                if self.org_route:
                    response = await client.get(
                        f"{self.endpoint}/health", headers=self._headers()
                    )
                else:
                    response = await client.get(f"{self.endpoint}/health")
                if response.status_code == 200:
                    return {"ok": True, "provider": self.name}
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "provider": self.name,
                "error": redact_text(str(exc)),
            }
        return {"ok": False, "provider": self.name}


class VibeVoiceProvider:
    """Microsoft VibeVoice — long-form, multi-speaker TTS via meet-vibevoice on midboy1."""

    name = "vibevoice"
    supports_podcast = True

    DEFAULT_VOICE = "alice"

    def __init__(
        self,
        endpoint: str = "",
        voice: str = "alice",
        api_key: str = "",
    ):
        self.endpoint = (
            endpoint
            or os.getenv("VIBEVOICE_ENDPOINT")
            or "http://192.168.10.68:8882"
        ).rstrip("/")
        self.voice = voice or self.DEFAULT_VOICE
        self.api_key = api_key or ""

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def synthesize(
        self,
        text: str,
        *,
        voice: Optional[str] = None,
        format: str = "mp3",
    ) -> bytes:
        import httpx

        payload = {
            "text": text,
            "voice_id": voice or self.voice,
            "format": format,
        }
        try:
            async with httpx.AsyncClient(timeout=600) as client:
                response = await client.post(
                    f"{self.endpoint}/tts",
                    headers=self._headers(),
                    json=payload,
                )
                if response.status_code == 200:
                    return response.content
                logger.error(
                    "VibeVoice TTS error %s: %s",
                    response.status_code,
                    redact_text(response.text[:200]),
                )
        except Exception as exc:  # noqa: BLE001
            logger.error("VibeVoice TTS failed: %s", redact_text(str(exc)))
        return b""

    async def synthesize_podcast(
        self,
        script: list[dict],
        voices: dict[str, str],
        *,
        format: str = "mp3",
    ) -> bytes:
        """Render a multi-speaker conversation.

        `script` is `[{speaker_id, text}, ...]`; `voices` maps each speaker_id to
        a voice preset. Long meetings can take several minutes — caller should
        run this in a background task and stream/poll status.
        """
        import httpx

        payload = {
            "script": script,
            "voices": voices or {},
            "format": format,
        }
        try:
            async with httpx.AsyncClient(timeout=900) as client:
                response = await client.post(
                    f"{self.endpoint}/podcast",
                    headers=self._headers(),
                    json=payload,
                )
                if response.status_code == 200:
                    return response.content
                logger.error(
                    "VibeVoice podcast error %s: %s",
                    response.status_code,
                    redact_text(response.text[:200]),
                )
        except Exception as exc:  # noqa: BLE001
            logger.error("VibeVoice podcast failed: %s", redact_text(str(exc)))
        return b""

    async def list_voices(self) -> list[dict]:
        import httpx

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(f"{self.endpoint}/voices", headers=self._headers())
                if response.status_code == 200:
                    payload = response.json()
                    return [
                        {"voice_id": v.get("voice_id"), "label": v.get("voice_id")}
                        for v in payload.get("voices", [])
                    ]
        except Exception as exc:  # noqa: BLE001
            logger.warning("VibeVoice voices listing failed: %s", redact_text(str(exc)))
        return [{"voice_id": self.DEFAULT_VOICE, "label": self.DEFAULT_VOICE}]

    async def health(self) -> dict:
        import httpx

        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{self.endpoint}/health", headers=self._headers())
                if response.status_code == 200:
                    body = response.json()
                    return {
                        "ok": True,
                        "provider": self.name,
                        "model_loaded": bool(body.get("model_loaded")),
                        "gpu_name": body.get("gpu_name"),
                        "voices": body.get("voices_available"),
                    }
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "provider": self.name,
                "error": redact_text(str(exc)),
            }
        return {"ok": False, "provider": self.name}
