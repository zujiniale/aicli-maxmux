# Changelog

## [1.5.7] — 2026-03-16

### Added

*(fill in release notes)*

---


All notable changes to aicli-maxmux are documented here.

---

## [1.5.6] — 2026-03-16 (Session 8 — ShellGPT parity + decisive wins)

### Added

#### `shell_integration.zsh` + `shell_integration.bash` — Context-aware Ctrl+G + Ctrl+E error-fix

- **`_aicli_terminal_context()` helper**: Captures last N lines of terminal scrollback before
  every AI call. Prefers `tmux capture-pane` (gets actual command output, not just history),
  falls back to `fc -ln` (zsh) / `history + awk` (bash).

- **Ctrl+G upgraded**: Now automatically passes `--terminal-context "$term_ctx"` to `aicli ask`
  so the AI sees what's on screen without the user having to describe it. ShellGPT's Ctrl+L
  is blind to terminal state — this is the decisive edge.
  - Empty buffer: inline `aicli>` prompt shown with hint: `(Ctrl+E auto-fixes last failed command)`

- **Ctrl+E error-fix hotkey** (new): Captures last failed command via `fc -ln -1` / `history 1`,
  captures 30 lines of terminal context (includes the error output when in tmux), sends
  `"Fix this failed command: <cmd>"` to `aicli ask --shell --dry-run --lite`. Result pasted
  directly into buffer. Zero typing required to fix a failed command.

#### `aicli/handlers/default.py` — Three new `_ask` capabilities

- **`--terminal-context`** (hidden, set by hotkeys): Last N terminal lines injected as
  `TERMINAL CONTEXT:` system message. Whitespace-only values ignored.

- **`--watch` / `--watch-lines`**: Streaming stdin AI monitor.
  ```bash
  tail -f /var/log/syslog | aicli ask --watch "alert on OOM killer"
  journalctl -f | aicli ask --watch "alert on authentication failure" --watch-lines 20
  ```
  - Reads stdin line-by-line without blocking the event loop (`run_in_executor`)
  - Buffers `watch_lines` lines (default 10), sends each batch to LLM as:
    `CONDITION TO WATCH FOR: <condition>
LOG LINES:
<batch>`
  - LLM responds `YES: reason` → timestamped `[ALERT HH:MM:SS]` printed with triggering batch
  - LLM responds `NO` → completely silent
  - Handles EOF (evaluates partial final batch), Ctrl+C exits cleanly
  - stdin pipe-read guarded: `if not watch and not sys.stdin.isatty()`
  - Specific error if condition omitted: `--watch requires a condition`

- **`--file / -f`** (multiple): Attach any file (text, log, code) as context.
  ```bash
  aicli ask -f error.log "explain this crash"
  aicli ask -f crash.log -f stack_trace.txt "root cause?"
  aicli ask -f screenshot.png -f error.log "same issue?"   # mixed image + text
  ```
  - UTF-8 decode → latin-1 fallback for binary-adjacent files
  - Unreadable files skipped with warning, not crash
  - `from pathlib import Path as _FilePath` hoisted above loop (not per-iteration)
  - Injected as `ATTACHED FILES:` system message

#### Injection Order Optimized (default.py)

Messages now built in LLM-optimal order — richest/most-structured first:
```
role_prompt → RAG context → terminal scrollback → attached files → web search → user
```
Previously TC was injected before RAG (reversed). The model now has semantic memory
framing the raw terminal dump, not the other way around.

### Added (Install UX — Lite Mode wins)

#### `app.py` — Direct invocation: `aicli "hello"` works without subcommand
- `cli` group now routes bare arguments to `ask` automatically:
  `aicli "explain this"` → `aicli ask "explain this"`
  `aicli "find large files" --shell` → `aicli ask --shell "find large files"`
- Flags `-s`, `-c`, `-w`, `-q`, `-r`, `-d`, `-x` all work in direct mode
- Known subcommand names are still routed normally (no conflict with `aicli chat`, `aicli tui` etc.)

