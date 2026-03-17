"""
aicli/tools/executor.py — Safe Tool Dispatch

Takes LLM tool_use blocks, validates them against TOOL_REGISTRY,
prompts user for confirmation (unless auto_confirm=True or dry_run=True),
executes the tool, and writes an audit log entry.

Better than ShellGPT's @FunctionCall:
  - ShellGPT: fires immediately, no confirmation, no audit, no dry-run
  - aicli: confirm gate → execute → audit (or dry-run → show only)

Audit log format (JSONL):
  {"ts": "2026-03-16T19:30:00", "tool": "open_url_in_browser",
   "args": {"url": "https://news.ycombinator.com"},
   "decision": "confirmed", "result": "Opened in browser: ...", "ok": true}

Usage:
    from aicli.tools.executor import dispatch_tool_calls

    results = await dispatch_tool_calls(
        tool_calls,          # list of {"name": ..., "input": {...}} dicts
        auto_confirm=False,  # True → skip all prompts
        dry_run=False,       # True → show calls, run nothing
        quiet=False,         # True → suppress non-alert output
    )
"""

from __future__ import annotations
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from .registry import get_tool, TOOL_REGISTRY

# Module-level imports so tests can patch aicli.tools.executor.ProviderPipeline
# and aicli.tools.executor.load_config cleanly.
try:
    from ..providers.pipeline import ProviderPipeline, ProviderExhaustedError
    from ..config import load_config
except ImportError:
    ProviderPipeline = None  # type: ignore[assignment,misc]
    ProviderExhaustedError = Exception  # type: ignore[assignment,misc]
    load_config = None  # type: ignore[assignment]


# ── Audit log ─────────────────────────────────────────────────────────────────

def _audit_log_path() -> Path:
    """Returns path to tool_audit.jsonl in aicli config dir."""
    try:
        from ..config import CONFIG_DIR
        return CONFIG_DIR / "tool_audit.jsonl"
    except ImportError:
        return Path.home() / ".config" / "aicli" / "tool_audit.jsonl"


def _write_audit(
    tool_name: str,
    args: dict,
    decision: str,
    result: str | None,
    ok: bool,
    safe: bool,
) -> None:
    """Append one JSONL record to the audit log. Silent on failure."""
    if safe:
        return  # skip logging for flagged-safe (read-only) tools
    try:
        entry = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "tool": tool_name,
            "args": {k: (v[:200] if isinstance(v, str) and len(v) > 200 else v) for k, v in args.items()},
            "decision": decision,
            "result": (result[:500] if result and len(result) > 500 else result),
            "ok": ok,
        }
        log_path = _audit_log_path()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass  # audit failure must never break the main flow


# ── Confirmation prompt ───────────────────────────────────────────────────────

def _format_tool_call(name: str, args: dict) -> str:
    """Format a tool call for display — ShellGPT @FunctionCall style but richer.

    ShellGPT shows:  @FunctionCall play_music()
    aicli shows:     @FunctionCall play_music(query='classical')
                       description of what it does

    The @FunctionCall prefix is recognisable to ShellGPT users while the
    args make the call transparent and auditable.
    """
    arg_str = ", ".join(
        f"{k}={v!r}" if not isinstance(v, str) or len(v) <= 60
        else f'{k}="{v[:57]}..."'
        for k, v in args.items()
    )
    return f"\033[1;36m@FunctionCall\033[0m \033[1m{name}\033[0m({arg_str})"


def _confirm_tool(name: str, args: dict, description: str) -> bool:
    """Prompt user to confirm a tool call. Returns True if confirmed."""
    print(f"\n{_format_tool_call(name, args)}")
    print(f"\033[90m       {description}\033[0m")
    try:
        ans = input("  Run? [Y/n] ").strip().lower()
        return ans in ("", "y", "yes")
    except (KeyboardInterrupt, EOFError):
        print("\n(cancelled)")
        return False


# ── Main dispatch ─────────────────────────────────────────────────────────────

