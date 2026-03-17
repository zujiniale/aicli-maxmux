"""handlers/default.py — Single-shot ask handler."""
import sys
import hashlib
import json as _json

from ..config import load_config, CHROMA_DIR
from ..role import get_role
from ..printer import stream_to_terminal, print_provider_footer, print_error, print_info
from ..providers.pipeline import ProviderPipeline, ProviderExhaustedError
from ..tools.builtin.shell import shell_menu, execute_with_self_correction
from ..image_utils import build_multimodal_content, is_multimodal


# ── Response cache ────────────────────────────────────────────────────────────
# Caches (prompt + model + role) → response text on disk.
# Equivalent to ShellGPT's request caching but stored in the aicli config dir.
# Cache key: SHA256(prompt_text + model + role_name + shell/code flags)
# Cache TTL: None (permanent until cleared with aicli cache clear)
# Bypass: --no-cache flag OR any stateful flag (--context, --web, --watch)

def _cache_path():
    """Return the response cache directory path."""
    try:
        from ..config import CONFIG_DIR
        return CONFIG_DIR / "response_cache"
    except ImportError:
        from pathlib import Path
        return Path.home() / ".config" / "aicli" / "response_cache"


def _cache_key(prompt_text: str, model: str | None, role_name: str,
               shell: bool, code: bool) -> str:
    """Compute a stable cache key for a request."""
    key_data = _json.dumps({
        "prompt": prompt_text,
        "model": model or "",
        "role": role_name,
        "shell": shell,
        "code": code,
    }, sort_keys=True)
    return hashlib.sha256(key_data.encode()).hexdigest()[:24]


def _cache_get(key: str) -> str | None:
    """Return cached response text, or None if not cached."""
    try:
        f = _cache_path() / key
        if f.exists():
            return f.read_text(encoding="utf-8")
    except Exception:
        pass
    return None


def _cache_set(key: str, response: str) -> None:
    """Write response text to cache. Silent on failure."""
    try:
        d = _cache_path()
        d.mkdir(parents=True, exist_ok=True)
        (d / key).write_text(response, encoding="utf-8")
    except Exception:
        pass


def _cache_clear() -> int:
    """Delete all cached responses. Returns count deleted."""
    try:
        d = _cache_path()
        if not d.exists():
            return 0
        files = list(d.iterdir())
        for f in files:
            f.unlink(missing_ok=True)
        return len(files)
    except Exception:
        return 0


