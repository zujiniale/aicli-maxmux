# Changelog

## [1.6.3] — 2026-03-17

### Added

*(fill in release notes)*

---


## [1.6.2] — 2026-03-17

### Added

*(fill in release notes)*

---


## [1.6.1] — 2026-03-17

### Added

*(fill in release notes)*

---


All notable changes to aicli-maxmux are documented here.

---

## [1.6.0] — 2026-03-16 (Session 16 — ShellGPT full parity + decisive wins) 🚀 Published to PyPI

### Added

#### `aicli/app.py` — Smart intent routing (`_detect_intent`)

- **`_detect_intent(prompt) -> str`**: Classifies any free-form prompt as `"do"` (function call / OS action) or `"ask"` (text answer) without requiring the user to pick a subcommand — matching ShellGPT's `sgpt "..."` UX while adding the full audit/confirm/retry stack underneath.
  - Tight action verbs that always → `do`: `play`, `open`, `send`, `delete`, `kill`, `install`, `notify`, `launch`, `start`, `stop`, `restart`
  - Disambiguated verbs (require OS-flavoured object): `copy` (needs "to clipboard"/"file"), `write` (needs "to/into"/extension), `create` (needs docker/container/file/dir/extension), `run` (needs docker/nginx/.py/.sh), `move` (needs filepath pattern), `save` (needs filepath/extension)
  - Filesystem path present anywhere in prompt (`/absolute` or `~/home`) → `do`
  - Query words (`what`, `why`, `how`, `explain`, `describe`, `tell me`, `summarize` without path) → `ask`
  - Domain keywords without query word → `do`
  - Default: `ask`
  - 34 edge cases validated including 12 verb-disambiguation cases that prevent routing LLM instruction prompts (`"write a function"`, `"create a mental model"`) to `do`

- **`--confirm` flag on `aicli do`**: Opt-in confirmation gate. Default is now silent execution (matches ShellGPT). Use `--confirm` for destructive actions.
  ```bash
  aicli do "open hacker news"                    # fires immediately
  aicli do --confirm "delete logs older than 7d"  # asks [Y/n] per step
  aicli do --dry-run "send email to alice@..."    # preview only, nothing runs
  ```

- **`--verbose` flag on `aicli do`**: Opt-in tool count display. Default is silent until `@FunctionCall` lines appear.

- **`_COMPOUND_RE` compound prompt guard** in `_try_direct_dispatch`: Detects `and/also/then/plus` in prompt — compound prompts bypass the fast path and go to the LLM which dispatches all tools in one JSON response.

#### `aicli/tools/executor.py` — @FunctionCall format + direct dispatch + pipeline fix

- **`@FunctionCall` display format**: `_format_tool_call()` now outputs `@FunctionCall play_music(query='classical')` with the tool description on the next line — identical to ShellGPT's visual style, more informative.

- **`auto_confirm=True` default** (was `False`): On the `auto_confirm` path, prints `@FunctionCall tool(args)` + description then executes silently — no `[Y/n]` pause.

- **Dry-run header**: `Dry-run plan: N tools available` shown before listing each call with description. `--verbose` flag restores the tool count line for non-dry-run calls.

- **`_try_direct_dispatch(prompt_text)` fast path**: For unambiguous single-tool commands, dispatches directly without an LLM round-trip (~50ms vs ~1–2s):
  | Pattern | Tool | Time |
  |---------|------|------|
  | `browse my music in this dir` | `browse_media(directory=cwd)` | ~50ms |
  | `play ~/Music/file.mp3` | `play_music(query=path)` | ~50ms |
  | `open https://...` | `open_url_in_browser(url=url)` | ~50ms |
  | `get system info` | `get_system_info()` | ~50ms |

- **Compact tool schema** (~2,100 chars vs ~5,600 chars full): Tool names + 80-char description + param names only embedded in system prompt. Prevents LLM response truncation on multi-tool prompts.

