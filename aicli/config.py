"""
config.py — Configuration management for aicli.
API keys stored encrypted in ~/.config/aicli/keys.enc (Fernet).
Config stored in ~/.config/aicli/config.toml (TOML).
Falls back to AICLI_* environment variables for CI/CD use.
"""

import os
import json
import getpass
import hashlib
import tomllib
from pathlib import Path
from cryptography.fernet import Fernet

# Optional keyring support — OS keychain when available, Fernet file as fallback
try:
    import keyring as _keyring
    _KEYRING_AVAILABLE = True
except ImportError:
    _KEYRING_AVAILABLE = False

_KEYRING_SERVICE = "aicli"

# ── Paths ──────────────────────────────────────────────────────────────────────
CONFIG_DIR = Path(os.environ.get("AICLI_CONFIG_DIR", Path.home() / ".config" / "aicli"))
CONFIG_FILE = CONFIG_DIR / "config.toml"
KEYS_FILE = CONFIG_DIR / "keys.enc"
DB_FILE = CONFIG_DIR / "sessions.db"
CACHE_DIR = CONFIG_DIR / "cache"
CHROMA_DIR = CONFIG_DIR / "chromadb"

# ── Defaults ────────────────────────────────────────────────────────────────────
DEFAULT_CONFIG = {
    "default_model": "llama-3.3-70b-versatile",
    "show_provider": True,
    "max_retries_per_provider": 1,
    "cooldown_seconds": 60,
    "token_limit": 6000,
    "summarize_threshold": 0.80,
    "encrypt_history": False,
    "summarize_verbose": True,
    "provider_chain": ["groq", "openrouter", "gemini", "mistral", "ollama"],
}

PROVIDER_MODELS = {
    "groq": "llama-3.3-70b-versatile",
    "openrouter": "meta-llama/llama-3.1-8b-instruct:free",
    "gemini": "gemini-1.5-flash",
    "mistral": "mistral-small-latest",
    "ollama": "llama3",
}

# ── Key derivation ──────────────────────────────────────────────────────────────

def _derive_fernet_key(password: str) -> bytes:
    """Derive a Fernet key from a password using SHA-256."""
    import base64
    digest = hashlib.sha256(password.encode()).digest()
    return base64.urlsafe_b64encode(digest)


def _machine_key() -> bytes:
    """Use a machine-specific value as the encryption password for key storage."""
    # Combine hostname + username for a stable machine-specific key
    machine_id = f"{os.uname().nodename}:{os.environ.get('USER', 'user')}"
    return _derive_fernet_key(machine_id)


# ── Key storage ─────────────────────────────────────────────────────────────────

def save_api_key(provider: str, key: str) -> None:
    """Encrypt and save an API key for a provider.
    Uses OS keychain (keyring) when available, Fernet file as fallback."""
    if _KEYRING_AVAILABLE:
        try:
            _keyring.set_password(_KEYRING_SERVICE, provider, key)
            return
        except Exception:
            pass  # fall through to Fernet file

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    fernet = Fernet(_machine_key())

    # Load existing keys
    existing = _load_keys_raw()
    existing[provider] = key

    encrypted = fernet.encrypt(json.dumps(existing).encode())
    KEYS_FILE.write_bytes(encrypted)
    KEYS_FILE.chmod(0o600)


def _load_keys_raw() -> dict:
    """Load all decrypted keys, returns empty dict if file doesn't exist."""
    if not KEYS_FILE.exists():
        return {}
    try:
        fernet = Fernet(_machine_key())
        data = fernet.decrypt(KEYS_FILE.read_bytes())
        return json.loads(data)
    except Exception:
        return {}


