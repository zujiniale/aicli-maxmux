#!/usr/bin/env python3
"""
app.py — aicli: A free, private, async CLI AI tool.

Commands:
  ask     — Single-shot prompt (default, --shell, --code, --describe)
  chat    — Persistent session with memory
  repl    — Interactive REPL loop
  export  — Export session to markdown or JSON
  agent   — Autonomous multi-step task execution
  config  — Configuration management (set-key, show, edit)
  provider — Provider management (status, test)
  session — Session management (list, show, delete)

Usage:
  aicli ask "list python files in current dir"
  aicli ask --shell "find all large files"
  aicli ask --code "write a merge sort in Python"
  aicli chat --session myproject
  aicli repl
  aicli export myproject > session.md
  aicli export myproject --format json > session.json
  aicli agent "set up a Python project with pytest"
  aicli agent --dry-run "deploy my app"
  aicli provider status
  aicli config set-key groq
"""

import asyncio

import click

from .config import load_config, get_api_key, save_api_key, CONFIG_FILE
from .printer import print_error, print_success, print_info, print_provider_status
from .db.chat_db import get_connection, list_sessions, load_messages, delete_session

from .handlers.default import _ask
from .handlers.chat import _chat
from .handlers.repl import _repl
from .handlers.index import _index
from .handlers.provider import _provider_status, _provider_test
from .handlers.export import _export
from .handlers.agent import _agent


# ── CLI Group ────────────────────────────────────────────────────────────────────

@click.group(invoke_without_command=True)
@click.pass_context
@click.version_option(version="1.1.0", prog_name="aicli")
def cli(ctx):
    """aicli — Free, private, async CLI AI. Run 'aicli ask \"your prompt\"' to start."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


# ── ask ──────────────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("prompt", nargs=-1, required=False)
@click.option("--shell", "-s", is_flag=True, help="Generate and execute shell commands")
@click.option("--code", "-c", is_flag=True, help="Generate code only")
@click.option("--describe", "-d", is_flag=True, help="Describe a shell command")
@click.option("--model", "-m", default=None, help="Override model")
@click.option("--no-stream", is_flag=True, help="Print full response at once")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
@click.option("--dry-run", is_flag=True, help="Show command without offering execute")
@click.option("--context", "-x", is_flag=True, help="Inject semantically relevant context from indexed files and chat history")
@click.option("--context-depth", default=1, type=int, help="Context retrieval depth multiplier (default: 1, more=deeper search)")
@click.option("--image", "-i", "images", multiple=True, type=click.Path(exists=True), help="Image path(s) to include (vision providers only: OpenRouter, Gemini)")
def ask(prompt, shell, code, describe, model, no_stream, json_output, dry_run, context, context_depth, images):
    """Single-shot prompt. Pipe stdin or pass prompt as argument."""
    asyncio.run(_ask(prompt, shell, code, describe, model, no_stream, json_output, dry_run, context, context_depth, images=images or None))


# ── chat ─────────────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--session", "-s", default=None, help="Session name (creates if new)")
@click.option("--new", "-n", is_flag=True, help="Force new session")
@click.option("--model", "-m", default=None, help="Override model")
@click.option("--no-history", is_flag=True, help="Don't print history on resume")
@click.option("--summarize-threshold", default=None, type=float,
              help="Override summarize threshold 0.0-1.0 (default: from config, 0.80)")
@click.option("--context", "-x", is_flag=True, help="Inject semantically relevant context before each message")
@click.option("--context-depth", default=1, type=int, help="Context retrieval depth multiplier (default: 1)")
def chat(session, new, model, no_history, summarize_threshold, context, context_depth):
    """Persistent conversation with memory. Ctrl+C to exit."""
    asyncio.run(_chat(session, new, model, no_history, summarize_threshold, context, context_depth))


# ── repl ─────────────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--model", "-m", default=None, help="Override model")
@click.option("--summarize-threshold", default=None, type=float,
              help="Override summarize threshold 0.0-1.0 (default: from config, 0.80)")
def repl(model, summarize_threshold):
    """Interactive REPL. Use \"\"\" for multiline input. /shell for shell mode."""
    asyncio.run(_repl(model, summarize_threshold))


# ── config ───────────────────────────────────────────────────────────────────────

@cli.group()
def config():
    """Configuration management."""
    pass


@config.command("set-key")
@click.argument("provider")
def config_set_key(provider):
    """Set API key for a provider. Key is stored encrypted."""
    import getpass
    key = getpass.getpass(f"Enter {provider} API key: ").strip()
    if key:
        save_api_key(provider, key)
        print_success(f"Key saved for {provider}")
    else:
        print_error("No key entered.")


@config.command("show")
def config_show():
    """Show current configuration."""
    cfg = load_config()
    print(f"\n\033[1mConfiguration\033[0m ({CONFIG_FILE})\n")
    for k, v in cfg.items():
        print(f"  {k:<28} {v}")
    print()
    print("\033[1mRequired env vars\033[0m (or use: aicli config set-key <provider>)\n")
    print("  GROQ_API_KEY          Groq          — fastest, primary provider")
    print("  OPENROUTER_API_KEY    OpenRouter     — vision support (--image flag)")
    print("  GEMINI_API_KEY        Gemini         — vision support (--image flag)")
    print("  MISTRAL_API_KEY       Mistral        — fallback text provider")
    print("  (Ollama needs no key  — runs locally on http://localhost:11434)")
    print()


