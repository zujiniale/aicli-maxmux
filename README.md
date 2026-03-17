# aicli-maxmux

![Version](https://img.shields.io/badge/version-1.5.7-ff4488) ![Tests](https://img.shields.io/badge/tests-752%20passing-22c55e) ![Python](https://img.shields.io/badge/python-3.11%2B-4f8ef7) ![License](https://img.shields.io/badge/license-MIT-6b6b80) ![Lite](https://img.shields.io/badge/lite%20mode-%7E20MB-a855f7)

A free, private, terminal-native AI CLI with multi-provider failover, persistent memory,
web search, vision support, and autonomous agent mode.

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
| **Quick shell command shorthand** | `aicli cmd "kill process on port 3000" --run` |
| **Quick code generation shorthand** | `aicli code "fibonacci" --run` |
| **Quiet / scriptable output** | `aicli ask -q "what is my IP"` |
| **Shell hotkey (Ctrl+G)** | `aicli config install-shell` |
| **Lite mode (~20MB, no RAG/TUI)** | `pip install aicli-maxmux[lite]` |
| **Vim-style TUI navigation** | `j/k` scroll · `G/g` top/bottom · `/` search · `dd` delete |
| **Graph node tags + filtering** | Tag bar in graph viewer, filter by tag |
| **Obsidian export** | `aicli export mysession --obsidian > vault/note.md` |
| **Local HTTP API** | `aicli serve` |
| **MCP server (Claude Desktop)** | `aicli mcp` · stdio + SSE · 4 tools · 2 resources |
| **Semantic history search** | `aicli history "query"` — search all past sessions |
| **Token & message stats** | `aicli stats` · per-session counts · `--top N` |
| **Background HTTP daemon** | `aicli serve --daemon` · `aicli serve stop` |
| **Windows shell hotkey (Ctrl+G)** | `aicli config install-shell --shell powershell` |
| **Atomic version bumping** | `python bump_version.py 1.5.5` |
| **Context-aware shell hotkey** | Ctrl+G captures tmux scrollback · Ctrl+E auto-fixes last error |
| **Watch mode (live log AI monitor)** | `tail -f app.log \| aicli ask --watch "alert on ERROR"` |
| **Multi-file context attach** | `aicli ask -f error.log -f screenshot.png "what happened"` |
| **Direct invocation** | `aicli "your prompt"` — no subcommand needed, like `sgpt` |
| **Zero-config start** | Auto-detects `GROQ_API_KEY`, `OPENROUTER_API_KEY` etc. from env |
| **pipx compatible** | `pipx install "aicli-maxmux[lite]"` — isolated, no venv needed |

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

# Quick shell command (new shorthand)
aicli cmd "find all files larger than 100MB"
aicli cmd "kill process on port 3000" --run

# Quick code generation (new shorthand)
aicli code "write a merge sort in Python"
aicli code "fibonacci function" --run

# Quiet / scriptable output
aicli ask -q "what is today's date"

# Install shell hotkey (Ctrl+G → generates commands in your buffer)
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

aicli cmd "prompt"                    # quick shell command (shorthand: ask --shell)
aicli cmd "prompt" --run              # generate + execute immediately
aicli cmd "prompt" --dry-run          # print command only, no menu
aicli cmd "prompt" --lite             # lite + shell

aicli code "prompt"                   # quick code generation (shorthand: ask --code)
aicli code "prompt" --run             # generate + execute
aicli code "prompt" --run --language bash   # run as bash
aicli code "prompt" --run --language node   # run as node.js
aicli code "prompt" --quiet           # raw code output only

aicli setup                           # interactive first-time setup wizard

aicli chat --session NAME             # persistent conversation
aicli repl                            # interactive REPL
aicli agent "task"                    # autonomous multi-step execution
aicli agent --dry-run "task"          # show plan without executing

aicli export SESSION > out.md         # export to markdown
aicli export SESSION --format json    # export to JSON
aicli export SESSION --obsidian > note.md          # Obsidian-compatible (YAML + callouts)
aicli export SESSION --obsidian --include-summary -o ~/vault/SESSION.md

aicli config set KEY VALUE            # store any key encrypted
aicli config get KEY                  # read stored key (masked)
aicli config set-key PROVIDER         # interactive key entry
aicli config show                     # show all config + env vars
aicli config keys                     # show which providers have keys
aicli config install-shell            # install Ctrl+G shell hotkey (auto-detects zsh/bash)
aicli config install-shell --shell zsh --hotkey "^L"   # custom shell + hotkey

aicli provider status                 # show provider availability
aicli provider test groq              # test a specific provider
aicli session list                    # list all sessions
aicli session show NAME               # show session messages
aicli session delete NAME             # delete a session
aicli index PATH                      # index files for RAG

aicli serve                           # start local HTTP API (default: localhost:8765)
aicli serve --port 9000               # custom port
aicli serve --host 0.0.0.0            # expose to network (use with caution)
aicli serve --quiet                   # suppress startup message
aicli serve --daemon                  # run in background (PID saved to ~/.config/aicli/serve.pid)
aicli serve stop                      # stop background daemon

aicli mcp                             # start MCP server (stdio, for Claude Desktop)
aicli mcp --transport sse             # SSE transport (browser/network clients)
aicli tag SESSION tag1,tag2           # tag a session (persisted to graph_links.json)

aicli history "query"                 # semantic search across all past sessions
aicli history "query" --results 10   # more results
aicli history "query" --min-score 0.3 # adjust similarity threshold

aicli stats                           # all sessions: message + token counts
aicli stats --session NAME            # single session detail
aicli stats --top 5                   # top 5 sessions by message count

aicli graph                           # session graph viewer (browser)
aicli graph --port 8080               # custom port
aicli graph --no-browser              # no auto-open

aicli plugin list                     # list installed plugins
aicli plugin run NAME ARG             # run a plugin
aicli plugin install URL              # install plugin from URL
aicli plugin doc NAME                 # show plugin details
aicli plugin errors                   # show load errors

./start.sh                            # open TUI + graph together
```


## Terminal UI (TUI)

```bash
aicli tui                        # open TUI
aicli tui --session myproject    # open specific session
aicli tui --no-history           # open without loading past messages
```

### TUI Keyboard Shortcuts

| Key | Action |
|-----|--------|
| **F1** | Help overlay |
| **F2** | Range select (click start → click end → Ctrl+Y) |
| **F3** | Cycle theme (Tokyo Night / Dracula / Gruvbox / Nord / Solarized) |
| **F4** | Export session to timestamped `.md` + `.json` |
| **F5** | Import latest exported session JSON into current session |
| **F6** | Sync all data to exports folder |
| **F7** | Open graph viewer in browser |
| **Ctrl+N** | New session |
| **Ctrl+D** | Delete session (or bulk) |
| **Ctrl+K** | Pin / unpin session |
| **Ctrl+B** | Toggle bulk select mode |
| **Ctrl+E** | Export to markdown (single or bulk) |
| **Ctrl+J** | Backup all sessions to JSON |
| **Ctrl+I** | Import from most recent backup |
| **Ctrl+W** | Toggle web search |
| **Ctrl+X** | Toggle RAG context |
| **Ctrl+S** | Summarize current session |
| **Ctrl+Y** | Copy message to clipboard |
| **Ctrl+R** | Copy typed range (e.g. type `3-7` then Ctrl+R) |
| **Ctrl+O** | Open exports folder |
| **Ctrl+9** | Settings (export path + hotkey remapping) |
| **Ctrl+Q** | Quit |
| **Enter** | Send message |
| **Ctrl+Enter** | Insert newline (multiline messages) |
| **Esc** | Clear range select |

### Vim Navigation (when input not focused)

| Key | Action |
|-----|--------|
| **j** | Scroll chat down |
| **k** | Scroll chat up |
| **G** | Jump to bottom |
| **g** | Jump to top |
| **/*** | Focus session search |
| **dd** | Delete session (press d twice) |

Requires: `pip install textual`

## MCP Server (Claude Desktop)

```bash
aicli mcp                    # stdio transport — use with Claude Desktop
aicli mcp --transport sse    # SSE transport — browser / network clients
```

Exposes aicli as a Model Context Protocol server so Claude Desktop can call your local AI pipeline, manage sessions, and tag conversations.

**Claude Desktop config** (`~/Library/Application Support/Claude/claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "aicli": { "command": "aicli", "args": ["mcp"] }
  }
}
```

| Tool | Description |
|------|-------------|
| `ask` | Full AI prompt via provider pipeline |
| `cmd` | Shell command generation (auto-strips fences) |
| `code` | Code generation (correct JS/TS/Node.js casing) |
| `tag` | Tag a session — merges, never overwrites |

| Resource | URI |
|----------|-----|
| Session list | `sessions://list` |
| Session messages | `sessions://{session_id}` |

