#!/usr/bin/env bash
# run_tests.sh — Run the full aicli test suite
#
# Usage:
#   ./run_tests.sh              # run all tests
#   ./run_tests.sh -k graph     # filter by name
#   ./run_tests.sh -x           # stop on first failure
#   ./run_tests.sh --cov        # with coverage report
#   ./run_tests.sh --fast       # skip slow integration tests
#   ./run_tests.sh --new        # run only the new tests (graph + tui_pure)
#
# Expected: 190+ tests passing
#
# Layout:
#   tests/
#     conftest.py           ← shared fixtures (merged)
#     test_aicli.py         ← 82 tests (core: tokens, DB, context, shell, plugins…)
#     test_integration.py   ← 15 tests (providers, failover, session resume…)
#     test_graph_server.py  ← 33 tests (HTTP server, load_sessions, links…)
#     test_tui_pure.py      ← 60 tests (themes, CSS, keys, clipboard…)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Activate venv ─────────────────────────────────────────────────────────────
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
fi

# ── Parse args ────────────────────────────────────────────────────────────────
COV=0
FAST=0
NEW=0
EXTRA_ARGS=()

for arg in "$@"; do
    case "$arg" in
        --cov)   COV=1 ;;
        --fast)  FAST=1 ;;
        --new)   NEW=1 ;;
        *)       EXTRA_ARGS+=("$arg") ;;
    esac
done

# ── Build pytest command ──────────────────────────────────────────────────────
CMD=(python -m pytest)

if [ "$NEW" -eq 1 ]; then
    CMD+=(tests/test_graph_server.py tests/test_tui_pure.py)
    echo "◆ Running new tests only (graph_server + tui_pure)"
else
    CMD+=(tests/)
    echo "◆ Running full test suite"
fi

CMD+=(-v --tb=short)

if [ "$FAST" -eq 1 ]; then
    CMD+=(-m "not slow" --ignore=tests/test_integration.py)
    echo "  Mode: fast (skipping integration tests)"
fi

if [ "$COV" -eq 1 ]; then
    CMD+=(--cov=aicli --cov-report=term-missing --cov-report=html:htmlcov)
    echo "  Coverage: ON (report → htmlcov/index.html)"
fi

if [ ${#EXTRA_ARGS[@]} -gt 0 ]; then
    CMD+=("${EXTRA_ARGS[@]}")
fi

# ── Run ───────────────────────────────────────────────────────────────────────
echo ""
echo "  ${CMD[*]}"
echo ""

START=$(date +%s)

"${CMD[@]}"
EXIT_CODE=$?

END=$(date +%s)
ELAPSED=$((END - START))

echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo "  ✓ All tests passed in ${ELAPSED}s"
    if [ "$COV" -eq 1 ]; then
        echo "  ◆ Coverage report → htmlcov/index.html"
    fi
else
    echo "  ✗ Tests failed (exit $EXIT_CODE)"
fi

exit $EXIT_CODE
