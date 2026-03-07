"""
providers/groq.py — Groq inference provider.
SSE streaming via httpx (preferred) or urllib fallback.
Free tier: 30 RPM on llama-3.3-70b-versatile.
"""
import json
import asyncio
import urllib.request
import urllib.error
from typing import AsyncGenerator
from .base import BaseProvider

try:
    import httpx as _httpx
    _HTTPX_AVAILABLE = True
except ImportError:
    _HTTPX_AVAILABLE = False

GROQ_API_URL  = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = "llama-3.3-70b-versatile"


class GroqProvider(BaseProvider):
    name = "groq"

    def __init__(self, api_key: str):
        self.api_key = api_key

    def _request(self, messages, model, stream, temperature=0.7):
        payload = json.dumps({
            "model": model, "messages": messages,
            "temperature": temperature, "stream": stream,
        }).encode()
        return urllib.request.Request(
            GROQ_API_URL, data=payload,
            headers={"Authorization": f"Bearer {self.api_key}",
                     "Content-Type": "application/json",
                     "User-Agent": "curl/8.5.0"},
            method="POST",
        )

    async def stream(self, messages, model=None, temperature=0.7) -> AsyncGenerator[str, None]:
        payload = {
            "model": model or DEFAULT_MODEL, "messages": messages,
            "temperature": temperature, "stream": True,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "curl/8.5.0",
        }

        if _HTTPX_AVAILABLE:
            async with _httpx.AsyncClient(timeout=60) as client:
                async with client.stream("POST", GROQ_API_URL, json=payload, headers=headers) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        try:
                            content = json.loads(data)["choices"][0]["delta"].get("content", "")
                            if content:
                                yield content
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue
            return

        req  = self._request(messages, model or DEFAULT_MODEL, True, temperature)
        loop = asyncio.get_event_loop()
        try:
            resp = await loop.run_in_executor(None, lambda: urllib.request.urlopen(req, timeout=60))
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            raise urllib.error.HTTPError(e.url, e.code, f"{e.reason} — {body}", e.headers, None) from None

        async def _gen():
            try:
                while True:
                    line = await loop.run_in_executor(None, resp.readline)
                    if not line:
                        break
                    line = line.decode().strip()
                    if not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    try:
                        content = json.loads(data)["choices"][0]["delta"].get("content", "")
                        if content:
                            yield content
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue
            finally:
                resp.close()

        async for chunk in _gen():
            yield chunk

    async def complete(self, messages, model=None) -> str:
        req  = self._request(messages, model or DEFAULT_MODEL, False, 0.3)
        loop = asyncio.get_event_loop()
        def _do():
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())
        data = await loop.run_in_executor(None, _do)
        return data["choices"][0]["message"]["content"]
