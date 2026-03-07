"""
providers/ollama.py — Local Ollama provider.
Unlimited, fully private. Requires: ollama serve
Default endpoint: http://localhost:11434
"""
import json
import asyncio
import urllib.request
import urllib.error
from typing import AsyncGenerator
from .base import BaseProvider

OLLAMA_API_URL = "http://localhost:11434/api/chat"
DEFAULT_MODEL  = "llama3"


class OllamaProvider(BaseProvider):
    name = "ollama"

    def __init__(self, api_key: str | None = None):
        pass  # No API key needed

    async def stream(self, messages, model=None, temperature=0.7) -> AsyncGenerator[str, None]:
        payload = json.dumps({
            "model": model or DEFAULT_MODEL,
            "messages": messages,
            "stream": True,
            "options": {"temperature": temperature},
        }).encode()
        req  = urllib.request.Request(
            OLLAMA_API_URL, data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        loop = asyncio.get_event_loop()

        def _do():
            try:
                return urllib.request.urlopen(req, timeout=120)
            except (urllib.error.URLError, OSError) as e:
                raise ConnectionError(
                    "Ollama not running at localhost:11434. Start with: ollama serve"
                ) from e

        resp = await loop.run_in_executor(None, _do)

        async def _gen():
            try:
                while True:
                    line = await loop.run_in_executor(None, resp.readline)
                    if not line:
                        break
                    try:
                        chunk = json.loads(line.decode())
                        content = chunk.get("message", {}).get("content", "")
                        if content:
                            yield content
                        if chunk.get("done"):
                            break
                    except json.JSONDecodeError:
                        continue
            finally:
                resp.close()

        async for chunk in _gen():
            yield chunk

    async def complete(self, messages, model=None) -> str:
        chunks = []
        async for chunk in self.stream(messages, model=model):
            chunks.append(chunk)
        return "".join(chunks)