## Local HTTP API (`aicli serve`)

```bash
aicli serve                    # start on localhost:8765
aicli serve --port 9000        # custom port
aicli serve --quiet            # suppress startup banner
```

Exposes aicli as a local REST API for scripting, tool integration, and MCP-style access.

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

**Example:**
```bash
# Ask
curl -s http://localhost:8765/ask \
  -H "Content-Type: application/json" \
  -d '{"prompt": "what is 2+2"}'

# Shell command
curl -s http://localhost:8765/ask/shell \
  -d '{"prompt": "find all log files"}' \
  -H "Content-Type: application/json"

# Health check
curl -s http://localhost:8765/health | jq .
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

## Requirements

- Python 3.11+
- Optional: `pip install aicli-maxmux[all]` for RAG + TUI
- Optional: `pip install aicli-maxmux[lite]` for minimal footprint (~20MB)
- Optional: `sudo apt install xclip` for TUI clipboard on Linux (Ctrl+Y)

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for full version history.

**Latest: v1.5.7** — context-aware Ctrl+G (tmux scrollback) · Ctrl+E error-fix hotkey · `--watch` streaming log monitor · `--file/-f` multi-file context · LLM-optimal injection order · 703 tests · 530 static checks · v1.5.5: patch fixes (`ContextRetriever` binding, stale `/tmp/` cleanup) · v1.5.4: MCP server · `aicli history` · `aicli stats` · `aicli serve --daemon` · PowerShell Ctrl+G

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
| v1.5.3 | Tests: `TestServe`, `TestWebSearch`, `TestNewCommands`, `TestVimNav`, `TestNodeTags`, `TestObsidianExport` | ✅ Done |
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
| v1.5.5 | `ContextRetriever` module-level binding — patchable in tests (`app.py`, `mcp_server.py`) | ✅ Done |
| v1.5.5 | Stale `/tmp/` source path auto-cleanup in `config install-shell` | ✅ Done |
| v1.5.5 | `test_history_handles_no_chromadb` — `side_effect=ImportError` → `patch to None` fix | ✅ Done |
| v1.5.5 | Phase 5 config import consolidation (`CHROMA_DIR` merged into single import line) | ✅ Done |
| v1.5.5 | 490+ static checks · `pathlib.Path.home()` patched in install-shell test | ✅ Done |
| v1.5.6 | Context-aware Ctrl+G — tmux scrollback injected as `--terminal-context` | ✅ Done |
| v1.5.6 | Ctrl+E error-fix hotkey — auto-diagnose last failed command (zsh + bash) | ✅ Done |
| v1.5.6 | `--watch` streaming mode — real-time AI log monitor (`tail -f \| aicli ask --watch`) | ✅ Done |
| v1.5.6 | `--file/-f` multi-file context — attach any text/log/code file to prompt | ✅ Done |
| v1.5.6 | LLM-optimal injection order: RAG → TC → files → web | ✅ Done |
| v1.5.6 | 703 pytest tests · 530 static checks | ✅ Done |
| v1.5.x | Missing TUI widget tests (`TestTUI` live render) | 📋 Scoped |
| v1.5.x | `aicli serve --daemon` Windows port (os.fork is Unix-only) | 📋 Scoped |

## License

MIT
