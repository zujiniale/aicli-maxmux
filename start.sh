#!/usr/bin/env bash
# start.sh — aicli tui (left 3/4) | graph terminal (top-right 1/4) | firefox (bottom-right 1/4)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -f "$SCRIPT_DIR/venv/bin/activate" ]; then
    source "$SCRIPT_DIR/venv/bin/activate"
fi

ACTIVATE="source $SCRIPT_DIR/venv/bin/activate 2>/dev/null"

if ! command -v wmctrl &>/dev/null; then
    echo "◆ Installing wmctrl..."
    sudo apt-get install -y wmctrl -qq
fi

# Screen size
SCREEN_W=$(xdpyinfo 2>/dev/null | awk '/dimensions/{print $2}' | cut -dx -f1)
SCREEN_H=$(xdpyinfo 2>/dev/null | awk '/dimensions/{print $2}' | cut -dx -f2)
SCREEN_W=${SCREEN_W:-1920}
SCREEN_H=${SCREEN_H:-1080}

# Layout math
TUI_W=$(( SCREEN_W * 3 / 4 ))   # left 3/4
QTR_W=$(( SCREEN_W / 4 ))        # right 1/4
HALF_H=$(( SCREEN_H / 2 ))       # top/bottom split

echo "◆ Starting aicli...  (${SCREEN_W}x${SCREEN_H})"
echo "  TUI    → left 3/4   (0,0  ${TUI_W}x${SCREEN_H})"
echo "  Graph  → top-right  (${TUI_W},0  ${QTR_W}x${HALF_H})"
echo "  Firefox→ bot-right  (${TUI_W},${HALF_H}  ${QTR_W}x${HALF_H})"

# ── 1. Launch TUI ─────────────────────────────────────────────────────────────
gnome-terminal \
    --title="aicli — TUI" \
    -- bash --login -c "cd $SCRIPT_DIR && $ACTIVATE && aicli tui; exec bash" &

sleep 1.0

# ── 2. Launch Graph terminal ──────────────────────────────────────────────────
gnome-terminal \
    --title="aicli — Graph" \
    -- bash --login -c "cd $SCRIPT_DIR && $ACTIVATE && aicli graph; exec bash" &

sleep 1.5

# ── 3. Open Firefox to graph URL ─────────────────────────────────────────────
if command -v firefox &>/dev/null; then
    firefox "http://localhost:7337" &
else
    xdg-open "http://localhost:7337" &
fi

sleep 2.0

# ── 4. Position all three windows ────────────────────────────────────────────
# TUI — left 3/4, full height
wmctrl -r "aicli — TUI" -b remove,maximized_vert,maximized_horz
wmctrl -r "aicli — TUI" -e 0,0,0,$TUI_W,$SCREEN_H

# Graph terminal — top-right 1/4
wmctrl -r "aicli — Graph" -b remove,maximized_vert,maximized_horz
wmctrl -r "aicli — Graph" -e 0,$TUI_W,0,$QTR_W,$HALF_H

# Firefox — bottom-right 1/4
wmctrl -r "Mozilla Firefox" -b remove,maximized_vert,maximized_horz
wmctrl -r "Mozilla Firefox" -e 0,$TUI_W,$HALF_H,$QTR_W,$HALF_H

echo "  Done. Graph → http://localhost:7337"
