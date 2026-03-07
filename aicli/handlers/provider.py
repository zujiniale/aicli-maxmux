"""handlers/provider.py — Provider management handlers."""
from ..config import load_config, get_api_key
from ..printer import print_provider_status, print_error, print_success, print_info
from ..providers.pipeline import ProviderPipeline, ProviderExhaustedError


async def _provider_status():
    config = load_config()
    try:
        pipeline = ProviderPipeline(
            provider_chain=config["provider_chain"],
            cooldown_seconds=config["cooldown_seconds"],
            max_retries_per_provider=config["max_retries_per_provider"],
        )
        print_provider_status(pipeline.status())
    except ProviderExhaustedError as e:
        print_error(str(e))


async def _provider_test(provider_name):
    key = get_api_key(provider_name)
    if not key and provider_name != "ollama":
        print_error(f"No key for {provider_name}. Run: aicli config set-key {provider_name}")
        return

    from ..providers.groq import GroqProvider
    from ..providers.openrouter import OpenRouterProvider
    from ..providers.gemini import GeminiProvider
    from ..providers.mistral import MistralProvider
    from ..providers.ollama import OllamaProvider
    providers_map = {
        "groq": GroqProvider,
        "openrouter": OpenRouterProvider,
        "gemini": GeminiProvider,
        "mistral": MistralProvider,
        "ollama": OllamaProvider,
    }

    cls = providers_map.get(provider_name)
    if not cls:
        print_error(f"Unknown provider: {provider_name}")
        return

    p = cls(api_key=key) if provider_name != "ollama" else cls()
    messages = [{"role": "user", "content": "Say 'OK' and nothing else."}]

    print_info(f"Testing {provider_name}...")
    try:
        chunks = []
        async for chunk in p.stream(messages):
            chunks.append(chunk)
        response = "".join(chunks).strip()
        print_success(f"{provider_name}: {response}")
    except Exception as e:
        print_error(f"{provider_name} failed: {e}")
