# Changelog

All notable changes to aicli-maxmux are documented here.

---

## [1.5.0] — 2026-03-08

### Added

#### Launch Script Overhaul (`start.sh`)
- **3-pane wmctrl layout**: TUI left ¾ (full height) · Graph terminal top-right ¼ · Firefox bottom-right ¼
- **Auto-installs `wmctrl`** if not present (`sudo apt-get install -y wmctrl -qq`)
- **Auto-detects screen resolution** via `xdpyinfo`; falls back to 1920×1080 if unavailable
- **Named terminal titles** (`aicli — TUI`, `aicli — Graph`) so wmctrl can reliably target each window
- **Auto-opens Firefox** to `http://localhost:7337` (graph viewer) on launch
- **Startup status print**: layout coordinates, graph URL printed to stdout on launch
- **venv activation** preserved from previous version — still activates `./venv/` if present
- Positions all three windows after a staggered `sleep` to allow windows time to open

#### Documentation Suite
- **`AICLI_DOCS.md`** — comprehensive project documentation:
  - Full component breakdown (TUI, graph server, Firefox view)
  - Annotated `start.sh` walkthrough
  - All 4 roadmap tracks with implementation detail
  - ~35 specific test function stubs for `TestTUI`, `TestGraphServer`, `TestWebSearch`
  - 6-tier feature roadmap
- **`MASTER_ROADMAP.md`** — unified prioritized roadmap (aicli + companion CrudLogin project):
  - Reward / Effort / Unlocks scoring for every item
  - Week-by-week 6-week execution plan
  - Full impact matrix table
- **`MASTER_SESSION_DOC.md`** — 1,052-line complete session record:
  - Every exchange, decision, and root cause documented
  - All code patterns with copy-paste snippets
  - All bugs fixed with root cause + fix

### Roadmap (Tracked — not yet implemented)
The following items were scoped and documented this session for upcoming releases:

- **`TestTUI`** — ~15 tests: TUI render, input handling, session lifecycle, error paths
- **`TestGraphServer`** — ~12 tests: HTTP routes, node/edge CRUD, graph serialization, `/api/sessions`
- **`TestWebSearch`** — ~8 tests: query formatting, result parsing, network error handling
- **v1.5.x: Graph node tags + filtering** — `aicli tag <id> <tags>`, filter sidebar in graph UI
- **v1.5.x: `aicli serve`** — local HTTP API (`POST /ask`, `GET /sessions`) for scripting + MCP
- **v1.5.x: Vim-style TUI navigation** — `j/k` scroll, `/` search, `dd` delete, `:q` quit
- **v1.6.x: Obsidian export** — `aicli export --obsidian <vault>` → `.md` + `[[wikilinks]]`
- **v2.0.x: MCP server** — expose aicli as Claude Desktop tool via Model Context Protocol

---

## [1.4.0] — 2026-03-08

### Added

#### TUI Overhaul (`tui.py`)
- **F1 — Help overlay**: Full keyboard shortcut reference, dismissable with Esc
- **F2 — Range select**: Click message start → click end → Ctrl+Y copies range to clipboard
- **F3 — Theme cycling**: 5 built-in themes (Tokyo Night, Dracula, Gruvbox, Nord, Solarized Dark), saved across restarts
- **F4 — Export session**: Timestamped `.md` + `.json` to exports dir; `__latest.json` always updated
- **F5 — Import session**: Loads most recent exported `.json` into current session in-place
- **F6 — Sync all**: Copies `sessions.db` + all TUI config JSONs + graph HTML to exports dir
- **F7 — Open graph**: Opens graph viewer HTML in browser via `xdg-open`
- **Ctrl+9 — Settings**: Configurable export folder path + all hotkey remappings, saved to `tui_keys.json`
- **Ctrl+K — Pin session**: Float to top of list with 📌 icon + amber border, persisted to `tui_pinned.json`
- **Ctrl+B — Bulk select**: Multi-session operations (delete, export, pin)
- **Ctrl+J — Backup JSON**: Dump all sessions + summaries to `backup-TIMESTAMP.json`
- **Ctrl+I — Import JSON**: Restore sessions from most recent backup (existing sessions skipped)
- **Ctrl+O — Open exports folder**: `xdg-open` exports directory
- **Ctrl+Y — Smart copy** (4 tiers): range → TextArea selection → message block → last assistant message
- **Ctrl+R — Typed range copy**: Type `3-7` in input then Ctrl+R to copy messages 3–7
- **TextArea selectability**: All message bodies use `TextArea(read_only=True)` — text is now selectable and copyable
- **Real system clipboard**: Uses `wl-copy` → `xclip` → `xsel` → `pbcopy` chain; falls back to `/tmp/aicli_copy.txt`
- **Dynamic CSS theming**: All colors driven by theme dict; `build_css(theme)` generates full CSS at init
- **Configurable exports dir**: Default `~/Music/aicli/exports/`; override via Ctrl+9 Settings, stored in `tui_exports.json`
- **Auto-sync**: DB + config silently synced to exports dir after every assistant message
- **`--no-history` flag**: `aicli tui --no-history` opens session without loading past messages

