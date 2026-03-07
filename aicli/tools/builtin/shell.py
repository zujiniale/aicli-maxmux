"""
shell.py — Safe shell command execution.

Security model:
- shell=False + shlex.split() → no shell injection at the execve level
- HIGH_RISK_PATTERNS → double confirmation for destructive commands
- E/M/D/A/R menu → explicit user confirmation before any execution
- Self-correction loop: on non-zero exit, re-prompt with error context
"""

import re
import shlex
import asyncio
import subprocess
from typing import Optional


# Commands that require double confirmation
HIGH_RISK_PATTERNS = re.compile(
    r"""
    \brm\s+-rf?\b |          # rm -r or rm -rf
    \bdd\b |                  # dd (disk destroyer)
    \bmkfs\b |                # format filesystem
    \bshred\b |               # secure delete
    >\s*/dev/ |               # write to device
    \|\s*sh\b |               # pipe to sh
    \|\s*bash\b |             # pipe to bash
    \bcurl\b.*\|\s*sh |       # curl | sh (classic RCE)
    \bwget\b.*\|\s*sh |       # wget | sh
    sudo\s+rm |               # sudo rm
    :\(\)\{.*\} |             # fork bomb pattern
    /etc/passwd |             # password file
    /etc/shadow               # shadow file
    """,
    re.VERBOSE | re.IGNORECASE,
)


def is_high_risk(command: str) -> bool:
    return bool(HIGH_RISK_PATTERNS.search(command))


def execute_command(command: str) -> tuple[int, str, str]:
    """
    Execute a shell command safely.
    Uses shell=False + shlex.split() — no shell interpretation.
    Returns (returncode, stdout, stderr).
    """
    try:
        args = shlex.split(command)
    except ValueError as e:
        return 1, "", f"Invalid command syntax: {e}"

    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=30,
            shell=False,  # Critical: no shell injection
        )
        return result.returncode, result.stdout, result.stderr
    except FileNotFoundError:
        return 127, "", f"Command not found: {args[0]}"
    except subprocess.TimeoutExpired:
        return 124, "", "Command timed out after 30 seconds"
    except Exception as e:
        return 1, "", str(e)


def print_command_box(command: str) -> None:
    """Display the generated command in a clear box."""
    width = min(max(len(command) + 4, 40), 80)
    print(f"\n{'─' * width}")
    print(f"  $ {command}")
    print(f"{'─' * width}")


def shell_menu(command: str, pipeline=None) -> tuple[str, Optional[str]]:
    """
    Display E/M/D/A/R menu and handle user choice.
    Returns (action, modified_command_or_none).

    Actions:
      E — Execute
      M — Modify (re-prompt AI with new instruction, or edit directly)
      D — Describe (explain what it does)
      A — Abort
    """
    print_command_box(command)

    risk_warning = ""
    if is_high_risk(command):
        risk_warning = "\n  ⚠️  HIGH RISK COMMAND — requires confirmation"
        print(risk_warning)

    print("\n  [E]xecute  [M]odify  [D]escribe  [A]bort")

    while True:
        try:
            choice = input("  > ").strip().upper()
        except (EOFError, KeyboardInterrupt):
            print("\nAborted.")
            return "abort", None

        if choice == "E":
            if is_high_risk(command):
                confirm = input("  ⚠️  Type 'yes' to confirm execution of high-risk command: ").strip()
                if confirm.lower() != "yes":
                    print("  Aborted.")
                    return "abort", None
            return "execute", command

        elif choice == "M":
            try:
                instruction = input("  New instruction (or edit command directly): ").strip()
                if not instruction:
                    return "abort", None
                # If it looks like a shell command (starts with known cmd or has flags),
                # use it directly. Otherwise treat as natural language → re-prompt AI.
                import shlex as _shlex
                try:
                    parts = _shlex.split(instruction)
                    # Treat as a shell command only if it has flags or path arguments.
                    # Plain "find sh files" or "ls python" are natural language.
                    has_flag = any(p.startswith("-") for p in parts[1:])
                    has_path = len(parts) > 1 and ("/" in parts[1] or parts[1] in (".", "..", "~"))
                    looks_like_command = (
                        len(parts) > 0 and
                        ("/" in parts[0] or parts[0] in (
                            "ls","find","grep","cat","echo","cp","mv","rm","mkdir",
                            "touch","chmod","chown","tar","zip","unzip","curl","wget",
                            "git","python","python3","pip","npm","node","make","sudo",
                        )) and (has_flag or has_path)
                    )
                except Exception:
                    looks_like_command = False
                if looks_like_command:
                    return "modify", instruction
                else:
                    return "reprompt", instruction
            except (EOFError, KeyboardInterrupt):
                return "abort", None

        elif choice == "D":
            return "describe", command

        elif choice == "A":
            print("  Aborted.")
            return "abort", None

        else:
            print("  Invalid choice. Enter E, M, D, A, or R.")


async def execute_with_self_correction(
    command: str,
    pipeline,
    original_prompt: str,
    max_corrections: int = 2,
    effective_prompt: str | None = None,
) -> None:
    """
    Execute a command. On non-zero exit, auto re-prompt AI with error context.
    Self-correction loop: transforms command generator → command solver.
    effective_prompt: use this instead of original_prompt for correction context
    (set when user has re-instructed via M).
    """
    correction_count = 0
    current_command = command

    while True:
        returncode, stdout, stderr = execute_command(current_command)

        if stdout:
            print(stdout, end="")
        if stderr:
            print(f"\033[33m{stderr}\033[0m", end="")  # Yellow for stderr

        if returncode == 0:
            print(f"\n\033[32m✓ Exit 0\033[0m")
            return

        print(f"\n\033[31m✗ Exit {returncode}\033[0m")

        if correction_count >= max_corrections or not pipeline:
            return

        # Self-correction: re-prompt with error context
        correction_count += 1
        error_context = stderr or stdout or f"Command exited with code {returncode}"

        print(f"  \033[90m[aicli] Auto-correcting (attempt {correction_count}/{max_corrections})...\033[0m")

        correction_messages = [
            {"role": "system", "content": "You are a shell command assistant. Output ONLY the corrected command, nothing else."},
            {"role": "user", "content": effective_prompt or original_prompt},
            {"role": "assistant", "content": current_command},
            {"role": "user", "content": f"That command failed with exit code {returncode}:\n{error_context}\n\nProvide the corrected command only."},
        ]

        corrected_chunks = []
        async for chunk in pipeline.stream(correction_messages):
            corrected_chunks.append(chunk)

        corrected = "".join(corrected_chunks).strip().strip("`").strip()

        if not corrected or corrected == current_command:
            return

        print(f"\n  Corrected command:")
        action, final_command = shell_menu(corrected)

        if action == "execute" and final_command:
            current_command = final_command
        else:
            return
