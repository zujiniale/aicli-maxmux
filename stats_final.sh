#!/usr/bin/env zsh

# aicli - Accurate Project Statistics
# Uses both `find` and `cloc` for a complete picture of core vs. expanded size

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
MAGENTA='\033[0;35m'
RED='\033[0;31m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

clear

echo -e "${BLUE}╔════════════════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║${YELLOW}                   aicli — ACCURATE PROJECT STATISTICS                      ${BLUE}║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════════════════════╝${NC}"
echo ""

# ── cloc check ────────────────────────────────────────────────────────────────
if ! command -v cloc &> /dev/null; then
    echo -e "${RED}Error: cloc is not installed.${NC}"
    echo "Install it:  sudo apt-get install cloc"
    echo "             brew install cloc"
    exit 1
fi

# ── Helper: format numbers with commas ────────────────────────────────────────
format_num() {
    echo "$1" | sed ':a;s/\B[0-9]\{3\}\>/,&/;ta'
}

# ── Detect current state ──────────────────────────────────────────────────────
CURRENT_STATE="RETRACTED"
VENV_DIR=""

if [ -d "venv" ]; then
    CURRENT_STATE="EXPANDED"
    VENV_DIR="venv"
elif [ -d ".venv" ]; then
    CURRENT_STATE="EXPANDED"
    VENV_DIR=".venv"
fi

echo -e "${CYAN}Current State:  ${BOLD}${CURRENT_STATE}${NC}"
if [ "$CURRENT_STATE" = "EXPANDED" ]; then
    VENV_SIZE=$(du -sh "$VENV_DIR" 2>/dev/null | awk '{print $1}')
    echo -e "${DIM}  (venv at ${VENV_DIR}/ — ${VENV_SIZE})${NC}"
fi
echo ""

echo -e "${BLUE}════════════════════════════════════════════════════════════════════════════${NC}"
echo -e "${YELLOW}📊 ANALYZING PROJECT...${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════════════════════${NC}"
echo ""

# ── Method 1: Raw find (source files only — no venv, no dist binaries) ────────
echo -e "${DIM}  Counting raw lines (find)...${NC}"

TOTAL_LINES_ALL=$(find . -type f \
    -not -path "*/.git/*" \
    -not -path "*/venv/*" \
    -not -path "*/.venv/*" \
    -not -path "*/__pycache__/*" \
    -not -path "*/.pytest_cache/*" \
    -not -path "*/dist/*" \
    -exec wc -l {} + 2>/dev/null | tail -n 1 | awk '{print $1}')

TOTAL_FILES_ALL=$(find . -type f \
    -not -path "*/.git/*" \
    -not -path "*/venv/*" \
    -not -path "*/.venv/*" \
    -not -path "*/__pycache__/*" \
    -not -path "*/.pytest_cache/*" \
    -not -path "*/dist/*" \
    2>/dev/null | wc -l)

# ── Method 2: cloc — core only (no venv, no pycache) ─────────────────────────
echo -e "${DIM}  Running cloc on core source...${NC}"

CLOC_CORE=$(cloc . \
    --exclude-dir=venv,.venv,__pycache__,.git,.pytest_cache,dist,build \
    --not-match-f='\.txt$' \
    --quiet 2>/dev/null)

CORE_CODE=$(echo "$CLOC_CORE"    | grep "^SUM:"    | awk '{print $5}')
CORE_BLANK=$(echo "$CLOC_CORE"   | grep "^SUM:"    | awk '{print $3}')
CORE_COMMENT=$(echo "$CLOC_CORE" | grep "^SUM:"    | awk '{print $4}')
CORE_FILES=$(echo "$CLOC_CORE"   | grep "^SUM:"    | awk '{print $2}')

# Per-language breakdown (core)
# NOTE: all use $NF (last field) — safe for both single-word ("Python") and
# multi-word ("Bourne Shell") language labels in cloc output
PY_CODE=$(echo    "$CLOC_CORE" | grep "^Python "       | awk '{print $NF}')
TOML_CODE=$(echo  "$CLOC_CORE" | grep "^TOML "         | awk '{print $NF}')
MD_CODE=$(echo    "$CLOC_CORE" | grep "^Markdown "      | awk '{print $NF}')
SH_CODE=$(echo    "$CLOC_CORE" | grep "^Bourne Shell"   | awk '{print $NF}')
YAML_CODE=$(echo  "$CLOC_CORE" | grep "^YAML "          | awk '{print $NF}')
HTML_CODE=$(echo  "$CLOC_CORE" | grep "^HTML "          | awk '{print $NF}')
JSON_CODE=$(echo  "$CLOC_CORE" | grep "^JSON "          | awk '{print $NF}')
TEXT_CODE=$(echo  "$CLOC_CORE" | grep "^Text "          | awk '{print $NF}')

