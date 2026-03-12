#!/usr/bin/env zsh

# aicli - Project Retraction Script
# Removes venv and all build artifacts — leaves core code and dist/ wheel intact

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"
echo -e "${YELLOW}📉 Retracting aicli Project${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"
echo ""

# ── Detect what's present ─────────────────────────────────────────────────────
HAS_DEPENDENCIES=false
TOTAL_TO_REMOVE=0

VENV_DIRS=()
if [ -d "venv" ]; then
    VENV_DIRS+=("venv")
    HAS_DEPENDENCIES=true
fi
if [ -d ".venv" ]; then
    VENV_DIRS+=(".venv")
    HAS_DEPENDENCIES=true
fi

HAS_PYCACHE=false
HAS_PYTEST_CACHE=false
HAS_EGGINFO=false
HAS_BUILD=false

if find . -type d -name "__pycache__" -not -path "*/venv/*" -not -path "*/.venv/*" 2>/dev/null | grep -q .; then
    HAS_PYCACHE=true
    HAS_DEPENDENCIES=true
fi
if [ -d ".pytest_cache" ]; then
    HAS_PYTEST_CACHE=true
    HAS_DEPENDENCIES=true
fi
if find . -type d -name "*.egg-info" -not -path "*/venv/*" -not -path "*/.venv/*" 2>/dev/null | grep -q .; then
    HAS_EGGINFO=true
    HAS_DEPENDENCIES=true
fi
# NOTE: dist/ is intentionally preserved — it contains the built wheel (.whl)
# Only remove build/ (intermediate build artifacts), not dist/
if [ -d "build" ]; then
    HAS_BUILD=true
    HAS_DEPENDENCIES=true
fi

# ── Guard: already retracted? ─────────────────────────────────────────────────
if [ "$HAS_DEPENDENCIES" = false ]; then
    echo -e "${YELLOW}⚠️  Project is already RETRACTED${NC}"
    echo ""
    echo "No dependencies or build artifacts found."
    echo ""

    CURRENT_LINES=$(find . -type f \
        -not -path "*/.git/*" \
        -not -path "*/__pycache__/*" \
        -not -path "*/dist/*" \
        -exec wc -l {} + 2>/dev/null | tail -n 1 | awk '{print $1}')
    CURRENT_FILES=$(find . -type f \
        -not -path "*/.git/*" \
        -not -path "*/__pycache__/*" \
        -not -path "*/dist/*" \
        2>/dev/null | wc -l)

    echo -e "${CYAN}Current state (core only):${NC}"
    echo -e "  Lines: ${GREEN}${CURRENT_LINES}${NC}"
    echo -e "  Files: ${GREEN}${CURRENT_FILES}${NC}"
    echo ""
    echo "To expand: ./expand.sh"
    exit 0
fi

# ── Capture EXPANDED stats before removal ────────────────────────────────────
echo -e "${YELLOW}📊 Current state (EXPANDED — with dependencies):${NC}"

INITIAL_LINES=$(find . -type f \
    -not -path "*/.git/*" \
    -not -path "*/dist/*" \
    -exec wc -l {} + 2>/dev/null | tail -n 1 | awk '{print $1}')

INITIAL_FILES=$(find . -type f \
    -not -path "*/.git/*" \
    -not -path "*/dist/*" \
    2>/dev/null | wc -l)

INITIAL_PY=$(find . -name "*.py" 2>/dev/null | wc -l)

echo -e "  Lines: ${GREEN}${INITIAL_LINES}${NC}"
echo -e "  Files: ${GREEN}${INITIAL_FILES}${NC}"
echo -e "  Python files: ${GREEN}${INITIAL_PY}${NC}"
echo ""

# ── Show what will be removed ─────────────────────────────────────────────────
echo -e "${YELLOW}📦 About to remove:${NC}"

for venv_dir in "${VENV_DIRS[@]}"; do
    VENV_SIZE=$(du -sh "$venv_dir" 2>/dev/null | awk '{print $1}')
    VENV_FILES=$(find "$venv_dir" -type f 2>/dev/null | wc -l)
    echo -e "  • ${venv_dir}/        ${CYAN}${VENV_SIZE}${NC}  (${VENV_FILES} files)"
    TOTAL_TO_REMOVE=$((TOTAL_TO_REMOVE + VENV_FILES))
done

