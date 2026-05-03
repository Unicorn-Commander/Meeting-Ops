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

    async def chat(self, system_prompt: str, user_prompt: str, *, max_tokens: int = 500, temperature: float = 0.7) -> str:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
            "chat_template_kwargs": {"enable_thinking": False},
            "reasoning_effort": "none",
        }

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

    async def chat_stream(self, system_prompt: str, user_prompt: str, *, max_tokens: int = 500, temperature: float = 0.7) -> AsyncGenerator[str, None]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
            "chat_template_kwargs": {"enable_thinking": False},
            "reasoning_effort": "none",
        }

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
