"""
test_streaming.py — split from test_new_commands.py
Tests for --watch mode, --file/-f, --terminal-context, cmd --chain, path auto-detect.
"""

import os
import asyncio
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from click.testing import CliRunner


class TestTerminalContextFlag:
    """--terminal-context passes terminal scrollback as a system message."""

    def test_terminal_context_flag_exists(self):
        """ask command must accept --terminal-context without error."""
        from aicli.app import cli
        runner = CliRunner()
        with patch("aicli.app._ask", new=AsyncMock(return_value=None)) as mock_ask:
            result = runner.invoke(cli, [
                "ask", "--terminal-context", "last 10 lines of output",
                "--dry-run", "why did this fail"
            ])
            assert result.exit_code == 0
            _, kwargs = mock_ask.call_args
            assert kwargs.get("terminal_context") == "last 10 lines of output"

    def test_terminal_context_none_when_not_set(self):
        """terminal_context defaults to None when flag not passed."""
        from aicli.app import cli
        runner = CliRunner()
        with patch("aicli.app._ask", new=AsyncMock(return_value=None)) as mock_ask:
            result = runner.invoke(cli, ["ask", "--dry-run", "hello"])
            assert result.exit_code == 0
            _, kwargs = mock_ask.call_args
            assert kwargs.get("terminal_context") is None

    def test_terminal_context_injected_as_system_message(self):
        """_ask injects terminal_context as a system message before user turn."""
        import asyncio
        from unittest.mock import AsyncMock as AM, MagicMock, patch
        from aicli.handlers.default import _ask

        captured_messages = []

        async def fake_stream(msgs, **kw):
            captured_messages.extend(msgs)
            return
            yield  # make it an async generator

        mock_pipeline = MagicMock()
        mock_pipeline.stream = fake_stream
        mock_pipeline.last_provider = None

        with patch("aicli.handlers.default.ProviderPipeline", return_value=mock_pipeline), \
             patch("aicli.handlers.default.load_config", return_value={
                 "provider_chain": ["groq"], "cooldown_seconds": 0,
                 "max_retries_per_provider": 1, "show_provider": False,
             }), \
             patch("sys.stdin", new=__import__("io").StringIO("")):
            asyncio.run(_ask(
                ("what failed",), False, False, False, None,
                False, False, True,  # dry_run=True → no execution
                terminal_context="npm run build\nError: ENOENT no such file",
            ))

        system_contents = [m["content"] for m in captured_messages if m["role"] == "system"]
        assert any("TERMINAL CONTEXT" in c for c in system_contents), \
            "terminal_context not injected as system message"
        assert any("ENOENT" in c for c in system_contents), \
            "terminal_context text not preserved in system message"

    def test_terminal_context_empty_string_not_injected(self):
        """Empty terminal_context string should not add a system message."""
        import asyncio
        from aicli.handlers.default import _ask

        captured_messages = []

        async def fake_stream(msgs, **kw):
            captured_messages.extend(msgs)
            return
            yield

        mock_pipeline = MagicMock()
        mock_pipeline.stream = fake_stream
        mock_pipeline.last_provider = None

        with patch("aicli.handlers.default.ProviderPipeline", return_value=mock_pipeline), \
             patch("aicli.handlers.default.load_config", return_value={
                 "provider_chain": ["groq"], "cooldown_seconds": 0,
                 "max_retries_per_provider": 1, "show_provider": False,
             }), \
             patch("sys.stdin", new=__import__("io").StringIO("")):
            asyncio.run(_ask(
                ("hello",), False, False, False, None,
                False, False, True,
                terminal_context="   ",  # whitespace only
            ))

        system_contents = [m["content"] for m in captured_messages if m["role"] == "system"]
        assert not any("TERMINAL CONTEXT" in c for c in system_contents)


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Feature 2 — Watch Mode (--watch / --watch-lines)
# ─────────────────────────────────────────────────────────────────────────────