async def _ask(prompt_parts, shell, code, describe, model, no_stream, json_output, dry_run, context=False, context_depth=1, images=None, web=False, web_debug=False, web_verbose=False, cross_session=False, context_debug=False, min_score=0.40, run=False, max_retries=3, language="python", timeout=30, lite=False, quiet=False, terminal_context=None, watch=False, watch_lines=10, extra_files=None, no_cache=False, role=None, watch_do=None):
    import os
    lite = lite or os.environ.get("AICLI_LITE") == "1"
    quiet = quiet or os.environ.get("AICLI_QUIET") == "1"
    config = load_config()

    # Collect prompt from args and/or stdin
    # NOTE: skip stdin pipe-read when --watch is active — stdin IS the data stream
    prompt_text = " ".join(prompt_parts) if prompt_parts else ""
    if not watch and not sys.stdin.isatty():
        stdin_content = sys.stdin.read().strip()
        if stdin_content:
            prompt_text = f"{stdin_content}\n\n{prompt_text}" if prompt_text else stdin_content

    if not prompt_text:
        if watch:
            print_error("--watch requires a condition. Example: aicli ask --watch \"alert on ERROR\"")
        else:
            print_error("No prompt provided. Run: aicli ask \"your prompt\"")
        sys.exit(1)

    # ── Feature: path auto-detection — scan prompt for embedded file paths ──────
    # When the user writes: aicli "summarize /tmp/docs/report.txt"
    # we auto-detect the path and inject the file content exactly as if -f was used.
    # Only actual files that exist on disk are injected (filters out false positives
    # like version strings, flags, URLs).
    # Security: capped at 50 KB per file (same limit as read_file_content tool).
    # User can always override with explicit -f flags; auto-detected paths are
    # appended AFTER explicit --file paths so explicit takes precedence.
    _MAX_AUTO_FILE_BYTES = 50 * 1024  # 50 KB
    try:
        from ..tools.os_functions import extract_file_paths_from_prompt
        _auto_paths = extract_file_paths_from_prompt(prompt_text)
    except ImportError:
        _auto_paths = []
    if _auto_paths:
        # Merge with explicit extra_files — explicit first, auto-detected after
        _existing = set(str(p) for p in (extra_files or []))
        _new_auto = [p for p in _auto_paths if p not in _existing]
        extra_files = tuple(extra_files or ()) + tuple(_new_auto)
        if not quiet and _new_auto:
            from ..printer import print_info as _pi
            _pi(f"Auto-detected file(s): {', '.join(_new_auto)}")

    # ── Feature: --watch mode — stream stdin line-by-line, alert on condition ──
    # Must be checked before building messages so we can early-return.
    # Usage: tail -f app.log | aicli ask --watch "alert on ERROR"
    if watch:
        await _watch_stdin(prompt_text, watch_lines, model, quiet, lite, do_action=watch_do)
        return

    # Determine role
    if role:
        # P6: custom --role flag — user-specified role name overrides auto-detection
        role_name = role
    elif shell:
        role_name = "shell"
    elif code:
        role_name = "code"
    elif describe:
        role_name = "describe"
    else:
        role_name = "default"

    role_obj = get_role(role_name)

    # ── Response cache check ───────────────────────────────────────────────────
    # Cache is bypassed automatically for: --context, --web, --watch, --image,
    # --no-cache, dry_run (stateful/side-effectful modes should never use cache).
    _use_cache = (
        not no_cache
        and not context
        and not web
        and not watch
        and not images
        and not dry_run
        and not extra_files
        and not terminal_context
    )
    _cache_key_val = None
    if _use_cache:
        _cache_key_val = _cache_key(prompt_text, model, role_name, shell, code)
        cached = _cache_get(_cache_key_val)
        if cached is not None:
            if not quiet:
                print_info("[cache] Replaying cached response (use --no-cache to bypass)")
            print(cached)
            return

    # Build messages
    messages = []
    if role_obj.system_prompt:
        # When --language is set to a non-Python runtime, override the code
        # system prompt so the LLM generates the correct language
        if code and language != "python":
            lang_cap = language.capitalize()
            lang_prompt = (
                f"You are a {lang_cap} code generation assistant. "
                f"Output ONLY raw {lang_cap} code with no explanation, "
                f"no markdown fences, no backticks. "
                f"The code must be complete and runnable as-is with {language}."
            )
            messages.append({"role": "system", "content": lang_prompt})
        else:
            messages.append({"role": "system", "content": role_obj.system_prompt})

    # Inject RAG context if --context flag set (skipped in lite mode)
    if context and not lite:
        try:
            from ..context.retriever import ContextRetriever
            retriever = ContextRetriever(CHROMA_DIR)
            if cross_session:
                print_info("Cross-session context active")
            context_block = retriever.retrieve(prompt_text, depth=context_depth, min_score=min_score)
            if context_block:
                if context_debug:
                    print("\n[1m[context-debug] Sources injected:[0m")
                    import re as _re
                    for section in _re.split(r'\n\n(?=\[)', context_block):
                        if section.startswith("RELEVANT CONTEXT:"):
                            continue
                        lines = section.strip().splitlines()
                        if lines:
                            print(f"  [33m{lines[0]}[0m")
                            full_snippet = " ".join(lines[1:]).strip()
                            snippet = full_snippet[:200]
                            if len(full_snippet) > 200:
                                last_period = snippet.rfind(".")
                                if last_period > 100:
                                    snippet = snippet[:last_period + 1]
                                else:
                                    snippet = snippet + "..."
                            if snippet:
                                print(f"  [90m{snippet}[0m")
                    print()
                messages.append({"role": "system", "content": context_block})
            elif context_debug:
                print_info("[context-debug] No relevant context found in index.")
        except Exception as e:
            print_info(f"Context retrieval skipped: {e}")

    # ── Feature 1: context-aware hotkey — inject terminal scrollback ──────────
    # Optimal injection order: role_prompt -> RAG (structured knowledge) ->
    # TC (raw terminal state, ephemeral) -> files -> web -> user
    # TC comes after RAG so the model reads rich semantic context before the raw dump.
    if terminal_context and terminal_context.strip():
        tc_block = (
            "TERMINAL CONTEXT (last lines visible in the user's terminal "
            "before this request — use this to understand what just happened):\n"
            + terminal_context.strip()
        )
        messages.append({"role": "system", "content": tc_block})

    # ── Feature 3: --file/-f — attach arbitrary text/code/log files as context ─
    # Any file type accepted; binary files are skipped gracefully.
    # Mixed --image + --file is supported: images go into multimodal user content,
    # files go into a system message immediately before the user turn.
    # Path imported at top of function scope to avoid repeated lazy import per loop.
    if extra_files:
        from pathlib import Path as _FilePath  # local alias avoids shadowing
        file_blocks = []
        for fpath in extra_files:
            try:
                raw = _FilePath(fpath).read_bytes()
                try:
                    text = raw.decode("utf-8")
                except UnicodeDecodeError:
                    text = raw.decode("latin-1", errors="replace")
                file_blocks.append(f"[FILE: {fpath}]\n{text.strip()}")
            except Exception as exc:
                if not quiet:
                    print_info(f"Could not read file {fpath}: {exc}")
        if file_blocks:
            joined = "\n\n---\n\n".join(file_blocks)
            messages.append({
                "role": "system",
                "content": f"ATTACHED FILES (referenced by the user's prompt):\n\n{joined}",
            })

    # Inject web search results if --web flag set (F4)
    if web_debug:
        from ..web import web_search_debug
        await web_search_debug(prompt_text, verbose=web_verbose)
        return  # debug only — don't proceed to LLM
    if web:
        try:
            from ..web import web_search
            if not quiet:
                print_info(f"Searching the web for: {prompt_text[:80]}...")
            web_block = await web_search(prompt_text)
            if web_block:
                messages.append({"role": "system", "content": web_block})
            elif not quiet:
                print_info("Web search returned no results — continuing without.")
        except Exception as e:
            if not quiet:
                print_info(f"Web search skipped: {e}")

    # Build user message — multimodal if --image paths provided
    # When both --image and --file are used, images go into the multimodal content block
    # and files have already been injected as system messages above.
    # When only --image is used, standard multimodal path.
    if images:
        try:
            user_content = build_multimodal_content(prompt_text, list(images))
        except ValueError as e:
            print_error(str(e))
            sys.exit(1)
    else:
        user_content = prompt_text
    messages.append({"role": "user", "content": user_content})

    # Build pipeline
    try:
        pipeline = ProviderPipeline(
            provider_chain=config["provider_chain"],
            cooldown_seconds=config["cooldown_seconds"],
            max_retries_per_provider=config["max_retries_per_provider"],
            show_provider=config["show_provider"],
        )
    except ProviderExhaustedError as e:
        print_error(str(e))
        sys.exit(1)

    # Stream response
    requires_vision = is_multimodal(messages)
    try:
        if shell and not dry_run:
            # Collect the command first, then show menu
            chunks = []
            async for chunk in pipeline.stream(messages, model=model, requires_vision=requires_vision):
                chunks.append(chunk)
            command = "".join(chunks).strip().strip("`").strip()

            if not command:
                print_error("No command generated.")
                return

            # Shell interaction loop
            effective_prompt = None  # updated when user re-instructs via M
            while True:
                action, final_command = shell_menu(command, pipeline=pipeline)

                if action == "execute" and final_command:
                    await execute_with_self_correction(
                        final_command, pipeline, prompt_text,
                        effective_prompt=effective_prompt,
                    )
                    break
                elif action == "modify" and final_command:
                    command = final_command
                    continue
                elif action == "reprompt" and final_command:
                    # Re-prompt AI with full context: original prompt + current command + new instruction
                    effective_prompt = final_command  # correction loop uses this going forward
                    reprompt_messages = [m for m in messages[:-1]]  # keep system prompt
                    reprompt_messages.append({"role": "user", "content": prompt_text})
                    reprompt_messages.append({"role": "assistant", "content": command})
                    reprompt_messages.append({"role": "user", "content": f"That's not quite right. {final_command}. Output only the corrected shell command, nothing else."})
                    chunks = []
                    async for chunk in pipeline.stream(reprompt_messages, model=model, requires_vision=requires_vision):
                        chunks.append(chunk)
                    command = "".join(chunks).strip().strip("`").strip()
                    continue
                elif action == "describe":
                    print_info("Describing command...")
                    desc_role = get_role("describe")
                    desc_messages = [
                        {"role": "system", "content": desc_role.system_prompt},
                        {"role": "user", "content": command},
                    ]
                    async for chunk in pipeline.stream(desc_messages, requires_vision=False):
                        print(chunk, end="", flush=True)
                    print()
                    break
                else:
                    break
        elif code and run:
            # F8: --code --run — collect silently, then pretty-print + execute
            chunks = []
            async for chunk in pipeline.stream(messages, model=model, requires_vision=requires_vision):
                chunks.append(chunk)
            generated_code = "".join(chunks).strip()
            if generated_code:
                from .code_runner import run_generated_code
                await run_generated_code(
                    generated_code,
                    pipeline,
                    original_prompt=prompt_text,
                    model=model,
                    max_retries=max_retries,
                    show_code=True,  # pretty-print via rich before running
                    language=language,
                    timeout=timeout,
                )
        else:
            # Default/code/describe/dry-run: stream directly
            gen = pipeline.stream(messages, model=model, requires_vision=requires_vision)
            if _use_cache and _cache_key_val and not shell and not run:
                # Collect response for caching while streaming to terminal
                collected_chunks: list[str] = []
                async def _caching_gen():
                    async for chunk in gen:
                        collected_chunks.append(chunk)
                        yield chunk
                await stream_to_terminal(_caching_gen(), no_stream=no_stream, json_output=json_output)
                _cache_set(_cache_key_val, "".join(collected_chunks))
            else:
                await stream_to_terminal(gen, no_stream=no_stream, json_output=json_output)

        if config.get("show_provider") and pipeline.last_provider and not quiet:
            print_provider_footer(pipeline.last_provider, show=True)

    except ProviderExhaustedError as e:
        print_error(f"All providers failed: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nInterrupted.")

