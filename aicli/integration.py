"""
integration.py — Idempotent shell integration installer.
Installs Ctrl+K hotkey for aicli ask --shell with current buffer.
INTEGRATION_MARKER prevents duplicate RC entries.
"""
import os
from pathlib import Path

INTEGRATION_MARKER = "# aicli-integration-marker"

BASH_INTEGRATION = '''
{marker}
_aicli_shell_integration() {{
    local query="$READLINE_LINE"
    if [ -z "$query" ]; then return; fi
    local result
    result=$(aicli ask --shell "$query" 2>/dev/null)
    if [ $? -eq 0 ] && [ -n "$result" ]; then
        READLINE_LINE="$result"
        READLINE_POINT=${{#READLINE_LINE}}
    fi
}}
bind -x '"\\C-k": _aicli_shell_integration'
{marker}
'''

ZSH_INTEGRATION = '''
{marker}
_aicli_shell_integration() {{
    local query="$BUFFER"
    if [ -z "$query" ]; then return; fi
    local result
    result=$(aicli ask --shell "$query" 2>/dev/null)
    if [ $? -eq 0 ] && [ -n "$result" ]; then
        BUFFER="$result"
        CURSOR=${{#BUFFER}}
    fi
    zle reset-prompt
}}
zle -N _aicli_shell_integration
bindkey '^K' _aicli_shell_integration
{marker}
'''


def _is_installed(rc_path: Path) -> bool:
    return rc_path.exists() and INTEGRATION_MARKER in rc_path.read_text()


def install_integration(shell: str = "auto", force: bool = False) -> str:
    if shell == "auto":
        shell = "zsh" if Path(os.environ.get("SHELL", "")).name == "zsh" else "bash"
    rc_path = Path.home() / (".zshrc" if shell == "zsh" else ".bashrc")
    block = (ZSH_INTEGRATION if shell == "zsh" else BASH_INTEGRATION).format(marker=INTEGRATION_MARKER)
    if _is_installed(rc_path) and not force:
        return f"Already installed in {rc_path}"
    base = rc_path.read_text() if rc_path.exists() else ""
    rc_path.write_text(base.rstrip() + "\n" + block)
    return f"Installed in {rc_path} — reload with: source {rc_path}"


def uninstall_integration(shell: str = "auto") -> str:
    if shell == "auto":
        shell = "zsh" if Path(os.environ.get("SHELL", "")).name == "zsh" else "bash"
    rc_path = Path.home() / (".zshrc" if shell == "zsh" else ".bashrc")
    if not _is_installed(rc_path):
        return f"Not installed in {rc_path}"
    lines = rc_path.read_text().split("\n")
    result, inside = [], False
    for line in lines:
        if line.strip() == INTEGRATION_MARKER:
            inside = not inside
            continue
        if not inside:
            result.append(line)
    rc_path.write_text("\n".join(result))
    return f"Removed from {rc_path}"
