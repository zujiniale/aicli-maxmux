#!/usr/bin/env zsh

# aicli - Project Expansion Script
# Creates venv and installs ALL Python dependencies

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"
echo -e "${YELLOW}🚀 Expanding aicli Project${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"
echo ""

# ── Guard: already expanded? ──────────────────────────────────────────────────
ALREADY_EXPANDED=false
VENV_DIR=""

if [ -d "venv" ]; then
    ALREADY_EXPANDED=true
    VENV_DIR="venv"
elif [ -d ".venv" ]; then
    ALREADY_EXPANDED=true
    VENV_DIR=".venv"
fi

if [ "$ALREADY_EXPANDED" = true ]; then
    echo -e "${YELLOW}⚠️  Project is already EXPANDED${NC}"
    echo ""
    echo "Virtual environment already exists at: ${VENV_DIR}/"
    echo ""

    CURRENT_LINES=$(find . -type f \
        -not -path "*/.git/*" \
        -exec wc -l {} + 2>/dev/null | tail -n 1 | awk '{print $1}')
    CURRENT_FILES=$(find . -type f \
        -not -path "*/.git/*" \
        2>/dev/null | wc -l)

    echo -e "${CYAN}Current state:${NC}"
    echo -e "  Total lines: ${GREEN}${CURRENT_LINES}${NC}"
    echo -e "  Total files: ${GREEN}${CURRENT_FILES}${NC}"
    echo ""
    echo "Next steps:"
    echo "  1. Activate venv:    source ${VENV_DIR}/bin/activate"
    echo "  2. Set API key:      aicli config set-key groq"
    echo "  3. Ask something:    aicli ask \"hello\""
    echo "  4. Named session:    aicli ask -s mysession \"hello\""
    echo "  5. Interactive REPL: aicli repl"
    echo "  6. Full TUI:         aicli tui"
    echo "  7. Session graph:    aicli graph"
    echo "  8. Export session:   aicli export mysession > out.md"
    echo "  9. Run tests:        python -m pytest tests/ -v"
    echo ""
    echo "To retract: ./retract.sh"
    exit 0
fi

# ── Sanity check ──────────────────────────────────────────────────────────────
if [ ! -f "requirements.txt" ]; then
    echo -e "${RED}✗ requirements.txt not found.${NC}"
    echo "  Are you in the aicli project root? Expected layout:"
    echo "    aicli/          ← package"
    echo "    tests/"
    echo "    requirements.txt"
    echo "    pyproject.toml"
    exit 1
fi

if [ ! -d "aicli" ]; then
    echo -e "${RED}✗ aicli/ package directory not found.${NC}"
    echo "  Are you in the aicli project root?"
    exit 1
fi

# ── Initial stats (retracted state) ──────────────────────────────────────────
echo -e "${YELLOW}📊 Initial state (RETRACTED — core code only):${NC}"

INITIAL_LINES=$(find . -type f \
    -not -path "*/venv/*" \
    -not -path "*/.venv/*" \
    -not -path "*/__pycache__/*" \
    -not -path "*/.git/*" \
    -not -path "*/.pytest_cache/*" \
    -not -path "*/dist/*" \
    -exec wc -l {} + 2>/dev/null | tail -n 1 | awk '{print $1}')

INITIAL_FILES=$(find . -type f \
    -not -path "*/venv/*" \
    -not -path "*/.venv/*" \
    -not -path "*/__pycache__/*" \
    -not -path "*/.git/*" \
    -not -path "*/.pytest_cache/*" \
    -not -path "*/dist/*" \
    2>/dev/null | wc -l)

INITIAL_PY=$(find . -name "*.py" \
    -not -path "*/venv/*" \
    -not -path "*/.venv/*" \
    -not -path "*/__pycache__/*" \
    -not -path "*/dist/*" \
    2>/dev/null | wc -l)

echo -e "  Lines: ${GREEN}${INITIAL_LINES}${NC}"
echo -e "  Files: ${GREEN}${INITIAL_FILES}${NC}"
echo -e "  Python files: ${GREEN}${INITIAL_PY}${NC}"
echo ""

# ── Create virtual environment ────────────────────────────────────────────────
echo -e "${YELLOW}━━━ Python Virtual Environment ━━━${NC}"

