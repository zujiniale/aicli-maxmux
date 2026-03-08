# Changelog

All notable changes to aicli-maxmux are documented here.

---

## [1.3.0] — 2026-03-08

### Added
- **F8 — `aicli ask --code --run`**: Execute generated Python code in a subprocess with self-correction loop
  - `--run` flag on `ask --code` — generates code, runs it, shows output
  - `--max-retries N` — self-correction attempts on error (default: 3)
  - On failure: feeds error back to LLM for correction, retries automatically
  - `handlers/code_runner.py` — `_extract_code()` strips ``` fences, `_run_code()` subprocess with 30s timeout
- **F6 — Plugin system**: Auto-load custom tools from `~/.config/aicli/plugins/`
  - Drop any `.py` file with `register() -> dict` into the plugins directory
  - `aicli plugin list` — show all loaded plugins + load errors
  - `aicli plugin run NAME ARG` — invoke a plugin directly from CLI
  - `aicli plugin errors` — show failed plugin load errors
  - `tools/loader.py` — `load_plugins()`, `call_plugin()`, `get_load_errors()`
  - Plugins cached on first load; `force_reload=True` to re-scan
  - Files starting with `_` (e.g. `__init__.py`) skipped automatically
- **F7 — TUI**: Full terminal UI via Textual (`pip install textual`)
  - `aicli tui [--session NAME] [--model MODEL]`
  - Left sidebar: session list with message counts, click to switch
  - Main panel: scrollable conversation with role colors
  - Bottom input bar with flags display (`[web ON]` / `[ctx ON]`)
  - Status bar: active provider, flags, token count
  - `Ctrl+N` new session, `Ctrl+D` delete, `Ctrl+E` export to markdown
  - `Ctrl+W` toggle web search, `Ctrl+X` toggle RAG context
  - `Ctrl+S` summarize current session, `Ctrl+Q` quit
  - Graceful: shows error if textual not installed
- **91 tests** — up from 71 (F8: 6 new, F6: 7 new, + 7 existing)

### Requires (optional)
- F7 TUI: `pip install textual`  (or `pip install aicli-maxmux[tui]` in v1.3.0)

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
