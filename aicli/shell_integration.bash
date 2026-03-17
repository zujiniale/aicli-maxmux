# aicli shell integration for bash
# Install: aicli config install-shell --shell bash
# Or manually: source ~/.config/aicli/shell_integration.bash
#
# Hotkeys:
#   Ctrl+G  — generate a shell command from buffer text or inline prompt.
#             Automatically captures last 20 terminal lines as context so
#             aicli can see what you were just doing (context-aware mode).
#   Ctrl+E  — error-fix mode: captures the last failed command + its output
#             and asks aicli to suggest a fix, no typing required.
#
# Change hotkey after sourcing: bind -x '"\C-l": _aicli_hotkey'  (Ctrl+L)

# ── Internal: capture last N lines of terminal scrollback ─────────────────────
_aicli_terminal_context() {
    local lines="${1:-20}"
    local ctx=""

    # Prefer tmux capture-pane for accurate scrollback (includes command output)
    if [[ -n "$TMUX" ]]; then
        ctx=$(tmux capture-pane -p -S -"$lines" 2>/dev/null | grep -v '^$' | tail -"$lines")
    fi

    # Fallback: recent shell history lines (commands only, no output)
    if [[ -z "$ctx" ]]; then
        ctx=$(history "$lines" 2>/dev/null | awk '{$1=""; print $0}' | tail -"$lines")
    fi

    echo "$ctx"
}

# ── Ctrl+G: context-aware command generation ──────────────────────────────────
_aicli_hotkey() {
    local prompt_text="$READLINE_LINE"

    if [[ -z "$prompt_text" ]]; then
        # Empty buffer — show inline prompt (hint: Ctrl+E auto-fixes last failed command)
        echo ""
        read -r -p "aicli> " prompt_text </dev/tty
    fi

    if [[ -n "$prompt_text" ]]; then
        local result
        local term_ctx
        term_ctx=$(_aicli_terminal_context 20)

        if [[ -n "$term_ctx" ]]; then
            result=$(aicli ask --shell --dry-run --lite \
                --terminal-context "$term_ctx" \
                "$prompt_text" 2>/dev/null | tail -n 1)
        else
            result=$(aicli ask --shell --dry-run --lite "$prompt_text" 2>/dev/null | tail -n 1)
        fi

        if [[ -n "$result" ]]; then
            READLINE_LINE="$result"
            READLINE_POINT=${#result}
        fi
    fi
}

# ── Ctrl+E: error-fix mode — auto-diagnose last failed command ────────────────
_aicli_fix() {
    local last_cmd
    last_cmd=$(history 1 | awk '{$1=""; print $0}' | sed 's/^[[:space:]]*//')

    if [[ -z "$last_cmd" ]]; then
        echo "aicli: no previous command found"
        return
    fi

    local term_ctx
    term_ctx=$(_aicli_terminal_context 30)

    # Build the fix prompt. tmux context contains actual error output so
    # the AI sees both the command AND the failure message automatically.
    local fix_prompt="Fix this failed command: ${last_cmd}"
    local result

    if [[ -n "$term_ctx" ]]; then
        result=$(aicli ask --shell --dry-run --lite \
            --terminal-context "$term_ctx" \
            "$fix_prompt" 2>/dev/null | tail -n 1)
    else
        result=$(aicli ask --shell --dry-run --lite "$fix_prompt" 2>/dev/null | tail -n 1)
    fi

    if [[ -n "$result" ]]; then
        READLINE_LINE="$result"
        READLINE_POINT=${#result}
    else
        echo "aicli: could not generate fix"
    fi
}

bind -x '"\C-g": _aicli_hotkey'
bind -x '"\C-e": _aicli_fix'

# ── Ctrl+I: inline next-command suggestion ────────────────────────────────────
# Suggests the contextually correct NEXT command based on what's on screen.
# Different from Ctrl+G: you don't type a prompt — it reads the terminal state
# and proposes the logical next step (build → run, status → add/commit, etc.)
#
# Note: Ctrl+I is Tab in many terminals. If Tab completion breaks after install,
# rebind to a different key:  bind -x '"\C-n": _aicli_next'  (Ctrl+N)
_aicli_next() {
    local term_ctx
    term_ctx=$(_aicli_terminal_context 30)

    if [[ -z "$term_ctx" ]]; then
        echo "aicli: no terminal context available (use tmux for best results)"
        return
    fi

    local next_prompt="Given this terminal context, what is the logical next shell command to run? Output ONLY the command, nothing else."
    local result

    if [[ -n "$term_ctx" ]]; then
        result=$(aicli ask --shell --dry-run --lite \
            --terminal-context "$term_ctx" \
            "$next_prompt" 2>/dev/null | tail -n 1)
    else
        result=$(aicli ask --shell --dry-run --lite "$next_prompt" 2>/dev/null | tail -n 1)
    fi

    if [[ -n "$result" ]]; then
        READLINE_LINE="$result"
        READLINE_POINT=${#result}
    else
        echo "aicli: could not suggest next command"
    fi
}

# Ctrl+I = Tab in many terminals. Use Ctrl+N as safe fallback if needed.
# To change: replace "\C-i" with "\C-n" below.
bind -x '"\C-i": _aicli_next'   # Ctrl+I — inline next-command suggestion

# ── Ctrl+L: multi-step chain generation ──────────────────────────────────────
# ShellGPT equivalent: Ctrl+L generates a multi-step command chain from the
# buffer text (or an inline prompt if buffer is empty).
#
# Better than ShellGPT: shows [N/total] progress, Y/n per step, halts on fail.
#
# Usage: type a task, press Ctrl+L — aicli generates and runs a numbered
# sequence of shell commands, confirming each before execution.
#   Example: type "create nginx container mounting index.html from current folder"
#            press Ctrl+L → [1/3] touch index.html  [Y/n]
#                         → [2/3] echo "<h1>hello</h1>" > index.html  [Y/n]
#                         → [3/3] docker run -d -p 80:80 ...  [Y/n]
#
# NOTE: Ctrl+L clears the screen in many terminals. Rebind if needed:
#   bind -x '"\C-\e": _aicli_chain'   # Alt+L safe alternative
# To restore clear-screen: bind -x '"\C-l": clear'
_aicli_chain() {
    local prompt_text="$READLINE_LINE"

    if [[ -z "$prompt_text" ]]; then
        echo ""
        read -r -p "aicli chain> " prompt_text </dev/tty
    fi

    if [[ -n "$prompt_text" ]]; then
        READLINE_LINE=""
        # Run chain in foreground so user can interact with Y/n prompts
        aicli cmd --chain "$prompt_text"
    fi
}

bind -x '"\C-l": _aicli_chain'   # Ctrl+L — multi-step chain (ShellGPT parity)
