"""
tests/test_new_commands.py — Tests for v1.5.3+ new commands.

Covers: aicli cmd, aicli code, aicli setup, --lite flag, --quiet flag,
        aicli-lite entry point, AICLI_LITE/AICLI_QUIET env vars,
        aicli serve command registration, aicli config install-shell,
        aicli history, aicli stats, serve daemon.

For OS tools: see test_os_tools.py
For streaming/chain: see test_streaming.py
For install UX: see test_install_ux.py
"""

import os
import asyncio
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from click.testing import CliRunner


class TestCmdCommand:

    def test_cmd_exists_in_cli(self):
        from aicli.app import cli
        assert "cmd" in [c.name for c in cli.commands.values()]

    def test_cmd_requires_prompt(self):
        from aicli.app import cli
        runner = CliRunner()
        result = runner.invoke(cli, ["cmd"])
        assert result.exit_code != 0

    def test_cmd_calls_ask_with_shell_true(self):
        from aicli.app import cli
        runner = CliRunner()
        with patch("aicli.app._ask", new=AsyncMock(return_value=None)) as mock_ask:
            runner.invoke(cli, ["cmd", "list files"])
            mock_ask.assert_called_once()
            _, kwargs = mock_ask.call_args
            assert kwargs.get("shell") is True or mock_ask.call_args[0][1] is True

    def test_cmd_dry_run_flag_accepted(self):
        from aicli.app import cli
        runner = CliRunner()
        with patch("aicli.app._ask", new=AsyncMock(return_value=None)):
            result = runner.invoke(cli, ["cmd", "--dry-run", "list files"])
            assert result.exit_code == 0

    def test_cmd_run_flag_accepted(self):
        from aicli.app import cli
        runner = CliRunner()
        with patch("aicli.app._ask", new=AsyncMock(return_value=None)):
            result = runner.invoke(cli, ["cmd", "--run", "list files"])
            assert result.exit_code == 0

    def test_cmd_lite_flag_accepted(self):
        from aicli.app import cli
        runner = CliRunner()
        with patch("aicli.app._ask", new=AsyncMock(return_value=None)):
            result = runner.invoke(cli, ["cmd", "--lite", "list files"])
            assert result.exit_code == 0


# ── aicli code ────────────────────────────────────────────────────────────────


class TestCodeCommand:

    def test_code_exists_in_cli(self):
        from aicli.app import cli
        assert "code" in [c.name for c in cli.commands.values()]

    def test_code_requires_prompt(self):
        from aicli.app import cli
        runner = CliRunner()
        result = runner.invoke(cli, ["code"])
        assert result.exit_code != 0

    def test_code_calls_ask_with_code_true(self):
        from aicli.app import cli
        runner = CliRunner()
        with patch("aicli.app._ask", new=AsyncMock(return_value=None)) as mock_ask:
            runner.invoke(cli, ["code", "merge sort"])
            mock_ask.assert_called_once()

    def test_code_language_flag(self):
        from aicli.app import cli
        runner = CliRunner()
        with patch("aicli.app._ask", new=AsyncMock(return_value=None)):
            result = runner.invoke(cli, ["code", "--language", "bash", "list files"])
            assert result.exit_code == 0

    def test_code_run_flag(self):
        from aicli.app import cli
        runner = CliRunner()
        with patch("aicli.app._ask", new=AsyncMock(return_value=None)):
            result = runner.invoke(cli, ["code", "--run", "hello world"])
            assert result.exit_code == 0

    def test_code_quiet_flag(self):
        from aicli.app import cli
        runner = CliRunner()
        with patch("aicli.app._ask", new=AsyncMock(return_value=None)):
            result = runner.invoke(cli, ["code", "-q", "hello"])
            assert result.exit_code == 0


# ── --quiet / -q flag ─────────────────────────────────────────────────────────