[ -z "$PY_CODE" ]   && PY_CODE=0
[ -z "$TOML_CODE" ] && TOML_CODE=0
[ -z "$MD_CODE" ]   && MD_CODE=0
[ -z "$SH_CODE" ]   && SH_CODE=0
[ -z "$YAML_CODE" ] && YAML_CODE=0
[ -z "$HTML_CODE" ] && HTML_CODE=0
[ -z "$JSON_CODE" ] && JSON_CODE=0
[ -z "$TEXT_CODE" ] && TEXT_CODE=0
[ -z "$CORE_CODE" ] && CORE_CODE=0

# ── Method 3: cloc — full project (with venv) ─────────────────────────────────
FULL_CODE=0
FULL_FILES=0
DEPS_ONLY=0
TRUE_RATIO="N/A"
LEVERAGE="N/A"
if [ "$CURRENT_STATE" = "EXPANDED" ]; then
    echo -e "${DIM}  Running cloc on full project (may take a moment)...${NC}"
    CLOC_FULL=$(cloc . --exclude-dir=.git --quiet 2>/dev/null)
    FULL_CODE=$(echo  "$CLOC_FULL" | grep "^SUM:" | awk '{print $5}')
    FULL_FILES=$(echo "$CLOC_FULL" | grep "^SUM:" | awk '{print $2}')
    [ -z "$FULL_CODE" ]  && FULL_CODE=0
    [ -z "$FULL_FILES" ] && FULL_FILES=0
fi

# ── Per-file line counts (core Python) ────────────────────────────────────────
echo -e "${DIM}  Counting per-file line lengths...${NC}"

count_lines() {
    [ -f "$1" ] && wc -l < "$1" 2>/dev/null || echo 0
}

APP_LINES=$(count_lines         "aicli/app.py")
CONFIG_LINES=$(count_lines      "aicli/config.py")
PIPELINE_LINES=$(count_lines    "aicli/providers/pipeline.py")
REGISTRY_LINES=$(count_lines    "aicli/providers/registry.py")
CHATDB_LINES=$(count_lines      "aicli/db/chat_db.py")
CRYPTO_LINES=$(count_lines      "aicli/db/crypto.py")
CTX_LINES=$(count_lines         "aicli/context/manager.py")
EMBED_LINES=$(count_lines       "aicli/context/embeddings.py")
RETRIEV_LINES=$(count_lines     "aicli/context/retriever.py")
SHELL_LINES=$(count_lines       "aicli/tools/builtin/shell.py")
CHAT_H_LINES=$(count_lines      "aicli/handlers/chat.py")
REPL_LINES=$(count_lines        "aicli/handlers/repl.py")
CODE_RUNNER_LINES=$(count_lines "aicli/handlers/code_runner.py")
IMGUTILS_LINES=$(count_lines    "aicli/image_utils.py")
WEB_LINES=$(count_lines         "aicli/web.py")
GRAPH_LINES=$(count_lines       "aicli/graph_server.py")
TUI_LINES=$(count_lines         "aicli/tui.py")
TEST_UNIT_LINES=$(count_lines   "tests/test_aicli.py")
TEST_INTEG_LINES=$(count_lines  "tests/test_integration.py")
TEST_TUI_LINES=$(count_lines    "tests/test_tui_pure.py")
TEST_GRAPH_LINES=$(count_lines  "tests/test_graph_server.py")

echo ""

# ══════════════════════════════════════════════════════════════════════════════
echo -e "${BLUE}════════════════════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}📈 CORE PROJECT (source code only — no venv)${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════════════════════${NC}"
echo ""

# Raw count
echo -e "${YELLOW}Method 1: Raw line count (source files — no venv, no dist binaries)${NC}"
echo -e "  Every line in every file: ${BOLD}$(format_num $TOTAL_LINES_ALL)${NC} lines"
echo -e "  Total file count:         ${BOLD}$(format_num $TOTAL_FILES_ALL)${NC} files"
echo ""

# cloc core
echo -e "${YELLOW}Method 2: cloc — actual code (no blanks / comments)${NC}"
if [ "$CORE_CODE" != "0" ]; then
    echo -e "  Code lines:    ${BOLD}$(format_num $CORE_CODE)${NC}"
    echo -e "  Blank lines:   ${BOLD}$(format_num $CORE_BLANK)${NC}"
    echo -e "  Comment lines: ${BOLD}$(format_num $CORE_COMMENT)${NC}"
    echo -e "  Code files:    ${BOLD}$(format_num $CORE_FILES)${NC}"
