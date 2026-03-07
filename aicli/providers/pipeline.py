"""
providers/pipeline.py — Multi-provider failover pipeline.

Failover behavior:
- Each provider has a ProviderState with cooldown_until timestamp
- On 429/rate-limit: set cooldown_until = now + cooldown_seconds, move to next INSTANTLY
- On other errors: immediate failover (no retry by default)
- Per-provider retry: configurable max_retries_per_provider (backoff before failover)
- All-in-cooldown edge case: wait min(remaining cooldowns) then retry

The user NEVER sees a pause between providers — failover is transparent.
"""

import time
import asyncio
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import AsyncGenerator

from .base import BaseProvider
from .groq import GroqProvider
from .openrouter import OpenRouterProvider
from .gemini import GeminiProvider
from .mistral import MistralProvider
from .ollama import OllamaProvider
from ..config import get_api_key

# Default models per provider — used when caller passes model=None
PROVIDER_MODELS = {
    "groq":        "llama-3.3-70b-versatile",
    "openrouter":  "openrouter/auto",
    "gemini":      "gemini-1.5-flash",
    "mistral":     "mistral-small-latest",
    "ollama":      "llama3",
}

# Providers that support vision/multimodal requests (F2)
# Groq and Mistral are text-only — skip them for image requests
VISION_PROVIDERS = {"openrouter", "gemini"}

# Adaptive cooldown durations by HTTP status code (TD-4)
# Overrides the flat cooldown_seconds default for specific error types
COOLDOWN_BY_STATUS = {
    429: 300,   # rate limit — wait 5 minutes before retrying
    401: 3600,  # bad API key — wait 1 hour (won't fix itself)
    403: 3600,  # forbidden — same as bad key
    500: 15,    # server error — short wait, usually transient
    502: 10,    # bad gateway — very transient
    503: 10,    # service unavailable — very transient
}


class ProviderExhaustedError(Exception):
    """All providers failed or are in cooldown with no fallback."""
    pass


@dataclass
class ProviderState:
    provider: BaseProvider
    cooldown_until: float = 0.0
    failure_count: int = 0

    def is_available(self) -> bool:
        return time.monotonic() >= self.cooldown_until

    def remaining_cooldown(self) -> float:
        return max(0.0, self.cooldown_until - time.monotonic())


PROVIDER_CLASSES = {
    "groq": GroqProvider,
    "openrouter": OpenRouterProvider,
    "gemini": GeminiProvider,
    "mistral": MistralProvider,
    "ollama": OllamaProvider,
}


class ProviderPipeline:
    """
    Manages a chain of providers with automatic failover.
    Instantiate once; reuse across all requests in a session.
    """

    def __init__(
        self,
        provider_chain: list[str],
        cooldown_seconds: int = 60,
        max_retries_per_provider: int = 1,
        show_provider: bool = True,
    ):
        self.cooldown_seconds = cooldown_seconds
        self.max_retries_per_provider = max_retries_per_provider
        self.show_provider = show_provider
        self.states: list[ProviderState] = []
        self._last_provider_name: str | None = None

        for name in provider_chain:
            cls = PROVIDER_CLASSES.get(name)
            if cls is None:
                continue
            key = get_api_key(name)
            if name != "ollama" and not key:
                continue  # Skip providers with no key configured
            try:
                provider = cls(api_key=key) if name != "ollama" else cls()
                self.states.append(ProviderState(provider=provider))
            except Exception:
                continue

        if not self.states:
            raise ProviderExhaustedError("No providers available. Run: aicli config set-key <provider>")

    @property
    def last_provider(self) -> str | None:
        return self._last_provider_name

    async def stream(
        self,
        messages: list[dict],
        model: str | None = None,
        requires_vision: bool = False,
    ) -> AsyncGenerator[str, None]:
        """
        Stream from the first available provider.
        On failure/429: immediately mark cooldown, move to next provider.
        If requires_vision=True, only providers in VISION_PROVIDERS are tried.
        """
        if requires_vision:
            available = [
                s for s in self.states
                if s.is_available() and s.provider.name in VISION_PROVIDERS
            ]
            if not available:
                raise ProviderExhaustedError(
                    "No vision-capable providers available. "
                    "Configure OPENROUTER_API_KEY or GEMINI_API_KEY."
                )
        else:
            available = [s for s in self.states if s.is_available()]

        if not available:
            # All in cooldown — wait minimum remaining time
            min_wait = min(s.remaining_cooldown() for s in self.states)
            await asyncio.sleep(min_wait + 0.1)
            available = [s for s in self.states if s.is_available()]

        last_error = None

        for state in available:
            provider = state.provider
            provider_model = model or PROVIDER_MODELS.get(provider.name)
            attempt = 0

            while attempt <= self.max_retries_per_provider:
                try:
                    self._last_provider_name = provider.name
                    chunks_yielded = False

                    async for chunk in provider.stream(messages, model=provider_model):
                        chunks_yielded = True
                        yield chunk

                    return  # Success — done

                except urllib.error.HTTPError as e:
                    if e.code == 429:
                        # Rate limited — adaptive cooldown, instant failover
                        cd = COOLDOWN_BY_STATUS.get(e.code, self.cooldown_seconds)
                        state.cooldown_until = time.monotonic() + cd
                        state.failure_count += 1
                        last_error = e
                        break  # No retry on 429 — instant failover

                    elif e.code >= 500:
                        # Server error — adaptive cooldown, retry once then failover
                        attempt += 1
                        if attempt > self.max_retries_per_provider:
                            cd = COOLDOWN_BY_STATUS.get(e.code, self.cooldown_seconds)
                            state.cooldown_until = time.monotonic() + cd
                            state.failure_count += 1
                            last_error = e
                            break
                        await asyncio.sleep(1.5 ** (attempt - 1))

                    else:
                        # 4xx client error (401/403/etc) — adaptive cooldown, not recoverable
                        cd = COOLDOWN_BY_STATUS.get(e.code, self.cooldown_seconds)
                        state.cooldown_until = time.monotonic() + cd
                        state.failure_count += 1
                        last_error = e
                        break

                except (ConnectionError, OSError, TimeoutError) as e:
                    # Network/connection error — failover immediately
                    last_error = e
                    break

                except Exception as e:
                    last_error = e
                    break

        raise ProviderExhaustedError(
            f"All providers exhausted. Last error: {last_error}"
        )

    async def complete(
        self,
        messages: list[dict],
        model: str | None = None,
        requires_vision: bool = False,
    ) -> str:
        """Non-streaming completion — collects stream() chunks into a single string."""
        chunks = []
        async for chunk in self.stream(messages, model=model, requires_vision=requires_vision):
            chunks.append(chunk)
        return "".join(chunks)

    def status(self) -> list[dict]:
        """Return status of all providers (for `aicli provider status`)."""
        now = time.monotonic()
        result = []
        for state in self.states:
            result.append({
                "name": state.provider.name,
                "available": state.is_available(),
                "cooldown_remaining": round(state.remaining_cooldown(), 1),
                "failures": state.failure_count,
            })
        return result
