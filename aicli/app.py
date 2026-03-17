#!/usr/bin/env python3
"""
app.py — aicli: A free, private, async CLI AI tool.

Commands:
  ask     — Single-shot prompt (default, --shell, --code, --describe, --run, --lite, --quiet)
  cmd     — Quick shell command generation (shorthand for ask --shell)
  code    — Quick code generation (shorthand for ask --code)
  setup   — Interactive first-time setup wizard
  chat    — Persistent session with memory
  repl    — Interactive REPL loop
  export  — Export session to markdown or JSON
  agent   — Autonomous multi-step task execution
  config  — Configuration management (set-key, set, get, show, edit, install-shell)
  provider — Provider management (status, test)
  session — Session management (list, show, delete, fork, fork --from-message N)
  tui     — Full terminal UI (session list, chat, themes, graph export)
  graph   — Interactive D3 session graph viewer (local HTTP server, auto-load)
  serve   — Local HTTP API server (POST /ask, GET /sessions, GET /health)
  tag     — Tag a session for graph filtering (aicli tag SESSION TAG1 TAG2)
  mcp     — MCP server for Claude Desktop (stdio or SSE transport)
  history — Semantic search across all past sessions (aicli history "query")
  stats   — Token usage and message counts per session (aicli stats)
  plugin  — Plugin management (list, run, errors, install, doc)

Usage (no subcommand needed for ask):
  aicli "list python files in current dir"
  aicli "find all large files" --shell
  aicli ask "list python files in current dir"  # explicit form also works
  aicli ask --shell "find all large files"
  aicli ask --shell --lite "find all large files"
  aicli ask --quiet "what is my public IP"
  aicli ask --code "write a merge sort in Python"
  aicli ask --code --run "write a fibonacci function"
  aicli ask --code --run --language bash "list all git branches"
  aicli ask --code --run --language node "fetch and print a URL"
  aicli ask --web "latest Python 3.13 features"
  aicli cmd "find all large files"
  aicli cmd "kill process on port 3000" --run
  aicli cmd "list docker containers" --dry-run
  aicli code "write a merge sort in Python"
  aicli code "fibonacci function" --run
  aicli code "parse a CSV file" --run --language bash
  aicli setup
  aicli chat --session myproject
  aicli repl
  aicli export myproject > session.md
  aicli export myproject --format json > session.json
  aicli export myproject --obsidian > myproject.md
  aicli export myproject --obsidian --include-summary -o ~/vault/myproject.md
  aicli agent "set up a Python project with pytest"
  aicli agent --dry-run "deploy my app"
  aicli provider status
  aicli config set-key groq
  aicli config install-shell
  aicli config install-shell --shell zsh --hotkey "^L"
  aicli config install-shell --shell powershell
  aicli session fork myproject
  aicli session fork myproject --from-message 12
  aicli config set TAVILY_API_KEY tvly-xxxx
  aicli config get TAVILY_API_KEY
  aicli tui
  aicli tui --session myproject
  aicli graph
  aicli graph --port 8080 --no-browser
  aicli serve
  aicli serve --port 9000
  aicli plugin list
  aicli plugin install https://example.com/my_tool.py
  aicli tag myproject work python urgent
  aicli mcp
  aicli mcp --transport sse --port 8766
  aicli history "async python patterns"
  aicli history "docker deploy" --results 10
  aicli stats
  aicli stats --session myproject
  aicli serve --daemon
  aicli serve stop
  aicli plugin doc my_tool
  aicli ask --watch "alert on OOM" < <(tail -f /var/log/syslog)
  aicli ask -f error.log -f screenshot.png "what caused this"
  aicli ask --shell "why is this failing"  # Ctrl+G auto-fills terminal context
  aicli do "play music and open hacker news"
  aicli do "send email to alice@example.com just say hi"
  aicli do "summarize /tmp/docs/report.txt"
  aicli do --dry-run "open hacker news and play music"
  aicli do --auto-confirm "open https://news.ycombinator.com"
  aicli cmd --chain "create nginx container mounting index.html from current folder"
  aicli tools list
  aicli tools audit
"""

import asyncio

import click

from aicli.__version__ import __version__
from .config import load_config, get_api_key, save_api_key, CONFIG_FILE, CONFIG_DIR
from .printer import print_error, print_success, print_info, print_provider_status
from .db.chat_db import get_connection, list_sessions, load_messages, delete_session, fork_session

from .handlers.default import _ask
from .handlers.chat import _chat
from .handlers.repl import _repl
from .handlers.index import _index
from .handlers.provider import _provider_status, _provider_test
from .handlers.export import _export
from .handlers.agent import _agent
from .handlers.serve import run_serve, stop_serve

# Optional RAG dependency — bound at module level so tests can patch aicli.app.ContextRetriever
# and aicli.app.CHROMA_DIR. A lazy import inside the function body makes those attributes
# invisible to unittest.mock.patch, causing AttributeError at patch __enter__.
try:
    from .context.retriever import ContextRetriever
    from .config import CHROMA_DIR as CHROMA_DIR  # re-export for patching
except ImportError:
    ContextRetriever = None  # type: ignore[assignment,misc]
    CHROMA_DIR = None  # type: ignore[assignment]


# ── CLI Group ────────────────────────────────────────────────────────────────────