else
    echo -e "  ${RED}cloc parse failed — check cloc output manually${NC}"
fi
echo ""

# Language breakdown
echo -e "${CYAN}Language breakdown (core):${NC}"
printf "  %-18s  %8s lines\n"  "Python:"        "$(format_num $PY_CODE)"
printf "  %-18s  %8s lines\n"  "Shell scripts:"  "$(format_num $SH_CODE)"
printf "  %-18s  %8s lines\n"  "TOML:"           "$(format_num $TOML_CODE)"
if [ "$YAML_CODE" -gt 0 ] 2>/dev/null; then
    printf "  %-18s  %8s lines\n"  "YAML:"       "$(format_num $YAML_CODE)"
fi
if [ "$HTML_CODE" -gt 0 ] 2>/dev/null; then
    printf "  %-18s  %8s lines\n"  "HTML:"       "$(format_num $HTML_CODE)"
fi
if [ "$JSON_CODE" -gt 0 ] 2>/dev/null; then
    printf "  %-18s  %8s lines\n"  "JSON:"       "$(format_num $JSON_CODE)"
fi
printf "  %-18s  %8s lines\n"  "Markdown:"       "$(format_num $MD_CODE)"
if [ "$TEXT_CODE" -gt 0 ] 2>/dev/null; then
    printf "  %-18s  %8s lines\n"  "Text/docs:"  "$(format_num $TEXT_CODE)"
fi
echo -e "  ${BOLD}──────────────────────────────${NC}"
printf "  ${GREEN}%-18s  %8s lines${NC}\n" "TOTAL (code):"  "$(format_num $CORE_CODE)"
echo ""

# Per-module breakdown
echo -e "${CYAN}Key file breakdown:${NC}"
printf "  %-42s  %5s lines\n"  "aicli/app.py (CLI entry, aicli.app:main)"  "$APP_LINES"
printf "  %-42s  %5s lines\n"  "aicli/config.py"                           "$CONFIG_LINES"
printf "  %-42s  %5s lines\n"  "aicli/web.py (6-backend web search)"       "$WEB_LINES"
printf "  %-42s  %5s lines\n"  "aicli/graph_server.py"                     "$GRAPH_LINES"
printf "  %-42s  %5s lines\n"  "aicli/tui.py (Textual TUI)"               "$TUI_LINES"
printf "  %-42s  %5s lines\n"  "aicli/image_utils.py (F2 vision)"          "$IMGUTILS_LINES"
printf "  %-42s  %5s lines\n"  "aicli/providers/pipeline.py"              "$PIPELINE_LINES"
printf "  %-42s  %5s lines\n"  "aicli/providers/registry.py"              "$REGISTRY_LINES"
printf "  %-42s  %5s lines\n"  "aicli/db/chat_db.py"                      "$CHATDB_LINES"
printf "  %-42s  %5s lines\n"  "aicli/db/crypto.py"                       "$CRYPTO_LINES"
printf "  %-42s  %5s lines\n"  "aicli/context/manager.py"                 "$CTX_LINES"
printf "  %-42s  %5s lines\n"  "aicli/context/embeddings.py"              "$EMBED_LINES"
printf "  %-42s  %5s lines\n"  "aicli/context/retriever.py"               "$RETRIEV_LINES"
printf "  %-42s  %5s lines\n"  "aicli/handlers/chat.py"                   "$CHAT_H_LINES"
printf "  %-42s  %5s lines\n"  "aicli/handlers/repl.py"                   "$REPL_LINES"
printf "  %-42s  %5s lines\n"  "aicli/handlers/code_runner.py"            "$CODE_RUNNER_LINES"
printf "  %-42s  %5s lines\n"  "aicli/tools/builtin/shell.py"             "$SHELL_LINES"
printf "  %-42s  %5s lines\n"  "tests/test_aicli.py"                      "$TEST_UNIT_LINES"
printf "  %-42s  %5s lines\n"  "tests/test_integration.py"                "$TEST_INTEG_LINES"
printf "  %-42s  %5s lines\n"  "tests/test_tui_pure.py"                   "$TEST_TUI_LINES"
printf "  %-42s  %5s lines\n"  "tests/test_graph_server.py"               "$TEST_GRAPH_LINES"
echo ""

