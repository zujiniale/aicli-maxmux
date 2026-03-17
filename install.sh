#!/usr/bin/env bash
# aicli — one-liner installer
# Usage: bash install.sh
# Or:    curl -sSL https://raw.githubusercontent.com/YOUR_USER/aicli/main/install.sh | bash

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${YELLOW}Installing aicli-maxmux...${NC}"
echo ""

# Check Python version
PYTHON=$(command -v python3 || command -v python || true)
if [[ -z "$PYTHON" ]]; then
    echo "✗ Python 3.11+ is required. Install from https://python.org"
    exit 1
fi

PY_VERSION=$($PYTHON -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=$($PYTHON -c "import sys; print(sys.version_info.major)")
PY_MINOR=$($PYTHON -c "import sys; print(sys.version_info.minor)")

if [[ "$PY_MAJOR" -lt 3 ]] || [[ "$PY_MAJOR" -eq 3 && "$PY_MINOR" -lt 11 ]]; then
    echo "✗ Python 3.11+ required (found $PY_VERSION)"
    exit 1
fi

echo -e "  ${GREEN}✓${NC} Python $PY_VERSION"

# Detect install mode
MODE="${1:-full}"

if [[ "$MODE" == "lite" ]]; then
    echo -e "  Installing ${CYAN}lite${NC} (no RAG, no TUI, ~20MB)..."
    pip install "aicli-maxmux[lite]" --quiet
    echo -e "  ${GREEN}✓${NC} aicli-lite installed"
    echo ""
    echo -e "${GREEN}Done!${NC} Run: aicli-lite ask \"hello\""
else
    echo -e "  Installing ${CYAN}full${NC} (all features, ~468MB with deps)..."
    pip install "aicli-maxmux[all]" --quiet
    echo -e "  ${GREEN}✓${NC} aicli installed"
    echo ""
    echo -e "${GREEN}Done!${NC} Next steps:"
    echo ""
    echo "  aicli setup                   ← configure API keys interactively"
    echo "  aicli ask \"hello\"             ← test it"
    echo "  aicli cmd \"list large files\"  ← quick shell command"
    echo "  aicli config install-shell    ← add Ctrl+G hotkey to your shell"
    echo "  aicli tui                     ← full terminal UI"
    echo ""
    echo "  Lite mode (minimal footprint):"
    echo "  bash install.sh lite          ← installs aicli-lite (~20MB)"
fi