def _detect_intent(prompt_text: str) -> str:
    """Detect whether a direct-invocation prompt is an action (→ do) or a query (→ ask).

    Returns 'do' when the prompt looks like an OS-level task, 'ask' otherwise.

    ShellGPT auto-routes between @FunctionCall and plain text answers. aicli does
    the same here: direct invocation checks intent before routing so the user never
    needs to know the "do" vs "ask" distinction.

    Action signals (any match → 'do'):
      - Starts with a strong action verb: play, open, send, create, run, kill, start,
        stop, restart, install, uninstall, launch, close, copy, move, delete, remove,
        write, save, notify, alert, check, get, fetch, download, upload, search,
        find (files/process), list (processes/ports), show (system info)
      - Contains "email to", "message to", "notification", "clipboard",
        "music", "browser", "docker", "container", "process", "port"
      - Explicit function-call keywords in prompt

    Query signals (→ 'ask' wins over weak action match):
      - Starts with "what", "why", "how", "when", "where", "who", "explain",
        "describe", "tell me", "is", "are", "does", "can you explain"
      - Ends with "?" (question)
      - No filesystem path + no action verb
    """
    import re
    text = prompt_text.strip().lower()

    # Hard query signals — always ask
    query_starts = (
        "what ", "why ", "how ", "when ", "where ", "who ", "which ",
        "explain ", "describe ", "tell me ", "is ", "are ", "does ",
        "can you explain", "what's ", "what is ", "what are ",
        "summarize ", "summary of ", "show me how",
    )
    if any(text.startswith(q) for q in query_starts) or text.endswith("?"):
        # Exception: "find files", "find process", "show memory", or any filesystem
        # path in the prompt (e.g. "summarize /tmp/docs/report.txt") are still actions
        action_exceptions = re.compile(
            r"\b(find\s+files?|find\s+process|show\s+(memory|disk|cpu|system|processes?|ports?))\b"
            r"|(?:^|[\s\"'])(/[a-z/]|~/)"   # /absolute or ~/home path anywhere in text
        )
        if not action_exceptions.search(text):
            return "ask"

    # Strong action verb at start of prompt
    # Ambiguous verbs (copy/move/write/save/create/run) are tightened with
    # object patterns to avoid false-positives on LLM instruction prompts
    # like "write a function", "create a mental model", "run me through X".
    action_verbs = re.compile(
        r"^(play|open|send|kill|start|stop|restart|install|uninstall|"
        r"launch|close|delete|remove|notify|alert|check\s+if|"
        r"get\s+clipboard|get\s+system|fetch|download|upload|search\s+for|"
        r"find\s+files?|find\s+process|list\s+process|list\s+ports?|"
        r"show\s+(memory|disk|cpu|system|processes?|ports?)|"
        r"read\s+file|write\s+file|make\s+file|touch |mkdir |"
        r"copy\s+(to\s+clipboard|this\s+to|file|files?)|"
        r"move\s+(file|files?|to\s+/|to\s+~)|"
        r"write\s+(to|into|hello|.+\.(txt|py|sh|html|json|yaml|md))|"
        r"save\s+(as|to|.+\.(txt|py|sh|html|json|yaml|md))|"
        r"create\s+(file|dir|folder|docker|container|nginx|db|database|"
        r".+\.(txt|py|sh|html|json|yaml|md))|"
        r"run\s+(docker|nginx|container|server|script|.+\.py|.+\.sh))\b"
    )
    if action_verbs.match(text):
        return "do"

    # Mid-prompt action signals
    action_patterns = re.compile(
        r"\b(email\s+to|message\s+to|notification|clipboard|music|"
        r"browser|docker|container|process\s+on\s+port|port\s+\d+|"
        r"browse\s+media|browse\s+my|pick\s+a\s+song|pick\s+a\s+file|"
        r"show\s+me\s+my\s+(music|video|media|files?|songs?)|"
        r"list\s+(my\s+)?(music|video|media|songs?|files?)|"
        r"play\s+the\s+(song|file|video|music)|"
        r"\.mp3|\.mp4|\.mkv|\.wav|\.flac|\.ogg|\.m4a|"
        r"\.py|\.sh|\.txt|\.html|\.json|\.yaml|\.md)\b"
        r"|(/[a-z]|~/)"   # filesystem path
    )
    if action_patterns.search(text):
        return "do"

    return "ask"


class _FallbackGroup(click.Group):
    """Click Group that enables direct invocation: aicli "prompt".

    Without this, Click raises "No such command 'explain'" when the user runs
    ``aicli explain async await`` because Click tries to resolve the first
    positional arg as a subcommand name before ``cli()`` is ever called.

    ``parse_args`` is overridden to detect this case early: if the first
    non-flag token is not a registered command, all args are stored in
    ``ctx.args`` and Click is told there are no more tokens to consume.
    The ``cli()`` callback then reads ``ctx.args`` and routes to ``ask`` or ``do``
    based on intent detection.

    This also eliminates the ``ctx.protected_args`` DeprecationWarning
    (removed in Click 9.0).
    """

    def parse_args(self, ctx: click.Context, args: list) -> list:
        first_positional = next((a for a in args if not a.startswith("-")), None)
        if first_positional and first_positional not in self.commands:
            ctx.args = list(args)
            return []
        return super().parse_args(ctx, args)


@click.group(cls=_FallbackGroup, invoke_without_command=True,
             context_settings={"ignore_unknown_options": True})
@click.pass_context
@click.version_option(version=__version__, prog_name="aicli")
def cli(ctx):
    """aicli — Free, private, async CLI AI.

    \b
    Quick start (no subcommand needed):
      aicli "play music and open hacker news"   # → do (action detected)
      aicli "send email to alice@example.com say hi"  # → do
      aicli "explain async/await in Python"     # → ask (question detected)
      aicli "find files larger than 100MB" -s   # → ask --shell
      aicli "write a merge sort" -c             # → ask --code
      aicli ask "your prompt"    # explicit subcommand also works
      aicli do "your task"       # force function-calling mode

    \b
    Run 'aicli --help' for all commands.
    """
    if ctx.invoked_subcommand is None:
        # Direct invocation: aicli "prompt" → route to ask.
        # _FallbackGroup.parse_args() already stored the raw token list in
        # ctx.args when the first positional arg was not a known subcommand,
        # so we read ctx.args directly here (no ctx.protected_args needed).
        args = ctx.args
        if not args:
            # No args at all → show help
            click.echo(ctx.get_help())
            return
        non_flag = [a for a in args if not a.startswith("-")]
        known_cmds = [c.name for c in cli.commands.values()]
        if non_flag and non_flag[0] not in known_cmds:
            # Detect intent: action tasks → do, questions/queries → ask
            prompt_text = " ".join(non_flag)
            intent = _detect_intent(prompt_text)
            try:
                if intent == "do":
                    # Route to 'do': natural language task → OS function calling
                    # Flags like --dry-run, --auto-confirm still work
                    sub_ctx = do_command.make_context("do", list(args), parent=ctx)
                    with sub_ctx:
                        do_command.invoke(sub_ctx)
                else:
                    # Route to 'ask': question or ambiguous prompt → LLM response
                    # make_context parses args through ask's full Click option set,
                    # so --role, --no-cache, --watch-lines etc. all just work.
                    sub_ctx = ask.make_context("ask", list(args), parent=ctx)
                    with sub_ctx:
                        ask.invoke(sub_ctx)
            except click.exceptions.UsageError as e:
                print_error(str(e))
            except SystemExit:
                pass
        else:
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
@click.option("--run", "-r", is_flag=True, help="Execute generated code immediately (use with --code)")
@click.option("--max-retries", "max_retries", default=3, type=int, help="Max self-correction retries when --run fails (default: 3)")
@click.option("--language", "language", default="python", type=click.Choice(["python", "bash", "node", "ruby"]), help="Runtime for --run (default: python)")
@click.option("--timeout", "timeout", default=30, type=int, help="Subprocess timeout in seconds for --run (default: 30)")
@click.option("--lite", is_flag=True, help="Lite mode: skip RAG/ChromaDB init. Faster cold start, lower footprint.")
@click.option("--quiet", "-q", is_flag=True, help="Quiet mode: raw output only, no provider footer or status messages.")
@click.option("--terminal-context", "terminal_context", default=None, hidden=True,
              help="Last N lines of terminal scrollback injected as context (set by Ctrl+G hotkey automatically).")
@click.option("--watch", is_flag=True,
              help="Watch mode: read stdin line-by-line (e.g. tail -f log) and alert when AI detects the condition.")
@click.option("--watch-lines", "watch_lines", default=10, type=int,
              help="Lines buffered per LLM evaluation in --watch mode (default: 10).")
@click.option("--file", "-f", "extra_files", multiple=True, type=click.Path(exists=True),
              help="Attach any file (text, log, code) as context. Combine with --image for mixed multimodal prompts.")
@click.option("--no-cache", "no_cache", is_flag=True,
              help="Bypass response cache — always call the LLM even if this prompt was cached.")
@click.option("--role", "role", default=None,
              help="Custom role name for system prompt (e.g. 'shell', 'code', 'default', or any custom role you've defined).")