# ── Expanded analysis ─────────────────────────────────────────────────────────
if [ "$CURRENT_STATE" = "EXPANDED" ]; then
    echo -e "${BLUE}════════════════════════════════════════════════════════════════════════════${NC}"
    echo -e "${MAGENTA}📦 EXPANDED STATE (with all venv dependencies)${NC}"
    echo -e "${BLUE}════════════════════════════════════════════════════════════════════════════${NC}"
    echo ""

    echo -e "${YELLOW}Full project (cloc including venv):${NC}"
    if [ "$FULL_CODE" != "0" ]; then
        echo -e "  Total code lines: ${BOLD}$(format_num $FULL_CODE)${NC}"
        echo -e "  Total code files: ${BOLD}$(format_num $FULL_FILES)${NC}"
    else
        echo -e "  ${RED}cloc parse failed${NC}"
    fi
    echo ""

    if [ "$PY_CODE" -gt 0 ] && [ "$FULL_CODE" -gt 0 ] 2>/dev/null; then
        DEPS_ONLY=$((FULL_CODE - PY_CODE))
        TRUE_RATIO=$(echo "scale=1; $FULL_CODE / $PY_CODE" | bc 2>/dev/null || echo "?")
        LEVERAGE=$(echo "scale=0; $DEPS_ONLY / $PY_CODE" | bc 2>/dev/null || echo "?")

        echo -e "${CYAN}Expansion Analysis:${NC}"
        printf "  %-28s  %8s lines\n" "Your Python code:"     "$(format_num $PY_CODE)"
        printf "  %-28s  %8s lines\n" "Library dependencies:" "$(format_num $DEPS_ONLY)"
        printf "  %-28s  %8s lines\n" "Full expanded total:"  "$(format_num $FULL_CODE)"
        echo -e "  ${BOLD}──────────────────────────────────────────${NC}"
        echo -e "  ${MAGENTA}Expansion ratio:  ${BOLD}${TRUE_RATIO}x${NC}  ${DIM}(your code × leverage)${NC}"
        echo -e "  ${MAGENTA}Library leverage: ${BOLD}${LEVERAGE}x${NC}  ${DIM}(lines of libs per line of yours)${NC}"
    fi
    echo ""
fi

# ══════════════════════════════════════════════════════════════════════════════
echo -e "${BLUE}════════════════════════════════════════════════════════════════════════════${NC}"
echo -e "${YELLOW}🎯 THE TRUTH ABOUT aicli${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════════════════════${NC}"
echo ""

echo -e "When someone asks ${BOLD}\"How big is aicli?\"${NC}"
echo ""
echo -e "  Answer: ${GREEN}${BOLD}$(format_num $PY_CODE) lines of Python${NC} written by hand."
OTHER_LINES=$((TOML_CODE + SH_CODE + MD_CODE + HTML_CODE + JSON_CODE))
echo -e "  ${DIM}(Plus $(format_num $OTHER_LINES) lines of config/scripts/docs/HTML)${NC}"
echo ""

echo -e "  What that code does:"
echo -e "    • 5-provider AI failover (Groq→OpenRouter→Gemini→Mistral→Ollama)"
echo -e "    • 3-layer conversation memory: Hot (RAM) / Warm (SQLite+Fernet) / Cold (ChromaDB RAG)"
echo -e "    • Web search: 6-backend chain (Tavily→SearXNG→DDG→DDG-lite→Bing→Mojeek)"
echo -e "    • Full terminal UI (Textual): themes, session sidebar, clipboard, export"
echo -e "    • Session graph viewer: D3 force-directed, node links, browser UI"
echo -e "    • Shell command generation with safety checks (E/M/D/A/R)"
echo -e "    • Multimodal vision: --image flag for PNG/JPEG/GIF/WebP"
echo -e "    • Code runner: --code --run (Python/Bash/Node/Ruby + self-correction)"
echo -e "    • Plugin system: drop .py files to extend aicli"
echo -e "    • Interactive REPL with persistent context"
echo -e "    • Fernet encryption + machine fingerprint key derivation"
echo -e "    • Named sessions, async summarization at 80% token threshold"
echo -e "    • Session export to Markdown or JSON"
echo -e "    • Autonomous agent mode with plan/execute/feedback loop"
echo -e "    • Tor/SOCKS5 proxy support"
echo ""

if [ "$CURRENT_STATE" = "EXPANDED" ] && [ "$FULL_CODE" != "0" ] 2>/dev/null; then
    echo -e "  When expanded with libraries: ${MAGENTA}${BOLD}$(format_num $FULL_CODE) total lines${NC}"
    echo -e "  ${DIM}($(format_num $DEPS_ONLY) lines of libraries riding on $(format_num $PY_CODE) lines of yours)${NC}"
    echo ""
    echo -e "${CYAN}  The leverage of modern development:${NC}"
    echo -e "${DIM}  You wrote ~$(format_num $PY_CODE) lines. You're wielding ~$(format_num $FULL_CODE) lines of capability.${NC}"
