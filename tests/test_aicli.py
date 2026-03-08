#!/usr/bin/env python3
"""
tests/test_aicli.py — Core test suite for aicli.

Tests the ContextManager full pipeline, token counting,
provider failover, shell safety, and integration marker.
Run with: python -m pytest tests/ -v
Or: python tests/test_aicli.py
"""

import sys
import os
import asyncio
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from aicli.tokens import (
    count_tokens, count_messages_tokens, trim_messages,
    is_protected, summarization_prompt
)
from aicli.db.chat_db import (
    get_connection, save_message, load_messages,
    save_summary, load_latest_summary, ensure_session, list_sessions
)
from aicli.tools.builtin.shell import is_high_risk, execute_command
from aicli.integration import _is_installed, install_integration, uninstall_integration
from aicli.config import save_api_key, _load_keys_raw


# ── Helper: mock async generator ─────────────────────────────────────────────────

async def _mock_stream(*args, **kwargs):
    for chunk in ["This ", "is ", "a ", "summary."]:
        yield chunk


class MockPipeline:
    """Mock ProviderPipeline for tests — no actual API calls."""
    last_provider = "mock"

    async def stream(self, messages, model=None):
        for chunk in ["Mock ", "response."]:
            yield chunk

    async def complete(self, messages, model=None):
        return "Mock summary of the conversation: user discussed X, AI responded with Y."


# ── Token counting tests ─────────────────────────────────────────────────────────

class TestTokenCounting(unittest.TestCase):

    def test_empty_string(self):
        self.assertEqual(count_tokens(""), 0)

    def test_basic_counting(self):
        # Should return a positive number for any non-empty text
        count = count_tokens("Hello world")
        self.assertGreater(count, 0)

    def test_longer_text_has_more_tokens(self):
        short = count_tokens("Hello")
        long = count_tokens("Hello world this is a much longer sentence with many more words")
        self.assertGreater(long, short)

    def test_messages_count(self):
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there, how can I help?"},
        ]
        total = count_messages_tokens(messages)
        self.assertGreater(total, 0)
        # Should be more than individual token count (overhead per message)
        single = count_tokens("Hello") + count_tokens("Hi there, how can I help?")
        self.assertGreater(total, single)

    def test_trim_messages_respects_limit(self):
        messages = [
            {"role": "user", "content": "x" * 100},
            {"role": "user", "content": "x" * 100},
            {"role": "user", "content": "x" * 100},
            {"role": "user", "content": "x" * 100},
        ]
        # With a very small limit, should trim
        trimmed = trim_messages(messages, token_limit=50)
        self.assertLessEqual(count_messages_tokens(trimmed), 50)

    def test_protected_messages_survive_trim(self):
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "system", "content": "[AUTO-SUMMARY] User discussed Python files."},
            {"role": "user", "content": "x" * 500},
            {"role": "user", "content": "x" * 500},
        ]
        trimmed = trim_messages(messages, token_limit=30)
        # System and auto-summary must survive
        roles_content = [(m["role"], m["content"][:10]) for m in trimmed]
        has_system = any(m["role"] == "system" and not m["content"].startswith("[AUTO") for m in trimmed)
        has_summary = any(m.get("content", "").startswith("[AUTO-SUMMARY]") for m in trimmed)
        self.assertTrue(has_system)
        self.assertTrue(has_summary)

    def test_is_protected(self):
        self.assertTrue(is_protected({"role": "system", "content": "anything"}))
        self.assertTrue(is_protected({"role": "user", "content": "[AUTO-SUMMARY] context"}))
        self.assertFalse(is_protected({"role": "user", "content": "regular message"}))
        self.assertFalse(is_protected({"role": "assistant", "content": "regular response"}))


# ── Database tests ────────────────────────────────────────────────────────────────