@click.option("--do", "watch_do", default=None,
              help="On --watch trigger: automatically run this aicli do action (auto-confirm). "
                   "Example: --watch 'OOM killer' --do 'send_notification title=OOM body=check logs'")
def ask(prompt, shell, code, describe, model, no_stream, json_output, dry_run, context, context_depth, images, web, web_debug, web_verbose, cross_session, context_debug, min_score, run, max_retries, language, timeout, lite, quiet, terminal_context, watch, watch_lines, extra_files, no_cache, role, watch_do):
    """Single-shot prompt. Pipe stdin or pass prompt as argument.

    \b
    Context-aware examples:
      aicli ask --shell "why is this failing"         # Ctrl+G injects terminal context automatically
      tail -f app.log | aicli ask --watch "alert on ERROR"
      aicli ask -f error.log -f screenshot.png "what caused this crash"
    """
    # ── First-run guard: friendly message if no providers configured ───────────
    # Detects zero keys so user gets one clear message instead of 5 provider
    # failure lines. Fastest free path: Groq key takes ~30 seconds to get.
    _providers = ["groq", "openrouter", "gemini", "mistral"]
    if not any(get_api_key(p) for p in _providers) and        not any(__import__("os").environ.get(f"AICLI_{p.upper()}_KEY") for p in _providers) and        not __import__("os").environ.get("OLLAMA_HOST", ""):
        import os as _os
        if not _os.environ.get("OLLAMA_HOST"):
            print_error("No AI provider configured.")
            print_info("  Fastest free option (30 sec): https://console.groq.com/keys")
            print_info("  Then run: aicli config set-key groq")
            print_info("  Or run:   aicli setup   (interactive wizard for all providers)")
            print_info("  Already have OPENAI_API_KEY set? aicli config set-key openrouter")
            return
    asyncio.run(_ask(
        prompt, shell, code, describe, model, no_stream, json_output, dry_run,
        context, context_depth, images=images or None, web=web,
        web_debug=web_debug, web_verbose=web_verbose, cross_session=cross_session,
        context_debug=context_debug, min_score=min_score, run=run,
        max_retries=max_retries, language=language, timeout=timeout,
        lite=lite, quiet=quiet,
        terminal_context=terminal_context or None,
        watch=watch, watch_lines=watch_lines,
        extra_files=extra_files or None,
        no_cache=no_cache,
        role=role or None,
        watch_do=watch_do or None,
    ))


# ── cmd ──────────────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("prompt", nargs=-1, required=True)
@click.option("--model", "-m", default=None, help="Override model")
@click.option("--run", "-r", is_flag=True, help="Execute immediately without menu")
@click.option("--dry-run", is_flag=True, help="Print command only, no menu")
@click.option("--chain", is_flag=True, help="Generate and run a SEQUENCE of commands from one prompt (multi-step chaining)")
@click.option("--auto-confirm", "auto_confirm", is_flag=True, help="Execute all chained commands without individual prompts (use carefully)")
@click.option("--role", "chain_role", default=None, help="Custom system prompt role for --chain command generation.")
@click.option("--lite", is_flag=True, help="Lite mode: skip RAG/ChromaDB init.")
@click.option("--quiet", "-q", is_flag=True, help="Quiet mode: raw output only, no status messages.")
def cmd(prompt, model, run, dry_run, chain, auto_confirm, chain_role, lite, quiet):
    """Quick shell command generation. Shorthand for: ask --shell

    \b
    Examples:
      aicli cmd "find all files larger than 100MB"
      aicli cmd "kill process on port 3000" --run
      aicli cmd "list docker containers sorted by size" --dry-run
      aicli cmd --chain "create nginx container mounting index.html from current folder"
      aicli cmd --chain --auto-confirm "init git repo, add all files, commit"
      aicli cmd --chain --role "senior devops" "deploy the app to staging"
    """
    if chain:
        asyncio.run(_cmd_chain(prompt, model=model, auto_confirm=auto_confirm,
                               dry_run=dry_run, quiet=quiet, role=chain_role))
        return
    asyncio.run(_ask(
        prompt,
        shell=True,
        code=False,
        describe=False,
        model=model,
        no_stream=False,
        json_output=False,
        dry_run=dry_run,
        run=run,
        lite=lite,
        quiet=quiet,
    ))



# ── _cmd_chain — multi-command sequencing ────────────────────────────────────

async def _cmd_chain(
    prompt_parts,
    model=None,
    auto_confirm: bool = False,
    dry_run: bool = False,
    quiet: bool = False,
    role: str | None = None,
) -> None:
    """Generate a sequence of shell commands from one prompt and run them in order.

    Better than ShellGPT: each step is numbered, shown before execution,
    requires individual confirmation (or --auto-confirm for all), and a failed
    step stops the chain with the exact error + a suggested fix — no silent
    partial executions.

    Example flow:
        aicli cmd --chain "create nginx container mounting index.html from current folder"
        [1/3] touch index.html           — run? [Y/n]
        [2/3] echo "<h1>hello</h1>" > index.html  — run? [Y/n]
        [3/3] docker run -d -p 80:80 ...  — run? [Y/n]
        ✓ All 3 steps completed.
    """
    import subprocess as _subprocess
    from .config import load_config as _load_config
    from .providers.pipeline import ProviderPipeline, ProviderExhaustedError
    from .printer import print_error as _perr, print_info as _pinfo, print_success as _psuc

    prompt_text = " ".join(prompt_parts) if prompt_parts else ""
    if not prompt_text:
        _perr("No prompt provided.")
        return

    config = _load_config()

    # Use custom role system prompt if provided, else default chain generator
    if role:
        try:
            from .role import get_role as _get_role
            _role_obj = _get_role(role)
            chain_system = _role_obj.system_prompt
        except Exception:
            chain_system = role  # treat as literal system prompt string
    else:
        chain_system = (
            "You are a shell command sequence generator. "
            "The user will describe a multi-step task. "
            "Output ONLY a numbered list of shell commands to accomplish it, one per line. "
            "Format: exactly one shell command per line, no explanations, no markdown fences. "
            "Example output:\n"
            "touch index.html\n"
            'echo "<h1>hello world</h1>" > index.html\n'
            "docker run -d -p 80:80 -v $(pwd)/index.html:/usr/share/nginx/html/index.html nginx:latest"
        )

    messages = [
        {"role": "system", "content": chain_system},
        {"role": "user", "content": prompt_text},
    ]

    try:
        pipeline = ProviderPipeline(
            provider_chain=config["provider_chain"],
            cooldown_seconds=config["cooldown_seconds"],
            max_retries_per_provider=config["max_retries_per_provider"],
            show_provider=False,
        )
        chunks = []
        async for chunk in pipeline.stream(messages, model=model, requires_vision=False):
            chunks.append(chunk)
        raw = "".join(chunks).strip()
    except ProviderExhaustedError as e:
        _perr(f"All providers failed: {e}")
        return

    # Parse: strip leading numbers like "1." or "1)" or "- "
    import re as _re
    lines = [_re.sub(r'^[\d]+[.)]\s*|^[-•]\s*', '', l).strip()
             for l in raw.splitlines() if l.strip()]
    commands = [l for l in lines if l and not l.startswith("#")]

    if not commands:
        _perr("No commands generated. Try rephrasing the prompt.")
        return

    total = len(commands)
    if not quiet:
        _pinfo(f"Generated {total} command(s) for: {prompt_text[:70]}")

    completed = 0
    for idx, command in enumerate(commands, 1):
        step_label = f"[{idx}/{total}]"

        if dry_run:
            print(f"\033[1;36m{step_label}\033[0m {command}")
            print(f"\033[90m  (dry-run — not executed)\033[0m")
            continue

        # Show command + confirm
        print(f"\n\033[1;36m{step_label}\033[0m \033[1m{command}\033[0m")

        if not auto_confirm:
            try:
                ans = input("  Run? [Y/n/s(kip)/q(uit)] ").strip().lower()
            except (KeyboardInterrupt, EOFError):
                print("\n(chain aborted)")
                break
            if ans in ("q", "quit"):
                _pinfo("Chain aborted by user.")
                break
            if ans in ("s", "skip"):
                _pinfo(f"  Skipped step {idx}.")
                continue
            if ans not in ("", "y", "yes"):
                _pinfo(f"  Skipped step {idx}.")
                continue

        # Execute
        try:
            result = _subprocess.run(
                command, shell=True, text=True,
                capture_output=False,   # stream output live — user sees it in real time
                timeout=120,
            )
            if result.returncode != 0:
                _perr(f"  Step {idx} failed (exit {result.returncode}).")
                if not quiet:
                    # Offer Ctrl+E-style fix suggestion inline
                    _pinfo("  Tip: run 'aicli cmd --chain' again or use Ctrl+E for a fix.")
                break
            completed += 1
        except _subprocess.TimeoutExpired:
            _perr(f"  Step {idx} timed out after 120s.")
            break
        except KeyboardInterrupt:
            print("\n(chain interrupted)")
            break

    if not dry_run and not quiet:
        if completed == total:
            _psuc(f"✓ All {total} step(s) completed.")
        else:
            _pinfo(f"Completed {completed}/{total} step(s).")


