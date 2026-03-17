"""
aicli/tools/registry.py — OS Function Tool Registry

Defines the @os_tool decorator and maintains a global dict of callable tools
that the LLM can dispatch to via structured function calling.

Design goals (better than ShellGPT):
  - Every tool has a strict JSON Schema so the LLM produces valid args
  - Every tool call requires explicit user confirmation unless --auto-confirm is set
  - Every execution is logged to ~/.config/aicli/tool_audit.jsonl
  - --dry-run prints the call without executing anything
  - Tools are importable independently (no circular deps)

Usage:
  from aicli.tools.registry import TOOL_REGISTRY, get_tool_schema

  # The LLM receives get_tool_schema() as its tools list.
  # When it returns a tool_use block, executor.py dispatches to TOOL_REGISTRY.
"""

from __future__ import annotations
import functools
import inspect
from typing import Any, Callable

# ── Global registry ──────────────────────────────────────────────────────────
# Maps tool_name → {"fn": callable, "schema": dict, "description": str, "confirm": bool}
TOOL_REGISTRY: dict[str, dict] = {}


def os_tool(
    name: str,
    description: str,
    parameters: dict,
    confirm: bool = True,
    safe: bool = False,
):
    """Decorator that registers a function as a callable OS tool.

    Args:
        name:        Tool name sent to the LLM (snake_case).
        description: Human-readable description shown in --dry-run and confirmations.
        parameters:  JSON Schema 'properties' dict for this tool's arguments.
        confirm:     If True (default), prompt user before executing.
                     Set False only for read-only / zero-side-effect tools.
        safe:        If True, skip audit log (for truly harmless ops like clipboard read).

    Example:
        @os_tool(
            name="open_url_in_browser",
            description="Open a URL in the default system browser.",
            parameters={"url": {"type": "string", "description": "URL to open"}},
        )
        async def open_url_in_browser(url: str) -> str:
            import webbrowser
            webbrowser.open(url)
            return f"Opened: {url}"
    """
    def decorator(fn: Callable) -> Callable:
        schema = {
            "name": name,
            "description": description,
            "input_schema": {
                "type": "object",
                "properties": parameters,
                "required": list(parameters.keys()),
            },
        }
        TOOL_REGISTRY[name] = {
            "fn": fn,
            "schema": schema,
            "description": description,
            "confirm": confirm,
            "safe": safe,
        }

        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            return await fn(*args, **kwargs)

        wrapper._tool_name = name  # type: ignore[attr-defined]
        return wrapper

    return decorator


def get_tool_schema() -> list[dict]:
    """Return the list of tool schemas to pass to the LLM's tools= parameter."""
    return [entry["schema"] for entry in TOOL_REGISTRY.values()]


def get_tool(name: str) -> dict | None:
    """Look up a tool by name. Returns None if not registered."""
    return TOOL_REGISTRY.get(name)


def list_tools() -> list[str]:
    """Return list of all registered tool names."""
    return list(TOOL_REGISTRY.keys())