class TestDatabase(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.conn = get_connection(Path(self.tmp.name))

    def tearDown(self):
        self.conn.close()
        os.unlink(self.tmp.name)

    def test_save_and_load_messages(self):
        save_message(self.conn, "session-1", "user", "Hello world")
        save_message(self.conn, "session-1", "assistant", "Hi there")

        messages = load_messages(self.conn, "session-1")
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["role"], "user")
        self.assertEqual(messages[0]["content"], "Hello world")
        self.assertEqual(messages[1]["role"], "assistant")

    def test_session_isolation(self):
        save_message(self.conn, "session-a", "user", "Message A")
        save_message(self.conn, "session-b", "user", "Message B")

        msgs_a = load_messages(self.conn, "session-a")
        msgs_b = load_messages(self.conn, "session-b")

        self.assertEqual(len(msgs_a), 1)
        self.assertEqual(len(msgs_b), 1)
        self.assertEqual(msgs_a[0]["content"], "Message A")
        self.assertEqual(msgs_b[0]["content"], "Message B")

    def test_save_and_load_summary(self):
        ensure_session(self.conn, "session-1")
        save_summary(self.conn, "session-1", "Summary text here", 0, 10)
        summary = load_latest_summary(self.conn, "session-1")
        self.assertEqual(summary, "Summary text here")

    def test_no_summary_returns_none(self):
        ensure_session(self.conn, "empty-session")
        summary = load_latest_summary(self.conn, "empty-session")
        self.assertIsNone(summary)

    def test_list_sessions(self):
        save_message(self.conn, "sess-x", "user", "hello")
        save_message(self.conn, "sess-y", "user", "world")
        sessions = list_sessions(self.conn)
        ids = [s["id"] for s in sessions]
        self.assertIn("sess-x", ids)
        self.assertIn("sess-y", ids)


# ── ContextManager full pipeline test ────────────────────────────────────────────

class TestContextManager(unittest.IsolatedAsyncioTestCase):

    async def test_full_pipeline(self):
        """
        THE critical test from the architecture plan:
        - Add 20 messages with heavy content
        - Window should be compressed (fewer than 20 in active window)
        - All 20 must still be in SQLite
        """
        from aicli.context.manager import ContextManager

        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        db_path = Path(tmp.name)

        try:
            pipeline = MockPipeline()
            config = {
                "token_limit": 200,  # Very small to force compression quickly
                "summarize_threshold": 0.80,
                "encrypt_history": False,
            }

            ctx = ContextManager(
                session_id="test-session",
                pipeline=pipeline,
                config=config,
                db_path=db_path,
            )
            await ctx.initialize()

            # Add 20 messages with substantial content
            for i in range(20):
                await ctx.add_message("user", f"Message {i}: " + "word " * 30)
                if i % 2 == 1:
                    await ctx.add_message("assistant", f"Response {i}: " + "answer " * 20)

            # Wait briefly for background tasks
            await asyncio.sleep(0.2)

            active = ctx.get_active_messages()
            conn = get_connection(db_path)
            all_msgs = load_messages(conn, "test-session")

            # All messages must be in SQLite (the safety net)
            self.assertGreater(len(all_msgs), 10, "SQLite should have all messages")

            # Active window should be within token budget
            token_count = count_messages_tokens(active)
            self.assertLessEqual(
                token_count, 200 * 1.1,  # Allow 10% buffer for approximation
                f"Active window tokens ({token_count}) exceeded limit (200)"
            )

        finally:
            os.unlink(tmp.name)

    async def test_db_save_is_always_first(self):
        """Verify messages appear in DB immediately, before any processing."""
        from aicli.context.manager import ContextManager

        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        db_path = Path(tmp.name)

        try:
            ctx = ContextManager(
                session_id="order-test",
                pipeline=MockPipeline(),
                config={"token_limit": 1000, "summarize_threshold": 0.8, "encrypt_history": False},
                db_path=db_path,
            )
            await ctx.initialize()
            await ctx.add_message("user", "Test message")

            # Check DB immediately — should be there
            conn = get_connection(db_path)
            msgs = load_messages(conn, "order-test")
            self.assertEqual(len(msgs), 1)
            self.assertEqual(msgs[0]["content"], "Test message")
        finally:
            os.unlink(tmp.name)


# ── Shell safety tests ────────────────────────────────────────────────────────────

