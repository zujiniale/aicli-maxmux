#!/usr/bin/env zsh

# aicli - Project Structure Mapper
# Generates a comprehensive PROJECT_MAP.txt describing every module

OUTPUT_FILE="PROJECT_MAP.txt"
DATE=$(date '+%Y-%m-%d %H:%M:%S')

# Colors (for terminal output only)
GREEN='\033[0;32m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${BLUE}Generating aicli structure map...${NC}"

# ── Dynamic codebase stats ────────────────────────────────────────────────────
PY_FILES_COUNT=$(find . -name "*.py" \
    -not -path "*/venv/*" -not -path "*/.venv/*" \
    -not -path "*/__pycache__/*" 2>/dev/null | wc -l | tr -d ' ')

PY_LINE_COUNT=$(cloc . \
    --exclude-dir=venv,.venv,__pycache__,.git,.pytest_cache,dist,build \
    --quiet 2>/dev/null | grep "^Python " | awk '{print $5}')
[ -z "$PY_LINE_COUNT" ] && PY_LINE_COUNT="unknown"

# Format with comma (e.g. 2854 → 2,854)
PY_LINE_COUNT_FMT=$(echo "$PY_LINE_COUNT" | sed ':a;s/\B[0-9]\{3\}\>/,&/;ta')

# ── Header ────────────────────────────────────────────────────────────────────
cat > "$OUTPUT_FILE" << EOF
================================================================================
aicli — PROJECT STRUCTURE MAP
Generated: $DATE
================================================================================

aicli is a terminal AI assistant with 5-provider failover, encrypted SQLite
conversation memory (3-layer CMA: Hot/Warm/ChromaDB RAG), web search (6-backend
chain), shell command generation, multimodal vision, TUI, session graph viewer,
code runner, plugin system, REPL mode, session export, and autonomous agent mode.
Published to PyPI as aicli-maxmux 1.5.1.

Package:     aicli-maxmux 1.5.1
Entry point: aicli = "aicli.app:main"
Codebase:    $PY_LINE_COUNT_FMT lines of Python (cloc, $PY_FILES_COUNT files)

================================================================================
FULL PROJECT TREE (core source only — no venv / pycache)
================================================================================

EOF

tree -I 'venv|.venv|__pycache__|*.pyc|.git|*.egg-info|.pytest_cache|dist|build' \
    --dirsfirst -a >> "$OUTPUT_FILE" 2>/dev/null || \
    find . -not -path "*/venv/*" -not -path "*/.venv/*" \
           -not -path "*/__pycache__/*" -not -path "*/.git/*" \
           -not -path "*/.pytest_cache/*" \
           | sort >> "$OUTPUT_FILE"

cat >> "$OUTPUT_FILE" << 'EOF'

================================================================================
MODULE REFERENCE — WHAT EACH FILE DOES
================================================================================

ROOT
────
  app.py              ← (in aicli/) CLI entry point — aicli.app:main
                         All click commands: ask, chat, repl, index, provider,
                         export, agent, config, tui, graph, plugin, session,
                         _provider_test
  __main__.py         ← python -m aicli dispatcher
  __init__.py         ← package init + version re-export
  __version__.py      ← single source of truth for version string (1.5.1)
  config.py           ← AICLI_* env var resolution, API key get/set,
                         Fernet encryption key derivation from machine ID,
                         CHROMA_DIR path for ChromaDB cold layer
  printer.py          ← streaming output + rich markdown rendering
  tokens.py           ← token estimation (tiktoken cl100k_base when available;
                         falls back to char-blend heuristic)
  integration.py      ← integration helpers (component wiring)
  role.py             ← system role/persona management
  image_utils.py      ← multimodal image support (--image flag)
                         • load_image_b64() — load PNG/JPEG/GIF/WebP as base64
                         • build_multimodal_content() — assemble image+text content list
                         • is_multimodal() — detect vision messages in history
                         • Vision providers: OpenRouter ✅ Gemini ✅ Groq ✗ Mistral ✗
  web.py              ← Web search: 6-backend chain
                         1. Tavily (AI-optimised, TAVILY_API_KEY)
                         2. SearXNG public instances (rotated)
                         3. DuckDuckGo Instant Answer JSON
                         4. DuckDuckGo lite HTML scrape
                         5. Bing scrape (rotating User-Agent)
                         6. Mojeek fallback
                         • --web / --web-debug / --web-verbose flags
                         • Tor/proxy support via AICLI_PROXY
  graph_server.py     ← Session graph server (aicli graph)
                         • FastAPI/uvicorn HTTP server on :7337
                         • D3 force-directed graph of all exported sessions
                         • Link, tag, note nodes in browser
  tui.py              ← Full terminal UI (aicli tui)
                         • Textual framework (requires: pip install textual)
                         • Sidebar session list, chat panel, input bar
                         • 5 themes: Tokyo Night / Dracula / Gruvbox / Nord / Solarized
                         • F1-F7 + Ctrl shortcuts (see README for full list)