- **Robust JSON response parser**: `re.search` finds JSON array anywhere in response (handles LLM preamble text), strips ``` fences, falls back to plain text.

- **Few-shot system prompt examples**: Single-tool, multi-tool, and question examples embedded so the LLM always returns clean JSON.

- **Blocking-tools-last dispatch ordering**: `browse_media` (and any tool using `input()`) sorted to run after all non-blocking tools in compound prompts. For `"browse my music and open hacker news"` → browser opens first, then picker menu.

- **Pipeline compatibility fix**: `ProviderPipeline.complete()` is text-only — removed `tools=tool_schemas` kwarg that was causing `TypeError`. Tool schemas embedded in system prompt instead.

- **`tool_schemas` assignment moved** before system prompt block — fixes `UnboundLocalError: cannot access local variable 'tool_schemas'`.

#### `aicli/tools/os_functions.py` — play_music + browse_media overhaul

- **`play_music` — full format support**:
  - `~` expansion bug fixed: was passing raw unexpanded `~` string to mpv subprocess. Now uses `play_target = str(file_path)` after `Path(query).expanduser()`.
  - Empty query: scans cwd → `~/Music` → `~/Videos` for media files, launches `mpv file1.mp3 file2.mp3 ...` as playlist. Opens `mpv --idle` if nothing found.
  - Player fallback chain: `playerctl` → `mpv` → `vlc/cvlc` → `rhythmbox` → `xdg-open`
  - macOS: `afplay` / `open`. Windows: `os.startfile`.
  - Supports any format: `.mkv`, `.mp4`, `.mp3`, `.flac`, `.wav`, `.ogg`, etc.

- **`browse_media` — smart directory picker**:
  - Current directory detection: "this dir", "here", "current directory", "." → `Path.cwd()`
  - Fast path passes `str(Path.cwd())` absolute path — no ambiguity in subprocess.
  - Auto-play single file: if only 1 file found, plays immediately without menu.
  - Improved numbered picker UI with file size and format columns.
  - Scans cwd first, falls back to `~/Music`, `~/Videos`, `~/Downloads`.
  - `filter: audio` or `filter: video` narrows results.
  - `_detect_intent` updated: `"browse my music"`, `"show me my video files"`, `"pick a song to play"`, `"list my music files"`, `"play the song in this directory"` all route to `do`.

- **Tool sandboxing** (from S15, now in `os_functions.py`):
  - `MAX_OUTPUT_BYTES = 32_768` — 32 KB output cap, truncation message appended
  - `_sandbox_available()` — checks `AICLI_SANDBOX=1` env var AND `firejail` on PATH
  - `_build_sandboxed_cmd()` — `--quiet --noprofile --noroot --private-tmp --net=none` by default; `AICLI_SANDBOX_NET=1` removes `--net=none`
  - Sandboxed path uses `shell=False` (list args); unsandboxed retains `shell=True`

#### `aicli/shell_integration.zsh` + `aicli/shell_integration.bash` — Ctrl+L chain widget

- **`_aicli_chain_widget` (zsh) / `_aicli_chain` (bash)**: Bound to Ctrl+L.
  - Empty buffer: shows inline `aicli chain>` prompt
  - Non-empty buffer: runs `aicli cmd --chain "$BUFFER"` in foreground for interactive `[1/3] ... [Y/n]` confirmations — matches ShellGPT Video 2 exactly
  - Comment included for Alt+L rebind (users where Ctrl+L conflicts with clear-screen)
  - Both shells now have full hotkey parity: Ctrl+G, Ctrl+E, Ctrl+I, Ctrl+L

#### `aicli/tui.py` — DoModeScreen confirm toggle (from S15, finalised S16)

- Ctrl+Y → `action_toggle_confirm` — switches between auto-confirm and dry-run mode live
- `_auto_confirm` state variable (default `True`)
- Mode label widget shows current mode
- `dismiss((prompt, auto_confirm))` tuple — caller receives both values
- `_run_do_command(prompt, *, auto_confirm=True)` — `dry_run=not auto_confirm` wired through

### Tests

- **`TestIntentRouting`** (24 tests): 13 action prompts → `'do'`, 7 query prompts → `'ask'`, 4 CLI integration tests; 12 disambiguation edge cases
- **`TestDoCommandUX`** (6 tests): `--confirm` flag, `auto_confirm=True` default, `--verbose` flag, dry-run header, `@FunctionCall` format on auto-confirm path
- **`TestCtrlLChainWidget`** (7 tests): `_aicli_chain_widget` defined in zsh, `_aicli_chain` defined in bash, Ctrl+L bound in both, `aicli cmd --chain` called in both, empty buffer handling
- **`TestRunShellCommandSandboxing`** (8 tests): `_sandbox_available`, `_build_sandboxed_cmd`, `MAX_OUTPUT_BYTES`, sandboxed/unsandboxed paths, `AICLI_SANDBOX_NET`
- **`test_rag_integration.py`** (18 `@pytest.mark.slow` tests, 6 classes):
  - `TestRAGRoundtrip` (5): index→retrieve, empty store, chunk count, status, context block format
  - `TestRAGMultiSession` (3): correct session, both indexed, high min_score filters weak
  - `TestRAGSummary` (3): summary indexed, preferred over raw messages
  - `TestRAGFileIndexing` (4): `index_directory`, file content retrievable, local_chunks in status
  - `TestRAGDepthScaling` (3): depth=2 returns ≥ depth=1

**Total: 784 pytest (non-slow) + 14 slow RAG · 786 static checks (run_tests.py)**

### Static Checks Added (run_tests.py)

- **Phase 45** (+33): watch+do wiring, multi-turn `--session`, plugin `TOOL_REGISTRY` auto-reg, TUI DoModeScreen/F9, 7 new KNOWN_PROXIED_CLASSES entries
- **Phase 46** (+17): `_detect_intent` defined, action/query patterns, `@FunctionCall` in executor, dry-run plan header, Ctrl+L in zsh + bash, `TestIntentRouting`/`TestDoCommandUX`/`TestCtrlLChainWidget` registered

### Bugs Fixed

- `ProviderPipeline.complete()` `TypeError` on `tools=` kwarg (text-only pipeline)
- `UnboundLocalError: tool_schemas` — used before assignment in executor
- `play_music` `~/` expansion — raw `~` passed to mpv subprocess instead of expanded path
- `_COMPOUND_RE` `\b` written as `\x08` (ASCII backspace) — compound guard never fired
- LLM response truncation on multi-tool prompts — compact schema format fix
- `"browse...and open..."` hitting fast path instead of LLM — compound guard placement
- `run_tests.py` Phase 46 reading stale `src` variable instead of live file
- Intent routing false positives: `"write a function"` / `"create a mental model"` / `"copy the first 3 lines"` / `"move the cursor left"` / `"run me through X"` all incorrectly routing to `do` — verb disambiguation fix
- `test_do_auto_confirm_flag_accepted` — test passed `--auto-confirm` but flag on `do` is `--confirm`
- `test_summary_pass_calls_pipeline_stream_twice` — `pipeline.complete` mock returned Python list instead of JSON string
- `test_run_do_command_passes_max_retries_to_dispatch` — prompt `"open example.com"` hit direct dispatch fast path, bypassing LLM mock
- `mcp_server.py` `_server_version()` fallback string stale at `"1.5.7"` → updated to `"1.6.0"`
- `run_tests.py` semver check regex didn't match `SERVER_VERSION_IMPORT` assignment pattern
- `pyproject.toml` missing `beautifulsoup4` from `[full]` and `[all]` extras
- `requirements.txt` had `pytest`/`pytest-asyncio` as runtime deps (dev-only since v1.5.3)

### Package

- `beautifulsoup4>=4.12.0` added to `[full]`, `[all]`, and new `[web]` extra
- `[web]` extra: `beautifulsoup4` + `pysocks` — clean install target for `--web` users
- `mcp_server.py` fallback version string updated to `"1.6.0"`
- **Published to PyPI 2026-03-16**: `pip install aicli-maxmux==1.6.0`

---

## [1.5.7] — 2026-03-16 (Sessions 14–15 — Test fixes, ShellGPT audit, feature backlog)

### Added

#### `aicli/app.py` — `_FallbackGroup` + CLI flags

- **`_FallbackGroup`** (replaces bare `click.Group`): Intercepts `parse_args` — if the first positional token is not a known subcommand name, stores all args as `ctx.args` and skips subcommand resolution. Fixes `UsageError: No such command 'explain'` on `aicli "explain async await"` and eliminates `ctx.protected_args` DeprecationWarning (Click 9.0 removal path).
  - Covers all cases: `aicli "explain"`, `aicli explain async await`, `aicli --shell "find files"`, known subcommands still route correctly, `aicli` with no args shows help.

- **`--retries N` flag on `aicli do`**: Exposes `max_retries` to users (was always defaulting to 1).
  ```bash
  aicli do --retries 3 "create a Jira ticket for the login bug"
  ```

- **`--session NAME` flag on `aicli do`**: Multi-turn do mode. Loads up to 10 prior turns from named session and injects before user turn.
  ```bash
  aicli do --session myproject "open the config file"
  aicli do --session myproject "now summarize it"
  ```

- **`--do ACTION` flag on `aicli ask`**: `--watch` + `--do` integration. When the watch condition fires, automatically dispatches an `aicli do` action with `auto_confirm=True`.
  ```bash
  tail -f app.log | aicli ask --watch "OOM killer invoked" \
      --do "send_notification title='OOM Alert' body='Check app.log'"
  journalctl -f | aicli ask --watch "disk usage above 90%" \
      --do "get_system_info detail=disk"
  ```

- **`--role "..."` on `aicli cmd --chain`**: Custom system prompt for multi-step chain generation.

- **MCP server docstring updated**: `do` tool added to listing (was missing from 4-tool description).

#### `aicli/tools/executor.py` — `max_retries` + `session_id`

- **`max_retries` wired through**: `dispatch_tool_calls` was always called with default `max_retries=1`. Now forwarded from `run_do_command(max_retries=...)`.
- **`session_id` multi-turn**: `run_do_command(session_id=...)` loads prior turns from SQLite on each call.
  - Messages: `[system] + [history[-10:]] + [user]`
  - Session lookup via `get_connection() → list_sessions() → load_messages()`, graceful on failure.

#### `aicli/handlers/default.py` — `--watch` + `--do` integration

- `_ask` signature: `watch_do: str | None = None`
- `_watch_stdin` signature: `do_action: str | None = None`; logs trigger message on startup
- `_watch_evaluate` signature: `do_action: str | None = None`
- When `response.upper().startswith("YES")` and `do_action` set: calls `run_do_command(prompt_parts=(do_action,), auto_confirm=True, ...)`
- `ImportError` on `run_do_command` handled gracefully (lite installs)

#### `aicli/tui.py` — DoModeScreen (F9)

- **`DoModeScreen`** modal class: `Label` with task examples, `Input` with placeholder, Enter → `dismiss(prompt)`, Escape → `dismiss(None)`
- **F9 binding**: Added to `BINDINGS` with `priority=True`; entry in ACTIONS list: `("do_mode", "f9", "aicli do — OS function calling")`
- **`action_do_mode` + `_run_do_command`** on `AicliTUI`: `auto_confirm=True` (TUI is non-interactive). Result appears as assistant message in active chat.

#### `aicli/tools/os_functions.py` — `run_shell_command` `working_dir`

- `run_shell_command` now accepts `working_dir` parameter + schema entry. Missing dir raises `FileNotFoundError`.

#### `aicli/handlers/loader.py` — Plugin auto-registration into TOOL_REGISTRY

- `_load_plugin_file()` checks for `"parameters"` key in plugin dict. If present, auto-registers into `TOOL_REGISTRY` — plugin is now fully available to `aicli do` and the LLM's function-calling system.
  ```python
  # ~/.config/aicli/plugins/jira.py
  def register():
      return {
          "name": "create_jira_ticket",
          "description": "Create a Jira ticket",
          "parameters": {"title": {"type": "string"}, "description": {"type": "string"}},
          "confirm": True,
          "fn": create_jira_ticket,
      }
  # → aicli do "create a ticket for the login bug" dispatches create_jira_ticket() automatically
  ```
- Silent on `ImportError` (lite installs). Existing plugins without `"parameters"` unchanged.

#### `aicli/shell_integration.zsh` — Alt+I rebind line

- Uncommentable `bindkey '^[i'` line added for users who want Alt+I instead of Ctrl+I.

### Fixed

- **`RuntimeWarning: coroutine never awaited`** (3 locations in `test_os_tools.py`, 1 in `test_streaming.py`): Tests used `patch("aicli.app.asyncio.run")` — a plain `MagicMock` received the coroutine but never awaited or closed it. Fixed by patching the coroutine function directly with `AsyncMock`:
  - `test_do_dry_run_flag_accepted`, `test_do_auto_confirm_flag_accepted`, `test_do_quiet_flag_accepted`: `patch("aicli.tools.executor.run_do_command", new=AsyncMock())`
  - `test_chain_flag_exists_on_cmd`: `patch("aicli.app._cmd_chain", new=AsyncMock())`

- **`TestDirectInvocation.test_direct_prompt_routes_to_ask` exit code 2**: Click's `Group.parse_args()` tried to resolve first positional token as subcommand before `cli()` was called. Fixed by `_FallbackGroup`. Also eliminated `ctx.protected_args` DeprecationWarning.

### Tests

- **`TestRunDoCommandMaxRetries`** (3 tests): signature check, value forwarded to dispatch, CLI `--retries 3`
- **`TestRunShellCommandWorkingDir`** (4 tests): cwd changes correctly, missing dir raises `FileNotFoundError`, defaults work, schema includes `working_dir`
- **`TestCmdChainRole`** (4 tests): `--role` accepted, value forwarded, defaults to `None`, signature
- **`TestWatchDoIntegration`** (8 tests): `--do` flag acceptance, value forwarded, default None, signatures, YES dispatches `run_do_command`, NO does not
- **`TestDoCommandSession`** (5 tests): `--session` flag, `session_id` forwarded, absent → None, signature, backward-compat default
- **`TestPluginOsToolRegistration`** (5 tests): plugin with `"parameters"` lands in registry, plugin without doesn't, schema `input_schema` format, confirm/safe fields preserved, ImportError silent in lite mode
- **`TestDoModeScreen`** (17 tests): class exists, Screen subclass, Escape/Enter bindings, action_submit/cancel, Input widget, on_input_submitted, F9 in BINDINGS, action_do_mode, _handle_do_result, _run_do_command (async, auto_confirm=True, redirect_stdout, ImportError guard), do_mode in ACTIONS

**Total: 759 pytest · 717 static checks (run_tests.py)**

### Static Checks Added (run_tests.py)

- **Phase 45** (+33): All items above verified against source files
- **KNOWN_PROXIED_CLASSES** updated: `TestWatchDoIntegration`, `TestDoCommandSession`, `TestPluginOsToolRegistration`, `TestRunDoCommandMaxRetries`, `TestRunShellCommandWorkingDir`, `TestCmdChainRole`, `TestDoModeScreen`

### ShellGPT Competitive Audit (Final State after S14–S15)

| Feature | ShellGPT | aicli | Advantage |
|---------|----------|-------|-----------|
| Function calling | `@FunctionCall` silent | `aicli do` | Confirm gate, dry-run, audit, retry, natural summary |
| Path auto-detect | ✅ | ✅ + 50KB cap | Prompt injection protection |
| Ctrl+I next command | History-blind | ✅ tmux scrollback | Sees actual output |
| Multi-step chain | Ctrl+L, no confirm | `cmd --chain` | [N/total], Y/n/s/q, failure halt |
| Tool audit log | ❌ | ✅ JSONL | Full tamper-evident record |
| Dry-run | ❌ | ✅ | Zero risk preview |
| Tool retry | ❌ | ✅ configurable | `↻ Retry N/max` feedback |
| Web search | ❌ | ✅ 6-backend | Callable as OS tool |
| MCP server | ❌ | ✅ 5 tools | Claude Desktop integration |
| TUI | ❌ | ✅ F9 do mode | Full Textual UI |
| Session memory | ❌ | ✅ SQLite + RAG | Cross-session context |
| Provider failover | LiteLLM | ✅ native 5-chain | Groq→OpenRouter→Gemini→Mistral→Ollama |

**Score: aicli 22W / Ties 3 / ShellGPT 0L**

### Files Changed (S14–S15)

| File | Lines Before | Lines After | Net |
|------|-------------|-------------|-----|
| `aicli/app.py` | 1,838 | 1,887 | +49 |
| `aicli/tools/executor.py` | 379 | 408 | +29 |
| `aicli/handlers/default.py` | 509 | 548 | +39 |
| `aicli/tui.py` | 1,632 | 1,715 | +83 |
| `aicli/tools/os_functions.py` | 623 | 636 | +13 |
| `aicli/handlers/loader.py` | 161 | 207 | +46 |
| `aicli/shell_integration.zsh` | 160 | 163 | +3 |
| `tests/test_os_tools.py` | 573 | 681 | +108 |
| `tests/test_streaming.py` | 543 | 596 | +53 |

**Zero deletions across all 9 files.**

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
    `CONDITION TO WATCH FOR: <condition>\nLOG LINES:\n<batch>`
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
  `MISTRAL_API_KEY` in the environment and auto-saves them — no manual entry required
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
  to the real home directory in tests, writing a real `.zshrc` entry.
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

#### `app.py` fixes
- **Lazy import shadow bugs (3)**: `CONFIG_DIR`, `run_serve`, and `CONFIG_DIR` in `tag()` were re-imported inside function bodies, silently defeating `patch()` in tests. All moved to module-level imports.
- **Duplicate `def tag`**: First (weaker) definition removed
- **Shebang position**: `__version__` import was before shebang; shebang moved to line 1

#### `handlers/mcp_server.py` fixes
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
- **`TestServeDaemon`** (4 tests, `test_new_commands.py`) — `--daemon` flag present, `stop_serve()` routing, missing PID graceful, PID file path
- **`TestHistorySearch`** (4 tests, `test_new_commands.py`) — command exists, requires query, no-chromadb graceful, no-indexed-data message
- **`TestStatsCommand`** (4 tests, `test_new_commands.py`) — command exists, no-sessions OK, shows summary, `--session` flag graceful
- **`TestMCPToolCallAsk` RAG** (2 new tests, `test_mcp_server.py`) — RAG context injected when available, continues without chromadb
- Bug fixes in existing tests:
  - `test_comprehensive.py`: `inspect.getsource(cmd)` → `.callback` for Click commands
  - `test_tui_pure.py`: `HotkeyInput._on_key` → `on_key`; `str(BINDINGS)` → `getsource` text search
  - `test_new_commands.py`: `getpass.getpass` mocked; `sys.stdin` mocked; `ContextRetriever` patch path fixed; `AsyncMock(return_value=aiter(...))` anti-pattern replaced with proper async generators
  - `test_serve.py`: Hardcoded ports → `_free_port()` OS-assigned; `load_config` + `get_role` patched; `pytestmark = pytest.mark.slow`
  - `test_web_search.py`: All 6 backends now patched in every test (3 tests were hitting real network, causing 166s slowdown)
  - `test_graph_server.py`: 7× `time.sleep(0.05/0.1)` → `_wait_for_port()` socket polling

**Total tests: 683 passing** (up from 669)
**Static checks: 482/482** (`python3 run_tests.py`)

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

**Total new tests this release: ~107** (193 existing + 107 new = **~300 passing**)

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
