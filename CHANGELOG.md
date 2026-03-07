# Changelog

All notable changes to aicli-maxmux are documented here.

---

## [Unreleased] — v1.2.0-dev

### Added
- F4: `--web` flag — 6-backend search chain, no API key required for free tier
  - Tavily AI search (primary, `TAVILY_API_KEY`, 1000 req/month free)
  - SearXNG public instances (rotated, no key, auto-skipped over Tor)
  - DuckDuckGo Instant Answer JSON API (no key)
  - DuckDuckGo lite HTML with cookie jar (no key)
  - Bing scrape with rotating User-Agent (no key)
  - Mojeek scrape (no key, most reliable free fallback)
- `--web-debug` flag — diagnose web search backends with clean output (successes only)
- `--web-verbose` flag — full debug output including empty/failed backends
- `aicli config set KEY VALUE` — store any key/value in encrypted OS keychain + Fernet file
- `aicli config get KEY` — read any stored key (masked output)
- SOCKS5/Tor proxy support via `AICLI_PROXY` env var or `aicli config set AICLI_PROXY`
  - Works with Tor: `socks5://127.0.0.1:9050` (requires `pip install pysocks`)
  - Works with HTTP proxies: `http://127.0.0.1:8118`
- `config show` now lists optional env vars (TAVILY_API_KEY, AICLI_PROXY)
- `get_config_value()` in config.py — unified key lookup: env → keyring → Fernet file

### Fixed
- Tavily key not found when running under Tor — `save_api_key()` now writes to both
  OS keychain and Fernet file; Fernet is the guaranteed fallback in all process contexts
- SearXNG wasting time on 15 doomed attempts over Tor — auto-skipped when SOCKS active
- Unawaited coroutine warnings from web search backend chain
- Mojeek results not reaching LLM (fixed by lazy lambda backend chain)
- SOCKS5 proxy not applied to executor threads (moved to lazy init in `_get_opener()`)
- `aicli config get` returning wrong key (was missing keyring lookup)
- Keyring priority: env var now correctly wins over keyring (intended behavior for CI/CD)
- SearXNG instance list refreshed — prior 8 instances were all rate-limited or dead

### Security
- `save_api_key()` now always writes to Fernet file as a guaranteed fallback — keys are
  no longer lost if OS keychain becomes unreachable (e.g. headless, Tor, no D-Bus session)
- API keys never written to shell config files
- `TAVILY_API_KEY` stored in OS keychain via `aicli config set`
- `aicli config get` shows masked values only (first 8 + last 4 chars)

---

## [1.1.0] — 2026-01-xx

*(existing changelog entry goes here)*
