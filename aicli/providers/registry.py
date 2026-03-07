"""
providers/registry.py — Builds ProviderPipeline from config.
Separates pipeline construction from pipeline operation.
"""
from .groq       import GroqProvider
from .openrouter import OpenRouterProvider
from .gemini     import GeminiProvider
from .mistral    import MistralProvider
from .ollama     import OllamaProvider
from .pipeline   import ProviderPipeline, ProviderExhaustedError
from ..config    import get_api_key

PROVIDER_CLASSES = {
    "groq":       GroqProvider,
    "openrouter": OpenRouterProvider,
    "gemini":     GeminiProvider,
    "mistral":    MistralProvider,
    "ollama":     OllamaProvider,
}


def build_pipeline(
    provider_chain: list[str],
    cooldown_seconds: int = 60,
    max_retries_per_provider: int = 1,
    show_provider: bool = True,
) -> ProviderPipeline:
    """Instantiate and return a ready ProviderPipeline from a chain of names."""
    return ProviderPipeline(
        provider_chain=provider_chain,
        cooldown_seconds=cooldown_seconds,
        max_retries_per_provider=max_retries_per_provider,
        show_provider=show_provider,
    )