echo "📦 Creating virtual environment (venv)..."
python3 -m venv venv
VENV_DIR="venv"

echo "📦 Activating..."
source venv/bin/activate

echo "📦 Upgrading pip..."
pip install --upgrade pip --quiet

echo "📦 Installing dependencies from requirements.txt..."
pip install -r requirements.txt --quiet

echo "📦 Installing aicli package (editable)..."
pip install -e . --quiet

echo -e "${GREEN}✓ All Python dependencies installed${NC}"
echo ""

# ── Verify required packages ──────────────────────────────────────────────────
# Each entry: "import_name|display_name|description"
echo -e "${YELLOW}━━━ Verifying Core Packages ━━━${NC}"

CORE_PKGS=(
    "click|click|CLI framework"
    "cryptography|cryptography|Fernet key encryption"
    "pytest|pytest|Test runner"
    "pytest_asyncio|pytest-asyncio|Async test support"
    "tiktoken|tiktoken|Exact token counting"
)

ALL_OK=true
for entry in "${CORE_PKGS[@]}"; do
    IMP="${entry%%|*}"
    REST="${entry#*|}"
    PKG="${REST%%|*}"
    DESC="${REST#*|}"
    if python -c "import ${IMP}" 2>/dev/null; then
        echo -e "  ${GREEN}✓${NC} ${PKG} — ${DESC}"
    else
        echo -e "  ${RED}✗${NC} ${PKG} — ${DESC} — MISSING"
        ALL_OK=false
    fi
done

echo ""
echo -e "${CYAN}  Feature packages (active if installed):${NC}"

OPT_PKGS=(
    "keyring|keyring|OS keychain storage"
    "httpx|httpx|Async HTTP client"
    "rich|rich|Rich terminal markdown output"
    "textual|textual|TUI framework (aicli tui)"
    "chromadb|chromadb|Vector RAG cold layer"
    "sentence_transformers|sentence-transformers|RAG embeddings (pip install .[rag])"
    "socks|pysocks|Tor/SOCKS5 proxy support (pip install .[proxy])"
)

for entry in "${OPT_PKGS[@]}"; do
    IMP="${entry%%|*}"
    REST="${entry#*|}"
    PKG="${REST%%|*}"
    DESC="${REST#*|}"
    if python -c "import ${IMP}" 2>/dev/null; then
        echo -e "  ${GREEN}✓${NC} ${PKG} — ${DESC}"
    else
        echo -e "  ${YELLOW}–${NC} ${PKG} — ${DESC} (not installed)"
    fi
done

echo ""

if [ "$ALL_OK" = false ]; then
    echo -e "${RED}⚠️  Some core packages failed to install. Try:${NC}"
    echo "     pip install -r requirements.txt"
    echo ""
fi

# ── Verify aicli package itself loads ────────────────────────────────────────
echo -e "${YELLOW}━━━ Verifying aicli Package ━━━${NC}"

# Core modules — must all import cleanly
MODULES=(
    "aicli"
    "aicli.config"
    "aicli.printer"
    "aicli.tokens"
    "aicli.role"
    "aicli.integration"
    "aicli.image_utils"
    "aicli.web"
    "aicli.graph_server"
    "aicli.db.chat_db"
    "aicli.db.crypto"
    "aicli.providers.pipeline"
    "aicli.providers.registry"
    "aicli.providers.base"
    "aicli.providers.groq"
    "aicli.providers.openrouter"
    "aicli.providers.gemini"
    "aicli.providers.mistral"
    "aicli.providers.ollama"
    "aicli.context.manager"
    "aicli.context.embeddings"
    "aicli.context.retriever"
    "aicli.handlers.handler"
    "aicli.handlers.chat"
    "aicli.handlers.repl"
    "aicli.handlers.default"
    "aicli.handlers.export"
    "aicli.handlers.agent"
    "aicli.handlers.index"
    "aicli.handlers.provider"
    "aicli.handlers.code_runner"
    "aicli.tools.loader"
    "aicli.tools.builtin.shell"
    "aicli.tools.builtin.read_file"
)

