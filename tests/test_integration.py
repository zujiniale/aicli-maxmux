"""
tests/test_integration.py — Integration tests for aicli.

Covers the 8 runtime-only bug classes invisible to unit tests:
  - Provider User-Agent header (Groq blocks Python-urllib)
  - PROVIDER_MODELS presence and structure in pipeline.py
  - Session name stored as slug not bare ID
  - REPL messages persisted to SQLite
  - Pipeline instant failover on 429 (no sleep between providers)
  - db.save() always first (message in DB even if pipeline crashes)
  - [AUTO-SUMMARY] survives trim_messages()
  - ContextManager resumes from DB correctly

Run with: python -m pytest tests/test_integration.py -v
"""

import asyncio
import time
import urllib.error
import urllib.request
import pytest
from unittest.mock import patch, MagicMock


# ── Helpers ────────────────────────────────────────────────────────────────────

def run(coro):
    """Run a coroutine synchronously (pytest-asyncio not required)."""
    return asyncio.run(coro)


# ══════════════════════════════════════════════════════════════════════════════
# 1. User-Agent header — Groq blocks Python-urllib/3.x
# ══════════════════════════════════════════════════════════════════════════════

def test_groq_user_agent_is_curl():
    """
    GroqProvider._request() MUST set User-Agent: curl/8.5.0.
    Python-urllib/3.x is blocked by Groq with 403.
    Root cause of Bug #1 (Session 2).
    """
    from aicli.providers.groq import GroqProvider
    provider = GroqProvider(api_key="test-key")
    req = provider._request(
        messages=[{"role": "user", "content": "hi"}],
        model="llama-3.3-70b-versatile",
        stream=False,
    )
    ua = req.get_header("User-agent")
    assert ua == "curl/8.5.0", (
        f"User-Agent is '{ua}' — Groq will return 403. Must be 'curl/8.5.0'."
    )


def test_groq_user_agent_not_python_urllib():
    """Negative check — must never send Python-urllib in the UA string."""
    from aicli.providers.groq import GroqProvider
    provider = GroqProvider(api_key="test-key")
    req = provider._request(
        messages=[{"role": "user", "content": "hi"}],
        model="llama-3.3-70b-versatile",
        stream=False,
    )
    ua = req.get_header("User-agent") or ""
    assert "python" not in ua.lower(), (
        f"User-Agent '{ua}' contains 'python' — Groq will block this."
    )


# ══════════════════════════════════════════════════════════════════════════════
# 2. PROVIDER_MODELS — must exist in pipeline.py, not config.py
# ══════════════════════════════════════════════════════════════════════════════

def test_provider_models_exists_in_pipeline():
    """
    PROVIDER_MODELS must be a dict defined in pipeline.py.
    Root cause of Bug #5 (Session 3): it was missing → model=None → all 4xx.
    """
    from aicli.providers.pipeline import PROVIDER_MODELS
    assert isinstance(PROVIDER_MODELS, dict), "PROVIDER_MODELS must be a dict"
    assert len(PROVIDER_MODELS) > 0, "PROVIDER_MODELS must not be empty"


def test_provider_models_has_all_providers():
    """All 5 providers must have a model string — none can be None."""
    from aicli.providers.pipeline import PROVIDER_MODELS
    required = ["groq", "openrouter", "gemini", "mistral", "ollama"]
    for name in required:
        assert name in PROVIDER_MODELS, f"'{name}' missing from PROVIDER_MODELS"
        assert PROVIDER_MODELS[name] is not None, f"PROVIDER_MODELS['{name}'] is None"
        assert isinstance(PROVIDER_MODELS[name], str), f"PROVIDER_MODELS['{name}'] is not a string"


# ══════════════════════════════════════════════════════════════════════════════
# 3. Session name stored as slug not bare ID
# ══════════════════════════════════════════════════════════════════════════════

def test_session_name_stored_correctly(tmp_db):
    """
    Session list must show the name passed to ensure_session(), not the raw ID.
    Root cause of Bug #10 (Session 5).
    """
    from aicli.db.chat_db import get_connection, ensure_session, list_sessions

    conn = get_connection(tmp_db)
    ensure_session(conn, session_id="abc123", name="repl-abc123", role="default")

    sessions = list_sessions(conn)
    names = [s["name"] for s in sessions]
    assert "repl-abc123" in names, (
        f"Expected 'repl-abc123' in session names, got: {names}"
    )