# ── do — LLM function calling with OS tool dispatch ──────────────────────────

@cli.command("do")
@click.argument("prompt", nargs=-1, required=True)
@click.option("--model", "-m", default=None, help="Override model")
@click.option("--dry-run", is_flag=True,
              help="Show which tool calls would be made without executing anything")
@click.option("--confirm", "require_confirm", is_flag=True,
              help="Prompt [Y/n] before each tool call (default: execute immediately like ShellGPT).")
@click.option("--quiet", "-q", is_flag=True, help="Quiet mode: minimal output")
@click.option("--role", "role", default=None,
              help="Custom role / system prompt for the function-calling LLM (default: tool-dispatcher role)")
@click.option("--retries", "max_retries", default=1, type=int,
              help="Max retry attempts per tool on transient failure (default: 1).")
@click.option("--session", "do_session", default=None,
              help="Session name for multi-turn do: loads prior conversation history as context.")
@click.option("--verbose", "-v", is_flag=True,
              help="Show tool count and provider info (hidden by default for clean ShellGPT-style output).")
def do_command(prompt, model, dry_run, require_confirm, quiet, role, max_retries, do_session, verbose):
    """Execute tasks by calling OS tools: open browser, play music, send email, and more.

    \b
    The LLM decides which tools to call based on your prompt.
    You are shown each tool call before it runs and must confirm (or use --auto-confirm).
    Every action is logged to ~/.config/aicli/tool_audit.jsonl.

    \b
    Available tools (aicli tools list):
      open_url_in_browser   — open a URL in the default browser
      play_music            — play music via system media player or Spotify
      send_email            — send email via system mail or configured SMTP
      send_notification     — send a desktop notification
      get_clipboard         — read clipboard content
      copy_to_clipboard     — copy text to clipboard
      open_file             — open any file with default application
      read_file_content     — read a file (auto-detected from paths in prompt)
      write_file_content    — write or create a file
      search_web            — search the web and return results
      get_system_info       — show OS, CPU, memory, disk usage
      run_shell_command     — run an arbitrary shell command (always requires confirm)

    \b
    Better than ShellGPT @FunctionCall:
      - Confirmation gate before every action (skip with --auto-confirm)
      - Dry-run mode shows calls without executing
      - Full audit log at ~/.config/aicli/tool_audit.jsonl
      - File read size-capped at 50 KB (prevents prompt injection)
      - File writes restricted to home dir and cwd
      - Tool retry on transient failure
      - Natural language summary after execution ("Music is now playing...")
      - Multi-turn sessions: --session keeps tool results in context across calls

    \b
    Examples:
      aicli do "play music and open hacker news"
      aicli do "send email to alice@example.com just say hi"
      aicli do "summarize /tmp/docs/report.txt"
      aicli do --dry-run "open hacker news and play music"
      aicli do "notify me the build is done"                # runs immediately
      aicli do --confirm "delete all logs older than 7 days"   # asks Y/n per step
      aicli do --role shell "check if port 3000 is open"
      aicli do --session myproject "open that file"
      aicli do --session myproject "now summarize it"
    """
    from .tools.executor import run_do_command
    asyncio.run(run_do_command(
        prompt,
        auto_confirm=not require_confirm,
        dry_run=dry_run,
        quiet=quiet if not verbose else False,
        model=model,
        lite=False,
        role=role or None,
        max_retries=max_retries,
        session_id=do_session or None,
        verbose=verbose,
    ))


# ── tools — tool management (list, audit) ────────────────────────────────────

@cli.group("tools")
def tools_group():
    """Manage and inspect aicli OS tools (function calling)."""
    pass


@tools_group.command("list")
def tools_list():
    """List all registered OS tools available for function calling.

    \b
    Example:
      aicli tools list
    """
    try:
        import aicli.tools.os_functions  # noqa: F401 — ensure tools registered
    except ImportError:
        pass
    from .tools.registry import TOOL_REGISTRY
    if not TOOL_REGISTRY:
        print_info("No tools registered.")
        return
    print(f"\n\033[1m{'Tool':<28} {'Confirm?':<10} Description\033[0m")
    print("─" * 78)
    for name, entry in TOOL_REGISTRY.items():
        confirm_str = "\033[33m✓ yes\033[0m" if entry["confirm"] else "\033[32m─ no\033[0m "
        desc = entry["description"][:46] + "…" if len(entry["description"]) > 47 else entry["description"]
        print(f"  {name:<26} {confirm_str:<18} {desc}")
    print(f"\n  Total: {len(TOOL_REGISTRY)} tool(s)  |  Use: aicli do \"your task\"\n")