IMPORT_ERRORS=0
for mod in "${MODULES[@]}"; do
    if python -c "import ${mod}" 2>/dev/null; then
        echo -e "  ${GREEN}✓${NC} ${mod}"
    else
        echo -e "  ${RED}✗${NC} ${mod} — import failed"
        IMPORT_ERRORS=$((IMPORT_ERRORS + 1))
    fi
done

# TUI requires textual — soft failure is expected without it
echo ""
echo -e "${CYAN}  Optional module imports (require extras):${NC}"
if python -c "import aicli.tui" 2>/dev/null; then
    echo -e "  ${GREEN}✓${NC} aicli.tui"
else
    echo -e "  ${YELLOW}–${NC} aicli.tui (requires: pip install textual)"
fi

echo ""

if [ "$IMPORT_ERRORS" -gt 0 ]; then
    echo -e "${RED}⚠️  ${IMPORT_ERRORS} module(s) failed to import. Run: python -m pytest tests/ -v${NC}"
else
    echo -e "${GREEN}✓ All core aicli modules import cleanly${NC}"
fi

echo ""
echo -e "${CYAN}  Entry point:${NC}"
if aicli --version 2>/dev/null; then
    echo -e "  ${GREEN}✓${NC} aicli command available"
else
    echo -e "  ${RED}✗${NC} aicli command not found — run: pip install -e ."
fi

echo ""

# ── Final stats ───────────────────────────────────────────────────────────────
FINAL_LINES=$(find . -type f \
    -not -path "*/.git/*" \
    -not -path "*/dist/*" \
    -not -path "*/__pycache__/*" \
    -not -path "*/.pytest_cache/*" \
    -exec wc -l {} + 2>/dev/null | tail -n 1 | awk '{print $1}')

FINAL_FILES=$(find . -type f \
    -not -path "*/.git/*" \
    -not -path "*/dist/*" \
    -not -path "*/__pycache__/*" \
    -not -path "*/.pytest_cache/*" \
    2>/dev/null | wc -l)

FINAL_PY=$(find . -name "*.py" 2>/dev/null | wc -l)

echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✅ aicli EXPANDED Successfully${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"
echo ""

echo -e "${YELLOW}📊 Final state (EXPANDED):${NC}"
echo -e "  Total lines:  ${GREEN}${FINAL_LINES}${NC}"
echo -e "  Total files:  ${GREEN}${FINAL_FILES}${NC}"
echo -e "  Python files: ${GREEN}${FINAL_PY}${NC}"
echo ""

if [ -n "$INITIAL_LINES" ] && [ "$INITIAL_LINES" -gt 0 ] 2>/dev/null; then
    ADDED=$((FINAL_LINES - INITIAL_LINES))
    if [ "$ADDED" -gt 0 ]; then
        RATIO=$(echo "scale=1; $FINAL_LINES / $INITIAL_LINES" | bc 2>/dev/null || echo "?")
        PERCENT=$(echo "scale=1; ($ADDED * 100) / $INITIAL_LINES" | bc 2>/dev/null || echo "?")
        echo -e "${YELLOW}📈 Expansion Analysis:${NC}"
        echo -e "  Lines added:     ${GREEN}${ADDED}${NC}"
        echo -e "  Files added:     ${GREEN}$((FINAL_FILES - INITIAL_FILES))${NC}"
        echo -e "  Size increase:   ${GREEN}${PERCENT}%${NC}"
        echo -e "  Expansion ratio: ${GREEN}${RATIO}x${NC}"
        echo ""
    fi
fi

echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"
echo ""
echo "Next steps:"
echo "  1. Activate venv:    source venv/bin/activate"
echo "  2. Set API key:      aicli config set-key groq"
echo "  3. Ask something:    aicli ask \"hello\""
echo "  4. Named session:    aicli ask -s mysession \"hello\""
echo "  5. Interactive REPL: aicli repl"
echo "  6. Full TUI:         aicli tui"
echo "  7. Session graph:    aicli graph"
echo "  8. Export session:   aicli export mysession > out.md"
echo "  9. Run tests:        python -m pytest tests/ -v"
echo ""
echo "Provider failover order: Groq → OpenRouter → Gemini → Mistral → Ollama"
echo ""
echo "To retract: ./retract.sh"
echo ""
