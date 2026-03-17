#!/usr/bin/env bash
# release.sh — full aicli-maxmux release pipeline
#
# Usage:
#   ./release.sh 1.6.3              # bump, test, build, tag, push, publish
#   ./release.sh 1.6.3 --dry-run   # preview everything, nothing is written or uploaded
#   ./release.sh --current          # print current version and exit
#
# What it does:
#   1. Validates you're on main, working tree is clean
#   2. Runs the full test suite (pytest + run_tests.py)
#   3. Bumps version across all files via bump_version.py
#   4. Builds the wheel + sdist
#   5. Runs twine check
#   6. Commits, tags, and pushes to git
#   7. Uploads to PyPI
#
# Requirements:
#   pip install build twine
#   git remote named "origin" pointing to your repo

set -euo pipefail

# ── Colours ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

ok()   { echo -e "${GREEN}✓${RESET}  $*"; }
warn() { echo -e "${YELLOW}⚠${RESET}  $*"; }
err()  { echo -e "${RED}✗  $*${RESET}"; exit 1; }
info() { echo -e "${CYAN}▶${RESET}  $*"; }
sep()  { echo -e "\n${BOLD}────────────────────────────────────────${RESET}"; }

# ── Args ─────────────────────────────────────────────────────────────────────
DRY_RUN=0
NEW_VERSION=""

for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=1 ;;
        --current)
            python bump_version.py --current
            exit 0
            ;;
        --help|-h)
            head -12 "$0" | grep "^#" | sed 's/^# \?//'
            exit 0
            ;;
        *)
            NEW_VERSION="$arg"
            ;;
    esac
done

if [[ -z "$NEW_VERSION" ]]; then
    echo "Usage: ./release.sh <version> [--dry-run]"
    echo "Current version: $(python bump_version.py --current)"
    exit 1
fi