@tools_group.command("audit")
@click.option("--last", "-n", default=20, type=int, help="Show last N entries (default: 20)")
@click.option("--tool", default=None, help="Filter by tool name")
def tools_audit(last, tool):
    """Show the tool execution audit log.

    \b
    Every aicli do execution is logged to:
      ~/.config/aicli/tool_audit.jsonl

    \b
    Examples:
      aicli tools audit
      aicli tools audit --last 50
      aicli tools audit --tool send_email
    """
    import json as _json
    from .tools.executor import _audit_log_path
    log_path = _audit_log_path()
    if not log_path.exists():
        print_info("No audit log yet. Run: aicli do \"your task\"")
        return
    try:
        lines = log_path.read_text(encoding="utf-8").splitlines()
    except OSError as e:
        print_error(f"Could not read audit log: {e}")
        return
    entries = []
    for line in lines:
        try:
            entry = _json.loads(line)
            if tool is None or entry.get("tool") == tool:
                entries.append(entry)
        except _json.JSONDecodeError:
            continue
    entries = entries[-last:]
    if not entries:
        print_info(f"No audit entries found{f' for tool: {tool}' if tool else ''}.")
        return
    print(f"\n\033[1m{'Timestamp':<22} {'Tool':<28} {'Decision':<16} {'OK':<5} Result\033[0m")
    print("─" * 100)
    for e in entries:
        ts = e.get("ts", "?")[:19]
        t = e.get("tool", "?")[:26]
        decision = e.get("decision", "?")[:14]
        ok = "\033[32m✓\033[0m" if e.get("ok") else "\033[31m✗\033[0m"
        result = (e.get("result") or "")[:40]
        print(f"  {ts:<22} {t:<28} {decision:<16} {ok:<5} {result}")
    print(f"\n  {len(entries)} entry/entries shown  |  Log: {log_path}\n")


# ── code ──────────────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("prompt", nargs=-1, required=True)
@click.option("--model", "-m", default=None, help="Override model")
@click.option("--run", "-r", is_flag=True, help="Execute generated code immediately")
@click.option("--language", "language", default="python",
              type=click.Choice(["python", "bash", "node", "ruby"]),
              help="Runtime for --run (default: python)")
@click.option("--max-retries", "max_retries", default=3, type=int,
              help="Max self-correction retries when --run fails (default: 3)")
@click.option("--timeout", "timeout", default=30, type=int,
              help="Subprocess timeout in seconds for --run (default: 30)")
@click.option("--lite", is_flag=True, help="Lite mode: skip RAG/ChromaDB init.")
@click.option("--quiet", "-q", is_flag=True, help="Quiet mode: raw output only.")
def code(prompt, model, run, language, max_retries, timeout, lite, quiet):
    """Quick code generation. Shorthand for: ask --code

    \b
    Examples:
      aicli code "write a merge sort in Python"
      aicli code "fibonacci function" --run
      aicli code "parse a CSV file" --run --language bash
      aicli code "fetch and print a URL" --run --language node
    """
    asyncio.run(_ask(
        prompt,
        shell=False,
        code=True,
        describe=False,
        model=model,
        no_stream=False,
        json_output=False,
        dry_run=False,
        run=run,
        language=language,
        max_retries=max_retries,
        timeout=timeout,
        lite=lite,
        quiet=quiet,
    ))


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



@config.command("migrate-keys")
def config_migrate_keys():
    """Migrate keys from OS keyring into the Fernet encrypted backup file.

    \b
    Run this once after upgrading from pre-1.2.0 to ensure all keys work
    under Tor, Docker, SSH, or any environment where the OS keychain
    (D-Bus / SecretService) may be inaccessible.

    Examples:
      aicli config migrate-keys
    """
    from .config import migrate_all_keys
    print_info("Reading keys from OS keyring...")
    migrated = migrate_all_keys()
    if migrated:
        for k in migrated:
            print_success(f"Migrated: {k}")
        print_success(f"\n{len(migrated)} key(s) written to Fernet backup file.")
        print_info("Keys now work in all process contexts (Tor, headless, Docker).")
    else:
        print_info("No keys found in OS keyring to migrate.")
        print_info("If keys are set, use: aicli config set KEY value")


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


@config.command("install-shell")
@click.option("--shell", "shell_type",
              type=click.Choice(["zsh", "bash", "powershell"]), default=None,
              help="Shell type (auto-detected from $SHELL if not set)")
@click.option("--hotkey", default="^G",
              help="Hotkey binding (default: Ctrl+G = ^G)")
def config_install_shell(shell_type, hotkey):
    """Install aicli hotkey integration into your shell rc file.

    \b
    Adds a hotkey (Ctrl+G by default) that pastes AI-generated
    shell commands directly into your terminal buffer.

    \b
    Examples:
      aicli config install-shell
      aicli config install-shell --shell zsh
      aicli config install-shell --shell powershell
      aicli config install-shell --hotkey "^L"
    """
    import os
    import shutil
    from pathlib import Path

    detected = shell_type or os.environ.get("SHELL", "").split("/")[-1]

    # ── PowerShell install ────────────────────────────────────────────────────
    if detected == "powershell":
        # Look for ps1 in the package dir first, then project root fallback
        src = Path(__file__).parent / "shell_integration.ps1"
        if not src.exists():
            src = Path(__file__).parent.parent / "shell_integration.ps1"
        if not src.exists():
            print_error("shell_integration.ps1 not found. Make sure aicli is up to date.")
            return

        dest = CONFIG_DIR / "shell_integration.ps1"
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy(src, dest)

        # $PROFILE candidates for PowerShell 7 and Windows PowerShell 5.1
        profile_candidates = [
            Path.home() / "Documents" / "PowerShell" / "Microsoft.PowerShell_profile.ps1",
            Path.home() / "Documents" / "WindowsPowerShell" / "Microsoft.PowerShell_profile.ps1",
        ]
        profile = next((p for p in profile_candidates if p.exists()), profile_candidates[0])
        source_line = f'\n. "{dest}"  # aicli shell integration\n'
        try:
            content = profile.read_text() if profile.exists() else ""
        except Exception:
            content = ""
        if str(dest) in content:
            print_info("PowerShell integration already installed.")
        else:
            profile.parent.mkdir(parents=True, exist_ok=True)
            with open(profile, "a") as f:
                f.write(source_line)
            print_success(f"Installed to {profile}")
            print_info("Restart PowerShell or run: . $PROFILE")
            print_info("Hotkey: Ctrl+G — type a description, get a shell command in your buffer")
        return

    # ── zsh / bash install ────────────────────────────────────────────────────
    if detected not in ("zsh", "bash"):
        print_error(
            f"Could not detect shell: '{detected}'. "
            "Use --shell zsh, --shell bash, or --shell powershell"
        )
        return

    src = Path(__file__).parent / f"shell_integration.{detected}"
    if not src.exists():
        print_error(f"Shell integration script not found: {src}")
        print_info("Make sure aicli is up to date.")
        return

    dest = CONFIG_DIR / f"shell_integration.{detected}"
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy(src, dest)

    rc_file = Path.home() / (".zshrc" if detected == "zsh" else ".bashrc")
    source_line = f'\nsource "{dest}"  # aicli shell integration\n'

    try:
        rc_content = rc_file.read_text() if rc_file.exists() else ""
    except Exception:
        rc_content = ""

    # Strip any stale /tmp/ source lines from previous test runs or bad installs.
    # These lines look like: source "/tmp/tmpXXXXXX/shell_integration.zsh"
    import re as _re
    cleaned = _re.sub(
        r'\nsource "/tmp/[^"]+/shell_integration\.[^"]+"\s*#[^\n]*\n?',
        "",
        rc_content,
    )
    if cleaned != rc_content:
        try:
            rc_file.write_text(cleaned)
            rc_content = cleaned
        except Exception:
            pass  # best-effort cleanup

    if str(dest) in rc_content:
        print_info("Shell integration already installed.")
    else:
        with open(rc_file, "a") as f:
            f.write(source_line)
        print_success(f"Installed to {rc_file}")
        print_info(f"Restart your shell or run: source {rc_file}")
        print_info(f"Hotkey: Ctrl+G — type a description, get a shell command in your buffer")


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
@click.option("--include-summary", "include_summary", is_flag=True, help="Prepend latest auto-summary to export")
@click.option("--obsidian", is_flag=True, help="Obsidian-compatible markdown: YAML frontmatter, [[wikilinks]], callout blocks")
def export(session_name, fmt, output, include_summary, obsidian):
    """Export a session to markdown or JSON. Pipe with: aicli export mysession > out.md

    \b
    Examples:
      aicli export myproject > session.md
      aicli export myproject --include-summary > full.md
      aicli export myproject --format json > session.json
      aicli export myproject --obsidian > myproject.md
      aicli export myproject --obsidian --include-summary -o ~/vault/myproject.md
    """
    asyncio.run(_export(session_name, fmt, output, include_summary=include_summary, obsidian=obsidian))


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