#### `app.py` — Zero-config start: auto-detect existing env keys
- `aicli setup` now scans for `GROQ_API_KEY`, `OPENROUTER_API_KEY`, `GEMINI_API_KEY`,
  `MISTRAL_API_KEY` in the environment and auto-saves them — no manual entry required (via  detection)
- Detects `OPENAI_API_KEY` and suggests OpenRouter as compatible drop-in
- `aicli "hello"` just works if any standard key env var is already set

#### `app.py` — First-run guard on `ask`
- When no providers are configured and Ollama is not running, instead of 5 silent
  provider failure lines, shows one clear actionable message:
  ```
  No AI provider configured.
    Fastest free option (30 sec): https://console.groq.com/keys
    Then run: aicli config set-key groq
    Or run:   aicli setup
    Already have OPENAI_API_KEY set? aicli config set-key openrouter
  ```

### Tests

- **`TestTerminalContextFlag`** (4 tests): flag exists, None default, injection as system
  message, empty string not injected
- **`TestWatchMode`** (9 tests): flag, default/custom watch-lines, stdin guard, YES alert,
  NO silent, lines passed to LLM, condition passed to LLM, alert includes batch
- **`TestExtraFilesFlag`** (6 tests): flag, -f shorthand, multiple files, content injected,
  unreadable gracefully skipped, no message when no files

**Total: 703 pytest tests · 530 static checks (run_tests.py)**

### Static Checks Added (run_tests.py)

- **Phase 4** (+12): all 4 new `_ask` params, `_watch_stdin`, `_watch_evaluate`, TERMINAL
  CONTEXT, ATTACHED FILES, injection order (RAG<TC, TC<WEB), `_FilePath` hoisted,
  `LOG LINES` + `CONDITION TO WATCH FOR` in LLM messages
- **Phase 10** (+9): `_aicli_terminal_context` helper, `--terminal-context` arg, tmux
  capture-pane (zsh + bash), Ctrl+E binding (zsh + bash), fix_prompt wording, Ctrl+E hint
- **Phase 28** (+7): `watch`, `watch_lines`, `file` in `ASK_FLAGS`; explicit option checks
  for `--terminal-context`, `--watch`, `--watch-lines`, `--file`
- **Phase 5**: `_server_version` check updated to 1.5.5/1.5.6 (was locked at 1.5.4)

---

## [1.5.5] — 2026-03-16 (Session 7 patch fixes)

### Fixed

#### `app.py` — `ContextRetriever` module-level binding
- **Lazy import shadow bug resolved**: `history_search()` previously imported `ContextRetriever`
  inside the function body via `from .context.retriever import ContextRetriever`. This made the
  name invisible to `unittest.mock.patch`, causing `AttributeError: <module 'aicli.app'> does not
  have the attribute 'ContextRetriever'` in two `TestHistorySearch` tests.
- **Fix**: Added module-level `try/except ImportError` block after handler imports:
  ```python
  try:
      from .context.retriever import ContextRetriever
      from .config import CHROMA_DIR as CHROMA_DIR  # re-export for patching
  except ImportError:
      ContextRetriever = None
      CHROMA_DIR = None
  ```
- `history_search()` now checks `if ContextRetriever is None` instead of catching `ImportError`
- `patch("aicli.app.ContextRetriever", None)` now works correctly — matches the real fallback state

#### `app.py` — Stale `/tmp/` path auto-cleanup in `config install-shell`
- **Root cause**: `test_install_shell_detects_zsh` patched `aicli.app.CONFIG_DIR` → temp dir but
  did not patch `pathlib.Path.home()`. This caused `rc_file = Path.home() / ".zshrc"` to resolve
  to the real `~/.zshrc`, writing `source "/tmp/tmpXXXXXX/shell_integration.zsh"` into it on
  every test run — two dead entries accumulated.
- **Production fix**: `config_install_shell()` now strips stale `/tmp/` source lines before
  appending the permanent path:
  ```python
  cleaned = re.sub(r'\nsource "/tmp/[^"]+/shell_integration\.[^"]+"[^\n]*\n?', "", rc_content)
  ```
  Self-healing: next `aicli config install-shell` run automatically removes stale entries.