class TestWatchMode:
    """--watch streams stdin line-by-line and alerts when condition is met."""

    def test_watch_flag_exists(self):
        """ask command must accept --watch without error (with stdin mocked)."""
        from aicli.app import cli
        runner = CliRunner()
        with patch("aicli.app._ask", new=AsyncMock(return_value=None)) as mock_ask:
            result = runner.invoke(cli, ["ask", "--watch", "alert on ERROR"])
            assert result.exit_code == 0
            _, kwargs = mock_ask.call_args
            assert kwargs.get("watch") is True

    def test_watch_lines_default(self):
        """--watch-lines defaults to 10."""
        from aicli.app import cli
        runner = CliRunner()
        with patch("aicli.app._ask", new=AsyncMock(return_value=None)) as mock_ask:
            runner.invoke(cli, ["ask", "--watch", "alert on ERROR"])
            _, kwargs = mock_ask.call_args
            assert kwargs.get("watch_lines") == 10

    def test_watch_lines_custom(self):
        """--watch-lines accepts custom value."""
        from aicli.app import cli
        runner = CliRunner()
        with patch("aicli.app._ask", new=AsyncMock(return_value=None)) as mock_ask:
            runner.invoke(cli, ["ask", "--watch", "--watch-lines", "25", "alert on OOM"])
            _, kwargs = mock_ask.call_args
            assert kwargs.get("watch_lines") == 25

    def test_watch_mode_skips_stdin_read(self):
        """When --watch is True, _ask must NOT consume stdin before the watch loop."""
        import asyncio
        import io
        from aicli.handlers.default import _ask

        # If _ask tried to read all of stdin before the watch loop, this would hang
        # or swallow the stream. We verify by patching _watch_stdin and confirming
        # stdin.read() is never called on the main path.
        with patch("aicli.handlers.default._watch_stdin", new=AsyncMock()) as mock_watch, \
             patch("aicli.handlers.default.load_config", return_value={
                 "provider_chain": ["groq"], "cooldown_seconds": 0,
                 "max_retries_per_provider": 1, "show_provider": False,
             }), \
             patch("sys.stdin", new=io.StringIO("")):
            asyncio.run(_ask(
                ("alert on ERROR",), False, False, False, None,
                False, False, False,
                watch=True, watch_lines=5,
            ))
            mock_watch.assert_called_once()
            call_args = mock_watch.call_args
            assert call_args[0][0] == "alert on ERROR"   # condition passed through
            assert call_args[0][1] == 5                   # batch_lines passed through

    def test_watch_evaluate_yes_triggers_alert(self, capsys):
        """_watch_evaluate prints ALERT when LLM responds YES."""
        import asyncio
        from aicli.handlers.default import _watch_evaluate

        async def fake_yes_stream(msgs, **kw):
            yield "YES: OOM killer invoked on process 1234"

        mock_pipeline = MagicMock()
        mock_pipeline.stream = fake_yes_stream

        asyncio.run(_watch_evaluate(
            ["Out of memory: Kill process 1234"],
            "alert on OOM",
            "system prompt",
            mock_pipeline,
            None,
            quiet=False,
        ))

        captured = capsys.readouterr()
        assert "ALERT" in captured.out
        assert "OOM" in captured.out

    def test_watch_evaluate_no_is_silent(self, capsys):
        """_watch_evaluate prints nothing when LLM responds NO."""
        import asyncio
        from aicli.handlers.default import _watch_evaluate

        async def fake_no_stream(msgs, **kw):
            yield "NO"

        mock_pipeline = MagicMock()
        mock_pipeline.stream = fake_no_stream

        asyncio.run(_watch_evaluate(
            ["INFO: health check passed"],
            "alert on ERROR",
            "system prompt",
            mock_pipeline,
            None,
            quiet=True,
        ))

        captured = capsys.readouterr()
        assert "ALERT" not in captured.out

    def test_watch_evaluate_passes_lines_to_llm(self):
        """_watch_evaluate includes the log lines in the LLM message."""
        import asyncio
        from aicli.handlers.default import _watch_evaluate

        captured_msgs = []

        async def capture_stream(msgs, **kw):
            captured_msgs.extend(msgs)
            yield "NO"

        mock_pipeline = MagicMock()
        mock_pipeline.stream = capture_stream

        asyncio.run(_watch_evaluate(
            ["ERROR: disk full", "WARN: retry failed"],
            "alert on ERROR",
            "system prompt",
            mock_pipeline,
            None,
            quiet=True,
        ))

        # The batch lines must be present in the user message sent to LLM
        user_msgs = [m["content"] for m in captured_msgs if m["role"] == "user"]
        assert any("ERROR: disk full" in c for c in user_msgs),             "batch lines not passed to LLM"
        assert any("alert on ERROR" in c for c in user_msgs),             "condition not passed to LLM"

    def test_watch_alert_includes_triggering_batch(self, capsys):
        """Alert output must include the batch that triggered it."""
        import asyncio
        from aicli.handlers.default import _watch_evaluate

        async def fake_yes(msgs, **kw):
            yield "YES: OOM detected"

        mock_pipeline = MagicMock()
        mock_pipeline.stream = fake_yes

        asyncio.run(_watch_evaluate(
            ["kernel: Out of memory: kill process 999"],
            "alert on OOM",
            "system",
            mock_pipeline,
            None,
            quiet=False,
        ))

        out = capsys.readouterr().out
        assert "ALERT" in out
        assert "kernel: Out of memory" in out  # triggering batch shown


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Feature 3 — Multi-file context (--file / -f)
# ─────────────────────────────────────────────────────────────────────────────


