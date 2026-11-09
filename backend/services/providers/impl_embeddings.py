import logging
import os

import httpx

from .protocols import EmbeddingsProvider
from utils.url_redaction import redact_text

logger = logging.getLogger(__name__)

DEFAULT_INFINITY_ENDPOINT = "http://unicorn-infinity-proxy:8086/v1"


class InfinityProvider:
    def __init__(
        self,
        api_key: str = "",
        endpoint: str = "",
        model: str = "Qwen/Qwen3-Embedding-0.6B",
        *,
        route: str | None = None,
        org_id: int | None = None,
        feature: str | None = None,
        user_id: int | str | None = None,
    ):
        self.api_key = api_key
        self.endpoint = endpoint.rstrip("/") if endpoint else DEFAULT_INFINITY_ENDPOINT
        self.model = model
        self.route = route
        self.org_id = org_id
        self.feature = feature or ("embedding" if route == "embed" else route or "embedding")
        self.user_id = user_id
        self.org_route = bool(route and org_id is not None)

    def _headers(self) -> dict:
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

    async def embed(self, texts: list[str]) -> list[list[float]]:
        payload = {
            "model": self.model,
            "input": texts,
        }

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(
                    f"{self.endpoint}/embeddings",
                    headers=self._headers(),
                    json=payload,
                )
                if response.status_code == 200:
                    result = response.json()
                    return [item["embedding"] for item in result.get("data", [])]
                logger.error("Embedding API error: %s", response.status_code)
                if self.org_route:
                    raise RuntimeError(
                        f"Gateway embeddings request failed: HTTP {response.status_code}"
                    )
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            if self.org_route:
                raise RuntimeError(
                    "Gateway embeddings request failed: invalid or unavailable response"
                ) from exc
            raise
        return []

    def embed_sync(self, texts: list[str]) -> list[list[float]]:
        import requests
        payload = {
            "model": self.model,
            "input": texts,
        }

        try:
            response = requests.post(
                f"{self.endpoint}/embeddings",
                headers=self._headers(),
                json=payload,
                timeout=60,
            )
            if response.status_code == 200:
                result = response.json()
                return [item["embedding"] for item in result.get("data", [])]
            if self.org_route:
                raise RuntimeError(
                    f"Gateway embeddings request failed: HTTP {response.status_code}"
                )
        except Exception as e:
            if self.org_route:
                raise RuntimeError("Gateway embeddings request failed") from e
            logger.error("Embedding API sync error: %s", redact_text(str(e)))
        return []