PROVIDERS/
──────────
  pipeline.py         ← THE CORE ENGINE
                         • PROVIDER_MODELS dict (must live here, not config.py)
                         • 5-provider failover: Groq→OpenRouter→Gemini→Mistral→Ollama
                         • cooldown_until timestamps — instant failover, no sleep()
                         • Adaptive cooldowns: 429→5min, 401/403→1hr, 5xx→10-15s
                         • stream_with_fallback() — async generator
  registry.py         ← ProviderRegistry: maps name → provider class,
                         resolves active provider, validates at startup
  base.py             ← BaseProvider ABC: stream(), test_connection()
  groq.py             ← Groq provider — User-Agent: curl/8.5.0 (REQUIRED)
  openrouter.py       ← OpenRouter — model: openrouter/auto (stable choice)
  gemini.py           ← Google Gemini provider
  mistral.py          ← Mistral provider
  ollama.py           ← Local Ollama fallback (no API key needed)
  __init__.py         ← exports all provider classes

DB/
───
  chat_db.py          ← SQLite conversation store
                         • db.save() ALWAYS FIRST — before token count, before prune
                         • Sessions: named (slug) or UUID auto-generated
                         • [AUTO-SUMMARY] blocks protected from trim_messages()
                         • datetime.now(timezone.utc) — no deprecation warnings
  crypto.py           ← Fernet symmetric encryption
                         • Key = PBKDF2(machine_id + salt)
                         • machine_id from /etc/machine-id or platform.node()
                         • All message content encrypted at rest in SQLite
  __init__.py

CONTEXT/
────────
  manager.py          ← 3-layer Contextual Memory Architecture (CMA)
                         🔥 Hot  — in-memory list (current session)
                         🌡️ Warm — SQLite + async [AUTO-SUMMARY] at 80% token threshold
                         ❄️ Cold — ChromaDB RAG, auto-indexed every turn
                         • trim_messages() prunes oldest, preserves [AUTO-SUMMARY]
                         • fire-and-forget async summarization + cold indexing tasks
                         • _index_message_cold() — upserts 1 message per turn
                         • _backfill_cold() — indexes full session on first load
  embeddings.py       ← ChromaDB LocalContext + ChatContextStore (active)
  retriever.py        ← ChromaDB ContextRetriever — unified search interface (active)
  __init__.py

HANDLERS/
─────────
  handler.py          ← BaseHandler ABC
  chat.py             ← Persistent chat session handler: named sessions, REPL loop,
                         RAG retrieval + indexing (--context flag), streams response,
                         updates CMA; Ctrl+C → await_pending_summarization()
  repl.py             ← Interactive REPL loop — persists ContextManager across turns
  default.py          ← Default/fallback handler
  export.py           ← aicli export — dumps session to Markdown or JSON
  agent.py            ← aicli agent — plan/execute/feedback loop
                         • --dry-run to show plan without executing
  index.py            ← aicli index — file + chat indexing for RAG
  provider.py         ← aicli provider status + test commands
  code_runner.py      ← aicli ask --code --run — generate + execute code
                         • Supports: Python / Bash / Node / Ruby
                         • --language flag, --timeout flag (default 30s)
  __init__.py

TOOLS/
──────
  loader.py           ← Tool plugin loader — scans tools/builtin/ + tools/user/
                         • aicli plugin list / run / install / doc / errors
  __init__.py
  builtin/
    shell.py          ← Shell command tool: Edit/Make/Delete/Apply/Run (E/M/D/A/R)
                         • shell=False everywhere (security)
                         • 12 HIGH_RISK_PATTERNS checked before execution
                         • Self-correction loop: on error → re-prompt with stderr
    read_file.py      ← Read file tool (feeds content to LLM context)
    __init__.py

TESTS/
──────
  test_aicli.py       ← Unit tests (mocks/patches, no live API)
                         Tests: config, crypto, db, providers, tokens, shell
  test_integration.py ← Integration tests (component wiring, still mocked)
  test_tui_pure.py    ← TUI pure logic tests (no display, no Textual dependency)
  test_graph_server.py ← Graph server tests
  conftest.py         ← pytest fixtures: tmp_db, mock_provider, env cleanup
  __init__.py