#### Graph Viewer (`graph_server.py`, `aicli graph`)
- `aicli graph` — starts local HTTP server on `localhost:7337`, opens browser automatically
- Auto-loads all session exports as nodes (no manual file picking)
- D3 force-directed graph with Tokyo Night theme, JetBrains Mono font
- Link mode (L key): click two nodes to create a directional link
- Node panel: rename, add notes, see connections, delete
- Hover link + click to delete
- Double-click to edit node
- Persistent graph state saved to `graph_links.json` in exports dir (reloaded on next `aicli graph`)
- `aicli graph --port N` — custom port
- `aicli graph --no-browser` — headless / scripted use
- R key reloads sessions (picks up new F4 exports without restart)

#### Code Interpreter (`code_runner.py`, `--run`)
- `--language bash|node|ruby` — generate and run code in non-Python runtimes
- `--timeout N` — subprocess execution timeout (default: 30s), wraps entire streaming coroutine
- Live streaming stdout — output appears line-by-line as it runs
- Correction count in done message: `✓ Done. (2 corrections)` vs `✓ Done.`

#### Plugin System (`loader.py`)
- `aicli plugin install URL [--name]` — download + install plugin from URL to `~/.config/aicli/plugins/`
- `aicli plugin doc NAME` — show full description, version, author, source path
- Async plugin functions auto-wrapped in sync shim — `asyncio.run()` wrapper injected transparently
- Missing `version` field now emits `UserWarning` instead of silently passing (plugin still loads)

#### Launch Script
- `start.sh` — opens TUI and graph viewer in two separate terminal windows simultaneously
  - Auto-detects terminal: kitty → alacritty → gnome-terminal → xterm
  - Activates venv if present at `./venv/`

### Fixed
- **Bug #41**: Range-pick second click not registering — `event.widget=NoneType` at App level in Textual 0.89; moved to `MessageBlock.on_click` (widget-level)
- **Bug #42**: Range state reset between clicks — `_append_message()` during pick mounted new widget triggering recursive event; replaced with `_set_range_status()` (Static update, no DOM change)
- **Bug #43**: `ctrl+m` dead — terminal converts to ASCII 13 (Enter) before Textual sees it; remapped range-pick to F2
- **Bug #44**: Hotkeys not firing from input — `call_later(app.on_key, event)` uses dead event; fixed with `call_later(app.action_X)` direct action dispatch
- **Bug #45**: Exports going to wrong dir — old `_exports_dir()` not replaced; fixed and defaulting to `~/Music/aicli/exports/`
- **Bug #46**: F5 import navigating away — rewrites INTO current session, calls `_render_chat()` in place
- **Bug #47**: Graph empty — browser security blocks local file reads; graph server now serves sessions via `/api/sessions`

### Tests
- 97 passing (up from 84)
- Added `TestCodeRunnerLanguage` (6 tests): runners map, bash execution, unknown language fallback, timeout propagation
- Added `TestPluginInstallDoc` (2 tests): async fn wrapper, missing version warning
- Added `TestCrossSessionRAG` (2 tests): cross-session retrieval, isolation verification
- Added `TestContextDebugSnippet` (3 tests): sentence-boundary truncation

---

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