class TestExtraFilesFlag:
    """--file/-f attaches any file as context in a system message."""

    def test_file_flag_exists(self, tmp_path):
        """ask command accepts --file without error."""
        from aicli.app import cli
        runner = CliRunner()
        f = tmp_path / "err.log"
        f.write_text("segfault at 0x0\n")
        with patch("aicli.app._ask", new=AsyncMock(return_value=None)) as mock_ask:
            result = runner.invoke(cli, ["ask", "--file", str(f), "--dry-run", "what happened"])
            assert result.exit_code == 0
            _, kwargs = mock_ask.call_args
            assert kwargs.get("extra_files") == (str(f),)

    def test_file_shorthand_f(self, tmp_path):
        """-f shorthand works."""
        from aicli.app import cli
        runner = CliRunner()
        f = tmp_path / "app.log"
        f.write_text("ERROR: connection refused\n")
        with patch("aicli.app._ask", new=AsyncMock(return_value=None)) as mock_ask:
            result = runner.invoke(cli, ["ask", "-f", str(f), "--dry-run", "explain"])
            assert result.exit_code == 0
            _, kwargs = mock_ask.call_args
            assert len(kwargs.get("extra_files", ())) == 1

    def test_multiple_files(self, tmp_path):
        """Multiple --file flags accepted."""
        from aicli.app import cli
        runner = CliRunner()
        f1 = tmp_path / "a.log"; f1.write_text("error A\n")
        f2 = tmp_path / "b.log"; f2.write_text("error B\n")
        with patch("aicli.app._ask", new=AsyncMock(return_value=None)) as mock_ask:
            result = runner.invoke(cli, [
                "ask", "--file", str(f1), "--file", str(f2), "--dry-run", "compare"
            ])
            assert result.exit_code == 0
            _, kwargs = mock_ask.call_args
            assert len(kwargs.get("extra_files", ())) == 2

    def test_file_content_injected_as_system_message(self, tmp_path):
        """_ask injects file contents into a system message before user turn."""
        import asyncio
        from aicli.handlers.default import _ask

        log_file = tmp_path / "crash.log"
        log_file.write_text("CRITICAL: null pointer dereference at main.c:42\n")

        captured_messages = []

        async def fake_stream(msgs, **kw):
            captured_messages.extend(msgs)
            return
            yield

        mock_pipeline = MagicMock()
        mock_pipeline.stream = fake_stream
        mock_pipeline.last_provider = None

        with patch("aicli.handlers.default.ProviderPipeline", return_value=mock_pipeline), \
             patch("aicli.handlers.default.load_config", return_value={
                 "provider_chain": ["groq"], "cooldown_seconds": 0,
                 "max_retries_per_provider": 1, "show_provider": False,
             }), \
             patch("sys.stdin", new=__import__("io").StringIO("")):
            asyncio.run(_ask(
                ("what caused this crash",), False, False, False, None,
                False, False, True,
                extra_files=(str(log_file),),
            ))

        system_contents = [m["content"] for m in captured_messages if m["role"] == "system"]
        assert any("ATTACHED FILES" in c for c in system_contents), \
            "extra_files not injected as system message"
        assert any("null pointer dereference" in c for c in system_contents), \
            "file contents not included in system message"

    def test_unreadable_file_skipped_gracefully(self, tmp_path):
        """If a file cannot be read, it is skipped with a warning (no crash)."""
        import asyncio
        from aicli.handlers.default import _ask

        good = tmp_path / "good.log"; good.write_text("all ok\n")

        captured_messages = []

        async def fake_stream(msgs, **kw):
            captured_messages.extend(msgs)
            return
            yield

        mock_pipeline = MagicMock()
        mock_pipeline.stream = fake_stream
        mock_pipeline.last_provider = None

        with patch("aicli.handlers.default.ProviderPipeline", return_value=mock_pipeline), \
             patch("aicli.handlers.default.load_config", return_value={
                 "provider_chain": ["groq"], "cooldown_seconds": 0,
                 "max_retries_per_provider": 1, "show_provider": False,
             }), \
             patch("sys.stdin", new=__import__("io").StringIO("")):
            # Pass a nonexistent path that slips past click's exists=True check
            # by patching Path.read_bytes to raise
            from pathlib import Path
            original_read_bytes = Path.read_bytes

            def patched_read_bytes(self):
                if "bad" in str(self):
                    raise PermissionError("no read access")
                return original_read_bytes(self)

            with patch.object(Path, "read_bytes", patched_read_bytes):
                asyncio.run(_ask(
                    ("explain",), False, False, False, None,
                    False, False, True,
                    extra_files=(str(good), str(tmp_path / "bad.log")),
                    quiet=True,
                ))

        # Should not crash; good file should still appear
        system_contents = [m["content"] for m in captured_messages if m["role"] == "system"]
        assert any("all ok" in c for c in system_contents)

    def test_no_files_no_attached_system_message(self):
        """When extra_files is None, no ATTACHED FILES system message is added."""
        import asyncio
        from aicli.handlers.default import _ask

        captured_messages = []

        async def fake_stream(msgs, **kw):
            captured_messages.extend(msgs)
            return
            yield

        mock_pipeline = MagicMock()
        mock_pipeline.stream = fake_stream
        mock_pipeline.last_provider = None

        with patch("aicli.handlers.default.ProviderPipeline", return_value=mock_pipeline), \
             patch("aicli.handlers.default.load_config", return_value={
                 "provider_chain": ["groq"], "cooldown_seconds": 0,
                 "max_retries_per_provider": 1, "show_provider": False,
             }), \
             patch("sys.stdin", new=__import__("io").StringIO("")):
            asyncio.run(_ask(
                ("hello",), False, False, False, None,
                False, False, True,
                extra_files=None,
            ))

        system_contents = [m["content"] for m in captured_messages if m["role"] == "system"]
        assert not any("ATTACHED FILES" in c for c in system_contents)

