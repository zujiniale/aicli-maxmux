#!/usr/bin/env python3
"""
app.py — aicli: A free, private, async CLI AI tool.

Commands:
  ask     — Single-shot prompt (default, --shell, --code, --describe)
  chat    — Persistent session with memory
  repl    — Interactive REPL loop
  export  — Export session to markdown or JSON
  agent   — Autonomous multi-step task execution
  config  — Configuration management (set-key, set, get, show, edit)
  provider — Provider management (status, test)
  session — Session management (list, show, delete, fork, fork --from-message N)

Usage:
  aicli ask "list python files in current dir"
  aicli ask --shell "find all large files"
  aicli ask --code "write a merge sort in Python"
  aicli ask --web "latest Python 3.13 features"
  aicli chat --session myproject
  aicli repl
  aicli export myproject > session.md
  aicli export myproject --format json > session.json
  aicli agent "set up a Python project with pytest"
  aicli agent --dry-run "deploy my app"
  aicli provider status
  aicli config set-key groq
  aicli session fork myproject
  aicli session fork myproject --from-message 12
  aicli config set TAVILY_API_KEY tvly-xxxx
  aicli config get TAVILY_API_KEY
"""

import asyncio

import click

from .config import load_config, get_api_key, save_api_key, CONFIG_FILE
from .printer import print_error, print_success, print_info, print_provider_status
from .db.chat_db import get_connection, list_sessions, load_messages, delete_session, fork_session

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
@click.version_option(version="1.2.0", prog_name="aicli")
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
@click.option("--web", "-w", is_flag=True, help="Search the web before answering (no API key required)")
@click.option("--web-debug", is_flag=True, help="Debug web search — show raw responses from all backends")
@click.option("--web-verbose", is_flag=True, help="Show all backends in --web-debug, including empty/failed ones")
@click.option("--cross-session", is_flag=True, help="Search RAG context across ALL sessions (requires --context)")
@click.option("--context-debug", is_flag=True, help="Show which sources were injected as context (requires --context)")
@click.option("--min-score", "min_score", default=0.40, type=float, help="Minimum similarity score for RAG context (default: 0.40)")
def ask(prompt, shell, code, describe, model, no_stream, json_output, dry_run, context, context_depth, images, web, web_debug, web_verbose, cross_session, context_debug, min_score):
    """Single-shot prompt. Pipe stdin or pass prompt as argument."""
    asyncio.run(_ask(prompt, shell, code, describe, model, no_stream, json_output, dry_run, context, context_depth, images=images or None, web=web, web_debug=web_debug, web_verbose=web_verbose, cross_session=cross_session, context_debug=context_debug, min_score=min_score))


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


@config.command("set")
@click.argument("key")
@click.argument("value")
def config_set(key, value):
    """Set any config key/env value. Stored in encrypted keys file.

    \b
    Examples:
      aicli session fork myproject
  aicli session fork myproject --from-message 12
  aicli config set TAVILY_API_KEY tvly-xxxx
      aicli config set OPENROUTER_API_KEY sk-or-xxxx
      aicli config set AICLI_PROXY socks5://127.0.0.1:9050
    """
    save_api_key(key, value)
    masked = value[:8] + "..." + value[-4:] if len(value) > 12 else "***"
    print_success(f"Saved: {key} = {masked}")


@config.command("get")
@click.argument("key")
def config_get(key):
    """Get a stored config value by key.

    \b
    Examples:
      aicli config get TAVILY_API_KEY
      aicli config get OPENROUTER_API_KEY
    """
    from .config import get_config_value
    value = get_config_value(key)
    if value:
        masked = value[:8] + "..." + value[-4:] if len(value) > 12 else "***"
        print_success(f"{key} = {masked}")
    else:
        print_error(f"No value found for: {key}")


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
    print("\n\033[1mOptional env vars\033[0m\n")
    print("  TAVILY_API_KEY        Tavily         — web search (--web flag, 1000 req/month free)")
    print("  AICLI_PROXY           Proxy/Tor      — e.g. socks5://127.0.0.1:9050")
    print()
    print("\033[1mTip:\033[0m  aicli config set KEY value  — stores any key in the encrypted keys file")
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
    print(f"\n{'ID':<10} {'Name':<28} {'Msgs':<6} {'Updated'}")
    print("─" * 60)
    for s in sessions:
        updated = s["updated_at"][:10] if s["updated_at"] else "unknown"
        sid = s["id"][:8]  # show short ID but user can use full name
        print(f"{sid:<10} {s['name']:<28} {s['message_count']:<6} {updated}  ({s['id']})")
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
@click.option("--image", "-i", "images", multiple=True, type=click.Path(exists=True), help="Image path(s) to include (vision providers only: OpenRouter, Gemini)")
def agent(task, model, dry_run, yes, images):
    """Autonomous multi-step agent. Plans and executes shell commands to complete a task."""
    asyncio.run(_agent(" ".join(task), model, dry_run, yes, images=list(images) if images else None))


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


# ── session fork ─────────────────────────────────────────────────────────────────

@session.command("fork")
@click.argument("session_name")
@click.option("--from-message", "from_message", default=None, type=int,
              help="Copy messages up to and including this message ID (default: all)")
@click.option("--name", "fork_name", default=None,
              help="Name for the new forked session (default: <source>-fork-<n>)")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
