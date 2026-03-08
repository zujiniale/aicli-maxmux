#!/usr/bin/env bash
# start.sh — launch aicli tui + aicli graph side by side

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Activate venv if present
if [ -f "$SCRIPT_DIR/venv/bin/activate" ]; then
    source "$SCRIPT_DIR/venv/bin/activate"
fi

# Try terminals in order of preference
launch() {
    local cmd="$1"
    local title="$2"
    if command -v kitty &>/dev/null; then
        kitty --title "$title" -- bash -c "$cmd; exec bash" &
    elif command -v alacritty &>/dev/null; then
        alacritty --title "$title" -e bash -c "$cmd; exec bash" &
    elif command -v gnome-terminal &>/dev/null; then
        gnome-terminal --title="$title" -- bash -c "$cmd; exec bash" &
    elif command -v xterm &>/dev/null; then
        xterm -title "$title" -e bash -c "$cmd; exec bash" &
    else
        echo "No terminal emulator found. Install kitty, alacritty, gnome-terminal, or xterm."
        exit 1
    fi
}

echo "◆ Starting aicli..."
launch "aicli tui" "aicli — TUI"
sleep 0.3
launch "aicli graph" "aicli — Graph"

echo "  TUI   → terminal window"
echo "  Graph → http://localhost:7337"
echo "  Both will open momentarily."