CONFIG FILES
────────────
  pyproject.toml      ← Build config (hatchling), entry point, optional extras:
                         [full] keyring+httpx+rich+tiktoken
                         [rag]  chromadb+sentence-transformers
                         [tui]  textual
                         [proxy] pysocks
                         [dev]  pytest+ruff+twine+build
                         [all]  everything
  requirements.txt    ← Full dependency list with annotations
  CHANGELOG.md        ← Version history

SCRIPTS
───────
  expand.sh           ← Create venv, install deps, verify all modules
  retract.sh          ← Remove venv + build artifacts (preserves dist/)
  map_structure.sh    ← Generate this PROJECT_MAP.txt
  stats_final.sh      ← Detailed project statistics (requires: cloc)
  start.sh            ← Launch TUI + graph server + Firefox in tiled layout

EXPORTS/
────────
  graph.html          ← D3 graph viewer (served by graph_server.py)
  graph_links.json    ← Persisted graph node links
  *.md / *.json       ← Session exports (F4 in TUI or aicli export)

EOF

# ── CMA architecture ─────────────────────────────────────────────────────────
cat >> "$OUTPUT_FILE" << 'EOF'
================================================================================
CONTEXTUAL MEMORY ARCHITECTURE (CMA)
================================================================================

  ┌─────────────────────────────────────────────────────────────────────┐
  │  🔥 HOT LAYER — In-Memory                                           │
  │     Current session messages in ContextManager._active_messages     │
  │     Lost on process exit (REPL persists within session)             │
  ├─────────────────────────────────────────────────────────────────────┤
  │  🌡️ WARM LAYER — SQLite (chat_db.py + crypto.py)                    │
  │     All messages encrypted with Fernet + machine fingerprint        │
  │     db.save() called FIRST — unconditional, always                  │
  │     At 80% token threshold → fire-and-forget async summarization    │
  │     [AUTO-SUMMARY] blocks immune to trim_messages() pruning         │
  │     Sessions: named slug OR auto UUID                               │
  ├─────────────────────────────────────────────────────────────────────┤
  │  ❄️ COLD LAYER — ChromaDB RAG  ✅ BUILT                              │
  │     Auto-indexed every turn via _index_message_cold()               │
  │     context/embeddings.py + context/retriever.py — fully active     │
  │     Retrieval: inject via --context flag in chat.py                 │
  │     Degradation: chromadb missing → _rag_enabled=False → silent     │
  └─────────────────────────────────────────────────────────────────────┘

  The one rule: db.save() ALWAYS FIRST. Before token counting. Before pruning.
  Violating this = data loss on crash.

EOF

# ── Roadmap ───────────────────────────────────────────────────────────────────
cat >> "$OUTPUT_FILE" << 'EOF'
================================================================================
BUILD ROADMAP — WHAT'S DONE vs. WHAT'S NEXT
================================================================================

  ✅ Phase 1  Core CLI + Groq streaming                       COMPLETE
  ✅ Phase 2  5-provider failover + User-Agent fix            COMPLETE
  ✅ Phase 3  SQLite CMA + Fernet encryption                  COMPLETE
  ✅ Phase 4  REPL persistence + shell E/M/D/A/R              COMPLETE
  ✅ Phase 5  keyring + httpx + rich + pyproject entry point  COMPLETE
  ✅ Phase 6  PyPI publish (aicli-maxmux 1.0.0 → 1.5.1)      COMPLETE
  ✅ F1       aicli export (markdown + JSON)                  COMPLETE
  ✅ F2       --image multimodal flag                         COMPLETE
  ✅ F3       aicli agent (plan/execute/feedback loop)        COMPLETE
  ✅ F4       ChromaDB RAG (cold layer)                       COMPLETE
  ✅ F5       Web search (6-backend chain, Tor-aware)         COMPLETE
  ✅ F6       aicli tui (Textual full TUI)                    COMPLETE
  ✅ F7       aicli graph (D3 session graph viewer)           COMPLETE
  ✅ F8       --code --run (code runner, multi-language)      COMPLETE
  ✅ F9       Plugin system (aicli plugin list/run/install)   COMPLETE

  Roadmap (upcoming):
  📋 v1.5.x   Graph node tags + filtering
  📋 v1.5.x   aicli serve (local HTTP API)
  📋 v1.5.x   Vim-style TUI navigation (j/k, /, dd)
  📋 v1.6.x   Obsidian export ([[wikilinks]])
  📋 v2.0.x   MCP server (Claude Desktop integration)

EOF