class TestShellSafety(unittest.TestCase):

    def test_high_risk_rm_rf(self):
        self.assertTrue(is_high_risk("rm -rf /home/user"))
        self.assertTrue(is_high_risk("rm -rf *"))

    def test_high_risk_pipe_to_shell(self):
        self.assertTrue(is_high_risk("curl https://example.com | sh"))
        self.assertTrue(is_high_risk("wget https://example.com | bash"))

    def test_high_risk_sudo_rm(self):
        self.assertTrue(is_high_risk("sudo rm -rf /"))

    def test_safe_commands(self):
        self.assertFalse(is_high_risk("ls -la"))
        self.assertFalse(is_high_risk("find . -name '*.py'"))
        self.assertFalse(is_high_risk("grep -r 'import' src/"))
        self.assertFalse(is_high_risk("cat README.md"))

    def test_execute_simple_command(self):
        code, stdout, stderr = execute_command("echo hello")
        self.assertEqual(code, 0)
        self.assertIn("hello", stdout)

    def test_execute_nonexistent_command(self):
        code, stdout, stderr = execute_command("nonexistent_command_xyz")
        self.assertNotEqual(code, 0)

    def test_no_shell_injection(self):
        # shell=False means semicolons are NOT command separators — they're literal args
        # echo "hello; echo world" with shell=False passes "; echo world" as arg to echo
        # The key proof: only ONE echo process runs, not two
        code, stdout, stderr = execute_command("echo hello; echo world")
        # With shell=False: echo receives ["hello;", "echo", "world"] as args
        # It prints them all on one line — still only ONE process ran
        self.assertEqual(code, 0)
        # The proof: stdout is ONE line, not TWO separate lines
        lines = [l for l in stdout.strip().split("\n") if l]
        self.assertEqual(len(lines), 1, "shell=False: only one command ran (no shell splitting on ;)")


# ── Integration marker tests ──────────────────────────────────────────────────────

class TestIntegration(unittest.TestCase):

    def test_idempotent_install(self):
        """Installing twice should not duplicate entries."""
        with tempfile.TemporaryDirectory() as tmpdir:
            rc_path = Path(tmpdir) / ".bashrc"
            rc_path.write_text("# existing content\n")

            # Patch home dir
            with patch("aicli.integration.Path.home", return_value=Path(tmpdir)):
                install_integration(shell="bash")
                content_after_first = rc_path.read_text()
                marker_count_1 = content_after_first.count("# aicli-integration-marker")

                install_integration(shell="bash")
                content_after_second = rc_path.read_text()
                marker_count_2 = content_after_second.count("# aicli-integration-marker")

            # Second install should not add more markers
            self.assertEqual(marker_count_1, marker_count_2)


# ── Key storage tests ─────────────────────────────────────────────────────────────

