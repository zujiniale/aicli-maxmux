# aicli-maxmux

![Version](https://img.shields.io/badge/version-1.5.0-ff4488) ![Tests](https://img.shields.io/badge/tests-193%20passing-22c55e) ![Python](https://img.shields.io/badge/python-3.10%2B-4f8ef7) ![License](https://img.shields.io/badge/license-MIT-6b6b80)

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
| Shell command generation + execution | `aicli ask --shell "find large files"` |
| Autonomous multi-step agent | `aicli agent "set up a Python project"` |
| Semantic RAG over chat history | `aicli chat --context` |
| Session export (Markdown / JSON) | `aicli export mysession > out.md` |
| Full terminal UI with themes, clipboard, range select | `aicli tui` |
| Interactive session graph viewer | `aicli graph` |
| Run generated code in Python / Bash / Node / Ruby | `aicli ask --code --run --language bash "..."` |
| Plugin system — drop `.py` files to extend aicli | `aicli plugin list` |
| Encrypted key storage, no shell exports | `aicli config set TAVILY_API_KEY tvly-xxxx` |
| Tor / proxy support | `aicli config set AICLI_PROXY socks5://127.0.0.1:9050` |

## Install

```bash
pip install aicli-maxmux
```

## Quick Start

```bash
# Set at least one API key
aicli config set-key groq        # fastest — free at console.groq.com
aicli config set-key openrouter  # vision support — free at openrouter.ai

# Ask something
aicli ask "explain async/await in Python"

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

aicli chat --session NAME             # persistent conversation
aicli repl                            # interactive REPL
aicli agent "task"                    # autonomous multi-step execution
aicli agent --dry-run "task"          # show plan without executing

aicli export SESSION > out.md         # export to markdown
aicli export SESSION --format json    # export to JSON

aicli config set KEY VALUE            # store any key encrypted
aicli config get KEY                  # read stored key (masked)
aicli config set-key PROVIDER         # interactive key entry
aicli config show                     # show all config + env vars
aicli config keys                     # show which providers have keys

aicli provider status                 # show provider availability
aicli provider test groq              # test a specific provider
aicli session list                    # list all sessions
aicli session show NAME               # show session messages
aicli session delete NAME             # delete a session
aicli index PATH                      # index files for RAG

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
| **Esc** | Clear range select |

Requires: `pip install textual`

## Session Graph

```bash
aicli graph                  # start graph server + open browser
aicli graph --port 8080      # custom port
aicli graph --no-browser     # headless use
```

An interactive D3 force-directed graph that auto-loads all your exported sessions as nodes. Create links between sessions, add notes, and explore connections.

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

## Requirements

- Python 3.10+
- Optional: `pip install textual` for TUI (`aicli tui`)
- Optional: `pip install pysocks` for Tor/SOCKS5 support
- Optional: `sudo apt install xclip` for TUI clipboard on Linux (Ctrl+Y)

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for full version history.

**Latest: v1.5.0** — 3-pane wmctrl launch layout · comprehensive documentation suite · roadmap scoped through v2.0

## Roadmap

| Version | Feature | Status |
|---------|---------|--------|
| v1.5.x | Graph node tags + filtering | 📋 Scoped |
| v1.5.x | `aicli serve` local HTTP API | 📋 Scoped |
| v1.5.x | Vim-style TUI navigation (`j/k`, `/`, `dd`) | 📋 Scoped |
| v1.5.x | Missing tests: `TestTUI`, `TestGraphServer`, `TestWebSearch` | 📋 Scoped |
| v1.6.x | Obsidian export (`[[wikilinks]]`) | 📋 Scoped |
| v2.0.x | MCP server (Claude Desktop integration) | 📋 Scoped |

## License

MIT