# ── history search ────────────────────────────────────────────────────────────────

@cli.command("history")
@click.argument("query")
@click.option("--sessions", "-s", default=5, type=int, help="Number of sessions to search across (default: 5)")
@click.option("--results", "-n", default=5, type=int, help="Max results to show (default: 5)")
@click.option("--min-score", "min_score", default=0.25, type=float, help="Min similarity score (default: 0.25)")
def history_search(query, sessions, results, min_score):
    """Search across all past sessions semantically.

    \b
    Examples:
      aicli history "async python patterns"
      aicli history "docker deploy" --results 10
      aicli history "bug fix" --min-score 0.3
    """
    if ContextRetriever is None or CHROMA_DIR is None:
        print_error("history search requires: pip install aicli-maxmux[rag]")
        return

    retriever = ContextRetriever(CHROMA_DIR)
    status = retriever.status()
    if status["chat_chunks"] == 0:
        print_info("No chat history indexed yet.")
        print_info("Index your sessions first: aicli index --chat")
        return

    result = retriever.retrieve(
        query,
        include_files=False,
        include_chat=True,
        n_chat=results,
        min_score=min_score,
    )
    if not result:
        print_info(f"No results found for: {query!r}")
        return

    print(f"\n\033[1mSearch results for:\033[0m {query!r}\n")
    print(result)


# ── stats ─────────────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--session", "-s", default=None, help="Show stats for a specific session only")
@click.option("--top", "-n", default=10, type=int, help="Number of sessions to show (default: 10)")
def stats(session, top):
    """Show token usage and message counts across sessions.

    \b
    Examples:
      aicli stats                   # all sessions summary
      aicli stats --session myproject   # single session detail
      aicli stats --top 5           # top 5 sessions by message count
    """
    conn = get_connection()

    if session:
        # Single session detail
        all_sessions = list_sessions(conn)
        matching = [s for s in all_sessions if s["name"] == session or s["id"] == session]
        if not matching:
            print_error(f"Session not found: {session}")
            return
        s = matching[0]
        from .db.chat_db import load_messages, load_latest_summary
        messages = load_messages(conn, s["id"])
        summary = load_latest_summary(conn, s["id"])
        total_tokens = sum(m.get("token_count", 0) if isinstance(m, dict) else 0 for m in messages)
        user_msgs = [m for m in messages if m["role"] == "user"]
        asst_msgs = [m for m in messages if m["role"] == "assistant"]
        print(f"\n\033[1m{s['name']}\033[0m  \033[90m({s['id'][:8]})\033[0m")
        print(f"  Messages : {len(messages)} total  ({len(user_msgs)} user, {len(asst_msgs)} assistant)")
        print(f"  Tokens   : {total_tokens:,} stored")
        print(f"  Summary  : {'yes' if summary else 'none'}")
        print(f"  Updated  : {s.get('updated_at', 'unknown')[:16]}")
        print()
        return

    # All sessions summary
    all_sessions = list_sessions(conn)
    if not all_sessions:
        print_info("No sessions yet. Start with: aicli chat")
        return

    # Get per-session token totals from DB
    rows = conn.execute("""
        SELECT session_id,
               COUNT(*) as msg_count,
               SUM(token_count) as total_tokens
        FROM messages
        GROUP BY session_id
    """).fetchall()
    token_map = {r["session_id"]: (r["msg_count"], r["total_tokens"] or 0) for r in rows}

    grand_msgs = sum(r["msg_count"] for r in rows)
    grand_tokens = sum(r["total_tokens"] or 0 for r in rows)

    # Sort by message count descending
    sorted_sessions = sorted(
        all_sessions,
        key=lambda s: token_map.get(s["id"], (0, 0))[0],
        reverse=True
    )[:top]

    print(f"\n\033[1maicli stats\033[0m — {len(all_sessions)} sessions, {grand_msgs:,} messages, {grand_tokens:,} tokens\n")
    print(f"  {'Session':<28} {'Msgs':>6} {'Tokens':>10}  {'Updated'}")
    print(f"  {'─'*28} {'─'*6} {'─'*10}  {'─'*10}")
    for s in sorted_sessions:
        msg_count, tok_count = token_map.get(s["id"], (0, 0))
        updated = s.get("updated_at", "")[:10] if s.get("updated_at") else "unknown"
        print(f"  {s['name']:<28} {msg_count:>6} {tok_count:>10,}  {updated}")
    if len(all_sessions) > top:
        print(f"  \033[90m... {len(all_sessions) - top} more sessions (use --top N)\033[0m")
    print()