- **Test fix**: `test_install_shell_detects_zsh` now also patches `pathlib.Path.home` → `tmp`
  so rc file writes go to `tmpdir/.zshrc`, never touching the real home directory.
- **Manual fix** (if already affected): `sed -i '/source.*\/tmp\/tmp.*shell_integration/d' ~/.zshrc`

#### `handlers/mcp_server.py` — `ContextRetriever` module-level binding
- **Same lazy import shadow bug**: `_tool_ask()` imported `ContextRetriever` inside a `try/except`
  block, bypassing `patch("aicli.handlers.mcp_server.ContextRetriever", ...)` entirely. The mock
  was never called → RAG system message not injected → `test_ask_injects_rag_context_when_available`
  assertion failed.
- **Fix**: Module-level `try/except ImportError` binding:
  ```python
  try:
      from ..context.retriever import ContextRetriever
  except ImportError:
      ContextRetriever = None
  ```
- `_tool_ask()` now checks `if ContextRetriever is None or CHROMA_DIR is None` before instantiating

#### `handlers/mcp_server.py` — `CHROMA_DIR` import consolidation (Phase 5 static check)
- **Root cause**: Fixing the `ContextRetriever` binding introduced a second `from ..config import`
  line (for `CHROMA_DIR` inside the `try/except`). Phase 5 static check enforces
  `mcp.count("from ..config import") <= 1` to prevent lazy re-import anti-patterns.
- **Fix**: `CHROMA_DIR` merged into the existing top-level import line:
  ```python
  from ..config import load_config, CONFIG_DIR, CHROMA_DIR
  ```
  `CHROMA_DIR` is always defined in `config.py` regardless of chromadb installation — only
  `ContextRetriever` is the optional dependency.

#### `tests/test_new_commands.py` — Mock semantics after module-level refactor
- **`test_history_handles_no_chromadb`**: Was using `side_effect=ImportError("no chromadb")` on
  the `ContextRetriever` patch. After the module-level binding fix, `history_search()` no longer
  catches `ImportError` — it checks `if ContextRetriever is None`. The mock was truthy (not None),
  so the None check passed, then `ContextRetriever(CHROMA_DIR)` fired the side_effect, raised
  unhandled → `exit_code = 1`.
- **Fix**: `patch("aicli.app.ContextRetriever", None)` + `patch("aicli.app.CHROMA_DIR", None)` —
  sets module attributes to `None`, exactly matching the real `except ImportError` fallback state.
  The function now exits cleanly with `exit_code = 0`.

### Tests

- **`TestHistorySearch.test_history_handles_no_chromadb`** — now passes (mock → None, not side_effect)
- **`TestHistorySearch.test_history_no_indexed_data`** — now passes (patch target exists at module level)
- **`TestMCPToolCallAsk.test_ask_injects_rag_context_when_available`** — now passes (module-level binding)
- **`test_install_shell_detects_zsh`** — `Path.home()` now patched; no longer writes to real `~/.zshrc`

**Total tests: 683 passing** (unchanged — tests that were failing now pass)
**Static checks: 490/490** (`python3 run_tests.py`) — up from 489/490 (Phase 5 fixed)

---

## [1.5.4] — 2026-03-16 (Session 5 additions)

### Added

#### `aicli history` — Semantic search across all sessions (`app.py`)
- **`aicli history QUERY`** — search all indexed chat sessions using ChromaDB RAG
  - `aicli history "async python patterns"`
  - `aicli history "docker deploy" --results 10`
  - `aicli history "bug fix" --min-score 0.3`
  - Options: `--results/-n` (default 5), `--min-score` (default 0.25), `--sessions/-s` (default 5)
  - Graceful degradation: prints helpful message if chromadb not installed or no sessions indexed

