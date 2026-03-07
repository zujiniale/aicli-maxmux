"""
printer.py — Terminal output formatting.
Streaming output, provider attribution footer, status display.
"""
import sys
import json
from typing import AsyncGenerator

# Optional rich support — markdown rendering when available, plain print as fallback
try:
    from rich.console import Console as _Console
    from rich.markdown import Markdown as _Markdown
    _RICH_CONSOLE = _Console()
    _RICH_AVAILABLE = True
except ImportError:
    _RICH_AVAILABLE = False

RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
CYAN   = "\033[36m"
GRAY   = "\033[90m"
RED    = "\033[31m"


async def stream_to_terminal(
    generator: AsyncGenerator[str, None],
    no_stream: bool = False,
    json_output: bool = False,
) -> str:
    chunks = []
    if no_stream:
        async for chunk in generator:
            chunks.append(chunk)
        full_text = "".join(chunks)
        if json_output:
            print(json.dumps({"response": full_text}, indent=2))
        else:
            print_markdown(full_text)
    else:
        async for chunk in generator:
            chunks.append(chunk)
            print(chunk, end="", flush=True)
        full_text = "".join(chunks)
        print()
        # Re-render with markdown after streaming if rich is available
        if _RICH_AVAILABLE and not json_output:
            # Move cursor up to overwrite the plain-streamed text
            # Only re-render if response contains markdown indicators
            if any(c in full_text for c in ("#", "```", "**", "- ", "| ")):
                # Clear streamed output and re-render
                lines = full_text.count("\n") + 1
                print(f"\033[{lines}A\033[J", end="")
                _RICH_CONSOLE.print(_Markdown(full_text))
    return full_text


def print_markdown(text: str) -> None:
    """Print text with markdown rendering if rich is available."""
    if _RICH_AVAILABLE:
        _RICH_CONSOLE.print(_Markdown(text))
    else:
        print(text)


def print_provider_footer(provider_name: str, show: bool = True) -> None:
    if not show or not provider_name:
        return
    from aicli.config import PROVIDER_MODELS
    model = PROVIDER_MODELS.get(provider_name, "")
    model_str = f" / {model}" if model else ""
    print(f"{GRAY}⚡ via {provider_name}{model_str}{RESET}", file=sys.stderr)


def print_error(message: str)   -> None: print(f"{RED}✗ {message}{RESET}", file=sys.stderr)
def print_success(message: str) -> None: print(f"{GREEN}✓ {message}{RESET}")
def print_warning(message: str) -> None: print(f"{YELLOW}⚠ {message}{RESET}", file=sys.stderr)
def print_info(message: str)    -> None: print(f"{CYAN}  {message}{RESET}", file=sys.stderr)


def print_provider_status(status_list: list[dict]) -> None:
    print(f"\n{'Provider':<14} {'Status':<20} {'Cooldown':<12} {'Failures'}")
    print("─" * 52)
    for p in status_list:
        if p["available"]:
            status = f"{GREEN}available{RESET}"
        else:
            status = f"{YELLOW}cooldown {p['cooldown_remaining']}s{RESET}"
        print(f"{p['name']:<14} {status:<28} {p['cooldown_remaining']:<12.1f} {p['failures']}")
    print()