@cli.command()
def setup():
    """Interactive first-time setup wizard.

    \b
    Walks through:
      1. Setting API keys for each provider
      2. Installing optional shell hotkey integration
      3. Printing a quick-start summary

    \b
    Examples:
      aicli setup
    """
    providers = ["groq", "openrouter", "gemini", "mistral"]
    urls = {
        "groq":       "https://console.groq.com/keys",
        "openrouter": "https://openrouter.ai/keys",
        "gemini":     "https://aistudio.google.com/app/apikey",
        "mistral":    "https://console.mistral.ai/api-keys",
    }

    import os as _os

    # ── Zero-config detection: reuse keys that already exist in environment ──
    # Developers who already have OPENAI_API_KEY, GROQ_API_KEY etc. in their
    # environment don't need to go through setup at all. Detect and auto-save.
    ENV_KEY_MAP = {
        "GROQ_API_KEY":       "groq",
        "OPENROUTER_API_KEY": "openrouter",
        "GEMINI_API_KEY":     "gemini",
        "MISTRAL_API_KEY":    "mistral",
        # Common keys that map to compatible providers
        "OPENAI_API_KEY":     None,   # informational only — suggest openrouter
        "ANTHROPIC_API_KEY":  None,   # informational only
    }
    auto_saved = []
    for env_var, provider in ENV_KEY_MAP.items():
        val = _os.environ.get(env_var)
        if val and provider:
            existing = get_api_key(provider)
            if not existing:
                save_api_key(provider, val)
                auto_saved.append(f"{provider} (from {env_var})")
            else:
                auto_saved.append(f"{provider} (already saved)")

    if auto_saved:
        print_success(f"\nAuto-configured from environment: {', '.join(auto_saved)}")
        print_info("You can start immediately: aicli \"hello\"\n")

    # Check for OPENAI key — suggest openrouter as drop-in
    if _os.environ.get("OPENAI_API_KEY") and not get_api_key("openrouter"):
        print_info("  Tip: OPENAI_API_KEY detected. OpenRouter accepts OpenAI keys too.")
        print_info("  Try: aicli config set-key openrouter  (paste your OPENAI_API_KEY)\n")

    print_info("\nWelcome to aicli setup!\n")
    print_info("Configure your AI providers. Press Enter to skip any.\n")

    configured = []
    for provider in providers:
        existing = get_api_key(provider)
        if existing:
            print_success(f"  {provider:<14} ✓ already configured")
            configured.append(provider)
            continue
        print_info(f"  {provider} — free key at: {urls[provider]}")
        import getpass as _gp
        ans = _gp.getpass(f"  Enter {provider} API key (hidden, Enter to skip): ").strip()
        if ans:
            save_api_key(provider, ans)
            print_success(f"  ✓ Key saved for {provider}")
            configured.append(provider)
        else:
            print_info(f"  Skipped.\n")

    print_info("\n─────────────────────────────────────")
    if configured:
        print_success(f"\nConfigured: {', '.join(configured)}")
    else:
        print_info("\nNo providers configured.")
        print_info("Ollama (local, no key needed) is always available: https://ollama.ai")

    print_info("\nQuick-start:")
    print_info('  aicli ask "hello"')
    print_info('  aicli cmd "list files by size"')
    print_info("  aicli tui")
    print_info("\nTo install shell hotkey (Ctrl+G → generates commands in buffer):")
    print_info("  aicli config install-shell\n")


# ── tui ──────────────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--session", "-s", default=None, help="Open a specific session on launch")
@click.option("--model", "-m", default=None, help="Override model")
@click.option("--no-history", "no_history", is_flag=True, help="Don't load past messages on open")
def tui(session, model, no_history):
    """Full terminal UI — session list, chat, web toggle, context toggle.

    \b
    Keyboard shortcuts:
      Ctrl+N    New session
      Ctrl+D    Delete current session
      Ctrl+E    Export session to markdown
      Ctrl+W    Toggle web search
      Ctrl+X    Toggle RAG context
      Ctrl+S    Summarize current session
      Ctrl+Q    Quit

    Requires: pip install textual
    """
    try:
        from .tui import run_tui
    except ImportError:
        print_error("textual not installed. Run: pip install textual")
        return
    run_tui(session=session, model=model, no_history=no_history)


# ── plugin ───────────────────────────────────────────────────────────────────────

@cli.group()
def plugin():
    """Plugin management. Plugins live in ~/.config/aicli/plugins/"""
    pass


@plugin.command("list")
def plugin_list():
    """List all installed plugins."""
    from .tools.loader import list_plugins
    list_plugins()


@plugin.command("run")
@click.argument("plugin_name")
@click.argument("arg", default="")
def plugin_run(plugin_name, arg):
    """Run a plugin by name with an optional argument.

    \b
    Examples:
      aicli plugin run calculator "2 + 2 * 10"
      aicli plugin run my_tool "some input"
    """
    from .tools.loader import call_plugin, load_plugins
    load_plugins()  # trigger load + error reporting
    result = call_plugin(plugin_name, arg)
    if result is None:
        print_error(f"Plugin not found: {plugin_name}")
        print_info("Run: aicli plugin list")
    else:
        print(result)


@plugin.command("errors")
def plugin_errors():
    """Show any plugin load errors."""
    from .tools.loader import get_load_errors
    errors = get_load_errors()
    if not errors:
        print_success("No plugin load errors.")
    else:
        for err in errors:
            print_error(err)


@plugin.command("install")
@click.argument("url")
@click.option("--name", default=None, help="Override filename (without .py extension)")
def plugin_install(url, name):
    """Download and install a plugin from a URL.

    \b
    Example:
      aicli plugin install https://example.com/my_tool.py
      aicli plugin install https://example.com/tool.py --name my_tool
    """
    import urllib.request
    from .tools.loader import _plugins_dir
    plugins_dir = _plugins_dir()
    plugins_dir.mkdir(parents=True, exist_ok=True)
    filename = (name or url.rstrip("/").split("/")[-1].removesuffix(".py")) + ".py"
    dest = plugins_dir / filename
    try:
        print_info(f"Downloading {url} → {dest}")
        urllib.request.urlretrieve(url, dest)
        print_success(f"Installed: {filename}")
        print_info("Run: aicli plugin list")
    except Exception as e:
        print_error(f"Install failed: {e}")


@plugin.command("doc")
@click.argument("plugin_name")
def plugin_doc(plugin_name):
    """Show full description and source path for a plugin.

    \b
    Example:
      aicli plugin doc calculator
    """
    from .tools.loader import get_plugin_tools
    for tool in get_plugin_tools():
        if tool["name"] == plugin_name:
            print(f"\n\033[1m{tool['name']}\033[0m")
            ver    = f"  version: {tool['version']}" if tool.get("version") else ""
            author = f"  author:  {tool['author']}" if tool.get("author") else ""
            if ver:
                print(ver)
            if author:
                print(author)
            print(f"\n  {tool.get('description', '(no description)')}\n")
            print(f"\033[90m  source: {tool.get('_source', 'unknown')}\033[0m\n")
            return
    print_error(f"Plugin not found: {plugin_name}")
    print_info("Run: aicli plugin list")



# ── serve ─────────────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--port", "-p", default=8765, help="Port to listen on (default: 8765)")
@click.option("--host", default="127.0.0.1",
              help="Host to bind to (default: 127.0.0.1). Use 0.0.0.0 to expose to network.")
@click.option("--quiet", "-q", is_flag=True, help="Suppress startup message")
@click.option("--daemon", "-d", is_flag=True,
              help="Run in background (writes PID to ~/.config/aicli/serve.pid). Stop with: aicli serve stop")
@click.argument("action", default="", required=False)
def serve(port, host, quiet, daemon, action):
    """Start a local HTTP API server for scripting and tool integration.

    \b
    Endpoints:
      POST /ask          — single-shot prompt
      POST /ask/shell    — shell command generation
      POST /ask/code     — code generation
      GET  /sessions     — list all sessions
      GET  /sessions/:id — get session messages
      GET  /health       — health check + provider status
      GET  /providers    — provider status

    \b
    Examples:
      aicli serve                    # foreground (Ctrl+C to stop)
      aicli serve --daemon           # background (PID saved to ~/.config/aicli/serve.pid)
      aicli serve stop               # stop background daemon
      aicli serve --port 9000
      aicli serve --host 0.0.0.0    # expose to LAN (use with caution)

    \b
    Curl examples:
      curl -s http://localhost:8765/health
      curl -s http://localhost:8765/ask \\
        -H "Content-Type: application/json" \\
        -d '{"prompt": "hello"}'
      curl -s http://localhost:8765/ask/shell \\
        -d '{"prompt": "find large files"}' \\
        -H "Content-Type: application/json"
    """
    if action == "stop":
        stop_serve()
        return
    run_serve(host=host, port=port, quiet=quiet, daemon=daemon)