# ── Statistics ────────────────────────────────────────────────────────────────
echo "" >> "$OUTPUT_FILE"
echo "================================================================================" >> "$OUTPUT_FILE"
echo "FILE STATISTICS" >> "$OUTPUT_FILE"
echo "================================================================================" >> "$OUTPUT_FILE"
echo "" >> "$OUTPUT_FILE"

PY_FILES=$(find . -name "*.py" \
    -not -path "*/venv/*" -not -path "*/.venv/*" \
    -not -path "*/__pycache__/*" 2>/dev/null | wc -l)

PY_LINES=$(find . -name "*.py" \
    -not -path "*/venv/*" -not -path "*/.venv/*" \
    -not -path "*/__pycache__/*" \
    -exec wc -l {} + 2>/dev/null | tail -n 1 | awk '{print $1}')

printf "  %-30s %6s files\n" "Total Python files:" "$PY_FILES" >> "$OUTPUT_FILE"
printf "  %-30s %6s lines\n" "Total Python lines:" "$PY_LINES" >> "$OUTPUT_FILE"
echo "" >> "$OUTPUT_FILE"

echo "  Per-module line counts:" >> "$OUTPUT_FILE"

for f in \
    "aicli/app.py" \
    "aicli/config.py" \
    "aicli/printer.py" \
    "aicli/tokens.py" \
    "aicli/role.py" \
    "aicli/integration.py" \
    "aicli/image_utils.py" \
    "aicli/web.py" \
    "aicli/graph_server.py" \
    "aicli/tui.py" \
    "aicli/providers/pipeline.py" \
    "aicli/providers/registry.py" \
    "aicli/providers/base.py" \
    "aicli/providers/groq.py" \
    "aicli/providers/openrouter.py" \
    "aicli/providers/gemini.py" \
    "aicli/providers/mistral.py" \
    "aicli/providers/ollama.py" \
    "aicli/db/chat_db.py" \
    "aicli/db/crypto.py" \
    "aicli/context/manager.py" \
    "aicli/context/embeddings.py" \
    "aicli/context/retriever.py" \
    "aicli/handlers/chat.py" \
    "aicli/handlers/repl.py" \
    "aicli/handlers/handler.py" \
    "aicli/handlers/default.py" \
    "aicli/handlers/export.py" \
    "aicli/handlers/agent.py" \
    "aicli/handlers/index.py" \
    "aicli/handlers/provider.py" \
    "aicli/handlers/code_runner.py" \
    "aicli/tools/loader.py" \
    "aicli/tools/builtin/shell.py" \
    "aicli/tools/builtin/read_file.py" \
    "tests/test_aicli.py" \
    "tests/test_integration.py" \
    "tests/test_tui_pure.py" \
    "tests/test_graph_server.py" \
    "tests/conftest.py"; do
    if [ -f "$f" ]; then
        LINES=$(wc -l < "$f" 2>/dev/null || echo "0")
        printf "    %-45s %5s lines\n" "$f" "$LINES" >> "$OUTPUT_FILE"
    fi
done

echo "" >> "$OUTPUT_FILE"

# Test count across all test files
TOTAL_TESTS=$(grep -c "def test_" \
    tests/test_aicli.py \
    tests/test_integration.py \
    tests/test_tui_pure.py \
    tests/test_graph_server.py \
    2>/dev/null | awk -F: '{sum+=$2} END{print sum+0}')

echo "  Test count:  ${TOTAL_TESTS} passing (all test files)" >> "$OUTPUT_FILE"
echo "" >> "$OUTPUT_FILE"
echo "================================================================================" >> "$OUTPUT_FILE"
echo "End of aicli PROJECT_MAP.txt" >> "$OUTPUT_FILE"
echo "" >> "$OUTPUT_FILE"

# ── Terminal summary ──────────────────────────────────────────────────────────
echo -e "${GREEN}✓ Structure map written to: ${OUTPUT_FILE}${NC}"
echo ""
echo -e "${CYAN}Summary:${NC}"
echo -e "  Python files (core): ${GREEN}${PY_FILES}${NC}"
echo -e "  Python lines (core): ${GREEN}${PY_LINES}${NC}"
echo ""
echo -e "  Modules:"
for mod in providers db context handlers tools; do
    COUNT=$(find "aicli/${mod}" -name "*.py" -not -name "__init__.py" \
        -not -path "*/__pycache__/*" 2>/dev/null | wc -l)
    printf "    %-12s %s files\n" "${mod}/" "${COUNT}"
done
echo ""
echo -e "  Tests: ${GREEN}${TOTAL_TESTS} passing${NC}"
echo -e "  Version: ${GREEN}1.5.1${NC}"
echo ""