@config.command("keys")
def config_keys():
    """Show which providers have keys configured."""
    from .config import _load_keys_raw
    keys = _load_keys_raw()
    providers = ["groq", "openrouter", "gemini", "mistral"]
    print("\n\033[1mProvider Keys\033[0m\n")
    for p in providers:
        if p in keys:
            masked = keys[p][:8] + "..." + keys[p][-4:] if len(keys[p]) > 12 else "***"
            print(f"  {p:<14} \033[32m✓ configured\033[0m  ({masked})")
        else:
            env_key = f"AICLI_{p.upper()}_KEY"
            if __import__("os").environ.get(env_key):
                print(f"  {p:<14} \033[33m✓ env var\033[0m    ({env_key})")
            else:
                print(f"  {p:<14} \033[90m✗ not set\033[0m")
    print()


# ── provider ─────────────────────────────────────────────────────────────────────

@cli.group()
def provider():
    """Provider management."""
    pass


@provider.command("status")
def provider_status():
    """Show provider availability and cooldown status."""
    asyncio.run(_provider_status())


@provider.command("test")
@click.argument("provider_name")
def provider_test(provider_name):
    """Test a specific provider with a simple prompt."""
    asyncio.run(_provider_test(provider_name))


# ── session ──────────────────────────────────────────────────────────────────────

@cli.group()
def session():
    """Session management."""
    pass


@session.command("list")
def session_list():
    """List all chat sessions."""
    conn = get_connection()
    sessions = list_sessions(conn)
    if not sessions:
        print_info("No sessions yet. Start with: aicli chat")
        return
    print(f"\n{'ID':<12} {'Name':<20} {'Messages':<10} {'Updated'}")
    print("─" * 60)
    for s in sessions:
        updated = s["updated_at"][:10] if s["updated_at"] else "unknown"
        print(f"{s['id']:<12} {s['name']:<20} {s['message_count']:<10} {updated}")
    print()


@session.command("show")
@click.argument("session_name")
def session_show(session_name):
    """Show messages in a session."""
    conn = get_connection()
    sessions = list_sessions(conn)
    matching = [s for s in sessions if s["name"] == session_name or s["id"] == session_name]
    if not matching:
        print_error(f"Session not found: {session_name}")
        return

    session_id = matching[0]["id"]
    messages = load_messages(conn, session_id)

    print(f"\n\033[1mSession: {session_name}\033[0m ({len(messages)} messages)\n")
    for msg in messages:
        role_color = "\033[34m" if msg["role"] == "user" else "\033[32m"
        print(f"{role_color}{msg['role'].upper()}\033[0m: {msg['content']}\n")


@session.command("delete")
@click.argument("session_name")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def session_delete(session_name, yes):
    """Delete a session and all its messages."""
    conn = get_connection()
    sessions = list_sessions(conn)
    matching = [s for s in sessions if s["name"] == session_name or s["id"] == session_name]
    if not matching:
        print_error(f"Session not found: {session_name}")
        return

    session_id = matching[0]["id"]
    msg_count = matching[0]["message_count"]

    if not yes:
        confirm = input(f"Delete session '{session_name}' ({msg_count} messages)? [y/N] ")
        if confirm.lower() != "y":
            print("Cancelled.")
            return

    delete_session(conn, session_id)
    print_success(f"Deleted session: {session_name}")


# ── index ────────────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--chat", "include_chat", is_flag=True, help="Also index all saved chat sessions")
def index(path, include_chat):
    """Index a directory for semantic context search. Use with --context flag."""
    asyncio.run(_index(path, include_chat))


# ── export ───────────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("session_name")
@click.option("--format", "fmt", default="markdown", type=click.Choice(["markdown", "json"]), help="Output format (default: markdown)")
@click.option("--output", "-o", default=None, help="Write to file instead of stdout")
def export(session_name, fmt, output):
    """Export a session to markdown or JSON. Pipe with: aicli export mysession > out.md"""
    asyncio.run(_export(session_name, fmt, output))


# ── agent ────────────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("task", nargs=-1, required=True)
@click.option("--model", "-m", default=None, help="Override model")
@click.option("--dry-run", is_flag=True, help="Show plan without executing")
@click.option("--yes", "-y", is_flag=True, help="Auto-confirm all steps (use with care)")
def agent(task, model, dry_run, yes):
    """Autonomous multi-step agent. Plans and executes shell commands to complete a task."""
    asyncio.run(_agent(" ".join(task), model, dry_run, yes))


# ── session summary ──────────────────────────────────────────────────────────────

@session.command("summary")
@click.argument("session_name")
def session_summary(session_name):
    """Show the latest auto-summary for a session."""
    from .db.chat_db import load_latest_summary
    conn = get_connection()
    sessions = list_sessions(conn)
    matching = [s for s in sessions if s["name"] == session_name or s["id"] == session_name]
    if not matching:
        print_error(f"Session not found: {session_name}")
        return

    session_id = matching[0]["id"]
    summary = load_latest_summary(conn, session_id)

    if summary:
        print(f"\n\033[1mSummary: {session_name}\033[0m\n")
        print(f"\033[90m{summary}\033[0m\n")
    else:
        print_info(f"No summary yet for session: {session_name}")


# ── Entry point ──────────────────────────────────────────────────────────────────

def main():
    cli()


if __name__ == "__main__":
    main()