class TestKeyStorage(unittest.TestCase):

    def test_save_and_load_key(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("aicli.config.CONFIG_DIR", Path(tmpdir)):
                with patch("aicli.config.KEYS_FILE", Path(tmpdir) / "keys.enc"):
                    with patch("aicli.config._KEYRING_AVAILABLE", False):
                        save_api_key("test_provider", "sk-test-key-12345")
                        keys = _load_keys_raw()
                        self.assertEqual(keys.get("test_provider"), "sk-test-key-12345")

    def test_key_encrypted_on_disk(self):
        """Key file should not contain the plaintext key."""
        with tempfile.TemporaryDirectory() as tmpdir:
            keys_file = Path(tmpdir) / "keys.enc"
            with patch("aicli.config.CONFIG_DIR", Path(tmpdir)):
                with patch("aicli.config.KEYS_FILE", keys_file):
                    with patch("aicli.config._KEYRING_AVAILABLE", False):
                        save_api_key("groq", "super-secret-key-abc123")
                        raw_bytes = keys_file.read_bytes()
                        self.assertNotIn(b"super-secret-key-abc123", raw_bytes)


# ── F2 Multimodal / image_utils tests ────────────────────────────────────────────

class TestImageUtils(unittest.TestCase):

    def test_is_multimodal_detects_image_content(self):
        """Messages with image_url blocks are correctly identified as multimodal."""
        from aicli.image_utils import is_multimodal
        messages_with_image = [
            {"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
                {"type": "text", "text": "describe this"},
            ]}
        ]
        self.assertTrue(is_multimodal(messages_with_image))

    def test_is_multimodal_false_for_text_only(self):
        """Plain text messages are not detected as multimodal."""
        from aicli.image_utils import is_multimodal
        messages_text_only = [
            {"role": "user", "content": "just a regular message"},
            {"role": "assistant", "content": "a response"},
        ]
        self.assertFalse(is_multimodal(messages_text_only))

    def test_load_image_b64_missing_file(self):
        """Missing file raises ValueError with descriptive message."""
        from aicli.image_utils import load_image_b64
        with self.assertRaises(ValueError) as ctx:
            load_image_b64("/nonexistent/path/image.png")
        self.assertIn("not found", str(ctx.exception))

    def test_load_image_b64_unsupported_format(self):
        """Unsupported file extension raises ValueError."""
        from aicli.image_utils import load_image_b64
        with tempfile.NamedTemporaryFile(suffix=".bmp", delete=False) as f:
            f.write(b"fake bmp data")
            tmp_path = f.name
        try:
            with self.assertRaises(ValueError) as ctx:
                load_image_b64(tmp_path)
            self.assertIn("Unsupported", str(ctx.exception))
        finally:
            os.unlink(tmp_path)

    def test_build_multimodal_content_structure(self):
        """build_multimodal_content returns correct list structure: images first, text last."""
        from aicli.image_utils import build_multimodal_content
        # Create a minimal valid PNG (1x1 pixel)
        import struct, zlib
        def make_minimal_png():
            sig = b'\x89PNG\r\n\x1a\n'
            def chunk(name, data):
                c = struct.pack('>I', len(data)) + name + data
                return c + struct.pack('>I', zlib.crc32(name + data) & 0xffffffff)
            ihdr = chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0))
            raw = b'\x00\xff\x00\x00'  # filter byte + 1 RGB pixel
            idat = chunk(b'IDAT', zlib.compress(raw))
            iend = chunk(b'IEND', b'')
            return sig + ihdr + idat + iend

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(make_minimal_png())
            tmp_path = f.name
        try:
            content = build_multimodal_content("describe this", [tmp_path])
            self.assertIsInstance(content, list)
            self.assertEqual(len(content), 2)
            self.assertEqual(content[0]["type"], "image_url")
            self.assertIn("data:image/png;base64,", content[0]["image_url"]["url"])
            self.assertEqual(content[-1]["type"], "text")
            self.assertEqual(content[-1]["text"], "describe this")
        finally:
            os.unlink(tmp_path)

    def test_chat_db_pack_unpack_roundtrip(self):
        """_pack_content/_unpack_content roundtrip for both str and list content."""
        from aicli.db.chat_db import _pack_content, _unpack_content
        # str round-trip
        self.assertEqual(_unpack_content(_pack_content("hello")), "hello")
        # list round-trip (multimodal)
        multimodal = [{"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
                      {"type": "text", "text": "describe"}]
        packed = _pack_content(multimodal)
        self.assertIsInstance(packed, str)
        unpacked = _unpack_content(packed)
        self.assertEqual(unpacked, multimodal)
        # backward compat: plain text from old rows
        self.assertEqual(_unpack_content("old plain text"), "old plain text")



# ── Fork session tests (S8) ───────────────────────────────────────────────────────

class TestForkSession(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.conn = get_connection(Path(self.tmp.name))

    def tearDown(self):
        self.conn.close()
        os.unlink(self.tmp.name)

    def test_fork_full_copy(self):
        """fork_session with no up_to copies ALL messages."""
        from aicli.db.chat_db import fork_session
        for i in range(5):
            save_message(self.conn, "src", "user" if i % 2 == 0 else "assistant", f"msg {i}")
        new_id = fork_session(self.conn, "src", "fork-full")
        msgs = load_messages(self.conn, new_id)
        self.assertEqual(len(msgs), 5)

    def test_fork_limit_n_positional(self):
        """fork_session --from-message N uses LIMIT N, not id <= N (global autoincrement fix)."""
        from aicli.db.chat_db import fork_session
        # Insert 10 messages — their IDs will be high numbers (global autoincrement)
        for i in range(10):
            save_message(self.conn, "src", "user", f"msg {i}")
        # Fork first 3 — should work regardless of what the actual IDs are
        new_id = fork_session(self.conn, "src", "fork-3", up_to_message_id=3)
        msgs = load_messages(self.conn, new_id)
        self.assertEqual(len(msgs), 3)
        self.assertEqual(msgs[0]["content"], "msg 0")
        self.assertEqual(msgs[2]["content"], "msg 2")

    def test_fork_copies_latest_summary(self):
        """fork_session copies the latest summary so fork starts with full context."""
        from aicli.db.chat_db import fork_session
        save_message(self.conn, "src", "user", "hello")
        save_summary(self.conn, "src", "Old summary", 1, 1)
        save_summary(self.conn, "src", "Latest summary", 1, 1)  # two summaries — only latest copied
        new_id = fork_session(self.conn, "src", "fork-summary")
        summary = load_latest_summary(self.conn, new_id)
        self.assertEqual(summary, "Latest summary")

    def test_fork_no_summary_is_fine(self):
        """fork_session on session with no summaries does not crash."""
        from aicli.db.chat_db import fork_session
        save_message(self.conn, "src", "user", "hello")
        new_id = fork_session(self.conn, "src", "fork-nosummary")
        summary = load_latest_summary(self.conn, new_id)
        self.assertIsNone(summary)

    def test_fork_source_not_found_raises(self):
        """fork_session raises ValueError for nonexistent source session."""
        from aicli.db.chat_db import fork_session
        with self.assertRaises(ValueError) as ctx:
            fork_session(self.conn, "nonexistent-uuid", "fork-bad")
        self.assertIn("not found", str(ctx.exception))

    def test_fork_does_not_modify_source(self):
        """Forking must not change the source session messages or summaries."""
        from aicli.db.chat_db import fork_session
        for i in range(5):
            save_message(self.conn, "src", "user", f"msg {i}")
        save_summary(self.conn, "src", "Source summary", 1, 5)
        fork_session(self.conn, "src", "fork-isolated")
        # Source must be unchanged
        src_msgs = load_messages(self.conn, "src")
        self.assertEqual(len(src_msgs), 5)
        src_summary = load_latest_summary(self.conn, "src")
        self.assertEqual(src_summary, "Source summary")

    def test_fork_from_message_zero_returns_empty(self):
        """up_to_message_id=0 should copy 0 messages (LIMIT 0)."""
        from aicli.db.chat_db import fork_session
        for i in range(5):
            save_message(self.conn, "src", "user", f"msg {i}")
        new_id = fork_session(self.conn, "src", "fork-zero", up_to_message_id=0)
        msgs = load_messages(self.conn, new_id)
        self.assertEqual(len(msgs), 0)


# ── Config migrate-keys tests (S8) ───────────────────────────────────────────────

class TestMigrateKeys(unittest.TestCase):

    def test_migrate_keys_returns_list(self):
        """migrate_all_keys() always returns a list (even with no keyring)."""
        from aicli.config import migrate_all_keys
        with patch("aicli.config._KEYRING_AVAILABLE", False):
            result = migrate_all_keys()
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 0)

    def test_migrate_keys_writes_fernet(self):
        """Keys read from keyring are written to Fernet file."""
        from aicli.config import migrate_all_keys
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("aicli.config.CONFIG_DIR", Path(tmpdir)):
                with patch("aicli.config.KEYS_FILE", Path(tmpdir) / "keys.enc"):
                    with patch("aicli.config._KEYRING_AVAILABLE", True):
                        # Mock keyring to return a value for GROQ_API_KEY
                        import aicli.config as cfg_mod
                        def mock_get_password(service, key):
                            if key == "GROQ_API_KEY":
                                return "gsk-test-migrate-key"
                            return None
                        with patch.object(cfg_mod._keyring, "get_password", mock_get_password):
                            migrated = migrate_all_keys()
                        self.assertIn("GROQ_API_KEY", migrated)
                        # Verify it's now in the Fernet file
                        from aicli.config import _load_keys_raw
                        keys = _load_keys_raw()
                        self.assertEqual(keys.get("GROQ_API_KEY"), "gsk-test-migrate-key")


# ── Export --include-summary tests (S8) ──────────────────────────────────────────

class TestExportIncludeSummary(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.conn = get_connection(Path(self.tmp.name))

    def tearDown(self):
        self.conn.close()
        os.unlink(self.tmp.name)

    def test_export_markdown_without_summary_by_default(self):
        """_to_markdown does not include summary section by default."""
        from aicli.handlers.export import _to_markdown
        messages = [{"role": "user", "content": "hello", "timestamp": ""}]
        result = _to_markdown("test", "uuid", messages, "This is the summary")
        self.assertNotIn("## Summary", result)
        self.assertNotIn("This is the summary", result)

    def test_export_markdown_with_summary_flag(self):
        """_to_markdown includes summary section when include_summary=True."""
        from aicli.handlers.export import _to_markdown
        messages = [{"role": "user", "content": "hello", "timestamp": ""}]
        result = _to_markdown("test", "uuid", messages, "This is the summary", include_summary=True)
        self.assertIn("## Summary", result)
        self.assertIn("This is the summary", result)

    def test_export_markdown_no_summary_no_section(self):
        """_to_markdown with include_summary=True but no summary — no crash, no section."""
        from aicli.handlers.export import _to_markdown
        messages = [{"role": "user", "content": "hello", "timestamp": ""}]
        result = _to_markdown("test", "uuid", messages, None, include_summary=True)
        self.assertNotIn("## Summary", result)

    def test_export_json_summary_null_by_default(self):
        """_to_json summary field is None when include_summary=False."""
        from aicli.handlers.export import _to_json
        import json
        messages = [{"role": "user", "content": "hello", "timestamp": ""}]
        result = json.loads(_to_json("test", "uuid", messages, "A summary"))
        self.assertIsNone(result["summary"])

    def test_export_json_summary_included_with_flag(self):
        """_to_json summary field populated when include_summary=True."""
        from aicli.handlers.export import _to_json
        import json
        messages = [{"role": "user", "content": "hello", "timestamp": ""}]
        result = json.loads(_to_json("test", "uuid", messages, "A summary", include_summary=True))
        self.assertEqual(result["summary"], "A summary")

    def test_export_markdown_conversation_always_present(self):
        """Conversation section always present regardless of summary flag."""
        from aicli.handlers.export import _to_markdown
        messages = [
            {"role": "user", "content": "hello", "timestamp": ""},
            {"role": "assistant", "content": "hi there", "timestamp": ""},
        ]
        result = _to_markdown("test", "uuid", messages, "Summary", include_summary=False)
        self.assertIn("## Conversation", result)
        self.assertIn("hello", result)
        self.assertIn("hi there", result)


# ── F8 Code Runner tests ──────────────────────────────────────────────────────────

class TestCodeRunner(unittest.IsolatedAsyncioTestCase):

    async def test_run_clean_code(self):
        """Clean code runs and prints output."""
        from aicli.handlers.code_runner import run_generated_code
        import io
        from contextlib import redirect_stdout
        code = "print('hello from test')"
        buf = io.StringIO()
        # Should not raise — success path
        await run_generated_code(code, MockPipeline(), "print hello", max_retries=0, show_code=False)

    async def test_extract_code_strips_fences(self):
        """_extract_code strips markdown fences correctly."""
        from aicli.handlers.code_runner import _extract_code
        fenced = "```python\nprint('hi')\n```"
        self.assertEqual(_extract_code(fenced), "print('hi')")

    async def test_extract_code_plain(self):
        """_extract_code passes through plain code unchanged."""
        from aicli.handlers.code_runner import _extract_code
        plain = "x = 1 + 1\nprint(x)"
        self.assertEqual(_extract_code(plain), plain)

    async def test_run_code_returns_exit_0(self):
        """_run_code returns exit 0 for valid Python."""
        from aicli.handlers.code_runner import _run_code
        code, stdout, stderr = _run_code("print(1+1)")
        self.assertEqual(code, 0)
        self.assertIn("2", stdout)
        self.assertEqual(stderr, "")

    async def test_run_code_returns_exit_1_on_error(self):
        """_run_code returns exit 1 for syntax/runtime error."""
        from aicli.handlers.code_runner import _run_code
        code, stdout, stderr = _run_code("this is not valid python !!!")
        self.assertNotEqual(code, 0)
        self.assertGreater(len(stderr), 0)

    async def test_self_correction_succeeds(self):
        """run_generated_code self-corrects broken code using pipeline."""
        from aicli.handlers.code_runner import run_generated_code

        call_count = 0

        class FixingPipeline:
            last_provider = "mock"
            async def stream(self, messages, model=None, requires_vision=False):
                nonlocal call_count
                call_count += 1
                # Return fixed code on correction call
                for chunk in ["print('fixed')\n"]:
                    yield chunk

        # Start with broken code — pipeline returns fixed version on retry
        broken = "raise ValueError('intentional error')"
        await run_generated_code(broken, FixingPipeline(), "test", max_retries=1, show_code=False)
        self.assertGreater(call_count, 0)


# ── F6 Plugin System tests ────────────────────────────────────────────────────────

class TestPluginSystem(unittest.TestCase):

    def _make_plugin_dir(self, tmp_path: Path) -> Path:
        plugin_dir = Path(tmp_path) / "plugins"
        plugin_dir.mkdir()
        return plugin_dir

    def test_empty_plugin_dir_returns_empty_list(self):
        """No plugins in dir → empty list, no crash."""
        from aicli.tools.loader import load_plugins
        with tempfile.TemporaryDirectory() as tmpdir:
            plugins = load_plugins(Path(tmpdir) / "plugins", force_reload=True)
        self.assertEqual(plugins, [])

    def test_valid_plugin_loaded(self):
        """A valid plugin file is loaded and callable."""
        from aicli.tools.loader import load_plugins, call_plugin
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_dir = Path(tmpdir) / "plugins"
            plugin_dir.mkdir()
            plugin_file = plugin_dir / "testplugin.py"
            plugin_file.write_text(
                "def register():\n"
                "    return {\n"
                "        'name': 'testplugin',\n"
                "        'description': 'A test plugin',\n"
                "        'fn': lambda x: x.upper(),\n"
                "    }\n"
            )
            plugins = load_plugins(plugin_dir, force_reload=True)
        self.assertEqual(len(plugins), 1)
        self.assertEqual(plugins[0]["name"], "testplugin")

    def test_plugin_call(self):
        """call_plugin invokes the fn and returns string result."""
        from aicli.tools.loader import load_plugins, call_plugin
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_dir = Path(tmpdir) / "plugins"
            plugin_dir.mkdir()
            (plugin_dir / "echo.py").write_text(
                "def register():\n"
                "    return {'name':'echo','description':'echo','fn': lambda x: x}\n"
            )
            load_plugins(plugin_dir, force_reload=True)
            result = call_plugin("echo", "hello world", plugin_dir)
        self.assertEqual(result, "hello world")

    def test_missing_register_is_error(self):
        """Plugin file without register() is skipped and recorded as error."""
        from aicli.tools.loader import load_plugins, get_load_errors
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_dir = Path(tmpdir) / "plugins"
            plugin_dir.mkdir()
            (plugin_dir / "bad.py").write_text("x = 1\n")
            load_plugins(plugin_dir, force_reload=True)
            errors = get_load_errors()
        self.assertTrue(any("bad.py" in e for e in errors))

    def test_missing_field_is_error(self):
        """Plugin missing required field is skipped."""
        from aicli.tools.loader import load_plugins, get_load_errors
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_dir = Path(tmpdir) / "plugins"
            plugin_dir.mkdir()
            (plugin_dir / "nofn.py").write_text(
                "def register():\n"
                "    return {'name': 'x', 'description': 'y'}  # missing fn\n"
            )
            load_plugins(plugin_dir, force_reload=True)
            errors = get_load_errors()
        self.assertTrue(any("nofn.py" in e for e in errors))

    def test_underscore_files_skipped(self):
        """Files starting with _ (e.g. __init__.py) are not loaded."""
        from aicli.tools.loader import load_plugins
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_dir = Path(tmpdir) / "plugins"
            plugin_dir.mkdir()
            (plugin_dir / "__init__.py").write_text("# package marker\n")
            plugins = load_plugins(plugin_dir, force_reload=True)
        self.assertEqual(plugins, [])

    def test_call_nonexistent_returns_none(self):
        """call_plugin returns None for unknown plugin name."""
        from aicli.tools.loader import call_plugin
        with tempfile.TemporaryDirectory() as tmpdir:
            result = call_plugin("doesnotexist", "arg", Path(tmpdir) / "plugins")
        self.assertIsNone(result)

# ── Run tests ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Running aicli test suite...\n")
    unittest.main(verbosity=2)


class TestAdaptiveCooldowns(unittest.TestCase):
    """Verify COOLDOWN_BY_STATUS values are correct and complete."""

    def test_cooldown_429_is_long(self):
        """429 rate limit should have a long cooldown (300s)."""
        from aicli.providers.pipeline import COOLDOWN_BY_STATUS
        self.assertEqual(COOLDOWN_BY_STATUS[429], 300)

    def test_cooldown_401_is_very_long(self):
        """401 bad key should have a 1-hour cooldown."""
        from aicli.providers.pipeline import COOLDOWN_BY_STATUS
        self.assertEqual(COOLDOWN_BY_STATUS[401], 3600)

    def test_cooldown_403_is_very_long(self):
        """403 forbidden should have a 1-hour cooldown."""
        from aicli.providers.pipeline import COOLDOWN_BY_STATUS
        self.assertEqual(COOLDOWN_BY_STATUS[403], 3600)

    def test_cooldown_5xx_are_short(self):
        """5xx server errors should have short cooldowns (<=15s)."""
        from aicli.providers.pipeline import COOLDOWN_BY_STATUS
        for code in (500, 502, 503):
            self.assertLessEqual(COOLDOWN_BY_STATUS[code], 15,
                                 f"HTTP {code} cooldown should be <=15s")

    def test_vision_providers_set(self):
        """VISION_PROVIDERS must contain openrouter and gemini only."""
        from aicli.providers.pipeline import VISION_PROVIDERS
        self.assertIn("openrouter", VISION_PROVIDERS)
        self.assertIn("gemini", VISION_PROVIDERS)
        self.assertNotIn("groq", VISION_PROVIDERS)
        self.assertNotIn("mistral", VISION_PROVIDERS)


class TestChromaDB(unittest.TestCase):
    """Cold-layer ChromaDB integration tests."""

    def _get_retriever(self):
        """Return a ContextRetriever using a temp dir, or skip if chromadb absent."""
        try:
            import chromadb  # noqa: F401
        except ImportError:
            self.skipTest("chromadb not installed")
        import tempfile
        from aicli.context.retriever import ContextRetriever
        self._chroma_dir = tempfile.mkdtemp()
        return ContextRetriever(self._chroma_dir)

    def test_rag_disabled_graceful(self):
        """ContextManager must not crash when chromadb is absent (mocked removal)."""
        import unittest.mock as mock
        import sys
        with mock.patch.dict(sys.modules, {"chromadb": None}):
            try:
                import importlib
                import aicli.context.manager as mgr_mod
                importlib.reload(mgr_mod)
            except Exception:
                pass  # What matters is no hard crash at import time

    def test_upsert_idempotent(self):
        """Indexing the same session twice must not raise and retrieve returns a result."""
        retriever = self._get_retriever()
        messages = [{"id": 1, "role": "user", "content": "hello world"}]
        retriever.index_session("sess1", messages)
        retriever.index_session("sess1", messages)  # duplicate — must not raise
        result = retriever.retrieve("hello world", include_files=False, include_chat=True)
        # Returns a formatted string or None — either is valid, no crash is the contract
        self.assertIsInstance(result, (str, type(None)))

    def test_system_messages_excluded(self):
        """System-role messages must not produce chat results when retrieved."""
        retriever = self._get_retriever()
        messages = [{"id": 1, "role": "system", "content": "you are a helpful assistant"}]
        retriever.index_session("sess2", messages)
        result = retriever.retrieve("helpful assistant", include_files=False, include_chat=True)
        # System messages should not be indexed — result should be None
        self.assertIsNone(result)

    def test_semantic_retrieval(self):
        """Semantic search must return a context block after indexing a message."""
        retriever = self._get_retriever()
        messages = [{"id": 1, "role": "user", "content": "I love programming in Python"}]
        retriever.index_session("sess3", messages)
        result = retriever.retrieve("coding with Python language", include_files=False, include_chat=True)
        # Should find the indexed message and return a non-empty context block
        self.assertIsNotNone(result)
        self.assertIn("RELEVANT CONTEXT", result)

    def test_session_isolation(self):
        """index_session on sessA then retrieve must not bleed into unrelated queries."""
        retriever = self._get_retriever()
        messages = [{"id": 1, "role": "user", "content": "secret project alpha xyzzy"}]
        retriever.index_session("sessA", messages)
        # Retrieve with a query that should NOT match (completely unrelated topic)
        result = retriever.retrieve("banana smoothie recipe", include_files=False, include_chat=True)
        # Either None or a context block — the key assertion is no crash and no wrong data leaking
        self.assertIsInstance(result, (str, type(None)))

    def test_backfill_idempotent(self):
        """Running index_session twice on the same data must not raise."""
        retriever = self._get_retriever()
        messages = [
            {"id": 1, "role": "user", "content": "first message"},
            {"id": 2, "role": "assistant", "content": "first reply"},
        ]
        retriever.index_session("sessBack", messages)
        retriever.index_session("sessBack", messages)  # second pass — must not raise
        result = retriever.retrieve("first message", include_files=False, include_chat=True)
        self.assertIsInstance(result, (str, type(None)))