# Validate semver format
if ! [[ "$NEW_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    err "Version must be x.y.z format, got: $NEW_VERSION"
fi

CURRENT_VERSION=$(python bump_version.py --current)
PACKAGE_NAME="aicli_maxmux-${NEW_VERSION}"

sep
echo -e "${BOLD}  aicli-maxmux release: ${CYAN}${CURRENT_VERSION}${RESET} → ${BOLD}${GREEN}${NEW_VERSION}${RESET}"
[[ $DRY_RUN -eq 1 ]] && echo -e "  ${YELLOW}DRY RUN — nothing will be written or uploaded${RESET}"
sep

# ── Step 1: Git checks ────────────────────────────────────────────────────────
info "Checking git state..."

BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [[ "$BRANCH" != "main" ]]; then
    warn "Not on main branch (on: $BRANCH) — continue? [y/N]"
    read -r confirm
    [[ "$confirm" =~ ^[yY]$ ]] || exit 1
fi

if ! git diff --quiet || ! git diff --cached --quiet; then
    warn "Working tree has uncommitted changes. They will be included in the release commit."
    git status --short
    echo ""
fi

ok "Git state checked (branch: $BRANCH)"

# ── Pre-flight: verify mcp_server.py fallback matches current version ─────────
info "Checking mcp_server.py version fallback..."
MCP_FILE="aicli/handlers/mcp_server.py"
if [[ -f "$MCP_FILE" ]]; then
    MCP_VER=$(grep 'SERVER_VERSION_IMPORT\s*=' "$MCP_FILE" | grep -o '"[0-9]*\.[0-9]*\.[0-9]*"' | tr -d '"' || true)
    if [[ "$MCP_VER" != "$CURRENT_VERSION" && "$MCP_VER" != "$NEW_VERSION" ]]; then
        warn "mcp_server.py fallback is '$MCP_VER' — expected '$CURRENT_VERSION' or '$NEW_VERSION'"
        warn "Auto-fixing..."
        if [[ $DRY_RUN -eq 0 ]]; then
            sed -i "s/SERVER_VERSION_IMPORT = \"[0-9]*\.[0-9]*\.[0-9]*\"/SERVER_VERSION_IMPORT = \"${NEW_VERSION}\"/" "$MCP_FILE"
            ok "mcp_server.py fallback updated to ${NEW_VERSION}"
        else
            warn "DRY RUN: would fix mcp_server.py fallback to ${NEW_VERSION}"
        fi
    else
        ok "mcp_server.py fallback is correct (${MCP_VER})"
    fi
else
    warn "mcp_server.py not found at ${MCP_FILE} — skipping check"
fi

# ── Step 2: Run test suite ────────────────────────────────────────────────────
sep
info "Running pytest (non-slow)..."
if [[ $DRY_RUN -eq 0 ]]; then
    pytest tests/ -q -m "not slow" || err "pytest failed — fix tests before releasing"
    ok "pytest passed"
else
    warn "DRY RUN: skipping pytest"
fi

info "Running run_tests.py static checks..."
if [[ $DRY_RUN -eq 0 ]]; then
    python3 run_tests.py --time || err "run_tests.py failed — fix checks before releasing"
    ok "run_tests.py passed"
else
    warn "DRY RUN: skipping run_tests.py"
fi

# ── Step 3: Bump version ──────────────────────────────────────────────────────
sep
info "Bumping version: ${CURRENT_VERSION} → ${NEW_VERSION}..."
if [[ $DRY_RUN -eq 1 ]]; then
    python bump_version.py "$NEW_VERSION" --dry-run
else
    python bump_version.py "$NEW_VERSION"
    ok "Version bumped to ${NEW_VERSION}"
fi

# ── Step 4: Build ─────────────────────────────────────────────────────────────
sep
info "Building wheel + sdist..."
rm -rf dist/ build/

if [[ $DRY_RUN -eq 0 ]]; then
    python -m build --quiet
    ok "Built: $(ls dist/)"
else
    warn "DRY RUN: skipping build"
fi

# ── Step 5: Twine check ───────────────────────────────────────────────────────
info "Running twine check..."
if [[ $DRY_RUN -eq 0 ]]; then
    twine check dist/${PACKAGE_NAME}* || err "twine check failed"
    ok "twine check passed"
else
    warn "DRY RUN: skipping twine check"
fi

# ── Step 6: Git commit + tag + push ──────────────────────────────────────────
sep
info "Committing and tagging v${NEW_VERSION}..."
if [[ $DRY_RUN -eq 0 ]]; then
    git add -A
    git commit -m "chore: bump version to ${NEW_VERSION}"
    git tag "v${NEW_VERSION}"
    git push origin main
    git push origin "v${NEW_VERSION}"
    ok "Pushed to git — tagged v${NEW_VERSION}"
else
    warn "DRY RUN: would run:"
    echo "    git add -A"
    echo "    git commit -m 'chore: bump version to ${NEW_VERSION}'"
    echo "    git tag v${NEW_VERSION}"
    echo "    git push origin main && git push origin v${NEW_VERSION}"
fi

# ── Step 7: PyPI upload ───────────────────────────────────────────────────────
sep
info "Uploading to PyPI..."
if [[ $DRY_RUN -eq 0 ]]; then
    twine upload dist/${PACKAGE_NAME}*
    ok "Published to PyPI: pip install aicli-maxmux==${NEW_VERSION}"
else
    warn "DRY RUN: would run: twine upload dist/${PACKAGE_NAME}*"
fi

# ── Done ──────────────────────────────────────────────────────────────────────
sep
if [[ $DRY_RUN -eq 1 ]]; then
    echo -e "\n${YELLOW}  Dry run complete — re-run without --dry-run to publish${RESET}\n"
else
    echo -e "\n${GREEN}${BOLD}  ✓ aicli-maxmux v${NEW_VERSION} released successfully!${RESET}"
    echo -e "  ${CYAN}pip install --upgrade aicli-maxmux${RESET}"
    echo -e "  ${CYAN}https://pypi.org/project/aicli-maxmux/${NEW_VERSION}/${RESET}\n"
fi