async def dispatch_tool_calls(
    tool_calls: list[dict],
    auto_confirm: bool = False,
    dry_run: bool = False,
    quiet: bool = False,
    max_retries: int = 1,
) -> list[dict]:
    """Dispatch a list of LLM tool_use blocks.

    Each item in tool_calls must have:
        {"name": str, "input": dict}   (Anthropic format)
    or:
        {"function": {"name": str, "arguments": str|dict}}  (OpenAI format)

    max_retries: how many extra attempts on transient failure (default: 1 = one retry).

    Returns a list of result dicts:
        {"name": str, "result": str, "ok": bool, "skipped": bool}
    """
    # Ensure os_functions are loaded/registered
    try:
        import aicli.tools.os_functions  # noqa: F401 — side-effect registration
    except ImportError:
        pass

    results = []

    for call in tool_calls:
        # ── Normalise to Anthropic format ────────────────────────────────────
        if "function" in call:
            # OpenAI-style
            fn = call["function"]
            name = fn.get("name", "")
            raw_args = fn.get("arguments", {})
            args: dict = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
        else:
            # Anthropic-style (native)
            name = call.get("name", "")
            args = call.get("input", {})

        tool = get_tool(name)
        if tool is None:
            msg = f"Unknown tool: {name!r}. Available: {', '.join(TOOL_REGISTRY.keys())}"
            if not quiet:
                print(f"\033[31m[TOOL ERROR] {msg}\033[0m")
            results.append({"name": name, "result": msg, "ok": False, "skipped": False})
            _write_audit(name, args, "unknown_tool", msg, ok=False, safe=False)
            continue

        fn_entry = tool
        description = fn_entry["description"]
        needs_confirm = fn_entry["confirm"]
        is_safe = fn_entry["safe"]
        fn = fn_entry["fn"]

        # ── Dry-run: show call, skip execution ───────────────────────────────
        if dry_run:
            print(f"\n{_format_tool_call(name, args)}")
            print(f"\033[90m  {description}\033[0m")
            print(f"\033[90m  (dry-run — not executed)\033[0m")
            results.append({"name": name, "result": "(dry-run)", "ok": True, "skipped": True})
            continue

        # ── Confirmation gate ─────────────────────────────────────────────────
        if needs_confirm and not auto_confirm:
            confirmed = _confirm_tool(name, args, description)
            if not confirmed:
                if not quiet:
                    print(f"\033[33m  Skipped: {name}\033[0m")
                _write_audit(name, args, "user_declined", None, ok=True, safe=is_safe)
                results.append({"name": name, "result": "(skipped by user)", "ok": True, "skipped": True})
                continue
            decision = "confirmed"
        else:
            # auto_confirm or no confirm required — show @FunctionCall line cleanly
            # (like ShellGPT: shows the call happening, no interactive pause)
            if not quiet:
                print(f"\n{_format_tool_call(name, args)}")
                print(f"\033[90m  {description}\033[0m")
            decision = "auto_confirmed" if auto_confirm else "no_confirm_required"

        # ── Execute (with retry) ──────────────────────────────────────────────
        # Tools can fail transiently (network blip, clipboard daemon not ready, etc.)
        # max_retries=1 default means one retry on failure (2 total attempts).
        # Configurable per dispatch_tool_calls call.
        import inspect
        last_exc: Exception | None = None
        _tool_max_retries = max_retries  # passed in from dispatch_tool_calls
        for attempt in range(max(_tool_max_retries, 0) + 1):  # max_retries=0 → 1 attempt, max_retries=1 → 2 attempts
            try:
                if inspect.iscoroutinefunction(fn):
                    result_text = await fn(**args)
                else:
                    result_text = fn(**args)

                result_text = str(result_text) if result_text is not None else "(done)"
                if not quiet:
                    print(f"\033[32m  ✓ {result_text}\033[0m")
                _write_audit(name, args, decision, result_text, ok=True, safe=is_safe)
                results.append({"name": name, "result": result_text, "ok": True, "skipped": False})
                last_exc = None
                break  # success — stop retry loop

            except Exception as exc:
                last_exc = exc
                if attempt < _tool_max_retries and not quiet:
                    print(f"\033[33m  ↻ Retry {attempt+1}/{_tool_max_retries}: {exc}\033[0m")

        if last_exc is not None:
            err = f"Tool error: {last_exc}"
            if not quiet:
                print(f"\033[31m  ✗ {err}\033[0m")
            _write_audit(name, args, decision, err, ok=False, safe=is_safe)
            results.append({"name": name, "result": err, "ok": False, "skipped": False})

    return results


# ── do command helper ─────────────────────────────────────────────────────────