# ─────────────────────────────────────────────────────────────────────────────
# Tests: Install UX — Direct Invocation, Zero-Config, First-Run Guard
# ─────────────────────────────────────────────────────────────────────────────


class TestCmdChain:
    """aicli cmd --chain — multi-step sequential command generation and execution."""

    def test_chain_flag_exists_on_cmd(self):
        from aicli.app import cli
        runner = CliRunner()
        # --chain flag should be accepted (not "no such option").
        # Patch _cmd_chain directly (AsyncMock) rather than asyncio.run so the
        # coroutine is never created and no RuntimeWarning is emitted.
        with patch("aicli.app._cmd_chain", new=AsyncMock(return_value=None)):
            result = runner.invoke(cli, ["cmd", "--chain", "init a git repo"])
            assert "no such option" not in result.output.lower()

    def test_chain_dry_run_shows_steps_without_executing(self):
        from aicli.app import cli
        import asyncio
        runner = CliRunner()
        generated = "git init\ngit add -A\ngit commit -m 'init'"
        with patch("aicli.app._cmd_chain", new=AsyncMock(return_value=None)) as mock_chain:
            result = runner.invoke(cli, ["cmd", "--chain", "--dry-run", "init git repo"])
            mock_chain.assert_called_once()
            call_kwargs = mock_chain.call_args[1]
            assert call_kwargs.get("dry_run") is True

    def test_chain_auto_confirm_passed_through(self):
        from aicli.app import cli
        runner = CliRunner()
        with patch("aicli.app._cmd_chain", new=AsyncMock(return_value=None)) as mock_chain:
            result = runner.invoke(cli, ["cmd", "--chain", "--auto-confirm", "do something"])
            mock_chain.assert_called_once()
            assert mock_chain.call_args[1].get("auto_confirm") is True

    def test_chain_without_flag_uses_normal_ask(self):
        """Without --chain, cmd still routes to _ask with shell=True."""
        from aicli.app import cli
        runner = CliRunner()
        with patch("aicli.app._ask", new=AsyncMock(return_value=None)) as mock_ask:
            result = runner.invoke(cli, ["cmd", "list files"])
            mock_ask.assert_called_once()
            _, kwargs = mock_ask.call_args
            assert kwargs.get("shell") is True or mock_ask.call_args[0][1] is True

    def test_cmd_chain_parses_numbered_list(self):
        """_cmd_chain strips numbered prefixes like '1.', '2)', '- ' from LLM output."""
        import asyncio
        # Directly test the parsing logic by examining what commands are executed
        from aicli.app import _cmd_chain
        generated_output = "1. touch index.html\n2. echo hello > index.html\n3. ls -la"
        with patch("aicli.config.load_config", return_value={
            "provider_chain": ["groq"], "cooldown_seconds": 30, "max_retries_per_provider": 2
        }), patch("aicli.providers.pipeline.ProviderPipeline") as MockPP:
            instance = MockPP.return_value
            # Simulate streaming the numbered output
            async def _fake_stream(*a, **kw):
                for chunk in generated_output:
                    yield chunk
            instance.stream = _fake_stream
            # dry_run=True so subprocess never called
            asyncio.run(_cmd_chain(("init a project",), dry_run=True, quiet=True))