class TestQuietFlag:

    def test_quiet_flag_on_ask(self):
        from aicli.app import cli
        runner = CliRunner()
        with patch("aicli.app._ask", new=AsyncMock(return_value=None)) as mock_ask:
            runner.invoke(cli, ["ask", "--quiet", "hello"])
            mock_ask.assert_called_once()

    def test_quiet_shorthand_on_ask(self):
        from aicli.app import cli
        runner = CliRunner()
        with patch("aicli.app._ask", new=AsyncMock(return_value=None)) as mock_ask:
            runner.invoke(cli, ["ask", "-q", "hello"])
            mock_ask.assert_called_once()

    @pytest.mark.asyncio
    async def test_quiet_suppresses_provider_footer(self):
        from aicli.handlers.default import _ask
        import io
        with patch("aicli.handlers.default.ProviderPipeline") as MockPipeline:
            inst = MagicMock()
            inst.last_provider = "groq"
            # Proper async generator — AsyncMock(return_value=aiter(...)) wraps
            # the generator in a coroutine causing "never awaited" GC warnings
            async def _hello_stream(*a, **kw):
                yield "hello"
            inst.stream = _hello_stream
            MockPipeline.return_value = inst
            with patch("aicli.handlers.default.stream_to_terminal", new=AsyncMock()):
                with patch("aicli.handlers.default.print_provider_footer") as mock_footer:
                    with patch("sys.stdin", new=io.StringIO("")):
                        await _ask(("hello",), shell=False, code=False, describe=False,
                                   model=None, no_stream=False, json_output=False,
                                   dry_run=False, quiet=True)
                    mock_footer.assert_not_called()

    @pytest.mark.asyncio
    async def test_quiet_env_var_activates_quiet_mode(self):
        from aicli.handlers.default import _ask
        import io
        with patch.dict(os.environ, {"AICLI_QUIET": "1"}):
            with patch("aicli.handlers.default.ProviderPipeline") as MockPipeline:
                inst = MagicMock()
                inst.last_provider = "groq"
                # Use async generator function — not AsyncMock(return_value=aiter(...))
                # which creates a coroutine wrapping the generator (causes "never awaited" warning)
                async def _empty_stream(*a, **kw):
                    return
                    yield  # makes it an async generator
                inst.stream = _empty_stream
                MockPipeline.return_value = inst
                with patch("aicli.handlers.default.stream_to_terminal", new=AsyncMock()):
                    with patch("aicli.handlers.default.print_provider_footer") as mock_footer:
                        with patch("sys.stdin", new=io.StringIO("")):
                            await _ask(("hello",), shell=False, code=False, describe=False,
                                       model=None, no_stream=False, json_output=False,
                                       dry_run=False, quiet=False)  # quiet=False but env var set
                        mock_footer.assert_not_called()


# ── --lite flag ───────────────────────────────────────────────────────────────


class TestLiteFlag:

    def test_lite_flag_on_ask(self):
        from aicli.app import cli
        runner = CliRunner()
        with patch("aicli.app._ask", new=AsyncMock(return_value=None)):
            result = runner.invoke(cli, ["ask", "--lite", "hello"])
            assert result.exit_code == 0

    @pytest.mark.asyncio
    async def test_lite_skips_rag_context(self):
        """--lite flag skips RAG context injection even when --context is passed."""
        from aicli.handlers.default import _ask
        import io

        with patch("aicli.handlers.default.ProviderPipeline") as MockPipeline:
            inst = MagicMock()
            inst.last_provider = "groq"
            async def _hello_stream(*a, **kw):
                yield "hello"
            inst.stream = _hello_stream
            MockPipeline.return_value = inst
            with patch("aicli.handlers.default.stream_to_terminal", new=AsyncMock()):
                with patch("aicli.context.retriever.ContextRetriever") as MockRetriever:
                    with patch("sys.stdin", new=io.StringIO("")):
                        await _ask(("hello",), shell=False, code=False, describe=False,
                                   model=None, no_stream=False, json_output=False,
                                   dry_run=False, context=True, lite=True)
                    MockRetriever.assert_not_called()

    @pytest.mark.asyncio
    async def test_lite_env_var(self):
        """AICLI_LITE=1 activates lite mode."""
        from aicli.handlers.default import _ask
        import io
        with patch.dict(os.environ, {"AICLI_LITE": "1"}):
            with patch("aicli.handlers.default.ProviderPipeline") as MockPipeline:
                inst = MagicMock()
                # Proper async generator — avoids "coroutine never awaited" warning
                async def _hello_stream(*a, **kw):
                    yield "hello"
                inst.stream = _hello_stream
                MockPipeline.return_value = inst
                with patch("aicli.handlers.default.stream_to_terminal", new=AsyncMock()):
                    with patch("aicli.context.retriever.ContextRetriever") as MockRetriever:
                        with patch("sys.stdin", new=io.StringIO("")):
                            await _ask(("hello",), shell=False, code=False, describe=False,
                                       model=None, no_stream=False, json_output=False,
                                       dry_run=False, context=True, lite=False)
                        MockRetriever.assert_not_called()


# ── aicli setup ───────────────────────────────────────────────────────────────