#### `aicli stats` — Token and message counts (`app.py`)
- **`aicli stats`** — show per-session message and token counts
  - `aicli stats --session myproject` — single session detail (user/assistant split + summary presence)
  - `aicli stats --top 5` — top 5 sessions by message count
  - Grand totals: total sessions, messages, tokens across all
  - NULL-safe token counting (`or 0` / `COALESCE` pattern for pre-1.5.4 messages)

#### `aicli serve --daemon` + `aicli serve stop` (`handlers/serve.py`, `app.py`)
- **`aicli serve --daemon`** — fork server to background, write PID to `~/.config/aicli/serve.pid`
  - `os.fork()` → `os.setsid()` → redirect stdio to `/dev/null` → `serve_forever()`
  - Stale PID detection via `os.kill(pid, 0)` — handles prior crash gracefully
- **`aicli serve stop`** — send `SIGTERM` to daemon PID and remove PID file
  - Handles: missing PID file, corrupt PID, `ProcessLookupError`, `PermissionError`
- `run_serve()` gains `daemon=False` parameter — backward compatible

#### MCP `_tool_ask` RAG context (`handlers/mcp_server.py`)
- `_tool_ask` now performs semantic RAG search before the session-history window
  - Calls `ContextRetriever.retrieve()` with `include_chat=True, n_chat=5, min_score=0.25`
  - RAG block injected as `{"role": "system", ...}` before the last-10-message window
  - Fully optional — `except Exception: pass` if chromadb not installed

#### `shell_integration.ps1` — PowerShell Ctrl+G hotkey (`shell_integration.ps1`)
- **Ctrl+G in PowerShell** — generates shell command from buffer content, pastes result back
- Uses `PSReadLine` `Set-PSReadLineKeyHandler` — graceful warning if PSReadLine missing
- Auto-installs via `aicli config install-shell --shell powershell` (new option)

#### `aicli config install-shell --shell powershell` (`app.py`)
- `--shell` choice expanded from `[zsh, bash]` to `[zsh, bash, powershell]`
- Copies `shell_integration.ps1` to `CONFIG_DIR`, appends `. "..."` line to `$PROFILE`
- Detects PowerShell 7 profile path first, falls back to Windows PowerShell 5.1

#### `bump_version.py` — Atomic version update across 6 files (new file, 180 lines)
- Updates `aicli/__version__.py`, `pyproject.toml`, `aicli/handlers/mcp_server.py` fallback,
  `map_structure.sh`, `README.md` badge + Latest line, `CHANGELOG.md` header
- `--dry-run` preview, `--current` query, `--update-tests N` for test badge
- Usage: `python bump_version.py 1.5.5`

### Fixed

#### `run_tests.py` — False positives and new checks
- **PS1 path check**: now accepts both `aicli/shell_integration.ps1` and `shell_integration.ps1` (file lives at project root)
- **New proxy checks** (6 added to Phase 16):
  - `proxy: serve.py has daemon mode + PID file`
  - `proxy: app.py has history search command`
  - `proxy: app.py has stats command`
  - `proxy: bump_version.py exists`
  - `proxy: shell_integration.ps1 exists`
  - `proxy: config install-shell supports powershell`
  - `proxy: _tool_ask uses RAG context (ContextRetriever) when available`
- **Phase 15 AsyncMock anti-pattern checks** (3 added): locks in `async def stream` pattern across test_new_commands.py, test_mcp_server.py, test_comprehensive.py
- **Phase 16 PYTEST_ONLY auto-generation**: replaced static list with `glob.glob("tests/test_*.py")` class scanner + `KNOWN_PROXIED_CLASSES` exclusion set

### Tests

New test classes (all passing):

- **`TestServeDaemon`** (4 tests, `test_new_commands.py`) — `--daemon` flag present, `stop_serve()` routing, missing PID graceful, PID file path
- **`TestHistorySearch`** (4 tests, `test_new_commands.py`) — command exists, requires query, no-chromadb graceful, no-indexed-data message
- **`TestStatsCommand`** (4 tests, `test_new_commands.py`) — command exists, no-sessions OK, shows summary, `--session` flag graceful
- **`TestMCPToolCallAsk` RAG** (2 new tests, `test_mcp_server.py`) — RAG context injected when available, continues without chromadb

