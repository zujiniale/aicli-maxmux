# aicli-maxmux

![Version](https://img.shields.io/badge/version-1.6.3-ff4488) ![Tests](https://img.shields.io/badge/tests-784%20passing-22c55e) ![Python](https://img.shields.io/badge/python-3.11%2B-4f8ef7) ![License](https://img.shields.io/badge/license-MIT-6b6b80) ![Lite](https://img.shields.io/badge/lite%20mode-%7E20MB-a855f7) ![PyPI](https://img.shields.io/badge/pypi-aicli--maxmux-blue)

A free, private, terminal-native AI CLI with multi-provider failover, persistent memory,
web search, vision support, autonomous agent mode, and OS function calling.

No vendor lock-in. No single point of failure. All keys stored encrypted locally.

## Features

| Feature | Command |
|---------|---------|
| Multi-provider failover (Groq → OpenRouter → Gemini → Mistral → Ollama) | `aicli ask "..."` |
| Persistent encrypted conversation memory (SQLite + Fernet) | `aicli chat --session myproject` |
| Web search with current results | `aicli ask --web "latest news"` |
| Vision / image analysis | `aicli ask --image screenshot.png "what error?"` |
| Shell command generation + execution | `aicli cmd "find large files"` |
| Autonomous multi-step agent | `aicli agent "set up a Python project"` |
| Semantic RAG over chat history | `aicli chat --context` |
| Session export (Markdown / JSON) | `aicli export mysession > out.md` |
| Full terminal UI with themes, clipboard, range select | `aicli tui` |
| Interactive session graph viewer | `aicli graph` |
| Run generated code in Python / Bash / Node / Ruby | `aicli code "..." --run --language bash` |
| Plugin system — drop `.py` files to extend aicli | `aicli plugin list` |
| Encrypted key storage, no shell exports | `aicli config set TAVILY_API_KEY tvly-xxxx` |
| Tor / proxy support | `aicli config set AICLI_PROXY socks5://127.0.0.1:9050` |
| **OS function calling with audit log** | `aicli do "open hacker news"` |
| **Smart intent routing** | `aicli "play music and open hacker news"` — no subcommand needed |
| **@FunctionCall display + dry-run** | `aicli do --dry-run "send email to alice@..."` |
| **Media browser + picker** | `aicli "browse my music in this dir"` |
| **Quick shell command shorthand** | `aicli cmd "kill process on port 3000" --run` |
| **Quick code generation shorthand** | `aicli code "fibonacci" --run` |
| **Quiet / scriptable output** | `aicli ask -q "what is my IP"` |
| **Shell hotkeys (Ctrl+G/E/I/L)** | `aicli config install-shell` |
| **Lite mode (~20MB, no RAG/TUI)** | `pip install aicli-maxmux[lite]` |
| **Vim-style TUI navigation** | `j/k` scroll · `G/g` top/bottom · `/` search · `dd` delete |
| **TUI F9 do-mode** | F9 in TUI → OS function calling with confirm toggle |
| **Graph node tags + filtering** | Tag bar in graph viewer, filter by tag |
| **Obsidian export** | `aicli export mysession --obsidian > vault/note.md` |
| **Local HTTP API** | `aicli serve` |
| **MCP server (Claude Desktop)** | `aicli mcp` · stdio + SSE · 5 tools · 2 resources |
| **Semantic history search** | `aicli history "query"` — search all past sessions |
| **Token & message stats** | `aicli stats` · per-session counts · `--top N` |
| **Background HTTP daemon** | `aicli serve --daemon` · `aicli serve stop` |
| **Windows shell hotkey (Ctrl+G)** | `aicli config install-shell --shell powershell` |
| **Atomic version bumping** | `python bump_version.py 1.6.0` |
| **Context-aware shell hotkey** | Ctrl+G captures tmux scrollback · Ctrl+E auto-fixes last error |
| **Watch mode (live log AI monitor)** | `tail -f app.log \| aicli ask --watch "alert on ERROR"` |
| **Watch + auto-do** | `tail -f app.log \| aicli ask --watch "OOM" --do "send_notification ..."` |
| **Multi-file context attach** | `aicli ask -f error.log -f screenshot.png "what happened"` |
| **Direct invocation** | `aicli "your prompt"` — no subcommand needed, like `sgpt` |
| **Zero-config start** | Auto-detects `GROQ_API_KEY`, `OPENROUTER_API_KEY` etc. from env |
| **pipx compatible** | `pipx install "aicli-maxmux[lite]"` — isolated, no venv needed |
| **Tool sandboxing** | firejail + 32KB output cap + `--net=none` (`AICLI_SANDBOX=1`) |
| **Cross-session RAG memory** | ChromaDB semantic retrieval across all past sessions |
| **Multi-turn `aicli do`** | `aicli do --session myproject "now summarize it"` |
| **Plugin → TOOL_REGISTRY auto-registration** | Plugin with `"parameters"` available to `aicli do` |
| **Ctrl+L multi-step chain** | Type task, press Ctrl+L → interactive chain with Y/n per step |

## Install

```bash
# ── Fastest (lite, ~20MB, isolated) ──────────────────────────────
pipx install "aicli-maxmux[lite]"
aicli-lite "hello"               # works immediately if GROQ_API_KEY is set

# ── Standard lite install ─────────────────────────────────────────
pip install "aicli-maxmux[lite]"
aicli-lite "hello"

# ── Full install — all features (~468MB with deps) ────────────────
pip install "aicli-maxmux[all]"
aicli "hello"                    # direct — no subcommand needed

# ── Zero-config: already have API keys? ──────────────────────────
# If GROQ_API_KEY, OPENROUTER_API_KEY, GEMINI_API_KEY, or MISTRAL_API_KEY
# are set in your environment, aicli uses them immediately — no setup needed.
export GROQ_API_KEY="gsk_..."
aicli "explain async/await"      # works instantly
```

### One-liner bootstrap
```bash
bash <(curl -sSL https://raw.githubusercontent.com/YOUR_USER/aicli/main/install.sh)
# Lite variant:
bash <(curl -sSL https://raw.githubusercontent.com/YOUR_USER/aicli/main/install.sh) lite
```

### From source
```bash
git clone https://github.com/YOUR_USER/aicli && cd aicli
./expand.sh          # creates venv, installs all deps + optional extras
source venv/bin/activate
aicli setup
```

## Quick Start

```bash
# ── If you already have an API key in your environment — just start ──
# GROQ_API_KEY, OPENROUTER_API_KEY, GEMINI_API_KEY etc. are auto-detected.
aicli "explain async/await in Python"   # direct — no subcommand, no setup

# ── First time with no keys ──────────────────────────────────────────
# Get a free Groq key in ~30 seconds: https://console.groq.com/keys
aicli config set-key groq        # paste key once, encrypted locally

# ── Or run the interactive setup wizard ──────────────────────────────
aicli setup                      # auto-detects existing env keys too

# Explicit subcommand form also works
aicli ask "explain async/await in Python"

# OS function calling — smart intent routing (no subcommand needed)
aicli "play music and open hacker news"        # auto-routes to do
aicli "browse my music in this dir"            # opens picker, plays selected file
aicli do "open https://news.ycombinator.com"   # explicit do subcommand

# Dry-run: see the plan without executing
aicli do --dry-run "send email to alice@example.com say build passed"

# Multi-turn do (remembers prior steps)
aicli do --session myproject "open the config file"
aicli do --session myproject "now summarize it"

# Retry on tool failure
aicli do --retries 3 "create a Jira ticket for the login bug"

# Quick shell command (new shorthand)
aicli cmd "find all files larger than 100MB"
aicli cmd "kill process on port 3000" --run

# Multi-step chain
aicli cmd --chain "create nginx container mounting index.html"
# Or press Ctrl+L in your terminal with the task already typed

# Quick code generation (new shorthand)
aicli code "write a merge sort in Python"
aicli code "fibonacci function" --run

# Watch mode — live log AI monitor + auto-action
tail -f app.log | aicli ask --watch "OOM killer invoked" \
    --do "send_notification title='OOM Alert' body='Check app.log'"

# Quiet / scriptable output
aicli ask -q "what is today's date"

# Install shell hotkeys (Ctrl+G/E/I/L)
aicli config install-shell

# Web search (current results)
aicli config set TAVILY_API_KEY tvly-xxxx   # free at app.tavily.com
aicli ask --web "latest Python version"

# Vision
aicli ask --image screenshot.png "what does this error mean?"

# Persistent session
aicli chat --session myproject

# Agent mode
aicli agent "create a Flask API with tests"
```

## Provider Setup

| Provider | Get Key | Env Var | Notes |
|----------|---------|---------|-------|
| Groq | https://console.groq.com/keys | `GROQ_API_KEY` | Fastest, free |
| OpenRouter | https://openrouter.ai/keys | `OPENROUTER_API_KEY` | Vision, free tier |
| Gemini | https://aistudio.google.com/app/apikey | `GEMINI_API_KEY` | Vision, free tier |
| Mistral | https://console.mistral.ai/api-keys | `MISTRAL_API_KEY` | Fallback |
| Ollama | (local) | — | Run `ollama serve` locally |
| Tavily | https://app.tavily.com | `TAVILY_API_KEY` | Web search, 1000/mo free |

Store keys securely (OS keychain, no shell exports needed):
```bash
aicli config set GROQ_API_KEY gsk-xxxx
aicli config set OPENROUTER_API_KEY sk-or-xxxx
```

## Architecture

aicli-maxmux uses a **3-layer CMA (Contextual Memory Architecture)**:

```
🔥 Hot Layer   — in-memory context for current session
🌡️ Warm Layer  — SQLite + Fernet encrypted persistent history
❄️ Cold Layer  — ChromaDB vector embeddings for semantic RAG
```

Provider failover chain: **Groq → OpenRouter → Gemini → Mistral → Ollama**  
Adaptive cooldowns: 429 → 5min, 401/403 → 1hr, 5xx → 10-15s

### `aicli do` — OS Function Calling Architecture

```
aicli "play music and open hacker news"
        │
        ▼
_detect_intent()         ← classifies "do" vs "ask" without subcommand
        │
        ▼
_try_direct_dispatch()   ← ~50ms fast path for unambiguous single-tool commands
        │ (compound prompt → falls through)
        ▼
LLM path                 ← compact tool schema in system prompt, JSON response
        │
        ▼
dispatch_tool_calls()    ← non-blocking tools first, blocking tools (pickers) last
        │
        ▼
@FunctionCall display + execute + audit log + natural summary
```

## All Commands

```bash
aicli ask "prompt"                    # single shot
aicli ask --shell "prompt"            # generate + execute shell commands
aicli ask --code "prompt"             # code only output
aicli ask --image file.png "prompt"   # vision (OpenRouter/Gemini)
aicli ask --web "prompt"              # web search + answer
aicli ask --web-debug "prompt"        # debug web backends (clean output)
aicli ask --web-debug --web-verbose   # debug web backends (full output)
aicli ask --context "prompt"          # inject semantic context from history
aicli ask --code --run "prompt"       # generate + run code (Python default)
aicli ask --code --run --language bash "prompt"   # run as bash
aicli ask --code --run --language node "prompt"   # run as node.js
aicli ask --code --run --timeout 60 "prompt"      # custom timeout (seconds)
aicli ask --lite "prompt"             # lite mode: skip RAG/ChromaDB init
aicli ask --quiet "prompt"            # quiet mode: raw output only
aicli ask -q "prompt"                 # quiet shorthand (great for scripting)
aicli ask --watch "CONDITION"         # streaming stdin AI monitor
aicli ask --watch "CONDITION" --watch-lines 20   # custom batch size
aicli ask --watch "CONDITION" --do "tool_call"   # auto-dispatch on trigger
aicli ask -f file.log "prompt"        # attach file as context
aicli ask -f img.png -f log.txt "prompt"         # multiple files (mixed)
aicli ask --terminal-context "..."    # inject terminal scrollback (set by hotkeys)

aicli do "task"                       # OS function calling (auto-routed)
aicli do --dry-run "task"             # preview tool calls, nothing runs
aicli do --confirm "task"             # ask [Y/n] before each tool call
aicli do --retries 3 "task"           # retry failed tools up to 3 times
aicli do --session NAME "task"        # multi-turn do with session memory
aicli do --verbose "task"             # show tool count info
aicli "task"                          # direct invocation — auto-routes to do or ask

aicli cmd "prompt"                    # shell command generation
aicli cmd "prompt" --run              # generate + execute
aicli cmd "prompt" --chain            # multi-step chain with Y/n per step
aicli cmd "prompt" --chain --role "system prompt"   # custom role for chain
aicli cmd "prompt" --dry-run          # preview only

aicli code "prompt"                   # code generation
aicli code "prompt" --run             # generate + execute
aicli code "prompt" --run --language bash   # run as bash

aicli chat                            # interactive multi-turn chat (last session)
aicli chat --session NAME             # named session
aicli chat --context                  # inject RAG context
aicli chat --web                      # web-enhanced chat
aicli chat --cross-session            # global RAG across all sessions

aicli tui                             # full Textual TUI
aicli tui --session NAME              # open specific session
# TUI hotkeys:
#   F9         → aicli do mode (OS function calling, confirm toggle via Ctrl+Y)
#   Ctrl+N     → new session
#   Ctrl+D     → delete session
#   Ctrl+W     → toggle web search
#   Ctrl+X     → toggle RAG context
#   Ctrl+S     → summarize session
#   Ctrl+Q     → quit
#   F2         → range-pick messages
#   F4         → export session to graph
#   F5         → import session
#   j/k        → scroll, G/g top/bottom, / search, dd delete

aicli agent "task"                    # autonomous multi-step agent
aicli agent --image file.png "task"   # with vision input

aicli session list                    # list all sessions
aicli session fork NAME               # fork session
aicli session fork NAME --from-message N --name new-name
aicli session rename OLD NEW          # rename session
aicli session summarize NAME          # generate/regenerate summary
aicli session summarize NAME --print-only --model MODEL

aicli export SESSION                  # export to markdown
aicli export SESSION --obsidian       # Obsidian-compatible markdown
aicli export SESSION --include-summary

aicli history "query"                 # semantic search all past sessions
aicli stats                           # token + message counts per session
aicli stats --top 10

aicli plugin list                     # list loaded plugins
aicli plugin run NAME ARG             # invoke plugin directly
aicli plugin errors                   # show failed plugin loads
aicli plugin doc NAME                 # show plugin description, version, source
aicli plugin install URL [--name]     # download + install plugin from URL
# Plugin auto-registration: plugins with "parameters" key auto-register into TOOL_REGISTRY
# → available to aicli do and the LLM's function-calling system

aicli tools list                      # list all registered OS tools
aicli tools audit                     # show tool call history (JSONL audit log)

aicli config set KEY VALUE            # store key in OS keychain + Fernet file
aicli config get KEY                  # read stored key (masked)
aicli config set-key groq             # interactive key entry for named provider
aicli config install-shell            # install zsh/bash hotkeys (Ctrl+G/E/I/L)
aicli config install-shell --shell powershell   # Windows PowerShell
aicli config migrate-keys             # migrate keys from keyring to Fernet backup
aicli config show                     # show all config + optional env vars

aicli setup                           # interactive first-run wizard

aicli tag SESSION TAG                 # tag a session

aicli graph                           # start graph server + open browser
aicli graph --port 8080               # custom port
aicli graph --no-browser              # headless use

aicli serve                           # local HTTP API on :8765
aicli serve --daemon                  # background daemon with PID file
aicli serve stop                      # stop background daemon
aicli serve --port 9000               # custom port
aicli serve --quiet                   # suppress startup banner

aicli mcp                             # MCP server (stdio + SSE) for Claude Desktop
# 5 tools: ask, cmd, do, search_history, get_session
# 2 resources: sessions list, individual session messages
```

## Shell Hotkeys

Install with `aicli config install-shell` (adds one `source` line to `~/.zshrc` / `~/.bashrc`).

| Hotkey | What It Does |
|--------|-------------|
| **Ctrl+G** | Suggest a shell command for what you typed (tmux-aware: sees actual terminal output) |
| **Ctrl+E** | Auto-fix last failed command — captures error, gets fix, pastes into buffer |
| **Ctrl+I** | Suggest next command based on what just ran (reads tmux scrollback) |
| **Ctrl+L** | Run current buffer as multi-step chain — each step asks Y/n before executing |

Ctrl+G empty buffer: inline `aicli>` prompt. Non-empty: uses typed text as the task.
Ctrl+L empty buffer: shows `aicli chain>` prompt. Non-empty: `aicli cmd --chain "$BUFFER"`.

> Users where Ctrl+L conflicts with clear-screen: uncomment the `Alt+L` rebind line in `shell_integration.zsh`.

## OS Function Calling (`aicli do`)

### Available Tools

| Tool | What It Does | Example |
|------|-------------|---------|
| `play_music` | Play any audio/video file or launch media player | `aicli "play ~/Music/Wired.mp3"` |
| `browse_media` | Numbered picker for audio/video files in a directory | `aicli "browse my music in this dir"` |
| `open_url_in_browser` | Open URL in default system browser | `aicli "open hacker news"` |
| `run_shell_command` | Run a shell command with optional sandbox + working_dir | `aicli do "list processes using port 8080"` |
| `send_email` | Send email via system mail client (address validated) | `aicli do "send email to alice@... say build passed"` |
| `get_system_info` | CPU, memory, disk, uptime | `aicli do "get system info"` |
| `send_notification` | Desktop notification | `aicli do "notify me the build is done"` |
| Custom plugins | Any plugin with `"parameters"` auto-registers | `aicli do "create a Jira ticket for..."` |

### Flags

```bash
aicli do "task"                  # executes immediately (auto_confirm=True default)
aicli do --confirm "task"        # ask [Y/n] before each tool call
aicli do --dry-run "task"        # show @FunctionCall plan, nothing executes
aicli do --retries 3 "task"      # retry failed tools up to 3 times
aicli do --session NAME "task"   # multi-turn with memory of prior do calls
aicli do --verbose "task"        # show tool count alongside @FunctionCall output
```

### Direct Invocation (Smart Routing)

```bash
# These auto-route to "do" (action intent detected):
aicli "play ~/Music/Wired.mp3"
aicli "open hacker news"
aicli "browse my music in this dir"
aicli "send email to alice@example.com just say hi"
aicli "play music and open hacker news"   # compound → LLM dispatches both

# These auto-route to "ask" (question/explanation intent detected):
aicli "explain async/await"
aicli "what is a load balancer"
aicli "how does TCP work"
aicli "write a function that sorts a list"   # LLM instruction → ask
```

### Audit Log

Every tool call is logged to `~/.config/aicli/tool_audit.jsonl`:
```bash
aicli tools audit            # view in terminal
cat ~/.config/aicli/tool_audit.jsonl | tail -5   # raw JSONL
```

### Sandboxing

Enable firejail sandboxing for `run_shell_command`:
```bash
export AICLI_SANDBOX=1   # requires firejail on PATH
# → --quiet --noprofile --noroot --private-tmp --net=none
# → 32KB output cap (truncated with message)
export AICLI_SANDBOX_NET=1   # allow network access inside sandbox
```

### Plugin Auto-Registration

Plugins with a `"parameters"` key are automatically available to `aicli do`:

```python
# ~/.config/aicli/plugins/jira.py
def register():
    return {
        "name": "create_jira_ticket",
        "description": "Create a Jira ticket with title and description",
        "parameters": {
            "title": {"type": "string", "description": "Ticket title"},
            "description": {"type": "string", "description": "Ticket body"},
        },
        "confirm": True,
        "fn": create_jira_ticket,
    }
```

After dropping this file in `~/.config/aicli/plugins/`:
```bash
aicli do "create a ticket for the login bug"
# → @FunctionCall create_jira_ticket(title='Fix login bug', description='...')
```

## Architecture

aicli-maxmux uses a **3-layer CMA (Contextual Memory Architecture)**:

```
🔥 Hot Layer   — in-memory context for current session
🌡️ Warm Layer  — SQLite + Fernet encrypted persistent history
❄️ Cold Layer  — ChromaDB vector embeddings for semantic RAG
```

Provider failover chain: **Groq → OpenRouter → Gemini → Mistral → Ollama**  
Adaptive cooldowns: 429 → 5min, 401/403 → 1hr, 5xx → 10-15s

## Local HTTP API (`aicli serve`)

```bash
aicli serve                    # start on :8765
aicli serve --daemon           # background daemon
aicli serve --port 9000        # custom port
aicli serve --quiet            # suppress startup banner
```

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/ask` | Single-shot prompt |
| POST | `/ask/shell` | Shell command generation |
| POST | `/ask/code` | Code generation |
| GET | `/sessions` | List all sessions |
| GET | `/sessions/:id` | Get session messages |
| GET | `/health` | Health check + provider status |
| GET | `/providers` | Provider availability |

**Request body (POST /ask):**
```json
{ "prompt": "explain async/await", "web": false, "lite": false, "model": null }
```

## Session Graph

```bash
aicli graph                  # start graph server + open browser
aicli graph --port 8080      # custom port
aicli graph --no-browser     # headless use
```

An interactive D3 force-directed graph that auto-loads all your exported sessions as nodes. Create links between sessions, add notes, and explore connections.

**Node tags:** Click any node → Tags field → enter comma-separated tags → Save. Tags appear as `#tag` labels under nodes. Filter the graph by tag using the tag bar at the top — click a tag chip or type in the filter box.

**Browser shortcuts:** `L` link mode · `R` reload · `Esc` cancel · double-click to edit · hover link + click to delete

Sessions exported via **F4** in the TUI appear automatically on next reload.

## Quick Launch

Open TUI, graph server, and browser graph view in one command:

```bash
./start.sh
```

**What it opens:**
```
┌────────────────────┬──────────┐
│                    │  Graph   │
│   aicli TUI        │ terminal │
│   (left ¾,         ├──────────┤
│    full height)    │ Firefox  │
│                    │  :7337   │
└────────────────────┴──────────┘
```

- Auto-installs `wmctrl` if missing
- Detects screen resolution via `xdpyinfo` (fallback 1920×1080)
- Opens Firefox to `http://localhost:7337` automatically
- Positions all 3 windows with exact pixel coordinates

**Requirements:** `wmctrl`, `xdpyinfo` (both auto-installed on first run)

## Web Search

`--web` uses a 6-backend chain — no API key required for the free tier:

1. **Tavily** — AI-optimised, most accurate (set `TAVILY_API_KEY` for best results)
2. **SearXNG** — public instances, rotated (skipped automatically over Tor)
3. **DuckDuckGo** — Instant Answer JSON API
4. **DuckDuckGo lite** — HTML scrape with cookie jar
5. **Bing** — scrape with rotating User-Agent
6. **Mojeek** — independent engine, scrape-friendly fallback

Tor/proxy support works out of the box — Tavily is used as the primary backend over SOCKS5.

## Privacy & Security

- All conversation history encrypted with Fernet (AES-128-CBC)
- Keys derived from machine fingerprint (hostname + username) — no master password needed
- API keys stored in OS keychain (libsecret / keychain) **and** encrypted Fernet file as fallback
- No telemetry, no cloud sync, no ads
- Tor/proxy support: `aicli config set AICLI_PROXY socks5://127.0.0.1:9050`
- Tool sandboxing via firejail (`AICLI_SANDBOX=1`): `--private-tmp --net=none`, 32KB output cap
- Tool audit log: every `aicli do` call logged to `~/.config/aicli/tool_audit.jsonl`

## Install Modes

| Mode | Command | Size | RAG | TUI | Hotkey |
|------|---------|------|-----|-----|--------|
| **Lite** | `pip install aicli-maxmux[lite]` | ~20MB | ✗ | ✗ | ✓ |
| **Full** | `pip install aicli-maxmux[all]` | ~468MB | ✓ | ✓ | ✓ |
| **Dev** | `pip install aicli-maxmux[dev]` | ~468MB+ | ✓ | ✓ | ✓ |

Lite mode uses `aicli-lite` as the entry point and sets `AICLI_LITE=1` automatically.
All commands work in lite mode except `--context` (RAG) and `aicli tui`.

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `AICLI_LITE=1` | Enable lite mode globally (skip RAG/ChromaDB init) |
| `AICLI_QUIET=1` | Enable quiet mode globally (raw output, no chrome) |
| `AICLI_PROVIDER_CHAIN` | Override provider order (e.g. `gemini,ollama`) |
| `AICLI_CONFIG_DIR` | Override config directory (default: `~/.config/aicli`) |
| `AICLI_{PROVIDER}_KEY` | Set API key via env (CI/CD friendly) |
| `TAVILY_API_KEY` | Tavily web search key (optional, 1000/mo free) |
| `AICLI_PROXY` | Proxy/Tor (e.g. `socks5://127.0.0.1:9050`) |
| `AICLI_SANDBOX=1` | Enable firejail sandboxing for `run_shell_command` |
| `AICLI_SANDBOX_NET=1` | Allow network access inside sandbox (removes `--net=none`) |

## Requirements

- Python 3.11+
- Optional: `pip install aicli-maxmux[all]` for RAG + TUI
- Optional: `pip install aicli-maxmux[lite]` for minimal footprint (~20MB)
- Optional: `sudo apt install xclip` for TUI clipboard on Linux (Ctrl+Y)
- Optional: `sudo apt install firejail` for tool sandboxing (`AICLI_SANDBOX=1`)

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for full version history.

**Latest: v1.6.3** — `_detect_intent` smart routing · `@FunctionCall` display · silent execution by default · Ctrl+L chain widget (zsh + bash) · direct dispatch fast path (~50ms) · `play_music`/`browse_media` overhaul · tool sandboxing · TUI DoModeScreen confirm toggle · `beautifulsoup4` + `[web]` extra · 784 pytest + 14 slow RAG · 786 static checks · **published to PyPI 2026-03-16**

**v1.5.7** — `_FallbackGroup` Click fix · `--retries`/`--session`/`--do` flags · plugin TOOL_REGISTRY auto-registration · DoModeScreen F9 · `run_shell_command` working_dir · 759 tests

**v1.5.6** — context-aware Ctrl+G (tmux scrollback) · Ctrl+E error-fix hotkey · `--watch` streaming log monitor · `--file/-f` multi-file context · 703 tests · v1.5.5: patch fixes

## Roadmap

| Version | Feature | Status |
|---------|---------|--------|
| v1.5.3 | `aicli cmd` shell shorthand | ✅ Done |
| v1.5.3 | `aicli code` code shorthand | ✅ Done |
| v1.5.3 | `--quiet / -q` mode | ✅ Done |
| v1.5.3 | Shell hotkey (`aicli config install-shell`) | ✅ Done |
| v1.5.3 | Lite mode + `aicli-lite` entry point | ✅ Done |
| v1.5.3 | `aicli setup` wizard | ✅ Done |
| v1.5.3 | `aicli serve` local HTTP API | ✅ Done |
| v1.5.3 | Vim navigation in TUI (`j/k/G/g/dd//`) | ✅ Done |
| v1.5.3 | Obsidian export (`--obsidian`) | ✅ Done |
| v1.5.3 | Graph node tags + tag filtering | ✅ Done |
| v1.5.4 | MCP server (Claude Desktop integration) | ✅ Done |
| v1.5.4 | `aicli tag` CLI shorthand | ✅ Done |
| v1.5.4 | 669 passing tests + 467 static checks | ✅ Done |
| v1.5.4 | `aicli serve --daemon` (background mode + PID file) | ✅ Done |
| v1.5.4 | `aicli history QUERY` (semantic search across sessions) | ✅ Done |
| v1.5.4 | `aicli stats` (token counts, message counts) | ✅ Done |
| v1.5.4 | MCP `_tool_ask` with RAG context | ✅ Done |
| v1.5.4 | Windows shell integration (`shell_integration.ps1`) | ✅ Done |
| v1.5.4 | `bump_version.py` atomic version update | ✅ Done |
| v1.5.4 | `aicli config install-shell --shell powershell` | ✅ Done |
| v1.5.5 | `ContextRetriever` module-level binding — patchable in tests | ✅ Done |
| v1.5.5 | Stale `/tmp/` source path auto-cleanup in `config install-shell` | ✅ Done |
| v1.5.5 | 490+ static checks | ✅ Done |
| v1.5.6 | Context-aware Ctrl+G — tmux scrollback injected as `--terminal-context` | ✅ Done |
| v1.5.6 | Ctrl+E error-fix hotkey — auto-diagnose last failed command (zsh + bash) | ✅ Done |
| v1.5.6 | `--watch` streaming mode — real-time AI log monitor | ✅ Done |
| v1.5.6 | `--file/-f` multi-file context | ✅ Done |
| v1.5.6 | LLM-optimal injection order: RAG → TC → files → web | ✅ Done |
| v1.5.6 | 703 pytest tests · 530 static checks | ✅ Done |
| v1.5.7 | `_FallbackGroup` Click fix · `--retries`/`--session`/`--do` flags | ✅ Done |
| v1.5.7 | Plugin TOOL_REGISTRY auto-registration | ✅ Done |
| v1.5.7 | DoModeScreen F9 TUI + `run_shell_command` working_dir | ✅ Done |
| v1.5.7 | 759 pytest tests · 717 static checks | ✅ Done |
| v1.6.0 | `_detect_intent` smart routing + `@FunctionCall` format | ✅ Done |
| v1.6.0 | Ctrl+L chain widget (zsh + bash) | ✅ Done |
| v1.6.0 | Direct dispatch fast path (~50ms single-tool commands) | ✅ Done |
| v1.6.0 | `play_music` + `browse_media` full overhaul | ✅ Done |
| v1.6.0 | Tool sandboxing (firejail + 32KB cap) | ✅ Done |
| v1.6.0 | End-to-end RAG test suite (18 `@pytest.mark.slow`) | ✅ Done |
| v1.6.0 | `beautifulsoup4` in `[full]`/`[all]` + new `[web]` extra | ✅ Done |
| v1.6.0 | 784 pytest (non-slow) + 14 slow · 786 static checks | ✅ Done |
| v1.6.0 | **Published to PyPI** — `pip install aicli-maxmux==1.6.0` | ✅ Done |
| v1.5.x | Missing TUI widget tests (`TestTUI` live render) | 📋 Scoped |
| v1.5.x | `aicli serve --daemon` Windows port (os.fork is Unix-only) | 📋 Scoped |
| v1.7.x | Next feature cycle | 🔜 Upcoming |

---

## Lite Mode — Run AI Anywhere

aicli-maxmux was designed from the ground up to work in constrained environments. The **lite install** strips everything non-essential and gets you a fully functional AI CLI in about 20MB.

```bash
pipx install "aicli-maxmux[lite]"   # ~20MB, isolated, no venv needed
aicli-lite "explain this error"      # works immediately if any API key is set
```

**What lite mode includes:**
- Full provider chain: Groq → OpenRouter → Gemini → Mistral → Ollama
- All CLI flags: `ask`, `cmd`, `code`, `chat`, `do`, `session`, `export`, `serve`
- Shell hotkeys: Ctrl+G, Ctrl+E, Ctrl+I, Ctrl+L
- Encrypted key storage, quiet mode, direct invocation
- Web search (`--web`) and file context (`-f`)

**What lite mode skips (optional):**
- ChromaDB RAG (`--context`) — add with `pip install "aicli-maxmux[rag]"`
- Textual TUI (`aicli tui`) — add with `pip install "aicli-maxmux[tui]"`
- Web scraping backends — add with `pip install "aicli-maxmux[web]"`

**Install only what you need:**

| Extra | Command | Adds |
|-------|---------|------|
| `[lite]` | `pip install "aicli-maxmux[lite]"` | Core only (~20MB) |
| `[web]` | `pip install "aicli-maxmux[web]"` | Bing + Mojeek scraping, Tor/SOCKS5 |
| `[rag]` | `pip install "aicli-maxmux[rag]"` | ChromaDB + sentence-transformers |
| `[tui]` | `pip install "aicli-maxmux[tui]"` | Textual terminal UI |
| `[mcp]` | `pip install "aicli-maxmux[mcp]"` | MCP server for Claude Desktop |
| `[all]` | `pip install "aicli-maxmux[all]"` | Everything (~468MB) |
| `[dev]` | `pip install "aicli-maxmux[dev]"` | All + test tools |

Lite mode is the default recommendation for most users. The full install is only needed if you specifically want RAG or the TUI.

---

## Modularity — Built to Extend

aicli-maxmux is not a monolith. Every layer is independently replaceable or extendable.

### Drop-in provider replacement
The provider chain is just a list in your config. Override it per-session or globally:
```bash
aicli ask --model gemini/gemini-2.0-flash "explain this"
AICLI_PROVIDER_CHAIN=ollama,groq aicli "local first, cloud fallback"
```

### Plugin system
Drop a `.py` file into `~/.config/aicli/plugins/` and it's immediately available to `aicli do`:
```python
# ~/.config/aicli/plugins/jira.py
def register():
    return {
        "name": "create_jira_ticket",
        "description": "Create a Jira ticket",
        "parameters": {"title": {"type": "string"}, "priority": {"type": "string"}},
        "confirm": True,
        "fn": create_ticket,
    }
```
```bash
aicli do "create a high priority ticket for the login bug"
# → @FunctionCall create_jira_ticket(title='Fix login bug', priority='high')
```
No restart required. No registration step. No core file changes.

### Custom roles
```bash
aicli ask --role devops "explain this Kubernetes error"
aicli cmd --chain --role "You are a senior SRE" "harden this nginx config"
```

### Local HTTP API
```bash
aicli serve   # starts REST API on :8765
curl -s http://localhost:8765/ask -d '{"prompt": "what is async/await"}' -H "Content-Type: application/json"
```
Scripting, CI/CD integration, third-party tools — all without touching the CLI directly.

### MCP server for Claude Desktop
```bash
aicli mcp   # stdio MCP server
```
```json
{"mcpServers": {"aicli": {"command": "aicli", "args": ["mcp"]}}}
```
Claude Desktop gets access to all 5 tools: `ask`, `cmd`, `do`, `search_history`, `get_session`.

---

## Privacy & Security — No Compromises

aicli-maxmux was built with the assumption that your data, keys, and conversations belong to you and no one else.

### Everything stays local
- All conversation history is **AES-128-CBC encrypted** (Fernet) on disk
- Encryption keys are derived from your machine fingerprint — no master password needed
- No telemetry. No analytics. No cloud sync. No ads. Ever.
- Sessions are stored in `~/.config/aicli/sessions.db` — yours, encrypted, offline

### API key storage
- Keys stored in the **OS keychain** (libsecret on Linux, Keychain on macOS) — not in shell config files, not in `.env`, not in plaintext
- Fernet-encrypted file backup for headless environments (CI/CD, Tor, no D-Bus session)
- Keys never appear in shell history — `aicli config set-key groq` uses masked input
- `aicli config get KEY` shows only first 8 + last 4 characters

### Tool sandboxing
When running OS tools via `aicli do`, you can enforce strict isolation:
```bash
export AICLI_SANDBOX=1   # requires firejail
# Every run_shell_command call gets:
#   --quiet --noprofile --noroot --private-tmp --net=none
#   + 32KB output cap (prevents prompt-flooding)
export AICLI_SANDBOX_NET=1   # allow network inside sandbox if needed
```

### Confirmation gate
```bash
aicli do --confirm "delete logs older than 30 days"
# → @FunctionCall delete_old_logs(days=30)
#   Delete log files older than 30 days.
#   Run? [Y/n]
```
By default, `aicli do` executes immediately (matching ShellGPT UX). Add `--confirm` for any destructive action — every tool call is gated individually.

### Audit log
Every tool execution is appended to `~/.config/aicli/tool_audit.jsonl`:
```json
{"ts": "2026-03-16T19:30:00", "tool": "run_shell_command", "args": {"command": "rm -rf /tmp/cache"}, "result": "ok", "session": "myproject"}
```
```bash
aicli tools audit          # view in terminal
aicli tools audit --tool run_shell_command   # filter by tool
```
Tamper-evident. Append-only. Stays local.

### Tor / proxy support
```bash
aicli config set AICLI_PROXY socks5://127.0.0.1:9050
aicli ask --web "..."   # all requests routed through Tor
# SearXNG auto-skipped over Tor (avoids rate-limit blocks)
# Tavily used as primary backend over SOCKS5
```

---

## Interface & UX — Designed for the Terminal

aicli-maxmux treats the terminal as a first-class interface, not an afterthought.

### Smart intent routing
No need to remember subcommands. Just type naturally:
```bash
aicli "play music and open hacker news"      # → do (action)
aicli "explain async/await"                  # → ask (question)
aicli "browse my music in this dir"          # → do (direct dispatch, ~50ms)
aicli "summarize /tmp/report.txt"            # → do (path detected)
```

### Shell hotkeys — zero friction
```
Ctrl+G   → suggest a command for what you typed (tmux-aware: sees actual output)
Ctrl+E   → auto-fix last failed command — captures error, generates fix, pastes into buffer
Ctrl+I   → suggest next command based on what just ran
Ctrl+L   → run current buffer as multi-step chain (Y/n per step)
```
Every hotkey works in both **zsh and bash**. Context-aware: Ctrl+G in tmux reads your actual terminal output, not just shell history — so it sees the error message without you having to describe it.

### @FunctionCall display
```
@FunctionCall play_music(query='~/Music/Wired.mp3')
  Play music or media using the system's default media player.
✓ Playing via mpv: /home/dev/Music/Wired.mp3
```
Clean, recognisable to ShellGPT users, more informative — shows the description line and execution result.

### Multi-step chains
```bash
aicli cmd --chain "create index.html with hello world, spin up nginx container mounting it"
# [1/3] touch index.html          Run? [Y/n]
# [2/3] echo "<h1>hello world</h1>" > index.html   Run? [Y/n]
# [3/3] docker run -d -p 80:80 -v $(pwd)/index.html:/usr/share/nginx/html/index.html nginx   Run? [Y/n]
```
Or just press **Ctrl+L** with the task typed in your buffer.

### Full TUI
```bash
aicli tui
```
- Left sidebar: all sessions with message counts, click to switch
- Scrollable chat with role colours and syntax highlighting
- F9 → OS function calling (DoModeScreen) with live confirm toggle (Ctrl+Y)
- F1 help · F2 range-select · F3 theme cycle · F4 export · F5 import · F6 sync
- Vim navigation: `j/k` scroll · `G/g` top/bottom · `/` search · `dd` delete
- 5 built-in themes: Tokyo Night · Dracula · Gruvbox · Nord · Solarized Dark
- Real clipboard: `wl-copy` → `xclip` → `xsel` → `pbcopy` chain

### Watch mode — AI as a live monitor
```bash
tail -f /var/log/syslog | aicli ask --watch "alert on OOM killer"
# → silent until condition fires
# [ALERT 19:42:07] OOM killer invoked — process nginx (PID 1234) killed

# Automatically take action on trigger:
journalctl -f | aicli ask --watch "disk usage above 90%" \
    --do "get_system_info detail=disk"
```

### Output modes
```bash
aicli ask -q "what is my IP"        # quiet: raw output only, no chrome — pipe-friendly
aicli ask --lite "explain this"     # lite: skip RAG init, faster cold start
aicli do --dry-run "send email..."  # dry-run: show @FunctionCall plan, nothing executes
aicli do --verbose "..."            # verbose: show tool count alongside output
```

### Session graph
```bash
aicli graph   # D3 force-directed graph of all your sessions, opens in browser
```
Link sessions, add notes, filter by tag, explore connections. Sessions exported via F4 in the TUI appear automatically.

---

## License

MIT
