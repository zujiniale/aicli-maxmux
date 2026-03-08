"""handlers/default.py — Single-shot ask handler."""
import sys

from ..config import load_config, CHROMA_DIR
from ..role import get_role
from ..printer import stream_to_terminal, print_provider_footer, print_error, print_info
from ..providers.pipeline import ProviderPipeline, ProviderExhaustedError
from ..tools.builtin.shell import shell_menu, execute_with_self_correction
from ..image_utils import build_multimodal_content, is_multimodal


async def _ask(prompt_parts, shell, code, describe, model, no_stream, json_output, dry_run, context=False, context_depth=1, images=None, web=False, web_debug=False, web_verbose=False, cross_session=False, context_debug=False, min_score=0.40, run=False, max_retries=3):
    config = load_config()

    # Collect prompt from args and/or stdin
    prompt_text = " ".join(prompt_parts) if prompt_parts else ""
    if not sys.stdin.isatty():
        stdin_content = sys.stdin.read().strip()
        if stdin_content:
            prompt_text = f"{stdin_content}\n\n{prompt_text}" if prompt_text else stdin_content

    if not prompt_text:
        print_error("No prompt provided. Run: aicli ask \"your prompt\"")
        sys.exit(1)

    # Determine role
    if shell:
        role_name = "shell"
    elif code:
        role_name = "code"
    elif describe:
        role_name = "describe"
    else:
        role_name = "default"

    role = get_role(role_name)

    # Build messages
    messages = []
    if role.system_prompt:
        messages.append({"role": "system", "content": role.system_prompt})

    # Inject RAG context if --context flag set
    if context:
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
                            snippet = " ".join(lines[1:])[:120].strip()
                            if snippet:
                                print(f"  [90m{snippet}...[0m")
                    print()
                messages.append({"role": "system", "content": context_block})
            elif context_debug:
                print_info("[context-debug] No relevant context found in index.")
        except Exception as e:
            print_info(f"Context retrieval skipped: {e}")

    # Inject web search results if --web flag set (F4)
    if web_debug:
        from ..web import web_search_debug
        await web_search_debug(prompt_text, verbose=web_verbose)
        return  # debug only — don't proceed to LLM
    if web:
        try:
            from ..web import web_search
            print_info(f"Searching the web for: {prompt_text[:80]}...")
            web_block = await web_search(prompt_text)
            if web_block:
                messages.append({"role": "system", "content": web_block})
            else:
                print_info("Web search returned no results — continuing without.")
        except Exception as e:
            print_info(f"Web search skipped: {e}")

    # Build user message — multimodal if --image paths provided
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
                )
        else:
            # Default/code/describe/dry-run: stream directly
            gen = pipeline.stream(messages, model=model, requires_vision=requires_vision)
            await stream_to_terminal(gen, no_stream=no_stream, json_output=json_output)

        if config.get("show_provider") and pipeline.last_provider:
            print_provider_footer(pipeline.last_provider, show=True)

    except ProviderExhaustedError as e:
        print_error(f"All providers failed: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nInterrupted.")
