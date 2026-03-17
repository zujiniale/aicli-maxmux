"""
context.py — ContextManager: the core memory pipeline.

Three-layer CMA (Continuum Memory Architecture):
  🔥 Hot  — active_messages (in-memory token window)
  🌡️ Warm — SQLite summaries table ([AUTO-SUMMARY] injected into window)
  ❄️ Cold — ChromaDB RAG (auto-index every turn; semantic retrieval on load)

Add message order (STRICT — never change):
  1. db.save()          ← ALWAYS FIRST. Unconditional. Safety net.
  2. active_messages.append()
  3. count_messages_tokens()
  4. if >80%: asyncio.create_task(_summarize_and_compress())
              ↑ fire-and-forget: user never waits for summarization
  5. asyncio.create_task(_index_message_cold(role, content))
              ↑ fire-and-forget: index into ChromaDB cold layer
"""

import asyncio
from typing import Optional

import sqlite3

from ..db.chat_db import (
    save_message,
    save_summary,
    load_messages,
    load_latest_summary,
    get_connection,
    ensure_session,
)
from ..tokens import (
    count_messages_tokens,
    trim_messages,
    summarization_prompt,
    count_tokens,
)
from ..config import load_config


class ContextManager:
    """
    Manages the active conversation window with automatic compression.

    Usage:
        ctx = ContextManager(session_id="my-session", pipeline=pipeline)
        await ctx.initialize()  # Loads from DB if resuming
        await ctx.add_message("user", "Hello!")
        messages = ctx.get_active_messages()  # Pass to provider
    """

    def __init__(
        self,
        session_id: str,
        pipeline=None,  # ProviderPipeline — injected to avoid circular import
        system_prompt: str | None = None,
        session_name: str | None = None,
        db_path=None,
        config: dict | None = None,
    ):
        self.session_id = session_id
        self.session_name = session_name or session_id
        self.pipeline = pipeline
        self.system_prompt = system_prompt
        self._config = config or load_config()
        self._token_limit = self._config.get("token_limit", 6000)
        self._threshold = self._config.get("summarize_threshold", 0.80)
        self._conn: sqlite3.Connection = get_connection(db_path)
        self._active_messages: list[dict] = []
        self._summarizing = False  # Prevent concurrent summarization tasks
        self._summarize_task: asyncio.Task | None = None  # Track for graceful shutdown
        self._fernet = None  # Set if encrypt_history = true
        self._rag_enabled: bool = False  # Set to True if chromadb is available
        self._chroma_dir = None  # Set during initialize() from config

        if self._config.get("encrypt_history"):
            from cryptography.fernet import Fernet
            from ..config import _machine_key
            self._fernet = Fernet(_machine_key())

    async def initialize(self, role: str = "default") -> None:
        """
        Load session from DB, or start fresh.
        Injects latest summary as [AUTO-SUMMARY] if present.
        """
        ensure_session(self._conn, self.session_id, name=self.session_name, role=role)

        # Build active window from DB
        all_messages = load_messages(self._conn, self.session_id, fernet=self._fernet)
        latest_summary = load_latest_summary(self._conn, self.session_id)

        self._active_messages = []

        # System prompt always first
        if self.system_prompt:
            self._active_messages.append({"role": "system", "content": self.system_prompt})

        # Inject latest summary if exists
        if latest_summary:
            self._active_messages.append({
                "role": "system",
                "content": f"[AUTO-SUMMARY] {latest_summary}"
            })

        # Add recent messages, trimming to token limit
        recent = [{"role": m["role"], "content": m["content"]} for m in all_messages]
        self._active_messages.extend(recent)
        self._active_messages = trim_messages(self._active_messages, self._token_limit)

        # ── Cold layer: detect chromadb availability + backfill existing session ──
        try:
            from ..config import CHROMA_DIR
            from ..context.retriever import ContextRetriever
            self._chroma_dir = CHROMA_DIR
            CHROMA_DIR.mkdir(parents=True, exist_ok=True)  # Created here, not in load_config()
            self._rag_enabled = True
            if all_messages:
                # Backfill: index any existing messages not yet in ChromaDB (fire-and-forget)
                asyncio.create_task(self._backfill_cold(all_messages, latest_summary))
        except Exception:
            self._rag_enabled = False  # chromadb not installed or import failed — silent degradation

    async def add_message(self, role: str, content: str) -> None:
        """
        Add a message to the conversation.
        Step 1 MUST be db.save() — this is the safety net.
        """
        # ── Step 1: SAVE TO DB — unconditional, always first ──────────────────
        token_count = count_tokens(content)
        save_message(
            self._conn,
            self.session_id,
            role,
            content,
            token_count=token_count,
            fernet=self._fernet,
        )

        # ── Step 2: Append to active window ───────────────────────────────────
        self._active_messages.append({"role": role, "content": content})

        # ── Step 3: Count tokens ───────────────────────────────────────────────
        current_tokens = count_messages_tokens(self._active_messages)
        threshold_tokens = int(self._token_limit * self._threshold)

        # ── Step 4: Trigger async summarization if over threshold ──────────────
        if current_tokens > threshold_tokens and not self._summarizing and self.pipeline:
            import sys
            print(f"\n\033[90m[aicli] Auto-summarizing ({current_tokens} > {threshold_tokens} tokens)...\033[0m", file=sys.stderr)
            self._summarize_task = asyncio.create_task(self._summarize_and_compress())
            # Returns immediately — user never waits

        # ── Step 5: Index into ChromaDB cold layer (fire-and-forget) ──────────
        if self._rag_enabled:
            asyncio.create_task(self._index_message_cold(role, content))

    def get_active_messages(self) -> list[dict]:
        """
        Return the current active window, trimmed to token limit.
        Used directly as the `messages` argument to provider.stream().
        """
        return trim_messages(self._active_messages, self._token_limit)

    async def summarize_now(self) -> str | None:
        """
        On-demand summarization — fully awaited, not fire-and-forget.
        Loads ALL messages from DB so summary covers full history, not just active window.
        Called by /summarize command. Returns summary text if produced, else None.
        """
        if self._summarizing:
            if self._summarize_task:
                try:
                    await asyncio.wait_for(asyncio.shield(self._summarize_task), timeout=30.0)
                except (asyncio.TimeoutError, Exception):
                    pass
            return load_latest_summary(self._conn, self.session_id)

        self._summarizing = True
        try:
            # Load full history from DB — not just the trimmed active window
            all_messages = load_messages(self._conn, self.session_id, fernet=self._fernet)
            non_protected = [{"role": m["role"], "content": m["content"]} for m in all_messages]

            if len(non_protected) < 4:
                return None

            prompt = summarization_prompt(non_protected)
            summary_text = await self.pipeline.complete([{"role": "user", "content": prompt}])

            save_summary(
                self._conn,
                self.session_id,
                summary=summary_text,
                covers_from=0,
                covers_to=len(non_protected),
            )

            # Rebuild active window: system prompt + full summary only
            self._active_messages = []
            if self.system_prompt:
                self._active_messages.append({"role": "system", "content": self.system_prompt})
            self._active_messages.append({
                "role": "system",
                "content": f"[AUTO-SUMMARY] {summary_text}"
            })

            return summary_text

        except Exception as e:
            import sys
            print(f"\n\033[90m[aicli] /summarize failed: {e}\033[0m", file=sys.stderr)
            return load_latest_summary(self._conn, self.session_id)
        finally:
            self._summarizing = False

    async def await_pending_summarization(self, timeout: float = 5.0) -> None:
        """
        Await any in-progress background summarization task.
        Called on Ctrl+C before exit. Non-fatal — messages already in SQLite.
        """
        if self._summarize_task and not self._summarize_task.done():
            try:
                await asyncio.wait_for(asyncio.shield(self._summarize_task), timeout=timeout)
            except (asyncio.TimeoutError, Exception):
                pass

    async def _summarize_and_compress(self) -> None:
        """
        Background task: summarize old messages, compress the active window.
        Fires via asyncio.create_task() — never blocks the user's response.
        """
        if self._summarizing:
            return
        self._summarizing = True

        try:
            # Identify messages to summarize (all non-protected non-recent)
            protected = [m for m in self._active_messages
                        if m.get("role") == "system" or
                        m.get("content", "").startswith("[AUTO-SUMMARY]")]
            non_protected = [m for m in self._active_messages
                            if m not in protected]

            if len(non_protected) < 4:
                return  # Not enough to summarize meaningfully

            # Summarize the oldest half of non-protected messages
            chunk_size = len(non_protected) // 2
            to_summarize = non_protected[:chunk_size]
            to_keep = non_protected[chunk_size:]

            # Build summarization prompt and call pipeline
            prompt = summarization_prompt(to_summarize)
            summary_messages = [{"role": "user", "content": prompt}]

            summary_text = await self.pipeline.complete(summary_messages)

            # Save summary to DB
            save_summary(
                self._conn,
                self.session_id,
                summary=summary_text,
                covers_from=0,  # Approximate — full tracking in production
                covers_to=chunk_size,
            )

            # Rebuild active window with summary replacing the old chunk
            self._active_messages = []

            if self.system_prompt:
                self._active_messages.append({"role": "system", "content": self.system_prompt})

            # Inject the new summary
            self._active_messages.append({
                "role": "system",
                "content": f"[AUTO-SUMMARY] {summary_text}"
            })

            # Keep remaining messages
            self._active_messages.extend(to_keep)

        except Exception as e:
            # Summarization failure is non-fatal — messages are already in SQLite
            import sys
            print(f"\n\033[90m[aicli] Auto-summarization failed: {e}\033[0m", file=sys.stderr)
        finally:
            self._summarizing = False

    async def _index_message_cold(self, role: str, content: str) -> None:
        """
        Background task: index the just-saved message into ChromaDB cold layer.
        Fire-and-forget from add_message() Step 5. Non-fatal on any error.
        Only system messages are skipped (they are session scaffolding, not content).
        """
        if role == "system":
            return
        try:
            from ..context.retriever import ContextRetriever
            retriever = ContextRetriever(self._chroma_dir)
            # Index as a single-message "session chunk" — upserts are idempotent
            retriever.index_session(
                session_id=self.session_id,
                messages=[{"role": role, "content": content}],
            )
        except Exception:
            pass  # chromadb write failure is non-fatal — warm layer already has the message

    async def _backfill_cold(self, all_messages: list[dict], summary: str | None) -> None:
        """
        Background task: index an existing session's messages into ChromaDB on first load.
        Runs once during initialize() if the session has prior messages.
        Upserts are idempotent — safe to run multiple times.
        """
        try:
            from ..context.retriever import ContextRetriever
            retriever = ContextRetriever(self._chroma_dir)
            messages = [{"role": m["role"], "content": m["content"]} for m in all_messages]
            retriever.index_session(
                session_id=self.session_id,
                messages=messages,
                summary=summary,
            )
        except Exception:
            pass  # chromadb not available or write failed — silent degradation