# ── graph ────────────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--port", "-p", default=7337, help="Port to serve on (default: 7337)")
@click.option("--no-browser", is_flag=True, help="Don't open browser automatically")
def graph(port, no_browser):
    """Interactive session graph viewer — auto-loads all exported sessions.

    \b
    Starts a local server at http://localhost:7337 and opens your browser.
    Sessions exported via F4 in the TUI appear as nodes automatically.
    Create links between sessions, add notes, and save the graph.

    \b
    Browser shortcuts:
      L          Toggle link mode (click two nodes to link)
      R          Reload sessions from server
      Esc        Cancel / close panel
      Click      Select node / open panel
      Dbl-click  Edit node name and notes
      Hover link + Click  Delete link

    \b
    Examples:
      aicli graph
      aicli graph --port 8080
      aicli graph --no-browser
    """
    try:
        from .graph_server import run_graph_server
    except ImportError as e:
        print_error(f"Graph server error: {e}")
        return
    run_graph_server(port=port, open_browser=not no_browser)


# ── tag ───────────────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("session_name")
@click.argument("tags", nargs=-1, required=True)
def tag(session_name, tags):
    """Add tags to a session for graph filtering.

    Tags are stored in graph_links.json and appear as filter chips
    in the session graph browser (aicli graph).

    \b
    Examples:
      aicli tag myproject work python
      aicli tag fa2bffaf urgent review
      aicli tag myproject done
    """
    import json
    from pathlib import Path

    graph_file = CONFIG_DIR / "graph_links.json"

    # Load existing graph data
    data: dict = {}
    if graph_file.exists():
        try:
            data = json.loads(graph_file.read_text())
        except (json.JSONDecodeError, OSError) as e:
            print_error(f"Could not read graph data: {e}")
            return

    # Resolve session_name → id via DB (so both name and short-id work)
    session_id = session_name
    try:
        conn = get_connection()
        sessions = list_sessions(conn)
        matching = [s for s in sessions if s["name"] == session_name or s["id"] == session_name or s["id"].startswith(session_name)]
        if matching:
            session_id = matching[0]["id"]
    except Exception:
        pass  # Fall back to using the literal string as key

    names = data.get("names", {})
    if session_id not in names:
        names[session_id] = {"name": session_id, "notes": "", "tags": []}

    existing = set(names[session_id].get("tags", []))
    new_tags = sorted(existing | set(tags))
    names[session_id]["tags"] = new_tags
    data["names"] = names

    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        graph_file.write_text(json.dumps(data, indent=2))
        added = sorted(set(tags) - existing)
        already = sorted(set(tags) & existing)
        if added:
            print_success(f"Tagged '{session_id[:8]}...' with: {', '.join(added)}")
        if already:
            print_info(f"Already had: {', '.join(already)}")
        print_info(f"All tags: {', '.join(new_tags)}")
    except OSError as e:
        print_error(f"Could not write graph data: {e}")


# ── mcp ──────────────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--transport", "-t",
              type=click.Choice(["stdio", "sse"]), default="stdio",
              help="Transport protocol (default: stdio for Claude Desktop, sse for web clients)")
@click.option("--port", "-p", default=8766,
              help="Port for SSE transport (default: 8766, ignored for stdio)")
@click.option("--host", default="127.0.0.1",
              help="Host for SSE transport (default: 127.0.0.1)")
@click.option("--quiet", "-q", is_flag=True,
              help="Suppress startup messages (stdio: suppresses stderr, sse: suppresses HTTP log)")
def mcp(transport, port, host, quiet):
    """Start an MCP (Model Context Protocol) server — expose aicli as a Claude Desktop tool.

    \b
    Transports:
      stdio   — default, used by Claude Desktop and most MCP clients
      sse     — HTTP + Server-Sent Events, for web-based MCP clients

    \b
    Tools exposed:
      ask(prompt, web?, role?)   — single-shot query, optional web search + custom role
      cmd(prompt)                — shell command generation
      code(prompt, language?)    — code generation
      tag(session_id, tags)      — tag a session in the graph
      do(prompt, dry_run?, auto_confirm?, role?)  — LLM OS function calling (12 tools)

    \b
    Resources exposed:
      sessions://list            — list all sessions
      sessions://{id}            — read session message history

    \b
    Claude Desktop setup (~/.config/claude/claude_desktop_config.json):
      {
        "mcpServers": {
          "aicli": {
            "command": "aicli",
            "args": ["mcp"]
          }
        }
      }

    \b
    Examples:
      aicli mcp                            # stdio (Claude Desktop)
      aicli mcp --transport sse            # SSE on localhost:8766
      aicli mcp --transport sse --port 9000
      aicli mcp --transport sse --host 0.0.0.0  # expose to network
    """
    from .handlers.mcp_server import run_mcp
    run_mcp(transport=transport, host=host, port=port, quiet=quiet)


# ── cache — response cache management ────────────────────────────────────────

@cli.group("cache")
def cache_group():
    """Manage aicli response cache (--no-cache to bypass per request)."""
    pass


@cache_group.command("clear")
def cache_clear():
    """Delete all cached responses.

    \b
    The response cache stores (prompt + model + role) → response text.
    It is bypassed automatically for: --context, --web, --watch, --image.
    Use --no-cache on any ask command to bypass for one request.

    \b
    Examples:
      aicli cache clear
      aicli ask "hello" --no-cache   # skip cache for this call
    """
    from .handlers.default import _cache_clear
    count = _cache_clear()
    if count:
        print_success(f"Cleared {count} cached response(s).")
    else:
        print_info("Cache is already empty.")


@cache_group.command("stats")
def cache_stats():
    """Show cache size and entry count.

    \b
    Example:
      aicli cache stats
    """
    from .handlers.default import _cache_path
    p = _cache_path()
    if not p.exists():
        print_info("Cache is empty (no cache directory).")
        return
    files = list(p.iterdir())
    total_bytes = sum(f.stat().st_size for f in files if f.is_file())
    print(f"\n\033[1mResponse Cache\033[0m  ({p})\n")
    print(f"  Entries : {len(files)}")
    print(f"  Size    : {total_bytes // 1024} KB")
    print(f"\n  Clear with: aicli cache clear\n")


# ── Entry point ──────────────────────────────────────────────────────────────────

def main():
    cli()


def main_lite():
    """Entry point for aicli-lite — sets AICLI_LITE=1 before boot.
    Skips RAG, ChromaDB, and TUI imports for a minimal footprint install.

    Install options:
      pip install aicli-maxmux[lite]         # standard
      pipx install aicli-maxmux[lite]        # isolated (recommended)
      pip install aicli-maxmux               # full, then use --lite flag per-call

    All three give you: aicli-lite "hello"   (or: aicli "hello" --lite)
    """
    import os
    os.environ["AICLI_LITE"] = "1"
    cli()


if __name__ == "__main__":
    main()