**Total tests: 683 passing** (up from 669)
**Static checks: 482/482** (`python3 run_tests.py`)

---


### Added

#### MCP Server (`handlers/mcp_server.py`) — 703 lines
- **`aicli mcp`** — new top-level command, starts a Model Context Protocol server for Claude Desktop integration
  - `aicli mcp` — stdio transport (default, for Claude Desktop `mcpServers` config)
  - `aicli mcp --transport sse` — SSE transport for browser/network clients
- **4 MCP tools** exposed to Claude Desktop:
  - `ask` — full AI prompt via provider pipeline (`prompt`, `session_id`, `model`)
  - `cmd` — shell command generation with fence-stripping (`prompt`, `dry_run`)
  - `code` — code generation with correct language casing (`prompt`, `language`)
  - `tag` — session tag management, merges without overwriting (`session_id`, `tags`)
- **2 MCP resources**:
  - `sessions://list` — all sessions with metadata
  - `sessions://{session_id}` — full message history for a session
- **Protocol**: JSON-RPC 2.0, `PROTOCOL_VERSION = "2024-11-05"` (MCP spec)
- **`_LANG_DISPLAY` dict** — correct casing for JavaScript, TypeScript, Node.js (not capitalized)
- **stdio transport**: `sys.stdin` → JSON-RPC → `sys.stdout.buffer` (avoids `asyncio.BaseProtocol` misuse)
- **SSE transport**: `HTTPServer` + `queue.SimpleQueue` (thread-safe; not `asyncio.Queue`)

**Claude Desktop config:**
```json
{"mcpServers": {"aicli": {"command": "aicli", "args": ["mcp"]}}}
```

#### `aicli tag` command (`app.py`)
- **`aicli tag SESSION TAGS`** — tag a session from the CLI
  - Resolves session by exact name, UUID prefix, or `startswith` fallback
  - Merges new tags into `graph_links.json` without overwriting existing tags
  - Handles `JSONDecodeError` gracefully

### Fixed

#### `app.py`
- **Lazy import shadow bugs (3)**: `CONFIG_DIR`, `run_serve`, and `CONFIG_DIR` in `tag()` were re-imported inside function bodies, silently defeating `patch()` in tests. All moved to module-level imports.
- **Duplicate `def tag`**: First (weaker) definition removed
- **Shebang position**: `__version__` import was before shebang; shebang moved to line 1