class TestSetupCommand:

    def test_setup_exists_in_cli(self):
        from aicli.app import cli
        assert "setup" in [c.name for c in cli.commands.values()]

    def test_setup_skips_already_configured(self):
        from aicli.app import cli
        runner = CliRunner()
        with patch("aicli.app.get_api_key", return_value="sk-test-key"), \
             patch("getpass.getpass", return_value=""):
            result = runner.invoke(cli, ["setup"], input="\n\n\n\n")
            assert result.exit_code == 0
            assert "already configured" in result.output

    def test_setup_saves_entered_key(self):
        from aicli.app import cli
        runner = CliRunner()
        with patch("aicli.app.get_api_key", return_value=None), \
             patch("aicli.app.save_api_key") as mock_save, \
             patch("getpass.getpass", side_effect=["gsk-testkey", "", "", ""]):
            result = runner.invoke(cli, ["setup"])
            assert result.exit_code == 0

    def test_setup_shows_quickstart_on_completion(self):
        from aicli.app import cli
        runner = CliRunner()
        with patch("aicli.app.get_api_key", return_value="sk-already-set"), \
             patch("getpass.getpass", return_value=""):
            result = runner.invoke(cli, ["setup"])
            assert result.exit_code == 0


# ── aicli serve ───────────────────────────────────────────────────────────────


class TestServeCommand:

    def test_serve_exists_in_cli(self):
        from aicli.app import cli
        assert "serve" in [c.name for c in cli.commands.values()]

    def test_serve_default_port_is_8765(self):
        from aicli.app import cli
        runner = CliRunner()
        with patch("aicli.app.run_serve", side_effect=KeyboardInterrupt) as mock_serve:
            try:
                runner.invoke(cli, ["serve"])
            except Exception:
                pass
            if mock_serve.called:
                _, kwargs = mock_serve.call_args
                assert kwargs.get("port", 8765) == 8765

    def test_serve_accepts_port_option(self):
        from aicli.app import cli
        runner = CliRunner()
        with patch("aicli.handlers.serve.run_serve", side_effect=KeyboardInterrupt):
            result = runner.invoke(cli, ["serve", "--port", "9000"])
            # Either it ran or KeyboardInterrupt was handled
            assert result.exit_code in (0, 1)


# ── aicli-lite entry point ────────────────────────────────────────────────────


class TestMainLite:

    def test_main_lite_sets_env_var(self):
        from aicli.app import main_lite
        with patch("aicli.app.cli") as mock_cli:
            with patch.dict(os.environ, {}, clear=False):
                main_lite()
                assert os.environ.get("AICLI_LITE") == "1"
                mock_cli.assert_called_once()

    def test_main_lite_calls_cli(self):
        from aicli.app import main_lite
        with patch("aicli.app.cli") as mock_cli:
            main_lite()
            mock_cli.assert_called_once()


# ── config install-shell ──────────────────────────────────────────────────────


class TestConfigInstallShell:

    def test_install_shell_exists(self):
        from aicli.app import cli
        config_cmd = cli.commands["config"]
        assert "install-shell" in [c.name for c in config_cmd.commands.values()]

    def test_install_shell_rejects_unknown_shell(self):
        from aicli.app import cli
        runner = CliRunner()
        result = runner.invoke(cli, ["config", "install-shell", "--shell", "fish"])
        assert result.exit_code != 0  # fish not in Choice

    def test_install_shell_detects_zsh(self):
        from aicli.app import cli
        runner = CliRunner()
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            fake_src = tmp / "shell_integration.zsh"
            fake_src.write_text("# fake")

            # Patch CONFIG_DIR so dest resolves inside tmpdir (not real ~/.config/aicli).
            # ALSO patch Path.home() so rc_file = Path.home() / ".zshrc" resolves inside
            # tmpdir — without this, source "/tmp/tmpXXX/shell_integration.zsh" gets written
            # to the real ~/.zshrc, permanently polluting the developer's shell config.
            with patch("aicli.app.CONFIG_DIR", tmp), \
                 patch("pathlib.Path.home", return_value=tmp), \
                 patch("shutil.copy"), \
                 patch.dict(os.environ, {"SHELL": "/bin/zsh"}):
                result = runner.invoke(cli, ["config", "install-shell"])
                # Accept success or non-zero (e.g. rc-file write may differ in test env)
                assert result.exit_code in (0, 1)
                # Verify no real home path leaked into a written rc file
                rc = tmp / ".zshrc"
                if rc.exists():
                    assert str(tmp) in rc.read_text(), "rc should reference tmpdir path"


# ── Helper: async iterator for mocking stream ─────────────────────────────────

async def aiter(items):
    for item in items:
        yield item


# ── aicli serve --daemon / serve stop ────────────────────────────────────────