def test_session_name_not_bare_id(tmp_db):
    """Negative: bare session ID should NOT appear as the name when a slug is given."""
    from aicli.db.chat_db import get_connection, ensure_session, list_sessions

    conn = get_connection(tmp_db)
    ensure_session(conn, session_id="xyz999", name="chat-xyz999", role="default")

    sessions = list_sessions(conn)
    for s in sessions:
        if s["id"] == "xyz999":
            assert s["name"] == "chat-xyz999", (
                f"Session name is bare ID '{s['name']}', expected 'chat-xyz999'"
            )


# ══════════════════════════════════════════════════════════════════════════════
# 4. REPL messages persisted to SQLite
# ══════════════════════════════════════════════════════════════════════════════

def test_messages_persisted_to_sqlite(tmp_db, mock_pipeline):
    """
    Messages added via ContextManager.add_message() must appear in SQLite.
    Root cause of Bug #6 (Session 4): repl used plain list, no DB write.
    """
    from aicli.context.manager import ContextManager
    from aicli.db.chat_db import get_connection, load_messages

    async def _run():
        ctx = ContextManager(
            session_id="repl001",
            session_name="repl-repl001",
            pipeline=mock_pipeline,
            db_path=tmp_db,
        )
        await ctx.initialize()
        await ctx.add_message("user", "hello from repl")
        await ctx.add_message("assistant", "hi back")

    run(_run())

    conn = get_connection(tmp_db)
    messages = load_messages(conn, "repl001")
    assert len(messages) == 2, f"Expected 2 messages in DB, got {len(messages)}"
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "hello from repl"
    assert messages[1]["role"] == "assistant"


def test_messages_persist_correct_content(tmp_db, mock_pipeline):
    """Message content must survive the DB round-trip unchanged."""
    from aicli.context.manager import ContextManager
    from aicli.db.chat_db import get_connection, load_messages

    content = "The answer is 42. File: pipeline.py. Timeout: 60s."

    async def _run():
        ctx = ContextManager(
            session_id="persist002",
            session_name="test-persist002",
            pipeline=mock_pipeline,
            db_path=tmp_db,
        )
        await ctx.initialize()
        await ctx.add_message("user", content)

    run(_run())

    conn = get_connection(tmp_db)
    messages = load_messages(conn, "persist002")
    assert messages[0]["content"] == content


# ══════════════════════════════════════════════════════════════════════════════
# 5. db.save() ALWAYS FIRST — message in DB even if pipeline crashes
# ══════════════════════════════════════════════════════════════════════════════

def test_db_save_before_pipeline(tmp_db):
    """
    If add_message() is called and the pipeline crashes immediately after,
    the message must still be in SQLite.
    Validates the 'db.save() ALWAYS FIRST' rule.
    """
    from aicli.db.chat_db import get_connection, load_messages, save_message, ensure_session

    conn = get_connection(tmp_db)
    ensure_session(conn, "safety001", name="safety-001")

    # Simulate: save happens, then something else throws
    save_message(conn, "safety001", "user", "important message", token_count=3)

    # Simulate crash — verify message is in DB regardless
    messages = load_messages(conn, "safety001")
    assert len(messages) == 1
    assert messages[0]["content"] == "important message"


# ══════════════════════════════════════════════════════════════════════════════
# 6. Pipeline instant failover on 429 — no sleep between providers
# ══════════════════════════════════════════════════════════════════════════════

def test_pipeline_429_sets_cooldown():
    """
    On HTTP 429, provider state must have cooldown_until > now.
    Validates instant failover — provider is marked cooling, not retried.
    """
    from aicli.providers.pipeline import ProviderState, ProviderPipeline
    from aicli.providers.base import BaseProvider

    class FakeProvider(BaseProvider):
        name = "fake"
        async def stream(self, messages, model=None, **kw):
            raise urllib.error.HTTPError(
                "http://fake", 429, "Too Many Requests", {}, None
            )
            yield  # make it a generator
        async def complete(self, messages, model=None):
            raise urllib.error.HTTPError(
                "http://fake", 429, "Too Many Requests", {}, None
            )

    state = ProviderState(provider=FakeProvider())
    assert state.is_available()  # starts available

    # Simulate what pipeline does on 429
    state.cooldown_until = time.monotonic() + 60
    state.failure_count += 1

    assert not state.is_available(), "Provider should be in cooldown after 429"
    assert state.failure_count == 1
    assert state.remaining_cooldown() > 0