# ── Direct dispatch: skip LLM for unambiguous media commands ─────────────────
# These patterns match prompts where the tool and args are fully determined
# from the prompt alone — no LLM needed. Cuts latency from ~2s to ~50ms.

import re as _re

_DIRECT_PATTERNS: list[tuple] = [
    # (regex, tool_name, arg_extractor_fn)
    # browse_media
    (
        _re.compile(
            r"browse|pick\s+a\s+(song|file|video|music)|"
            r"show\s+me\s+my\s+(music|video|media|songs?|files?)|"
            r"list\s+(my\s+)?(music|video|media|songs?|files?)",
            _re.IGNORECASE,
        ),
        "browse_media",
        lambda m, text: {
            "directory": (
                # Pass the actual absolute cwd so there's zero ambiguity
                str(__import__("pathlib").Path.cwd())
                if any(w in text.lower() for w in ("this dir", "this directory", "here", "current", "this folder"))
                else ""
            ),
            "filter": (
                "audio" if any(w in text.lower() for w in ("music", "song", "audio", "mp3", "wav", "flac"))
                else "video" if any(w in text.lower() for w in ("video", "movie", "mkv", "mp4"))
                else ""
            ),
        },
    ),
    # play_music with explicit file path
    (
        _re.compile(r"play\s+(.+\.(mp3|mp4|mkv|wav|flac|ogg|m4a|aac|avi|mov|webm|opus|aiff))", _re.IGNORECASE),
        "play_music",
        lambda m, text: {"query": m.group(1).strip()},
    ),
    # play music / resume
    (
        _re.compile(r"^(play\s+music|play\s+some\s+music|resume\s+(music|playback)|play\s+the\s+song)$", _re.IGNORECASE),
        "play_music",
        lambda m, text: {"query": ""},
    ),
    # open URL
    (
        _re.compile(r"open\s+(https?://\S+)", _re.IGNORECASE),
        "open_url_in_browser",
        lambda m, text: {"url": m.group(1).rstrip(".,;)")},
    ),
    # get system info
    (
        _re.compile(r"(get|show|check)\s+(system\s+info|cpu|memory|disk|ram)", _re.IGNORECASE),
        "get_system_info",
        lambda m, text: {"detail": "all"},
    ),
    # get clipboard
    (
        _re.compile(r"(get|read|show|what.*in)\s+(my\s+)?clipboard", _re.IGNORECASE),
        "get_clipboard",
        lambda m, text: {},
    ),
]


# Conjunctions that signal multiple tools — always send to LLM

_COMPOUND_RE = _re.compile(r"\band\b|\balso\b|\bthen\b|\bplus\b", _re.IGNORECASE)


def _try_direct_dispatch(prompt_text: str) -> tuple[str, dict] | None:
    """Return (tool_name, args) if the prompt matches a direct-dispatch pattern, else None.

    Returns None for compound prompts ("browse music AND open hacker news")
    so they go through the LLM which can dispatch multiple tools in one response.
    """
    text = prompt_text.strip()

    # Compound prompt → let LLM handle all tools together
    if _COMPOUND_RE.search(text):
        return None

    for pattern, tool_name, arg_extractor in _DIRECT_PATTERNS:
        m = pattern.search(text)
        if m:
            try:
                args = arg_extractor(m, text)
                return tool_name, args
            except Exception:
                continue
    return None