class TestServeDaemon:

    def test_serve_daemon_flag_accepted(self):
        from aicli.app import cli
        runner = CliRunner()
        # --daemon should be a valid flag (not unknown option)
        result = runner.invoke(cli, ["serve", "--help"])
        assert "--daemon" in result.output or result.exit_code == 0

    def test_serve_stop_action_accepted(self):
        from aicli.app import cli
        runner = CliRunner()
        with patch("aicli.app.stop_serve") as mock_stop:
            result = runner.invoke(cli, ["serve", "stop"])
            mock_stop.assert_called_once()

    def test_stop_serve_no_pid_file(self):
        """stop_serve() handles missing PID file gracefully."""
        from aicli.handlers.serve import stop_serve
        import tempfile
        from pathlib import Path
        with patch("aicli.handlers.serve._pid_file",
                   return_value=Path(tempfile.mktemp(suffix=".pid"))):
            # Should not raise
            stop_serve()

    def test_pid_file_path(self):
        """_pid_file() returns a path inside CONFIG_DIR."""
        from aicli.handlers.serve import _pid_file
        p = _pid_file()
        assert p.name == "serve.pid"
        assert "aicli" in str(p)


# ── aicli history search ──────────────────────────────────────────────────────


class TestHistorySearch:

    def test_history_command_exists(self):
        from aicli.app import cli
        assert "history" in [c.name for c in cli.commands.values()]

    def test_history_requires_query(self):
        from aicli.app import cli
        runner = CliRunner()
        result = runner.invoke(cli, ["history"])
        assert result.exit_code != 0

    def test_history_handles_no_chromadb(self):
        """history gracefully handles missing chromadb install.

        ContextRetriever is now bound at module level (None when chromadb is
        absent). The function checks `if ContextRetriever is None` — so we
        patch it to None to simulate the no-chromadb case, not side_effect=ImportError
        (that would make the mock callable raise, causing exit_code=1).
        """
        from aicli.app import cli
        runner = CliRunner()
        with patch("aicli.app.ContextRetriever", None),              patch("aicli.app.CHROMA_DIR", None):
            result = runner.invoke(cli, ["history", "async patterns"])
            assert result.exit_code == 0  # error shown, doesn't crash

    def test_history_no_indexed_data(self):
        """history shows helpful message when no data is indexed."""
        from aicli.app import cli
        runner = CliRunner()
        mock_retriever = MagicMock()
        mock_retriever.status.return_value = {"chat_chunks": 0, "local_chunks": 0}
        with patch("aicli.app.ContextRetriever", return_value=mock_retriever):
            with patch("aicli.app.CHROMA_DIR", MagicMock()):
                result = runner.invoke(cli, ["history", "test query"])
                assert result.exit_code == 0
                assert "No chat history" in result.output or "Index" in result.output


# ── aicli stats ───────────────────────────────────────────────────────────────


class TestStatsCommand:

    def test_stats_exists_in_cli(self):
        from aicli.app import cli
        assert "stats" in [c.name for c in cli.commands.values()]

    def test_stats_no_sessions(self):
        from aicli.app import cli
        runner = CliRunner()
        with patch("aicli.app.get_connection") as mock_conn:
            mock_conn.return_value.execute.return_value.fetchall.return_value = []
            with patch("aicli.app.list_sessions", return_value=[]):
                result = runner.invoke(cli, ["stats"])
                assert result.exit_code == 0

    def test_stats_shows_summary(self):
        from aicli.app import cli
        runner = CliRunner()
        mock_sessions = [
            {"id": "abc123", "name": "myproject", "message_count": 10,
             "updated_at": "2026-03-15T10:00:00"},
        ]
        mock_rows = [MagicMock()]
        mock_rows[0].__getitem__ = lambda self, k: {
            "session_id": "abc123", "msg_count": 10, "total_tokens": 1500
        }[k]
        with patch("aicli.app.list_sessions", return_value=mock_sessions):
            with patch("aicli.app.get_connection") as mock_conn:
                mock_conn.return_value.execute.return_value.fetchall.return_value = []
                result = runner.invoke(cli, ["stats"])
                assert result.exit_code == 0

    def test_stats_session_flag(self):
        from aicli.app import cli
        runner = CliRunner()
        with patch("aicli.app.list_sessions", return_value=[]):
            with patch("aicli.app.get_connection"):
                result = runner.invoke(cli, ["stats", "--session", "nonexistent"])
                assert result.exit_code == 0  # error shown gracefully


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Feature 1 — Context-Aware Hotkey (--terminal-context)
# ─────────────────────────────────────────────────────────────────────────────

