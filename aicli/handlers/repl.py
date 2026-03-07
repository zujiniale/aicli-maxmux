"""handlers/repl.py — Interactive REPL handler."""
import sys
import uuid

from ..config import load_config
from ..role import get_role
from ..printer import print_provider_footer, print_error, print_success, print_info
from ..providers.pipeline import ProviderPipeline, ProviderExhaustedError
from ..context.manager import ContextManager


async def _repl(model, summarize_threshold=None):
    config = load_config()
    if summarize_threshold is not None:
        config["summarize_threshold"] = summarize_threshold

    try:
        pipeline = ProviderPipeline(
            provider_chain=config["provider_chain"],
            cooldown_seconds=config["cooldown_seconds"],
            max_retries_per_provider=config["max_retries_per_provider"],
        )
    except ProviderExhaustedError as e:
        print_error(str(e))
        sys.exit(1)

    # Create a session so repl conversations are persisted like chat
    session_id = str(uuid.uuid4())[:8]
    session_name = f"repl-{session_id}"
    ctx = ContextManager(session_id=session_id, session_name=session_name, pipeline=pipeline, config=config)
    await ctx.initialize()
    print_info(f"Session: {session_name} (auto-saved)")

    role = get_role("default")
    messages = [{"role": "system", "content": role.system_prompt}]
    current_mode = "default"

    print("\n\033[36maicli repl\033[0m — Ctrl+C to exit | /shell /code /default /summarize | \"\"\" for multiline\n")

    while True:
        mode_indicator = f"\033[90m[{current_mode}]\033[0m " if current_mode != "default" else ""
        try:
            line = input(f"{mode_indicator}\033[1m>\033[0m ").strip()
        except (EOFError, KeyboardInterrupt):
            await ctx.await_pending_summarization()
            print("\nGoodbye.")
            break

        if not line:
            continue

        # Mode switching
        if line == "/shell":
            current_mode = "shell"
            role = get_role("shell")
            messages = [{"role": "system", "content": role.system_prompt}]
            print_info("Switched to shell mode")
            continue
        elif line == "/code":
            current_mode = "code"
            role = get_role("code")
            messages = [{"role": "system", "content": role.system_prompt}]
            print_info("Switched to code mode")
            continue
        elif line == "/default":
            current_mode = "default"
            role = get_role("default")
            messages = [{"role": "system", "content": role.system_prompt}]
            print_info("Switched to default mode")
            continue
        elif line == "/clear":
            messages = [{"role": "system", "content": role.system_prompt}]
            print_info("Context cleared")
            continue
        elif line in ("/quit", "/exit", "/q"):
            print("Goodbye.")
            break

        # /summarize on-demand
        elif line.lower().startswith("/summarize"):
            silent = "silent" in line.lower()
            verbose = not silent and config.get("summarize_verbose", True)
            if verbose:
                print_info("Summarizing...")
            summary = await ctx.summarize_now()
            if summary:
                if verbose:
                    print(f"\n\033[90m[AUTO-SUMMARY]\033[0m {summary}\n")
                print_success("Summarized and saved to DB")
            else:
                print_info("Not enough messages to summarize (need at least 4).")
            continue

        # Multiline input with """
        if line == '"""':
            print('  (multiline mode — end with """)')
            lines = []
            while True:
                try:
                    l = input("  ")
                    if l == '"""':
                        break
                    lines.append(l)
                except (EOFError, KeyboardInterrupt):
                    break
            line = "\n".join(lines)

        await ctx.add_message("user", line)
        messages = ctx.get_active_messages()

        try:
            chunks = []
            async for chunk in pipeline.stream(messages, model=model):
                chunks.append(chunk)
                print(chunk, end="", flush=True)
            print()

            response_text = "".join(chunks)
            await ctx.add_message("assistant", response_text)

            if config.get("show_provider") and pipeline.last_provider:
                print_provider_footer(pipeline.last_provider, show=True)

        except ProviderExhaustedError as e:
            print_error(f"All providers failed: {e}")
        except KeyboardInterrupt:
            print()
            continue