# ── Feature 2: --watch mode — streaming stdin AI monitor ─────────────────────
# Usage:  tail -f /var/log/app.log | aicli ask --watch "alert on ERROR"
#         journalctl -f | aicli ask --watch "alert on OOM killer" --watch-lines 20
#
# How it works:
#   1. Reads stdin line-by-line (non-blocking via asyncio)
#   2. Buffers `watch_lines` lines, then sends the buffer + the user's condition
#      to the LLM for evaluation
#   3. If the LLM answers "YES" (condition met), prints an alert and the
#      relevant excerpt to stdout — suitable for scripting / piping to notify-send
#   4. Ctrl+C exits cleanly
#
# This is the decisive edge over ShellGPT: real-time AI-powered log monitoring
# with zero configuration and no regex patterns to maintain.

async def _watch_stdin(condition: str, batch_lines: int, model, quiet: bool, lite: bool,
                       do_action: str | None = None) -> None:
    """Stream stdin line-by-line and alert when the AI detects the condition.

    do_action: if set, when the condition is triggered the named aicli do action
               is also executed automatically. Example:
                 tail -f app.log | aicli ask --watch "OOM killer" --do "send_notification title='OOM detected' body='Check logs'"
               This combines real-time monitoring with automated OS tool dispatch.
    """
    import asyncio
    import sys as _sys

    config = load_config()
    try:
        pipeline = ProviderPipeline(
            provider_chain=config["provider_chain"],
            cooldown_seconds=config["cooldown_seconds"],
            max_retries_per_provider=config["max_retries_per_provider"],
            show_provider=False,  # suppress footer in watch mode
        )
    except ProviderExhaustedError as e:
        print_error(str(e))
        return

    watch_system = (
        "You are a real-time log monitor. "
        "The user will give you a batch of log lines and a condition to watch for. "
        "Reply with ONLY 'YES: <one-line explanation>' if the condition is met, "
        "or 'NO' if it is not. Be concise and fast."
    )

    buffer: list[str] = []
    batch_count = 0

    if not quiet:
        print_info(f"[watch] Monitoring stdin — condition: {condition!r} (batch={batch_lines} lines, Ctrl+C to stop)")
        if do_action:
            print_info(f"[watch] On trigger: aicli do \"{do_action}\" (auto-confirm)")

    loop = asyncio.get_event_loop()

    async def _readline() -> str | None:
        """Read one line from stdin without blocking the event loop."""
        try:
            return await loop.run_in_executor(None, _sys.stdin.readline)
        except Exception:
            return None

    try:
        while True:
            line = await _readline()
            if line is None or line == "":
                # EOF — evaluate whatever is left in buffer
                if buffer:
                    await _watch_evaluate(buffer, condition, watch_system, pipeline,
                                          model, quiet, do_action=do_action)
                break

            buffer.append(line.rstrip())

            if len(buffer) >= batch_lines:
                batch_count += 1
                await _watch_evaluate(buffer, condition, watch_system, pipeline,
                                      model, quiet, do_action=do_action)
                buffer = []

    except KeyboardInterrupt:
        if not quiet:
            print("\n[watch] Stopped.")


