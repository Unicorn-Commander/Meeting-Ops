import json
import logging
import os
import time
from typing import AsyncGenerator

import httpx

from .protocols import LLMProvider

logger = logging.getLogger(__name__)

DEFAULT_LITELLM_ENDPOINT = "http://unicorn-litellm:4000/v1"


class LiteLLMProvider:
    def __init__(self, api_key: str, endpoint: str = "", model: str = "gemma-4-26b-moe"):
        self.api_key = api_key
        self.endpoint = endpoint.rstrip("/") if endpoint else DEFAULT_LITELLM_ENDPOINT
        self.model = model

    def _build_payload(self, system_prompt: str, user_prompt: str, max_tokens: int, temperature: float, stream: bool) -> dict:
        # Some LiteLLM upstreams (notably the openai provider for Gemma 4 GGUFs)
        # reject the `reasoning_effort` field outright. We rely on
        # `chat_template_kwargs.enable_thinking=False` to suppress reasoning
        # preambles instead.
        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
            "chat_template_kwargs": {"enable_thinking": False},
        }

    def _build_headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def chat(self, system_prompt: str, user_prompt: str, *, max_tokens: int = 500, temperature: float = 0.7) -> str:
        headers = self._build_headers()
        payload = self._build_payload(system_prompt, user_prompt, max_tokens, temperature, stream=False)

        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(f"{self.endpoint}/chat/completions", headers=headers, json=payload)
            if response.status_code == 200:
                result = response.json()
                msg = result["choices"][0].get("message", {})
                content = (msg.get("content") or "").strip()
                if not content:
                    content = (msg.get("reasoning_content") or "").strip()
                return content
            else:
                logger.error(f"LLM API error: {response.status_code} - {response.text[:200]}")
                return ""

    def chat_sync(self, system_prompt: str, user_prompt: str, *, max_tokens: int = 500, temperature: float = 0.7) -> str:
        """Synchronous chat call. Safe to invoke from sync code or via run_in_executor."""
        headers = self._build_headers()
        payload = self._build_payload(system_prompt, user_prompt, max_tokens, temperature, stream=False)

        try:
            with httpx.Client(timeout=120) as client:
                response = client.post(f"{self.endpoint}/chat/completions", headers=headers, json=payload)
                if response.status_code == 200:
                    result = response.json()
                    msg = result["choices"][0].get("message", {})
                    content = (msg.get("content") or "").strip()
                    if not content:
                        content = (msg.get("reasoning_content") or "").strip()
                    return content
                else:
                    logger.error(f"LLM API error: {response.status_code} - {response.text[:200]}")
                    return ""
        except Exception as e:
            logger.error(f"LLM sync call failed: {e}")
            return ""

    async def chat_stream(self, system_prompt: str, user_prompt: str, *, max_tokens: int = 500, temperature: float = 0.7) -> AsyncGenerator[str, None]:
        headers = self._build_headers()
        payload = self._build_payload(system_prompt, user_prompt, max_tokens, temperature, stream=True)

        async with httpx.AsyncClient(timeout=300) as client:
            async with client.stream("POST", f"{self.endpoint}/chat/completions", headers=headers, json=payload) as response:
                if response.status_code != 200:
                    logger.error(f"LLM stream error: {response.status_code}")
                    yield ""
                    return
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                            delta = chunk["choices"][0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue

    async def health(self) -> dict:
        """Probe upstream availability via /v1/models, falling back to /health.
        Never raises — returns {available, endpoint, model, error}."""
        headers = self._build_headers()
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self.endpoint}/models", headers=headers)
                if resp.status_code == 200:
                    return {"available": True, "endpoint": self.endpoint, "model": self.model, "error": None}
                # Fall back to /health (some llama.cpp builds expose it without auth)
                base = self.endpoint.rsplit("/v1", 1)[0]
                resp2 = await client.get(f"{base}/health")
                if resp2.status_code == 200:
                    return {"available": True, "endpoint": self.endpoint, "model": self.model, "error": None}
                return {
                    "available": False,
                    "endpoint": self.endpoint,
                    "model": self.model,
                    "error": f"HTTP {resp.status_code}",
                }
        except Exception as exc:
            return {"available": False, "endpoint": self.endpoint, "model": self.model, "error": str(exc)}