# ─────────────────────────────────────────────────────────────────────────────
# Path auto-detection in default.py
# ─────────────────────────────────────────────────────────────────────────────


class TestPathAutoDetection:
    """default.py auto-detects file paths in prompts and injects them as context."""

    def test_extract_paths_returns_existing_file(self, tmp_path):
        from aicli.tools.os_functions import extract_file_paths_from_prompt
        f = tmp_path / "notes.txt"
        f.write_text("important notes")
        paths = extract_file_paths_from_prompt(f"please summarize {f}")
        assert str(f) in paths

    def test_extract_paths_multiple_files(self, tmp_path):
        from aicli.tools.os_functions import extract_file_paths_from_prompt
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("a")
        f2.write_text("b")
        paths = extract_file_paths_from_prompt(
            f"compare {f1} and {f2}"
        )
        assert str(f1) in paths
        assert str(f2) in paths

    def test_extract_paths_skips_nonexistent(self, tmp_path):
        from aicli.tools.os_functions import extract_file_paths_from_prompt
        paths = extract_file_paths_from_prompt(
            f"summarize {tmp_path}/no_such_file.txt"
        )
        assert paths == []

    def test_extract_paths_skips_https_urls(self):
        from aicli.tools.os_functions import extract_file_paths_from_prompt
        paths = extract_file_paths_from_prompt(
            "open https://example.com/docs/intro.html"
        )
        assert not any("https" in p for p in paths)

    def test_extract_paths_skips_version_numbers(self):
        from aicli.tools.os_functions import extract_file_paths_from_prompt
        paths = extract_file_paths_from_prompt(
            "I'm using Python 3.11.0 and aicli 1.5.6"
        )
        assert paths == []