def session_fork(session_name, from_message, fork_name, yes):
    """Fork a session — copy its messages into a new session to explore alternatives.

    \b
    Examples:
      aicli session fork myproject                        # copy all messages
      aicli session fork myproject --from-message 12      # copy messages 1-12
      aicli session fork myproject --name myproject-v2   # custom fork name
    """
    conn = get_connection()
    sessions = list_sessions(conn)
    matching = [s for s in sessions if s["name"] == session_name or s["id"] == session_name]
    if not matching:
        print_error(f"Session not found: {session_name}")
        return

    source = matching[0]
    source_id   = source["id"]
    source_name = source["name"]
    msg_count   = source["message_count"]

    # Auto-generate fork name if not provided: myproject-fork-1, -2, ...
    if not fork_name:
        existing_names = {s["name"] for s in sessions}
        idx = 1
        while f"{source_name}-fork-{idx}" in existing_names:
            idx += 1
        fork_name = f"{source_name}-fork-{idx}"

    if from_message is not None and from_message < 1:
        print_error("--from-message must be >= 1")
        return

    desc = f"messages 1-{from_message} of {msg_count}" if from_message is not None else f"all {msg_count} messages"

    if not yes:
        print(f"\n  Fork  : {source_name} -> {fork_name}")
        print(f"  Copy  : {desc}")
        confirm = input("  Proceed? [y/N] ")
        if confirm.lower() != "y":
            print("  Cancelled.")
            return

    try:
        new_id = fork_session(conn, source_id, fork_name, up_to_message_id=from_message)
        copied = len(load_messages(conn, new_id))
        print_success(f"Forked -> '{fork_name}' ({copied} messages copied)")
        print(f"  Continue: aicli chat --session {fork_name}")
    except ValueError as e:
        print_error(str(e))




# ── session rename ────────────────────────────────────────────────────────────────

@session.command("rename")
@click.argument("session_name")
@click.argument("new_name")
def session_rename(session_name, new_name):
    """Rename a session.

    \b
    Examples:
      aicli session rename fa2bffaf myproject
      aicli session rename old-name new-name
    """
    conn = get_connection()
    sessions = list_sessions(conn)
    matching = [s for s in sessions if s["name"] == session_name or s["id"] == session_name]
    if not matching:
        print_error(f"Session not found: {session_name}")
        return

    # Check new name isn't already taken
    taken = [s for s in sessions if s["name"] == new_name and s["id"] != matching[0]["id"]]
    if taken:
        print_error(f"Name already in use: {new_name}")
        return

    session_id = matching[0]["id"]
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    conn.execute("UPDATE sessions SET name = ?, updated_at = ? WHERE id = ?", (new_name, now, session_id))
    conn.commit()
    print_success(f"Renamed '{session_name}' → '{new_name}'")


# ── session summarize ─────────────────────────────────────────────────────────────

@session.command("summarize")
@click.argument("session_name")
@click.option("--model", "-m", default=None, help="Override model for summarization")
@click.option("--print-only", is_flag=True, help="Print result but do not save to DB")
def session_summarize(session_name, model, print_only):
    """Generate (or regenerate) a summary for a session without resuming it.

    \b
    Examples:
      aicli session summarize myproject
      aicli session summarize fa2bffaf --model groq
      aicli session summarize myproject --print-only
    """
    import asyncio as _asyncio

    conn = get_connection()
    sessions = list_sessions(conn)
    matching = [s for s in sessions if s["name"] == session_name or s["id"] == session_name]
    if not matching:
        print_error(f"Session not found: {session_name}")
        return

    source = matching[0]
    session_id   = source["id"]
    source_name  = source["name"]
    msg_count    = source["message_count"]

    if msg_count < 4:
        print_error(f"Session '{source_name}' has only {msg_count} messages — need at least 4 to summarize.")
        return

    print_info(f"Summarizing '{source_name}' ({msg_count} messages)...")

    async def _run():
        from .config import load_config
        from .providers.pipeline import ProviderPipeline, ProviderExhaustedError
        from .context.manager import ContextManager

        config = load_config()
        try:
            pipeline = ProviderPipeline(
                provider_chain=config["provider_chain"],
                cooldown_seconds=config["cooldown_seconds"],
                max_retries_per_provider=config["max_retries_per_provider"],
            )
            if model:
                pipeline._model_override = model
        except ProviderExhaustedError as e:
            print_error(str(e))
            return

        ctx = ContextManager(
            session_id=session_id,
            pipeline=pipeline,
            session_name=source_name,
            config=config,
        )
        await ctx.initialize()

        # Temporarily disable saving if --print-only
        if print_only:
            from aicli.db import chat_db as _cdb
            _orig_save = _cdb.save_summary
            _cdb.save_summary = lambda *a, **kw: None

        summary = await ctx.summarize_now()

        if print_only:
            _cdb.save_summary = _orig_save

        if summary:
            print(f"\n[1mSummary: {source_name}[0m\n")
            print(f"[90m{summary}[0m\n")
            if not print_only:
                print_success("Summary saved.")
        else:
            print_error("Summarization failed or returned empty.")

    _asyncio.run(_run())


# ── Entry point ──────────────────────────────────────────────────────────────────

def main():
    cli()


if __name__ == "__main__":
    main()