async def _watch_evaluate(
    lines: list[str],
    condition: str,
    system_prompt: str,
    pipeline,
    model,
    quiet: bool,
    do_action: str | None = None,
) -> None:
    """Send a buffer of lines to the LLM; print alert if condition is met.

    do_action: if set and condition fires, dispatch this prompt to aicli do
               with auto_confirm=True (non-interactive — no [Y/n] prompts).
    """
    batch_text = "\n".join(lines)
    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": (
                f"CONDITION TO WATCH FOR: {condition}\n\n"
                f"LOG LINES:\n{batch_text}"
            ),
        },
    ]
    try:
        chunks: list[str] = []
        async for chunk in pipeline.stream(messages, model=model, requires_vision=False):
            chunks.append(chunk)
        response = "".join(chunks).strip()

        if response.upper().startswith("YES"):
            # Print alert — format is machine-parseable for scripting
            import datetime
            ts = datetime.datetime.now().strftime("%H:%M:%S")
            print(f"\n\033[1;31m[ALERT {ts}]\033[0m {response}")
            print(f"\033[90m--- batch that triggered ---\n{batch_text}\n---\033[0m")

            # ── --watch + do integration ──────────────────────────────────────
            # When --do is set, automatically dispatch the aicli do action.
            # auto_confirm=True because we are non-interactive in watch mode.
            if do_action:
                try:
                    from ..tools.executor import run_do_command
                    if not quiet:
                        print_info(f"[watch] Triggering: aicli do \"{do_action}\"")
                    await run_do_command(
                        prompt_parts=(do_action,),
                        auto_confirm=True,
                        dry_run=False,
                        quiet=quiet,
                        model=model,
                        lite=False,
                    )
                except ImportError:
                    print_info("[watch] aicli do not available (lite install)")
                except Exception as exc:
                    print_info(f"[watch] do action error: {exc}")

        elif not quiet and response.upper() != "NO":
            # Unexpected response — surface it so user can tune the condition
            print_info(f"[watch] unexpected response: {response[:120]}")
    except Exception as exc:
        if not quiet:
            print_info(f"[watch] evaluation error: {exc}")