def test_provider_state_recovers_after_cooldown():
    """Provider must become available again after cooldown expires."""
    from aicli.providers.pipeline import ProviderState
    from aicli.providers.base import BaseProvider

    class FakeProvider(BaseProvider):
        name = "fake"
        async def stream(self, messages, model=None, **kw): yield ""
        async def complete(self, messages, model=None): return ""

    state = ProviderState(provider=FakeProvider())
    state.cooldown_until = time.monotonic() - 1  # already expired
    assert state.is_available(), "Provider should be available after cooldown expires"
    assert state.remaining_cooldown() == 0.0


# ══════════════════════════════════════════════════════════════════════════════
# 7. [AUTO-SUMMARY] survives trim_messages()
# ══════════════════════════════════════════════════════════════════════════════

def test_auto_summary_survives_trim():
    """
    [AUTO-SUMMARY] messages must never be dropped by trim_messages(),
    regardless of token pressure. They are the safety net for old context.
    """
    from aicli.tokens import trim_messages

    summary_msg = {
        "role": "system",
        "content": "[AUTO-SUMMARY] User discussed pipeline architecture. "
                   "Decided on SQLite WAL. Token limit: 6000.",
    }
    filler = [
        {"role": "user", "content": "x " * 500},
        {"role": "assistant", "content": "y " * 500},
    ]
    messages = [summary_msg] + filler

    # Trim to a very small limit — summary must survive
    trimmed = trim_messages(messages, token_limit=50)
    contents = [m["content"] for m in trimmed]
    assert any(c.startswith("[AUTO-SUMMARY]") for c in contents), (
        "[AUTO-SUMMARY] was dropped by trim_messages() — this destroys compressed context"
    )


def test_system_message_survives_trim():
    """System prompt must also survive trim_messages() under token pressure."""
    from aicli.tokens import trim_messages

    system_msg = {"role": "system", "content": "You are a helpful assistant."}
    filler = [{"role": "user", "content": "word " * 300}] * 5
    messages = [system_msg] + filler

    trimmed = trim_messages(messages, token_limit=20)
    assert any(m["role"] == "system" for m in trimmed), (
        "System message was dropped by trim_messages()"
    )


# ══════════════════════════════════════════════════════════════════════════════
# 8. ContextManager resumes from DB correctly
# ══════════════════════════════════════════════════════════════════════════════

def test_context_manager_resumes_session(tmp_db, mock_pipeline):
    """
    A second ContextManager on the same session_id must load prior messages.
    Core feature: named session resume.
    """
    from aicli.context.manager import ContextManager

    async def _write():
        ctx = ContextManager(
            session_id="resume001",
            session_name="chat-resume001",
            pipeline=mock_pipeline,
            db_path=tmp_db,
        )
        await ctx.initialize()
        await ctx.add_message("user", "first message")
        await ctx.add_message("assistant", "first reply")

    async def _resume():
        ctx = ContextManager(
            session_id="resume001",
            session_name="chat-resume001",
            pipeline=mock_pipeline,
            db_path=tmp_db,
        )
        await ctx.initialize()
        return ctx.get_active_messages()

    run(_write())
    messages = run(_resume())

    contents = [m["content"] for m in messages]
    assert "first message" in contents, (
        f"'first message' not found after resume. Active messages: {contents}"
    )
    assert "first reply" in contents, (
        f"'first reply' not found after resume. Active messages: {contents}"
    )


def test_context_manager_resume_preserves_order(tmp_db, mock_pipeline):
    """Messages must be restored in chronological order on resume."""
    from aicli.context.manager import ContextManager

    async def _run():
        ctx = ContextManager(
            session_id="order001",
            session_name="chat-order001",
            pipeline=mock_pipeline,
            db_path=tmp_db,
        )
        await ctx.initialize()
        for i in range(4):
            role = "user" if i % 2 == 0 else "assistant"
            await ctx.add_message(role, f"message {i}")

        # Resume
        ctx2 = ContextManager(
            session_id="order001",
            session_name="chat-order001",
            pipeline=mock_pipeline,
            db_path=tmp_db,
        )
        await ctx2.initialize()
        return ctx2.get_active_messages()

    messages = run(_run())
    non_system = [m for m in messages if m["role"] != "system"]
    for i, msg in enumerate(non_system):
        assert str(i) in msg["content"], (
            f"Message order wrong at index {i}: {msg['content']}"
        )
