# aicli shell integration for zsh
# Install: aicli config install-shell --shell zsh
# Or manually: source ~/.config/aicli/shell_integration.zsh
#
# Hotkeys:
#   Ctrl+G  — generate a shell command from buffer text or inline prompt
#             Automatically captures last 20 terminal lines as context so
#             aicli can see what you were just doing (context-aware mode).
#   Ctrl+E  — error-fix mode: captures the last failed command + its output
#             and asks aicli to suggest a fix, no typing required.
#
# Change hotkey: bindkey '^L' _aicli_hotkey_widget  (Ctrl+L)

# ── Internal: capture last N lines of terminal scrollback ─────────────────────
# Uses `fc -ln` to get recent history lines as a lightweight proxy for terminal
# context. For full scrollback capture, tmux users get `tmux capture-pane`.
_aicli_terminal_context() {
    local lines="${1:-20}"
    local ctx=""

    # Prefer tmux capture-pane for accurate scrollback (includes command output)
    if [[ -n "$TMUX" ]]; then
        ctx=$(tmux capture-pane -p -S -"$lines" 2>/dev/null | grep -v '^$' | tail -"$lines")
    fi

    # Fallback: recent shell history lines (commands only, no output)
    if [[ -z "$ctx" ]]; then
        ctx=$(fc -ln -"$lines" 2>/dev/null | tail -"$lines")
    fi

    echo "$ctx"
}

# ── Ctrl+G: context-aware command generation ──────────────────────────────────
_aicli_hotkey_widget() {
    local prompt_text="$BUFFER"

    if [[ -z "$prompt_text" ]]; then
        # Empty buffer — show inline prompt (hint: Ctrl+E auto-fixes last failed command)
        zle -M ""
        echo -n "aicli> "
        read -r prompt_text </dev/tty
    fi

    if [[ -n "$prompt_text" ]]; then
        local result
        local term_ctx
        term_ctx=$(_aicli_terminal_context 20)

        if [[ -n "$term_ctx" ]]; then
            # Pass terminal context so aicli can see what's on screen
            result=$(aicli ask --shell --dry-run --lite \
                --terminal-context "$term_ctx" \
                "$prompt_text" 2>/dev/null | tail -n 1)
        else
            result=$(aicli ask --shell --dry-run --lite "$prompt_text" 2>/dev/null | tail -n 1)
        fi

        if [[ -n "$result" ]]; then
            BUFFER="$result"
            CURSOR=${#BUFFER}
            zle -M "aicli: $result"
        else
            zle -M "aicli: no command generated"
        fi
    fi

    zle redisplay
}

# ── Ctrl+E: error-fix mode — auto-diagnose last failed command ────────────────
# Grabs the last command + any visible error output and asks aicli to fix it.
_aicli_fix_widget() {
    local last_cmd
    last_cmd=$(fc -ln -1 2>/dev/null | sed 's/^[[:space:]]*//')

    if [[ -z "$last_cmd" ]]; then
        zle -M "aicli: no previous command found"
        zle redisplay
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
        BUFFER="$result"
        CURSOR=${#BUFFER}
        zle -M "aicli fix: $result"
    else
        zle -M "aicli: could not generate fix"
    fi

    zle redisplay
}

zle -N _aicli_hotkey_widget
zle -N _aicli_fix_widget
bindkey '^G' _aicli_hotkey_widget
bindkey '^E' _aicli_fix_widget

# ── Ctrl+I: inline next-command suggestion ────────────────────────────────────
# Different from Ctrl+G (which generates from a typed prompt):
# Ctrl+I reads what's already on screen and suggests the CONTEXTUALLY CORRECT
# next command — it knows what just ran. Like ShellGPT Ctrl+I but smarter:
# tmux scrollback means it sees actual output, not just history.
#
# Usage: after running a command, press Ctrl+I to get the logical next step.
#   Example: you ran `git status`, press Ctrl+I → `git add -A && git commit -m "..."`
#   Example: you ran `docker build .`, press Ctrl+I → `docker run -it <image>`
#   Example: you ran a failing command, press Ctrl+I → suggested fix (like Ctrl+E
#            but for "what should I do next?" not just "fix this")
_aicli_next_widget() {
    local term_ctx
    term_ctx=$(_aicli_terminal_context 30)

    if [[ -z "$term_ctx" ]]; then
        zle -M "aicli: no terminal context available (use tmux for best results)"
        zle redisplay
        return
    fi

    local next_prompt="Given this terminal context, what is the logical next shell command to run? Output ONLY the command, nothing else."
    local result

    result=$(aicli ask --shell --dry-run --lite \
        --terminal-context "$term_ctx" \
        "$next_prompt" 2>/dev/null | tail -n 1)

    if [[ -n "$result" ]]; then
        BUFFER="$result"
        CURSOR=${#BUFFER}
        zle -M "aicli next: $result"
    else
        zle -M "aicli: could not suggest next command"
    fi

    zle redisplay
}

zle -N _aicli_next_widget
bindkey '^I' _aicli_next_widget  # Ctrl+I — inline next-command suggestion
# NOTE: Ctrl+I = Tab in many terminals. If this breaks Tab completion, rebind:
#   bindkey '^I' _aicli_next_widget    ← current (overrides Tab)
#   bindkey '^[i' _aicli_next_widget   ← Alt+I (safe alternative, no Tab conflict)
#   bindkey '^N' _aicli_next_widget    ← Ctrl+N (another safe option)
# To restore Tab completion: bindkey '^I' expand-or-complete
#
# One-line switch to Alt+I (uncomment to use):
# bindkey '^[i' _aicli_next_widget   # Alt+I — no Tab conflict

# ── Ctrl+L: multi-step chain generation ──────────────────────────────────────
# ShellGPT equivalent: Ctrl+L generates a multi-step command chain from the
# buffer text (or an inline prompt if buffer is empty).
#
# Better than ShellGPT: shows [N/total] progress, Y/n per step, halts on fail.
#
# Usage: type a task description, press Ctrl+L — aicli generates and runs
# a numbered sequence of shell commands, confirming each before execution.
#   Example: type "create nginx container mounting index.html from current folder"
#            press Ctrl+L → [1/3] touch index.html  [Y/n]
#                         → [2/3] echo "<h1>hello</h1>" > index.html  [Y/n]
#                         → [3/3] docker run -d -p 80:80 ...  [Y/n]
#
# Flags that can be added to the buffer:
#   --auto-confirm  : execute all steps without prompting (like ShellGPT)
#   --dry-run       : show steps only, execute nothing
#   --role "devops" : custom system prompt for chain generation
_aicli_chain_widget() {
    local prompt_text="$BUFFER"

    if [[ -z "$prompt_text" ]]; then
        zle -M ""
        echo -n "aicli chain> "
        read -r prompt_text </dev/tty
    fi

    if [[ -n "$prompt_text" ]]; then
        # Clear the buffer — chain runs interactively in terminal
        BUFFER=""
        zle redisplay
        # Run chain in foreground so user can interact with Y/n prompts
        aicli cmd --chain "$prompt_text"
    fi
}

zle -N _aicli_chain_widget
bindkey '^L' _aicli_chain_widget   # Ctrl+L — multi-step chain (ShellGPT parity)
# NOTE: Ctrl+L clears the screen in many terminals. If this conflicts, rebind:
#   bindkey '^[l' _aicli_chain_widget  # Alt+L — safe alternative
# To restore clear-screen: bindkey '^L' clear-screen