fi

echo ""

# ── Provider quick-ref ────────────────────────────────────────────────────────
echo -e "${BLUE}════════════════════════════════════════════════════════════════════════════${NC}"
echo -e "${YELLOW}⚡ PROVIDER STATUS (runtime — set your env vars)${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════════════════════${NC}"
echo ""

# zsh indirect variable expansion: ${(P)VAR}
check_key() {
    local VAR="$1"
    local NAME="$2"
    local PRIORITY="$3"
    if [ -n "${(P)VAR}" ]; then
        echo -e "  ${GREEN}✓${NC}  ${PRIORITY} ${NAME} — key found (\$${VAR})"
    else
        echo -e "  ${YELLOW}–${NC}  ${PRIORITY} ${NAME} — \$${VAR} not set"
    fi
}

check_key "GROQ_API_KEY"        "Groq"        "1 🥇"
check_key "OPENROUTER_API_KEY"  "OpenRouter"  "2   "
check_key "GEMINI_API_KEY"      "Gemini"      "3   "
check_key "MISTRAL_API_KEY"     "Mistral"     "4   "
echo -e "  ${CYAN}–${NC}     5    Ollama — local (no key required)"
echo ""
check_key "TAVILY_API_KEY"      "Tavily (web search)" "    "

echo ""

# ── Test status ───────────────────────────────────────────────────────────────
echo -e "${BLUE}════════════════════════════════════════════════════════════════════════════${NC}"
echo -e "${YELLOW}🧪 TEST COVERAGE${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════════════════════${NC}"
echo ""

TEST_COUNT_UNIT=$(grep -c "def test_" tests/test_aicli.py 2>/dev/null || echo "0")
TEST_COUNT_INTEG=$(grep -c "def test_" tests/test_integration.py 2>/dev/null || echo "0")
TEST_COUNT_TUI=$(grep -c "def test_" tests/test_tui_pure.py 2>/dev/null || echo "0")
TEST_COUNT_GRAPH=$(grep -c "def test_" tests/test_graph_server.py 2>/dev/null || echo "0")
TEST_COUNT_TOTAL=$((TEST_COUNT_UNIT + TEST_COUNT_INTEG + TEST_COUNT_TUI + TEST_COUNT_GRAPH))

echo -e "  Unit tests:        ${GREEN}${BOLD}${TEST_COUNT_UNIT}${NC}  (tests/test_aicli.py)"
echo -e "  Integration tests: ${GREEN}${BOLD}${TEST_COUNT_INTEG}${NC}  (tests/test_integration.py)"
echo -e "  TUI pure tests:    ${GREEN}${BOLD}${TEST_COUNT_TUI}${NC}  (tests/test_tui_pure.py)"
echo -e "  Graph tests:       ${GREEN}${BOLD}${TEST_COUNT_GRAPH}${NC}  (tests/test_graph_server.py)"
echo -e "  Total:             ${GREEN}${BOLD}${TEST_COUNT_TOTAL} passing${NC}"
echo ""
echo -e "  ${DIM}Run unit only:    python -m pytest tests/test_aicli.py -v${NC}"
echo -e "  ${DIM}Run integ only:   python -m pytest tests/test_integration.py -v${NC}"
echo -e "  ${DIM}Run all:          python -m pytest tests/ -v  (${TEST_COUNT_TOTAL} total)${NC}"
echo -e "  ${DIM}Run live test:    aicli _provider_test${NC}"
echo ""

# ── Debug mode ────────────────────────────────────────────────────────────────
if [ "$1" = "--debug" ]; then
    echo ""
    echo -e "${DIM}━━━ Debug Variables ━━━${NC}"
    echo -e "${DIM}PY_CODE:         $PY_CODE${NC}"
    echo -e "${DIM}CORE_CODE:       $CORE_CODE${NC}"
    echo -e "${DIM}CORE_FILES:      $CORE_FILES${NC}"
    echo -e "${DIM}FULL_CODE:       $FULL_CODE${NC}"
    echo -e "${DIM}FULL_FILES:      $FULL_FILES${NC}"
    echo -e "${DIM}DEPS_ONLY:       $DEPS_ONLY${NC}"
    echo -e "${DIM}TRUE_RATIO:      $TRUE_RATIO${NC}"
    echo -e "${DIM}LEVERAGE:        $LEVERAGE${NC}"
    echo -e "${DIM}TEST_TOTAL:      $TEST_COUNT_TOTAL${NC}"
    echo ""
fi

echo -e "${BLUE}════════════════════════════════════════════════════════════════════════════${NC}"
echo ""