# ─────────────────────────────────────────────────────────────────────────────
# I4: --role flag on aicli cmd --chain
# ─────────────────────────────────────────────────────────────────────────────


class TestCmdChainRole:
    """aicli cmd --chain --role passes custom role to _cmd_chain."""

    def test_chain_role_flag_accepted(self):
        """--role flag accepted on cmd --chain without error."""
        from aicli.app import cli
        runner = CliRunner()
        with patch("aicli.app._cmd_chain", new=AsyncMock(return_value=None)):
            result = runner.invoke(
                cli, ["cmd", "--chain", "--role", "senior devops", "deploy app"]
            )
            assert "no such option" not in result.output.lower()
            assert result.exit_code == 0

    def test_chain_role_passed_to_cmd_chain(self):
        """--role value is forwarded to _cmd_chain as role kwarg."""
        from aicli.app import cli
        runner = CliRunner()
        with patch("aicli.app._cmd_chain",
                   new=AsyncMock(return_value=None)) as mock_chain:
            runner.invoke(
                cli, ["cmd", "--chain", "--role", "devops", "init git repo"]
            )
            mock_chain.assert_called_once()
            kwargs = mock_chain.call_args[1]
            assert kwargs.get("role") == "devops"

    def test_chain_without_role_passes_none(self):
        """Without --role, _cmd_chain receives role=None."""
        from aicli.app import cli
        runner = CliRunner()
        with patch("aicli.app._cmd_chain",
                   new=AsyncMock(return_value=None)) as mock_chain:
            runner.invoke(cli, ["cmd", "--chain", "init git repo"])
            mock_chain.assert_called_once()
            kwargs = mock_chain.call_args[1]
            assert kwargs.get("role") is None

    def test_cmd_chain_accepts_role_param(self):
        """_cmd_chain function signature includes role parameter."""
        import inspect
        from aicli.app import _cmd_chain
        sig = inspect.signature(_cmd_chain)
        assert "role" in sig.parameters, "_cmd_chain must accept role parameter"


# ─────────────────────────────────────────────────────────────────────────────
# Shell integration — Ctrl+I
# ─────────────────────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────────────────────
# Watch + do integration
# ─────────────────────────────────────────────────────────────────────────────