def get_api_key(provider: str, prompt: bool = False) -> str | None:
    """
    Get API key for a provider. Priority:
    1. AICLI_{PROVIDER}_KEY env var (CI/CD override)
    2. Encrypted keys file
    3. Prompt user only if prompt=True (used by `config set-key` only)

    The pipeline calls this with prompt=False — missing keys are skipped silently.
    """
    # 1. Environment variable override
    env_key = os.environ.get(f"AICLI_{provider.upper()}_KEY")
    if env_key:
        return env_key

    # 2. OS keychain (keyring) when available
    if _KEYRING_AVAILABLE:
        try:
            kr_key = _keyring.get_password(_KEYRING_SERVICE, provider)
            if kr_key:
                return kr_key
        except Exception:
            pass  # fall through to Fernet file

    # 3. Encrypted file fallback
    keys = _load_keys_raw()
    if provider in keys:
        return keys[provider]

    # 3. Ollama needs no key
    if provider == "ollama":
        return None

    # 4. Only prompt when explicitly requested (config set-key command)
    if not prompt:
        return None

    print(f"\n[aicli] No API key found for {provider}.")
    print(f"  Get a free key at: {_key_url(provider)}")
    key = getpass.getpass(f"  Enter {provider} API key (hidden): ").strip()
    if key:
        save_api_key(provider, key)
        print(f"  ✓ Key saved to {KEYS_FILE}")
    return key or None


def get_config_value(key: str) -> str | None:
    """
    Get any stored value by its exact key name.
    Checks (in order): env var → OS keychain (keyring) → encrypted keys file.
    Used by non-provider integrations like TAVILY_API_KEY, AICLI_PROXY, etc.
    """
    # 1. Direct env var (e.g. TAVILY_API_KEY set in shell)
    env_val = os.environ.get(key)
    if env_val:
        return env_val
    # 2. OS keychain — same store save_api_key() uses when keyring is available
    if _KEYRING_AVAILABLE:
        try:
            kr_val = _keyring.get_password(_KEYRING_SERVICE, key)
            if kr_val:
                return kr_val
        except Exception:
            pass
    # 3. Encrypted Fernet file fallback
    keys = _load_keys_raw()
    return keys.get(key)


def _key_url(provider: str) -> str:
    urls = {
        "groq": "https://console.groq.com/keys",
        "openrouter": "https://openrouter.ai/keys",
        "gemini": "https://aistudio.google.com/app/apikey",
        "mistral": "https://console.mistral.ai/api-keys",
    }
    return urls.get(provider, f"https://{provider}.com")


# ── Config file ─────────────────────────────────────────────────────────────────

def load_config() -> dict:
    """Load config.toml, creating defaults if missing."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)

    if not CONFIG_FILE.exists():
        _write_default_config()

    with open(CONFIG_FILE, "rb") as f:
        user_config = tomllib.load(f)

    # Merge with defaults (user config takes priority)
    config = dict(DEFAULT_CONFIG)
    config.update(user_config)

    # AICLI_PROVIDER_CHAIN env var override (CI/CD friendly)
    env_chain = os.environ.get("AICLI_PROVIDER_CHAIN")
    if env_chain:
        config["provider_chain"] = [p.strip() for p in env_chain.split(",")]

    return config


def _write_default_config() -> None:
    """Write a default config.toml with comments."""
    content = '''# aicli configuration
# ~/.config/aicli/config.toml

# Default model for Groq inference
default_model = "llama-3.3-70b-versatile"

# Show which provider answered each request
show_provider = true

# Retries per provider before failing over to next
max_retries_per_provider = 1

# Seconds to wait before retrying a rate-limited provider
cooldown_seconds = 60

# Token budget for the active context window
token_limit = 6000

# Trigger summarization when window reaches this fraction of token_limit
summarize_threshold = 0.80

# Encrypt chat history in SQLite (optional, slight perf cost)
encrypt_history = false

# Print summary text when /summarize is used (false = silent by default)
summarize_verbose = true

# Provider failover order (override with AICLI_PROVIDER_CHAIN env var)
provider_chain = ["groq", "openrouter", "gemini", "mistral", "ollama"]
'''
    CONFIG_FILE.write_text(content)
