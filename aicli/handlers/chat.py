"""handlers/chat.py — Persistent chat session handler."""
import sys
import uuid

from ..config import load_config, CHROMA_DIR
from ..role import get_role
from ..printer import print_provider_footer, print_error, print_success, print_info
from ..providers.pipeline import ProviderPipeline, ProviderExhaustedError
from ..db.chat_db import get_connection, list_sessions
from ..context.manager import ContextManager
from ..image_utils import is_multimodal


async def _chat(session_name, new, model, no_history=False, summarize_threshold=None, context=False, context_depth=1):
    config = load_config()
    if summarize_threshold is not None:
        config["summarize_threshold"] = summarize_threshold
    conn = get_connection()

    # Determine session ID
    if new or not session_name:
        session_id = str(uuid.uuid4())[:8]
        session_name = session_name or session_id
        print_info(f"New session: {session_name} ({session_id})")
    else:
        # Find existing session by name or use as ID
        sessions = list_sessions(conn)
        matching = [s for s in sessions if s["name"] == session_name or s["id"] == session_name]
        if matching:
            session_id = matching[0]["id"]
            msg_count = matching[0]["message_count"]
            print_info(f"Resuming session: {session_name} ({msg_count} messages)")
        else:
            session_id = str(uuid.uuid4())[:8]
            print_info(f"New session: {session_name} ({session_id})")

    # Build pipeline
    try:
        pipeline = ProviderPipeline(
            provider_chain=config["provider_chain"],
            cooldown_seconds=config["cooldown_seconds"],
            max_retries_per_provider=config["max_retries_per_provider"],
        )
    except ProviderExhaustedError as e:
        print_error(str(e))
        sys.exit(1)

    # Initialize context manager
    ctx = ContextManager(
        session_id=session_id,
        session_name=session_name,
        pipeline=pipeline,
        config=config,
    )
    await ctx.initialize()

    # Print history on resume (unless --no-history)
    if not new and not no_history:
        prior = [m for m in ctx.get_active_messages() if m["role"] != "system"]
        if prior:
            print()
            for msg in prior:
                role_color = "\033[34m" if msg["role"] == "user" else "\033[32m"
                label = "You" if msg["role"] == "user" else "Assistant"
                print(f"{role_color}{label}:\033[0m {msg['content']}")
            print()

    print(f"\n\033[36maicli chat\033[0m — session: {session_name} | Ctrl+C to exit\n")

    while True:
        try:
            user_input = input("\033[1mYou:\033[0m ").strip()
        except (EOFError, KeyboardInterrupt):
            await ctx.await_pending_summarization()
            print("\n\nSession saved. Resume with: aicli chat --session " + session_name)
            break

        if not user_input:
            continue

        if user_input.lower() in ("/quit", "/exit", "/q"):
            print("Session saved. Resume with: aicli chat --session " + session_name)
            break

        # /summarize on-demand
        if user_input.lower().startswith("/summarize"):
            silent = "silent" in user_input.lower()
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

        # Add user message (db.save() called inside, always first)
        await ctx.add_message("user", user_input)

        # Get active messages and stream
        messages = ctx.get_active_messages()

        # Inject RAG context if --context flag set
        if context:
            try:
                from ..context.retriever import ContextRetriever
                retriever = ContextRetriever(CHROMA_DIR)
                context_block = retriever.retrieve(user_input, depth=context_depth)
                if context_block:
                    messages = list(messages)  # copy
                    messages.insert(1, {"role": "system", "content": context_block})
            except Exception:
                pass

        print("\033[1mAssistant:\033[0m ", end="", flush=True)

        try:
            chunks = []
            requires_vision = is_multimodal(messages)
            async for chunk in pipeline.stream(messages, model=model, requires_vision=requires_vision):
                chunks.append(chunk)
                print(chunk, end="", flush=True)
            print()

            response_text = "".join(chunks)
            await ctx.add_message("assistant", response_text)

            # Index current session into cold layer after each completed exchange
            # (ctx.add_message already fires _index_message_cold per-message;
            #  this ensures the full session summary is kept current in ChromaDB)
            if context and ctx._rag_enabled:
                try:
                    from ..context.retriever import ContextRetriever
                    from ..db.chat_db import load_latest_summary
                    retriever = ContextRetriever(CHROMA_DIR)
                    latest_summary = load_latest_summary(ctx._conn, session_id)
                    retriever.index_session(
                        session_id=session_id,
                        messages=ctx.get_active_messages(),
                        summary=latest_summary,
                    )
                except Exception:
                    pass

            if config.get("show_provider") and pipeline.last_provider:
                print_provider_footer(pipeline.last_provider, show=True)

        except ProviderExhaustedError as e:
            print_error(f"\nAll providers failed: {e}")
            continue
        except KeyboardInterrupt:
            await ctx.await_pending_summarization()
            print("\n\nSession saved.")
            break