async def run_do_command(
    prompt_parts: tuple,
    quiet: bool = False,
    model: str | None = None,
    lite: bool = False,
    auto_confirm: bool = True,   # default: execute immediately (no Y/n prompts)
    dry_run: bool = False,
    role: str | None = None,
    max_retries: int = 1,
    session_id: str | None = None,
    verbose: bool = False,
) -> None:
    """Entry point for `aicli do "prompt"` — the function-calling command.

    Sends the prompt to the LLM with all registered tools available.
    Dispatches any tool_use blocks through the confirmation gate.
    Falls back to streaming plain-text if the LLM returns no tool calls.

    role:       optional custom system prompt role name.
    max_retries: max retry attempts per tool on transient failure (default: 1).
    session_id: optional session name/id for multi-turn do sessions.
                When provided, loads prior conversation history so the LLM
                has context from previous turns. Enables follow-up prompts like
                "open that file" → "now summarize it" → "send it to alice".
    """
    # Ensure tools registered
    try:
        import aicli.tools.os_functions  # noqa: F401
    except ImportError:
        pass

    from ..printer import stream_to_terminal, print_error, print_info
    from .registry import get_tool_schema

    prompt_text = " ".join(prompt_parts) if prompt_parts else ""
    if not prompt_text:
        print_error("No prompt provided. Run: aicli do \"open hacker news\"")
        return

    # ── Fast path: direct dispatch — skip LLM for unambiguous commands ────────
    # For commands like "browse my music" or "play file.mp3" the tool and args
    # are fully determined from the prompt — no need for a 1–2s LLM round-trip.
    if not dry_run:
        direct = _try_direct_dispatch(prompt_text)
        if direct:
            direct_tool, direct_args = direct
            if not quiet:
                from ..printer import print_info as _pi
                _pi(f"Direct dispatch → {direct_tool} (no LLM needed)")
            # Import tools so they register
            try:
                import aicli.tools.os_functions  # noqa: F401
            except ImportError:
                pass
            results = await dispatch_tool_calls(
                [{"name": direct_tool, "input": direct_args}],
                auto_confirm=auto_confirm,
                dry_run=False,
                quiet=quiet,
                max_retries=max_retries,
            )
            # Natural summary
            if not quiet:
                successful = [r for r in results if r.get("ok") and not r.get("skipped")]
                if successful:
                    result_text = successful[0]["result"]
                    print(f"\n\033[1m{result_text}\033[0m")
            return
    # ──────────────────────────────────────────────────────────────────────────

    config = load_config()

    # Ensure tools registered and get schemas before building system prompt
    tool_schemas = get_tool_schema()

    # Build system prompt — use custom role if provided, else default tool-dispatcher
    if role:
        try:
            from ..role import get_role as _get_role
            role_obj = _get_role(role)
            system_prompt = role_obj.system_prompt
        except Exception:
            system_prompt = role  # treat as literal system prompt string if role not found
    else:
        import json as _json
        # Compact schema — only name, short description, param names
        # Full schemas are too verbose and eat into response token budget
        compact_tools = []
        for t in tool_schemas:
            props = t.get("input_schema", {}).get("properties", {})
            compact_tools.append({
                "name": t["name"],
                "desc": t["description"][:80],
                "params": {k: v.get("type", "string") for k, v in props.items()},
            })
        tools_json = _json.dumps(compact_tools)
        system_prompt = (
            "You are an OS automation assistant. Execute tasks using tools.\n\n"
            "TOOLS: " + tools_json + "\n\n"
            "RULES:\n"
            "1. Action request → output ONLY a JSON array, no other text:\n"
            '   [{"name":"tool_name","input":{"param":"value"}}]\n'
            "2. Multiple actions → include all in one array.\n"
            "3. Question → plain text answer.\n\n"
            "EXAMPLES:\n"
            'open hacker news → [{"name":"open_url_in_browser","input":{"url":"https://news.ycombinator.com"}}]\n'
            'play music and open hacker news → [{"name":"play_music","input":{"query":""}},{"name":"open_url_in_browser","input":{"url":"https://news.ycombinator.com"}}]\n'
            'browse music in /home/dev/Music/aicli → [{"name":"browse_media","input":{"directory":"/home/dev/Music/aicli","filter":"audio"}}]\n'
            'what is Python → Python is a programming language...'
        )

    messages = [
        {"role": "system", "content": system_prompt},
    ]

    # ── Multi-turn: load session history ──────────────────────────────────────
    # When session_id is provided, inject prior conversation turns so the LLM
    # has context from previous `aicli do` calls in this session.
    if session_id:
        try:
            from ..db.chat_db import get_connection, list_sessions, load_messages
            conn = get_connection()
            sessions = list_sessions(conn)
            matching = [s for s in sessions if s["name"] == session_id or s["id"] == session_id]
            if matching:
                history = load_messages(conn, matching[0]["id"])
                # Include last 10 turns to keep context window reasonable
                for msg in history[-10:]:
                    messages.append({"role": msg["role"], "content": msg["content"]})
                if not quiet and history:
                    print_info(f"[do] Session '{session_id}': {len(history)} prior turns loaded")
        except Exception:
            pass  # session context optional — continue without it

    messages.append({"role": "user", "content": prompt_text})

    if dry_run and not quiet:
        print_info(f"Dry-run plan: {len(tool_schemas)} tools available — showing calls only, nothing will execute")
    elif verbose and not quiet:
        print_info(f"Function-call mode: {len(tool_schemas)} tools available")

    try:
        pipeline = ProviderPipeline(
            provider_chain=config["provider_chain"],
            cooldown_seconds=config["cooldown_seconds"],
            max_retries_per_provider=config["max_retries_per_provider"],
            show_provider=not quiet,
        )

        # Request: complete (not stream) so we can inspect tool call JSON.
        # pipeline.complete() returns plain text — tool schemas are embedded
        # in the system prompt so the LLM responds with structured JSON.
        response_content = await pipeline.complete(
            messages,
            model=model,
        )

        # Parse response: try JSON array of tool calls first, fall back to plain text.
        # The system prompt instructs the LLM to respond with a JSON array for actions
        # or plain text for questions — pipeline returns plain concatenated string.
        import json as _json
        import re as _re

        tool_calls = []
        text_parts = []

        raw = response_content.strip() if isinstance(response_content, str) else ""

        # Strip markdown fences
        raw_clean = _re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=_re.MULTILINE).strip()

        parsed_as_tools = False

        # Try to find a JSON array anywhere in the response —
        # some models add preamble text before the JSON despite instructions
        json_match = _re.search(r"\[\s*\{.*?\}\s*(?:,\s*\{.*?\}\s*)*\]", raw_clean, _re.DOTALL)
        if json_match:
            try:
                parsed = _json.loads(json_match.group(0))
                if isinstance(parsed, list) and all(
                    isinstance(item, dict) and "name" in item for item in parsed
                ):
                    for item in parsed:
                        tool_calls.append({
                            "name": item["name"],
                            "input": item.get("input", item.get("arguments", item.get("args", {}))),
                        })
                    parsed_as_tools = True
            except (_json.JSONDecodeError, KeyError):
                pass

        if not parsed_as_tools:
            # Plain text response (question / no action)
            text_parts.append(raw)

        # Print any text response first
        if text_parts:
            print("".join(text_parts))

        # Sort tool_calls: non-blocking tools first, blocking (interactive) tools last.
        # This ensures open_url_in_browser fires before browse_media asks for input.
        _BLOCKING = {"browse_media"}
        if tool_calls:
            tool_calls = sorted(tool_calls, key=lambda c: 1 if (c.get("name") or "") in _BLOCKING else 0)

        if tool_calls:
            results = await dispatch_tool_calls(
                tool_calls,
                auto_confirm=auto_confirm,
                dry_run=dry_run,
                quiet=quiet,
                max_retries=max_retries,
            )

            # ── Natural summary pass — ShellGPT's "Music is now playing..." ──
            # After executing tools, send results back to the LLM so it can
            # produce a natural language summary of what happened.
            # This is the key UX difference: ShellGPT says "Music is now playing,
            # and Hacker News has been opened in your browser. Enjoy!" — we do too.
            # Only runs when: not dry_run, not quiet, at least one tool succeeded.
            if not dry_run and not quiet:
                successful = [r for r in results if r.get("ok") and not r.get("skipped")]
                if successful:
                    results_text = "\n".join(
                        f"- {r['name']}(): {r['result']}" for r in successful
                    )
                    summary_messages = [
                        {
                            "role": "system",
                            "content": (
                                "You are a helpful assistant. The user asked you to perform "
                                "actions and the following tools were executed successfully. "
                                "Write ONE concise, friendly sentence confirming what was done. "
                                "Be natural and warm, like: "
                                "'Music is now playing, and Hacker News has been opened in your browser. Enjoy!'"
                            ),
                        },
                        {"role": "user", "content": prompt_text},
                        {
                            "role": "assistant",
                            "content": f"Tool results:\n{results_text}",
                        },
                        {
                            "role": "user",
                            "content": "Please summarize what was done in one friendly sentence.",
                        },
                    ]
                    try:
                        summary_chunks: list[str] = []
                        async for chunk in pipeline.stream(
                            summary_messages, model=model, requires_vision=False
                        ):
                            summary_chunks.append(chunk)
                        summary = "".join(summary_chunks).strip()
                        if summary:
                            print(f"\n\033[1m{summary}\033[0m")
                    except Exception:
                        pass  # summary pass is best-effort — never break main flow

        elif not text_parts:
            if not quiet:
                print_info("No tool calls or text returned.")

    except ProviderExhaustedError as e:
        print_error(f"All providers failed: {e}")
