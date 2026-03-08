# Changelog

All notable changes to aicli-maxmux are documented here.

---

## [1.2.0] — 2026-03-07

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

### Added (v1.2.0 — Session 8)
- **F5 — `session fork`**: Fork any session into a new branch
  - `--from-message N` copies first N messages (1-indexed within session)
  - `--name NAME` for custom fork name (auto-names `<source>-fork-1`, `-2`, etc.)
  - Copies latest summary so fork starts with complete historical context
- **F9 — `--cross-session`**: `aicli ask --context --cross-session` searches all past sessions globally
- **F10 — `agent --image`**: Vision input for agent — images passed to plan generation AND observer steps
- **`--context-debug`**: Show injected RAG source tags + 120-char snippets before answering
- **`--min-score FLOAT`**: Override RAG relevance threshold per query (default: 0.40)
- **`session rename OLD NEW`**: Rename session display name; UUID preserved; collision-checked
- **`session summarize NAME`**: Generate/regenerate summary without resuming session
  - `--print-only` to preview without saving
  - `--model` to override provider
- **`session list`**: Now shows full UUID at end of each row for fork/rename commands
- **`aicli config migrate-keys`**: Migrate keys from OS keyring to Fernet backup file
- **`aicli export --include-summary`**: Prepend latest summary to exported session
- SearXNG quiet mode now shows failure count instead of silence

### Fixed (v1.2.0 — Session 8)
- **Fork 0 messages**: `id <= N` used global autoincrement — session messages have high IDs. Fixed: `LIMIT N ORDER BY id ASC`
- **Fork loses context**: Fork now copies latest summary row from source session
- **Irrelevant summaries in cross-session RAG**: `min_score` now applied to summaries (previously all summaries always included)
- **`ImportError` in session summarize**: `from ..db import chat_db` fails in nested async inside Click. Fixed: absolute import
- **`--cross-session` / `--context-debug` missing**: Stale `app.py`/`default.py` repatched from live files

### Security (v1.2.0)
- `pyproject.toml`: Added `readme = "README.md"` — fixes `twine check` warnings
- `.gitignore`: Added `*.png` to prevent accidental media commits
- `config migrate-keys`: Ensures Fernet backup populated for all keys stored pre-1.2.0


## [1.1.0] — 2026-01-xx

*(existing changelog entry goes here)*