if [ "$HAS_PYCACHE" = true ]; then
    CACHE_FILES=$(find . -type d -name "__pycache__" -not -path "*/venv/*" -not -path "*/.venv/*" \
        -exec find {} -type f \; 2>/dev/null | wc -l)
    echo -e "  • __pycache__/   compiled .pyc files  (${CACHE_FILES} files)"
    TOTAL_TO_REMOVE=$((TOTAL_TO_REMOVE + CACHE_FILES))
fi
if [ "$HAS_PYTEST_CACHE" = true ]; then
    echo -e "  • .pytest_cache/  test cache"
fi
if [ "$HAS_EGGINFO" = true ]; then
    echo -e "  • *.egg-info/     editable install metadata"
fi
if [ "$HAS_BUILD" = true ]; then
    echo -e "  • build/          setuptools intermediate artifacts"
fi

echo -e "  ${BOLD}Total to remove: ~${TOTAL_TO_REMOVE} files${NC}"
echo ""
echo -e "  ${CYAN}Note: dist/ is preserved (contains built wheel aicli-maxmux-*.whl)${NC}"
echo ""

# ── Remove venv(s) ────────────────────────────────────────────────────────────
if [ ${#VENV_DIRS[@]} -gt 0 ]; then
    echo -e "${YELLOW}━━━ Python Virtual Environment ━━━${NC}"
    for venv_dir in "${VENV_DIRS[@]}"; do
        VENV_SIZE=$(du -sh "$venv_dir" 2>/dev/null | awk '{print $1}')
        echo "🗑️  Removing ${venv_dir}/ ..."
        rm -rf "$venv_dir"
        echo -e "${GREEN}✓ Removed ${venv_dir}/ ${NC}(was ${VENV_SIZE})"
    done
    echo ""
fi

# ── Remove build artifacts ────────────────────────────────────────────────────
echo -e "${YELLOW}━━━ Cleaning Build Artifacts ━━━${NC}"
CLEANED=0

# __pycache__ everywhere (outside venv — already gone)
if find . -type d -name "__pycache__" 2>/dev/null | grep -q .; then
    find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    echo -e "${GREEN}✓ Removed __pycache__ directories${NC}"
    CLEANED=$((CLEANED + 1))
fi

# .pyc / .pyo compiled files
if find . -type f \( -name "*.pyc" -o -name "*.pyo" \) 2>/dev/null | grep -q .; then
    find . -type f \( -name "*.pyc" -o -name "*.pyo" \) -delete 2>/dev/null || true
    echo -e "${GREEN}✓ Removed compiled .pyc/.pyo files${NC}"
    CLEANED=$((CLEANED + 1))
fi

# .pytest_cache
if [ -d ".pytest_cache" ]; then
    rm -rf .pytest_cache
    echo -e "${GREEN}✓ Removed .pytest_cache/${NC}"
    CLEANED=$((CLEANED + 1))
fi

# egg-info (from pip install -e .) — handles both aicli.egg-info and aicli_maxmux.egg-info
if find . -type d -name "*.egg-info" -not -path "*/venv/*" -not -path "*/.venv/*" 2>/dev/null | grep -q .; then
    find . -type d -name "*.egg-info" -not -path "*/venv/*" -not -path "*/.venv/*" -exec rm -rf {} + 2>/dev/null || true
    echo -e "${GREEN}✓ Removed *.egg-info directories${NC}"
    CLEANED=$((CLEANED + 1))
fi

# build/ intermediate artifacts only (NOT dist/ — wheel preserved)
if [ -d "build" ]; then
    rm -rf build
    echo -e "${GREEN}✓ Removed build/ directory${NC}"
    CLEANED=$((CLEANED + 1))
fi

if [ "$CLEANED" -eq 0 ]; then
    echo -e "${YELLOW}–  No build artifacts found${NC}"
fi

echo ""

# ── Final stats (retracted state) ────────────────────────────────────────────
FINAL_LINES=$(find . -type f \
    -not -path "*/venv/*" \
    -not -path "*/.venv/*" \
    -not -path "*/__pycache__/*" \
    -not -path "*/.git/*" \
    -not -path "*/.pytest_cache/*" \
    -not -path "*/dist/*" \
    -exec wc -l {} + 2>/dev/null | tail -n 1 | awk '{print $1}')

FINAL_FILES=$(find . -type f \
    -not -path "*/venv/*" \
    -not -path "*/.venv/*" \
    -not -path "*/__pycache__/*" \
    -not -path "*/.git/*" \
    -not -path "*/.pytest_cache/*" \
    -not -path "*/dist/*" \
    2>/dev/null | wc -l)

FINAL_PY=$(find . -name "*.py" \
    -not -path "*/venv/*" \
    -not -path "*/.venv/*" \
    -not -path "*/__pycache__/*" \
    -not -path "*/dist/*" \
    2>/dev/null | wc -l)

echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✅ aicli RETRACTED Successfully${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"
echo ""

echo -e "${CYAN}📊 Final state (RETRACTED — core code only):${NC}"
echo -e "  Lines: ${GREEN}${FINAL_LINES}${NC}"
echo -e "  Files: ${GREEN}${FINAL_FILES}${NC}"
echo -e "  Python files: ${GREEN}${FINAL_PY}${NC}"
echo ""

# Reduction analysis
if [ -n "$INITIAL_LINES" ] && [ -n "$FINAL_LINES" ] && [ "$INITIAL_LINES" -gt 0 ] 2>/dev/null; then
    REMOVED=$((INITIAL_LINES - FINAL_LINES))
    if [ "$REMOVED" -gt 0 ]; then
        PERCENT=$(echo "scale=1; ($REMOVED * 100) / $INITIAL_LINES" | bc 2>/dev/null || echo "?")
        RATIO=$(echo "scale=1; $INITIAL_LINES / $FINAL_LINES" | bc 2>/dev/null || echo "?")
        echo -e "${YELLOW}📉 Reduction Analysis:${NC}"
        echo -e "  Lines removed:  ${GREEN}${REMOVED}${NC}"
        echo -e "  Files removed:  ${GREEN}$((INITIAL_FILES - FINAL_FILES))${NC}"
        echo -e "  Size reduction: ${GREEN}${PERCENT}%${NC}"
        echo -e "  Compression:    ${GREEN}${RATIO}x smaller${NC}"
        echo ""
    fi
fi

echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"
echo ""
echo "Project is now RETRACTED — core source only."
echo ""
echo "Core files preserved:"
echo "  aicli/                      ← main package"
echo "    app.py                    ← CLI entry (aicli.app:main)"
echo "    config.py                 ← config + API key store"
echo "    printer.py                ← streaming output + rich markdown rendering"
echo "    tokens.py                 ← token estimation (tiktoken cl100k_base)"
echo "    role.py                   ← system role/persona management"
echo "    image_utils.py            ← multimodal image support (--image flag)"
echo "    integration.py            ← integration helpers"
echo "    web.py                    ← web search backends (6-chain)"
echo "    graph_server.py           ← session graph server (aicli graph)"
echo "    tui.py                    ← Textual TUI (aicli tui)"
echo "    providers/pipeline.py     ← PROVIDER_MODELS + 5-provider failover engine"
echo "    providers/registry.py     ← ProviderRegistry: name→class mapping"
echo "    providers/                ← base, groq, openrouter, gemini, mistral, ollama"
echo "    db/chat_db.py             ← SQLite CMA"
echo "    db/crypto.py              ← Fernet encryption"
echo "    context/manager.py        ← 3-layer CMA (Hot/Warm/ChromaDB RAG cold)"
echo "    context/embeddings.py     ← ChromaDB LocalContext + ChatContextStore"
echo "    context/retriever.py      ← ChromaDB ContextRetriever unified search"
echo "    handlers/                 ← chat, repl, default, export, agent, index,"
echo "                                 provider, code_runner"
echo "    tools/builtin/shell.py    ← shell E/M/D/A/R"
echo "    tools/builtin/read_file.py ← read file tool"
echo "    tools/loader.py           ← tool plugin loader"
echo "  tests/test_aicli.py         ← unit tests"
echo "  tests/test_integration.py   ← integration tests"
echo "  tests/test_tui_pure.py      ← TUI pure logic tests"
echo "  tests/test_graph_server.py  ← graph server tests"
echo "  tests/conftest.py           ← pytest fixtures"
echo "  dist/                       ← built wheel (preserved)"
echo "  requirements.txt"
echo "  pyproject.toml"
echo ""
echo "To expand again: ./expand.sh"
echo ""