#### `handlers/mcp_server.py`
- **`asyncio.BaseProtocol` misuse**: `connect_write_pipe(BaseProtocol, stdout)` replaced with `sys.stdout.buffer`
- **`asyncio.Queue` in sync thread**: Replaced with `queue.SimpleQueue` in SSE transport
- **`asyncio.get_event_loop()` deprecated** (Python 3.12+): Replaced with `asyncio.get_running_loop()`
- **`_server_version()` fallback**: Was hardcoded `"1.5.3"`, corrected to `"1.5.4"`
- **Triple-fence stripping**: `_tool_cmd` now strips ` ```bash ... ``` ` fences via `re.sub()`
- **Lone-backtick stripping**: Added `.strip('`')` after fence strip
- **`_tool_tag` session resolution**: Was using `config.get("data_dir")` (key doesn't exist); now uses `CONFIG_DIR` and resolves by name → UUID → startswith
- **Empty tool_name guard**: Added `-32602` JSON-RPC error for missing tool name
- **Language casing**: `language.capitalize()` produced `Javascript`; replaced with `_LANG_DISPLAY` dict

#### `handlers/serve.py`
- **`load_config()` + `get_role()` not mocked in tests**: Both now patched in test fixtures; were hitting real keyring/config files and returning 500

#### `web.py`
- **`_tavily_search` alias**: Added `_tavily_search = _search_tavily` at module level for test patchability

#### `pyproject.toml`
- `pytest` / `pytest-asyncio` confirmed dev-only (not in core deps)
- `asyncio_mode = "auto"` confirmed present
- `[rag]`, `[proxy]`, `[mcp]` extras added/confirmed

### Tests

New and updated test suites (`tests/` — all passing):

- **`test_mcp_server.py`** (70 tests, 13 classes) — complete JSON-RPC dispatch, all 4 tools, 2 resources, edge cases, transport constants, language name casing, fence stripping, server version semver
- **`test_comprehensive.py`** (245 tests, 22 classes) — master regression suite covering every bug S1-1 through V3-4, all CLI commands, all flags, all MCP protocol paths, env var mirrors, shell scripts
- **`tests/conftest.py`** — session-scoped `aicli_cli` fixture (import once per run), `_BindingStub` stub (no async GC warnings), `slow`/`fast`/`serve` pytest markers, module-level `aicli.app` pre-warm
- **`run_tests.py`** — 467 static checks across 32 phases, `--time` flag, runs in 0.15s
- **Bug fixes in existing tests**:
  - `test_comprehensive.py`: `inspect.getsource(cmd)` → `.callback` for Click commands
  - `test_tui_pure.py`: `HotkeyInput._on_key` → `on_key`; `str(BINDINGS)` → `getsource` text search
  - `test_new_commands.py`: `getpass.getpass` mocked; `sys.stdin` mocked; `ContextRetriever` patch path fixed; `AsyncMock(return_value=aiter(...))` anti-pattern replaced with proper async generators
  - `test_serve.py`: Hardcoded ports (18801–18807) → `_free_port()` OS-assigned; `load_config` + `get_role` patched; `pytestmark = pytest.mark.slow`
  - `test_web_search.py`: All 6 backends now patched in every test (3 tests were hitting real network, causing 166s slowdown)
  - `test_graph_server.py`: 7× `time.sleep(0.05/0.1)` → `_wait_for_port()` socket polling

**Total tests: 669 passing** (up from 354 after v1.5.3)  
**Static checks: 467/467** (`python3 run_tests.py`)  
**Full suite runtime: ~30s** (down from 3+ minutes; 166s web search timeouts eliminated)

---

## [1.5.3] — 2026-03-15

### Added

#### CLI (`app.py`, `handlers/default.py`)
- **`aicli cmd`** — new top-level command, shorthand for `ask --shell`
  - `aicli cmd "find all files larger than 100MB"`
  - `aicli cmd "kill process on port 3000" --run` — execute immediately, skip menu
  - `aicli cmd "list docker containers" --dry-run` — print only, no menu
  - Supports `--lite` and `--quiet` flags
- **`aicli code`** — new top-level command, shorthand for `ask --code`
  - `aicli code "write a merge sort in Python"`
  - `aicli code "fibonacci function" --run` — generate + execute
  - `aicli code "parse CSV" --run --language bash` — run as bash
  - Supports `--run`, `--language`, `--max-retries`, `--timeout`, `--lite`, `--quiet`
- **`--quiet / -q` flag** on `ask` and `code`
  - Suppresses provider footer, web search status messages, and all info chrome
  - Raw output only — ideal for shell scripting and piping: `aicli ask -q "..." > out.txt`
  - Also available via `AICLI_QUIET=1` environment variable
- **`aicli setup`** — interactive first-time setup wizard
  - Walks through all four providers with masked key entry
  - Skips providers that are already configured
  - Prints quick-start summary and hotkey install hint on completion
- **`aicli config install-shell`** — install shell hotkey integration
  - Auto-detects `zsh` or `bash` from `$SHELL`; override with `--shell zsh|bash`
  - Configurable hotkey via `--hotkey` (default: `Ctrl+G = ^G`)
  - Appends `source` line to `~/.zshrc` or `~/.bashrc`
  - Hotkey behaviour: pastes AI-generated shell command directly into terminal buffer
  - Shell integration scripts: `aicli/shell_integration.zsh`, `aicli/shell_integration.bash`
- **`--lite` flag** on `ask` and `cmd`
  - Skips RAG/ChromaDB initialization entirely — faster cold start
  - Also available via `AICLI_LITE=1` environment variable
- **`aicli-lite` entry point** — separate binary for minimal installs
  - Sets `AICLI_LITE=1` automatically; no need to pass flag
  - `pip install aicli-maxmux[lite]` → `aicli-lite ask "hello"` (~20MB install)

#### Local HTTP API (`handlers/serve.py`, `aicli serve`)
- **`aicli serve`** — new top-level command, starts a local REST API server
  - Default: `localhost:8765` (does not conflict with graph server on `7337`)
  - `--port`, `--host`, `--quiet` options
  - Endpoints: `POST /ask`, `POST /ask/shell`, `POST /ask/code`, `GET /sessions`, `GET /sessions/:id`, `GET /health`, `GET /providers`
  - Request body: `{"prompt": "...", "web": false, "lite": false, "model": null}`
  - Shell responses automatically strip backtick fences
  - CORS header (`Access-Control-Allow-Origin: http://localhost`) for local browser tools
  - Designed for scripting, MCP integration, and third-party tool access

#### Lite Mode (`pyproject.toml`)
- **`[lite]` optional extra** — minimal dependency set (~20MB vs ~468MB full)
  - Includes: `cryptography`, `click`, `tiktoken`, `httpx`, `rich`
  - Excludes: `chromadb`, `textual`, `sentence-transformers`
  - Install: `pip install aicli-maxmux[lite]`
- **`install.sh`** — one-liner bootstrap script
  - `bash install.sh` — full install
  - `bash install.sh lite` — lite install
  - Python version check (3.11+ required)

#### Shell Integration (`aicli/shell_integration.zsh`, `aicli/shell_integration.bash`)
- Two new integration scripts installed via `aicli config install-shell`
- `Ctrl+G` in terminal → generates a shell command from current buffer or inline prompt → pastes into buffer
- Uses `--lite --dry-run` for minimal overhead

#### Vim-style TUI Navigation (`tui.py`)
- **`j` / `k`** — scroll chat down / up (disabled when prompt input is focused)
- **`G`** — jump to bottom of chat
- **`g`** — jump to top of chat
- **`/`** — focus the session search box
- **`dd`** — delete session: press `d` twice within 1.5s; auto-cancels on any other key
- All vim keys guarded by `_is_input_focused()` — won't fire while typing in prompt
- HelpScreen updated with vim navigation section
- `_dd_pending` state with `set_timer(1.5, _cancel_dd)` auto-cancel

#### Obsidian Export (`handlers/export.py`)
- **`aicli export SESSION --obsidian`** — Obsidian-compatible markdown export
  - YAML frontmatter: `title`, `session_id`, `date`, `created`, `message_count`, `tags`, `description`
  - Assistant messages wrapped in `> [!assistant]-` callout blocks
  - Summary (with `--include-summary`) in `> [!summary]+` callout
  - Auto-summary system messages as `> [!info]-` callouts
  - Per-message heading anchors (`^msg-N`) for `[[wikilink]]` cross-referencing
  - `aicli export SESSION --obsidian --include-summary -o ~/vault/SESSION.md`

#### Graph Node Tags + Filtering (`graph_server.py`)
- **Tag field** in node panel (comma-separated) — persisted to `graph_links.json` `names` dict
- **Tag bar** in graph UI header — filter input + auto-generated tag chip buttons per tag
- **`filterByTag()`** — dims non-matching nodes to 18% opacity; shows match count
- **`clearTagFilter()`** — restores all nodes
- **`#tag` label** beneath each node (first tag shown)
- **`POST /api/tags`** endpoint — server-side filter: `{"tag": "python"}` → `{"nodes": [...]}`
- Tag filter is case-insensitive
- `GET /api/sessions` now includes `tags: []` per node

### Fixed / Improved

#### Config (`config.py`)
- **Lazy ChromaDB directory creation**: `CHROMA_DIR.mkdir()` removed from `load_config()` — directory is now only created when RAG is actually initialized in `context/manager.py`
  - Previously: ChromaDB dir created on every `aicli` invocation (even `aicli --version`)
  - Now: created on-demand only when `ContextManager.initialize()` runs and chromadb is available

#### Context Manager (`context/manager.py`)
- `CHROMA_DIR.mkdir(parents=True, exist_ok=True)` moved into `initialize()` cold layer block — created only when RAG actually loads

#### Dependencies (`pyproject.toml`, `requirements.txt`)
- **Removed `pytest`/`pytest-asyncio` from core `dependencies`** — they are dev tools, not runtime requirements. Were incorrectly listed as install dependencies since v1.0; now correctly in `[dev]` only
- `requirements.txt` reorganized into sections: lite-compatible / dev-only / full-only
- Added install mode header with `pip install` examples for each mode

### Tests

New test suites added (`tests/` — all passing):

- **`test_serve.py`** (18 tests) — `TestServeHealth`, `TestServeProviders`, `TestServeAsk`, `TestServeAskShell`, `TestServeSessions`: covers all 7 HTTP endpoints, error cases, provider exhaustion, backtick stripping
- **`test_web_search.py`** (9 tests) — `TestWebSearch`, `TestWebSearchQueryFormatting`, `TestWebSearchResultFormat`: chain fallback, Tor/SOCKS5 SearXNG skip, network error handling, result injection
- **`test_new_commands.py`** (28 tests) — `TestCmdCommand`, `TestCodeCommand`, `TestQuietFlag`, `TestLiteFlag`, `TestSetupCommand`, `TestServeCommand`, `TestMainLite`, `TestConfigInstallShell`: all v1.5.3 CLI additions
- **`test_tui_pure.py`** — extended with 3 new classes (32 tests):
  - `TestVimNavActionsStructure` (14 tests): ACTIONS entries, DEFAULT_KEYS mappings, no duplicate IDs
  - `TestVimNavSourceInspection` (14 tests): action methods exist, focus guard, dd state, help screen
  - `TestVimNavBindingsInSource` (5 tests): BINDINGS list contains j/k/G/g/slash
  - `TestObsidianExport` (12 tests): frontmatter, callouts, anchors, summary, message content
- **`test_graph_server.py`** — extended with `TestNodeTags` (10 tests): tag save/load roundtrip, `/api/tags` filter, case-insensitive matching, HTML tag bar/panel/chips presence

Total new tests this release: **~107** (193 existing + 107 new = **~300 passing**)

---

## [1.5.1] — 2026-03-09

### Fixed

#### TUI (`tui.py`)
- **Bug #48**: Sending messages broken — `HotkeyInput.on_key` missing `super()._on_key(event)` fallback caused all unhandled keys (including regular typing) to be silently dropped; fixed by adding `else: super()._on_key(event)`
- **Bug #49**: `action_send` was `async def` but called via `call_later()` which doesn't await coroutines — silently no-ops every time; fixed by making `action_send` a sync `def` that launches `_send_message` via `run_worker()`
- **Bug #50**: `action_summarize` used `call_later(self._run_summarize)` which doesn't run async functions; fixed with `run_worker(self._run_summarize(), exclusive=False)`
- **Bug #51**: `ctx.summarize_now(messages)` passed messages as argument but method takes no positional args; fixed to `ctx.summarize_now()`
- **Bug #52**: F7 opened static `graph.html` file (empty due to browser security blocking local file reads); fixed to open `http://localhost:7337/` directly
- **Bug #53**: Prompt input not focused on startup — Enter/hotkeys appeared dead on first launch; fixed with `call_after_refresh(lambda: query_one("#prompt-input").focus())` in `on_mount`

### Added

#### TUI (`tui.py`)
- **▶ Send button**: Clickable send button next to input bar — works regardless of terminal F-key interception
- **Enter = send**: Native `on_input_submitted` at App level + `HotkeyInput.on_key` both handle Enter to send
- **Ctrl+Enter = newline**: Insert newline for multiline messages (replaces send)
- **Taller input bar**: Input area height increased from 3 to 5 rows for comfortable typing

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