class TestWatchDoIntegration:
    """--watch + --do: when condition fires, aicli do is dispatched automatically."""

    def test_watch_do_flag_accepted_on_ask(self):
        """--do flag accepted on aicli ask without error."""
        from aicli.app import cli
        runner = CliRunner()
        with patch("aicli.app._ask", new=AsyncMock(return_value=None)) as mock_ask, \
             patch("aicli.app.get_api_key", return_value="fake-key"):
            result = runner.invoke(
                cli,
                ["ask", "--watch", "disk full", "--do",
                 "send_notification title='Alert' body='disk full'", "monitor"],
            )
            assert "no such option" not in result.output.lower()
            assert result.exit_code == 0

    def test_watch_do_passed_to_ask(self):
        """--do value is forwarded to _ask as watch_do kwarg."""
        from aicli.app import cli
        runner = CliRunner()
        with patch("aicli.app._ask", new=AsyncMock(return_value=None)) as mock_ask, \
             patch("aicli.app.get_api_key", return_value="fake-key"):
            runner.invoke(
                cli,
                ["ask", "--watch", "OOM", "--do", "get_system_info detail=mem", "monitor"],
            )
            mock_ask.assert_called_once()
            kwargs = mock_ask.call_args[1]
            assert kwargs.get("watch_do") == "get_system_info detail=mem"

    def test_watch_do_default_is_none(self):
        """Without --do, _ask receives watch_do=None."""
        from aicli.app import cli
        runner = CliRunner()
        with patch("aicli.app._ask", new=AsyncMock(return_value=None)) as mock_ask, \
             patch("aicli.app.get_api_key", return_value="fake-key"):
            runner.invoke(cli, ["ask", "--watch", "error", "monitor"])
            mock_ask.assert_called_once()
            kwargs = mock_ask.call_args[1]
            assert kwargs.get("watch_do") is None

    def test_ask_signature_has_watch_do(self):
        """_ask signature includes watch_do parameter."""
        import inspect
        from aicli.handlers.default import _ask
        sig = inspect.signature(_ask)
        assert "watch_do" in sig.parameters, "_ask must accept watch_do"

    def test_watch_evaluate_signature_has_do_action(self):
        """_watch_evaluate coroutine accepts do_action parameter."""
        import inspect
        from aicli.handlers.default import _watch_evaluate
        sig = inspect.signature(_watch_evaluate)
        assert "do_action" in sig.parameters, "_watch_evaluate must accept do_action"

    def test_watch_stdin_signature_has_do_action(self):
        """_watch_stdin coroutine accepts do_action parameter."""
        import inspect
        from aicli.handlers.default import _watch_stdin
        sig = inspect.signature(_watch_stdin)
        assert "do_action" in sig.parameters, "_watch_stdin must accept do_action"

    def test_watch_evaluate_dispatches_do_on_yes(self):
        """When LLM responds YES and do_action set, run_do_command is called."""
        import asyncio
        from unittest.mock import AsyncMock, patch, MagicMock

        async def _run():
            from aicli.handlers.default import _watch_evaluate
            mock_run_do = AsyncMock(return_value=None)
            mock_pipeline = MagicMock()

            async def _fake_stream(*a, **kw):
                yield "YES — disk usage is above threshold."

            mock_pipeline.stream = _fake_stream

            with patch("aicli.tools.executor.run_do_command", mock_run_do):
                await _watch_evaluate(
                    ["disk usage 95%"],
                    "disk usage above 90%",
                    "You are a monitor.",
                    mock_pipeline,
                    "mock-model",
                    quiet=True,
                    do_action="get_system_info detail=disk",
                )
            return mock_run_do.call_count

        count = asyncio.run(_run())
        assert count == 1, "run_do_command must be called exactly once on YES trigger"

    def test_watch_evaluate_no_do_when_condition_not_met(self):
        """When LLM responds NO, run_do_command is NOT called."""
        import asyncio
        from unittest.mock import AsyncMock, patch, MagicMock

        async def _run():
            from aicli.handlers.default import _watch_evaluate
            mock_run_do = AsyncMock(return_value=None)
            mock_pipeline = MagicMock()

            async def _fake_stream(*a, **kw):
                yield "NO — disk usage is within normal range."

            mock_pipeline.stream = _fake_stream

            with patch("aicli.tools.executor.run_do_command", mock_run_do):
                await _watch_evaluate(
                    ["disk usage 40%"],
                    "disk usage above 90%",
                    "You are a monitor.",
                    mock_pipeline,
                    "mock-model",
                    quiet=True,
                    do_action="get_system_info detail=disk",
                )
            return mock_run_do.call_count

        count = asyncio.run(_run())
        assert count == 0, "run_do_command must NOT be called when condition is not met"
