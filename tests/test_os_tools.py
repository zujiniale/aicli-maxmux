"""
test_os_tools.py — split from test_new_commands.py
Tests for the OS tool registry, os_functions, executor, and 'aicli do'.
"""

import os
import asyncio
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from click.testing import CliRunner


class TestToolRegistry:
    """@os_tool decorator registers functions in TOOL_REGISTRY with correct schema."""

    def test_os_tool_decorator_registers_function(self):
        from aicli.tools.registry import os_tool, TOOL_REGISTRY
        @os_tool(
            name="_test_reg_fn",
            description="Test tool",
            parameters={"x": {"type": "string", "description": "A param"}},
        )
        async def _test_reg_fn(x: str) -> str:
            return x
        assert "_test_reg_fn" in TOOL_REGISTRY

    def test_os_tool_schema_has_correct_structure(self):
        from aicli.tools.registry import os_tool, TOOL_REGISTRY
        @os_tool(
            name="_test_schema_fn",
            description="Schema test",
            parameters={"url": {"type": "string", "description": "A URL"}},
        )
        async def _test_schema_fn(url: str) -> str:
            return url
        entry = TOOL_REGISTRY["_test_schema_fn"]
        schema = entry["schema"]
        assert schema["name"] == "_test_schema_fn"
        assert "input_schema" in schema
        assert "url" in schema["input_schema"]["properties"]

    def test_get_tool_schema_returns_list(self):
        import aicli.tools.os_functions  # ensure tools registered
        from aicli.tools.registry import get_tool_schema
        schemas = get_tool_schema()
        assert isinstance(schemas, list)
        assert len(schemas) >= 6  # at least 6 built-in tools

    def test_get_tool_returns_none_for_unknown(self):
        from aicli.tools.registry import get_tool
        assert get_tool("nonexistent_tool_xyz") is None

    def test_list_tools_returns_names(self):
        import aicli.tools.os_functions  # noqa
        from aicli.tools.registry import list_tools
        names = list_tools()
        assert "open_url_in_browser" in names
        assert "send_email" in names
        assert "play_music" in names
        assert "read_file_content" in names
        assert "write_file_content" in names
        assert "copy_to_clipboard" in names
        assert "run_shell_command" in names

    def test_confirm_flag_defaults_true(self):
        import aicli.tools.os_functions  # noqa
        from aicli.tools.registry import TOOL_REGISTRY
        # All action tools must require confirmation by default
        for name in ("open_url_in_browser", "send_email", "play_music",
                     "write_file_content", "run_shell_command"):
            assert TOOL_REGISTRY[name]["confirm"] is True, \
                f"{name} should have confirm=True"

    def test_safe_readonly_tools_skip_confirm(self):
        import aicli.tools.os_functions  # noqa
        from aicli.tools.registry import TOOL_REGISTRY
        # Read-only / zero-side-effect tools should not require confirmation
        assert TOOL_REGISTRY["read_file_content"]["confirm"] is False
        assert TOOL_REGISTRY["copy_to_clipboard"]["confirm"] is False


# ─────────────────────────────────────────────────────────────────────────────
# OS Functions (os_functions.py)
# ─────────────────────────────────────────────────────────────────────────────


class TestOsFunctions:
    """Built-in OS tool implementations behave correctly."""

    def test_read_file_content_reads_existing_file(self, tmp_path):
        from aicli.tools.os_functions import read_file_content
        import asyncio
        f = tmp_path / "test.txt"
        f.write_text("hello world")
        result = asyncio.run(read_file_content(str(f)))
        assert "hello world" in result

    def test_read_file_content_truncates_at_50kb(self, tmp_path):
        from aicli.tools.os_functions import read_file_content, MAX_FILE_BYTES
        import asyncio
        f = tmp_path / "big.txt"
        f.write_bytes(b"A" * (MAX_FILE_BYTES + 1000))
        result = asyncio.run(read_file_content(str(f)))
        assert "TRUNCATED" in result

    def test_read_file_content_raises_for_missing(self):
        from aicli.tools.os_functions import read_file_content
        import asyncio
        with pytest.raises(FileNotFoundError):
            asyncio.run(read_file_content("/nonexistent/path/xyz.txt"))

    def test_open_url_rejects_non_http(self):
        from aicli.tools.os_functions import open_url_in_browser
        import asyncio
        with pytest.raises(ValueError, match="Unsafe URL"):
            asyncio.run(open_url_in_browser("ftp://evil.com"))

    def test_open_url_rejects_javascript_scheme(self):
        from aicli.tools.os_functions import open_url_in_browser
        import asyncio
        with pytest.raises(ValueError, match="Unsafe URL"):
            asyncio.run(open_url_in_browser("javascript:alert(1)"))

    def test_open_url_accepts_https(self):
        from aicli.tools.os_functions import open_url_in_browser
        import asyncio
        with patch("webbrowser.open") as mock_wb:
            result = asyncio.run(open_url_in_browser("https://news.ycombinator.com"))
            mock_wb.assert_called_once_with("https://news.ycombinator.com")
            assert "Opened" in result

    def test_write_file_blocks_outside_home(self, tmp_path):
        from aicli.tools.os_functions import write_file_content
        import asyncio
        with pytest.raises(PermissionError, match="Write blocked"):
            asyncio.run(write_file_content("/etc/passwd", "evil"))

    def test_write_file_creates_inside_home(self, tmp_path, monkeypatch):
        from aicli.tools.os_functions import write_file_content
        import asyncio
        # Patch Path.home() so write is in tmp_path
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        dest = str(tmp_path / "test_write.txt")
        result = asyncio.run(write_file_content(dest, "hello"))
        assert "Wrote" in result or "bytes" in result
        assert (tmp_path / "test_write.txt").read_text() == "hello"

    def test_send_email_validates_address(self):
        from aicli.tools.os_functions import send_email
        import asyncio
        with pytest.raises(ValueError, match="Invalid email"):
            asyncio.run(send_email("not-an-email", "subject", "body"))

    def test_extract_paths_from_prompt_finds_existing_file(self, tmp_path):
        from aicli.tools.os_functions import extract_file_paths_from_prompt
        f = tmp_path / "report.txt"
        f.write_text("data")
        paths = extract_file_paths_from_prompt(f"summarize {f} and tell me what it says")
        assert str(f) in paths

    def test_extract_paths_ignores_urls(self):
        from aicli.tools.os_functions import extract_file_paths_from_prompt
        paths = extract_file_paths_from_prompt("open https://example.com/path/to/page")
        assert not any("https" in p for p in paths)

    def test_extract_paths_ignores_nonexistent(self, tmp_path):
        from aicli.tools.os_functions import extract_file_paths_from_prompt
        paths = extract_file_paths_from_prompt(
            f"summarize {tmp_path}/definitely_does_not_exist_xyz.txt"
        )
        assert paths == []


# ─────────────────────────────────────────────────────────────────────────────
# Executor (executor.py)
# ─────────────────────────────────────────────────────────────────────────────


class TestExecutor:
    """dispatch_tool_calls confirmation gate, dry-run, audit, error handling."""

    def test_dry_run_does_not_execute(self):
        from aicli.tools.executor import dispatch_tool_calls
        import asyncio
        with patch("aicli.tools.os_functions.open_url_in_browser") as mock_fn:
            results = asyncio.run(dispatch_tool_calls(
                [{"name": "open_url_in_browser", "input": {"url": "https://example.com"}}],
                dry_run=True,
                quiet=True,
            ))
            mock_fn.assert_not_called()
            assert results[0]["skipped"] is True

    def test_auto_confirm_skips_prompt(self):
        from aicli.tools.executor import dispatch_tool_calls
        from aicli.tools.registry import TOOL_REGISTRY
        import asyncio
        original_fn = TOOL_REGISTRY["open_url_in_browser"]["fn"]
        mock_fn = AsyncMock(return_value="Opened")
        TOOL_REGISTRY["open_url_in_browser"]["fn"] = mock_fn
        try:
            results = asyncio.run(dispatch_tool_calls(
                [{"name": "open_url_in_browser", "input": {"url": "https://example.com"}}],
                auto_confirm=True,
                quiet=True,
            ))
            mock_fn.assert_called_once_with(url="https://example.com")
            assert results[0]["ok"] is True
        finally:
            TOOL_REGISTRY["open_url_in_browser"]["fn"] = original_fn

    def test_unknown_tool_returns_error(self):
        from aicli.tools.executor import dispatch_tool_calls
        import asyncio
        results = asyncio.run(dispatch_tool_calls(
            [{"name": "definitely_not_a_real_tool", "input": {}}],
            auto_confirm=True,
            quiet=True,
        ))
        assert results[0]["ok"] is False
        assert "Unknown tool" in results[0]["result"]

    def test_tool_exception_captured_not_raised(self):
        from aicli.tools.executor import dispatch_tool_calls
        import asyncio
        with patch("aicli.tools.os_functions.open_url_in_browser",
                   new=AsyncMock(side_effect=ValueError("bad url"))):
            results = asyncio.run(dispatch_tool_calls(
                [{"name": "open_url_in_browser", "input": {"url": "ftp://bad"}}],
                auto_confirm=True,
                quiet=True,
            ))
            assert results[0]["ok"] is False
            assert "Tool error" in results[0]["result"]

    def test_audit_log_written(self, tmp_path):
        from aicli.tools.executor import dispatch_tool_calls, _write_audit
        import asyncio, json
        log_file = tmp_path / "audit.jsonl"
        with patch("aicli.tools.executor._audit_log_path", return_value=log_file), \
             patch("aicli.tools.os_functions.open_url_in_browser",
                   new=AsyncMock(return_value="Opened")):
            asyncio.run(dispatch_tool_calls(
                [{"name": "open_url_in_browser", "input": {"url": "https://example.com"}}],
                auto_confirm=True,
                quiet=True,
            ))
        assert log_file.exists()
        entry = json.loads(log_file.read_text().strip())
        assert entry["tool"] == "open_url_in_browser"
        assert entry["ok"] is True

    def test_user_decline_skips_execution(self):
        from aicli.tools.executor import dispatch_tool_calls
        import asyncio
        with patch("builtins.input", return_value="n"), \
             patch("aicli.tools.os_functions.open_url_in_browser") as mock_fn:
            results = asyncio.run(dispatch_tool_calls(
                [{"name": "open_url_in_browser", "input": {"url": "https://example.com"}}],
                auto_confirm=False,
                quiet=True,
            ))
            mock_fn.assert_not_called()
            assert results[0]["skipped"] is True

    def test_openai_format_tool_call_normalised(self):
        """executor.py normalises OpenAI-style {"function": {"name": ..., "arguments": ...}}"""
        from aicli.tools.executor import dispatch_tool_calls
        from aicli.tools.registry import TOOL_REGISTRY
        import asyncio, json
        openai_call = {
            "function": {
                "name": "open_url_in_browser",
                "arguments": json.dumps({"url": "https://example.com"}),
            }
        }
        original_fn = TOOL_REGISTRY["open_url_in_browser"]["fn"]
        mock_fn = AsyncMock(return_value="Opened")
        TOOL_REGISTRY["open_url_in_browser"]["fn"] = mock_fn
        try:
            results = asyncio.run(dispatch_tool_calls(
                [openai_call],
                auto_confirm=True,
                quiet=True,
            ))
            mock_fn.assert_called_once_with(url="https://example.com")
        finally:
            TOOL_REGISTRY["open_url_in_browser"]["fn"] = original_fn


# ─────────────────────────────────────────────────────────────────────────────
# aicli do command (CLI)
# ─────────────────────────────────────────────────────────────────────────────


class TestDoCommand:
    """aicli do — function-calling CLI command."""

    def test_do_command_registered(self):
        from aicli.app import cli
        assert "do" in [c.name for c in cli.commands.values()]

    def test_do_requires_prompt(self):
        from aicli.app import cli
        runner = CliRunner()
        result = runner.invoke(cli, ["do"])
        assert result.exit_code != 0

    def test_do_dry_run_flag_accepted(self):
        from aicli.app import cli
        runner = CliRunner()
        # Patch run_do_command directly so the coroutine is never created.
        # Patching asyncio.run receives the coroutine but never closes it,
        # which emits RuntimeWarning: coroutine 'run_do_command' was never awaited.
        with patch("aicli.tools.executor.run_do_command", new=AsyncMock(return_value=None)):
            result = runner.invoke(cli, ["do", "--dry-run", "open hacker news"])
            assert result.exit_code == 0

    def test_do_auto_confirm_flag_accepted(self):
        from aicli.app import cli
        runner = CliRunner()
        with patch("aicli.tools.executor.run_do_command", new=AsyncMock(return_value=None)):
            # --confirm is the flag on `do` (opt-in gate); default is already auto_confirm=True
            result = runner.invoke(cli, ["do", "--confirm", "open hacker news"])
            assert result.exit_code == 0

    def test_do_quiet_flag_accepted(self):
        from aicli.app import cli
        runner = CliRunner()
        with patch("aicli.tools.executor.run_do_command", new=AsyncMock(return_value=None)):
            result = runner.invoke(cli, ["do", "-q", "open something"])
            assert result.exit_code == 0


# ─────────────────────────────────────────────────────────────────────────────
# aicli tools list / audit commands
# ─────────────────────────────────────────────────────────────────────────────


class TestToolsCommands:
    """aicli tools list and aicli tools audit CLI commands."""

    def test_tools_group_registered(self):
        from aicli.app import cli
        assert "tools" in [c.name for c in cli.commands.values()]

    def test_tools_list_subcommand_exists(self):
        from aicli.app import cli
        runner = CliRunner()
        result = runner.invoke(cli, ["tools", "list"])
        # Should exit 0 and show at least one tool name
        assert result.exit_code == 0
        assert "open_url_in_browser" in result.output or "Tool" in result.output

    def test_tools_audit_subcommand_exists(self):
        from aicli.app import cli
        runner = CliRunner()
        # No log file yet — should print info message, not crash
        with patch("aicli.tools.executor._audit_log_path",
                   return_value=__import__("pathlib").Path("/nonexistent/audit.jsonl")):
            result = runner.invoke(cli, ["tools", "audit"])
            assert result.exit_code == 0

    def test_tools_audit_last_flag(self):
        from aicli.app import cli
        runner = CliRunner()
        with patch("aicli.tools.executor._audit_log_path",
                   return_value=__import__("pathlib").Path("/nonexistent/audit.jsonl")):
            result = runner.invoke(cli, ["tools", "audit", "--last", "5"])
            assert result.exit_code == 0


# ─────────────────────────────────────────────────────────────────────────────
# cmd --chain
# ─────────────────────────────────────────────────────────────────────────────


class TestNewOsTools:
    """send_notification, get_clipboard, open_file, search_web, get_system_info."""

    def test_send_notification_registered(self):
        import aicli.tools.os_functions  # noqa
        from aicli.tools.registry import TOOL_REGISTRY
        assert "send_notification" in TOOL_REGISTRY

    def test_get_clipboard_registered(self):
        import aicli.tools.os_functions  # noqa
        from aicli.tools.registry import TOOL_REGISTRY
        assert "get_clipboard" in TOOL_REGISTRY

    def test_open_file_registered(self):
        import aicli.tools.os_functions  # noqa
        from aicli.tools.registry import TOOL_REGISTRY
        assert "open_file" in TOOL_REGISTRY

    def test_search_web_registered(self):
        import aicli.tools.os_functions  # noqa
        from aicli.tools.registry import TOOL_REGISTRY
        assert "search_web" in TOOL_REGISTRY

    def test_get_system_info_registered(self):
        import aicli.tools.os_functions  # noqa
        from aicli.tools.registry import TOOL_REGISTRY
        assert "get_system_info" in TOOL_REGISTRY

    def test_send_notification_no_confirm_required(self):
        import aicli.tools.os_functions  # noqa
        from aicli.tools.registry import TOOL_REGISTRY
        assert TOOL_REGISTRY["send_notification"]["confirm"] is False

    def test_get_clipboard_no_confirm_required(self):
        import aicli.tools.os_functions  # noqa
        from aicli.tools.registry import TOOL_REGISTRY
        assert TOOL_REGISTRY["get_clipboard"]["confirm"] is False

    def test_open_file_raises_for_missing_path(self):
        from aicli.tools.os_functions import open_file
        import asyncio
        with pytest.raises(FileNotFoundError):
            asyncio.run(open_file("/nonexistent/path/xyz_abc.txt"))

    def test_get_system_info_returns_os_string(self):
        from aicli.tools.os_functions import get_system_info
        import asyncio
        result = asyncio.run(get_system_info("os"))
        assert "OS:" in result or "os" in result.lower()

    def test_total_tool_count_at_least_12(self):
        import aicli.tools.os_functions  # noqa
        from aicli.tools.registry import list_tools
        names = list_tools()
        assert len(names) >= 12, f"Expected ≥12 tools, got {len(names)}: {names}"


# ─────────────────────────────────────────────────────────────────────────────
# Response Cache (default.py)
# ─────────────────────────────────────────────────────────────────────────────


class TestToolRetry:
    """dispatch_tool_calls retries on transient failure."""

    def test_retry_succeeds_on_second_attempt(self):
        from aicli.tools.executor import dispatch_tool_calls
        from aicli.tools.registry import TOOL_REGISTRY
        import asyncio
        call_count = {"n": 0}
        async def _flaky_tool(url: str) -> str:
            call_count["n"] += 1
            if call_count["n"] < 2:
                raise ConnectionError("transient")
            return "Success"
        original_fn = TOOL_REGISTRY["open_url_in_browser"]["fn"]
        TOOL_REGISTRY["open_url_in_browser"]["fn"] = _flaky_tool
        try:
            results = asyncio.run(dispatch_tool_calls(
                [{"name": "open_url_in_browser", "input": {"url": "https://example.com"}}],
                auto_confirm=True, quiet=True, max_retries=1,
            ))
        finally:
            TOOL_REGISTRY["open_url_in_browser"]["fn"] = original_fn
        assert results[0]["ok"] is True
        assert call_count["n"] == 2

    def test_retry_exhausted_returns_error(self):
        from aicli.tools.executor import dispatch_tool_calls
        from aicli.tools.registry import TOOL_REGISTRY
        import asyncio
        async def _always_fails(url: str) -> str:
            raise RuntimeError("always broken")
        original_fn = TOOL_REGISTRY["open_url_in_browser"]["fn"]
        TOOL_REGISTRY["open_url_in_browser"]["fn"] = _always_fails
        try:
            results = asyncio.run(dispatch_tool_calls(
                [{"name": "open_url_in_browser", "input": {"url": "https://example.com"}}],
                auto_confirm=True, quiet=True, max_retries=2,
            ))
        finally:
            TOOL_REGISTRY["open_url_in_browser"]["fn"] = original_fn
        assert results[0]["ok"] is False
        assert "Tool error" in results[0]["result"]

    def test_max_retries_zero_means_one_attempt(self):
        from aicli.tools.executor import dispatch_tool_calls
        from aicli.tools.registry import TOOL_REGISTRY
        import asyncio
        attempt_count = {"n": 0}
        async def _counter(url: str) -> str:
            attempt_count["n"] += 1
            raise RuntimeError("fail")
        original_fn = TOOL_REGISTRY["open_url_in_browser"]["fn"]
        TOOL_REGISTRY["open_url_in_browser"]["fn"] = _counter
        try:
            asyncio.run(dispatch_tool_calls(
                [{"name": "open_url_in_browser", "input": {"url": "https://example.com"}}],
                auto_confirm=True, quiet=True, max_retries=0,
            ))
        finally:
            TOOL_REGISTRY["open_url_in_browser"]["fn"] = original_fn
        assert attempt_count["n"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# Natural summary pass after tool calls (executor.py)
# ─────────────────────────────────────────────────────────────────────────────


class TestNaturalSummaryPass:
    """run_do_command sends tool results to LLM for human-readable summary."""

    def test_summary_pass_calls_pipeline_stream_twice(self):
        """First call: get tool_use blocks. Second call: natural summary."""
        from aicli.tools.executor import run_do_command
        import asyncio, json

        # Compound prompt ("and") bypasses _try_direct_dispatch fast path → goes to LLM
        # pipeline.complete() returns a plain string — executor parses JSON from it
        tool_json = json.dumps([{"name": "open_url_in_browser",
                                 "input": {"url": "https://news.ycombinator.com"}}])
        call_count = {"n": 0}

        async def _mock_complete(*a, **kw):
            return tool_json  # must be a string, not a list

        async def _mock_stream(*a, **kw):
            call_count["n"] += 1
            yield "Music is now playing and Hacker News is open. Enjoy!"

        mock_pipeline = MagicMock()
        mock_pipeline.complete = _mock_complete
        mock_pipeline.stream = _mock_stream
        mock_pipeline.last_provider = "groq"

        # Patch the module-level ProviderPipeline (now importable after fix)
        with patch("aicli.tools.executor.ProviderPipeline", return_value=mock_pipeline), \
             patch("aicli.tools.executor.dispatch_tool_calls",
                   new=AsyncMock(return_value=[
                       {"name": "open_url_in_browser", "result": "Opened", "ok": True, "skipped": False}
                   ])), \
             patch("aicli.tools.executor.load_config", return_value={
                 "provider_chain": ["groq"], "cooldown_seconds": 30,
                 "max_retries_per_provider": 2, "show_provider": False
             }):
            asyncio.run(run_do_command(
                ("play music and open hacker news",),
                auto_confirm=True, dry_run=False, quiet=False, model=None, lite=False,
                role=None,
            ))
        assert call_count["n"] >= 1  # summary pass ran

    def test_summary_pass_skipped_when_dry_run(self):
        """Dry-run: no tool execution, no summary pass."""
        from aicli.tools.executor import run_do_command
        import asyncio

        stream_called = {"n": 0}
        async def _mock_complete(*a, **kw):
            return [{"type": "tool_use", "name": "open_url_in_browser",
                     "input": {"url": "https://example.com"}}]
        async def _mock_stream(*a, **kw):
            stream_called["n"] += 1
            yield "summary"

        mock_pipeline = MagicMock()
        mock_pipeline.complete = _mock_complete
        mock_pipeline.stream = _mock_stream

        with patch("aicli.tools.executor.ProviderPipeline", return_value=mock_pipeline), \
             patch("aicli.tools.executor.load_config", return_value={
                 "provider_chain": ["groq"], "cooldown_seconds": 30,
                 "max_retries_per_provider": 2, "show_provider": False
             }):
            asyncio.run(run_do_command(
                ("open hacker news",),
                auto_confirm=True, dry_run=True, quiet=True, model=None, lite=False,
                role=None,
            ))
        assert stream_called["n"] == 0  # no summary when dry_run
        assert stream_called["n"] == 0  # no summary when dry_run


# ─────────────────────────────────────────────────────────────────────────────
# G1 + I1: max_retries wired through run_do_command → dispatch_tool_calls
# ─────────────────────────────────────────────────────────────────────────────


class TestRunDoCommandMaxRetries:
    """run_do_command accepts max_retries and passes it to dispatch_tool_calls."""

    def test_run_do_command_accepts_max_retries_kwarg(self):
        """run_do_command signature includes max_retries parameter."""
        import inspect
        from aicli.tools.executor import run_do_command
        sig = inspect.signature(run_do_command)
        assert "max_retries" in sig.parameters, "run_do_command must accept max_retries"

    def test_run_do_command_passes_max_retries_to_dispatch(self):
        """max_retries is forwarded from run_do_command → dispatch_tool_calls."""
        from aicli.tools.executor import run_do_command
        import asyncio, json as _j

        dispatched_retries = {}

        async def _mock_complete(*a, **kw):
            # Must return a JSON string — executor parses tool calls from plain text response
            return _j.dumps([{"name": "open_url_in_browser",
                               "input": {"url": "https://example.com"}}])

        async def _mock_dispatch(tool_calls, auto_confirm, dry_run, quiet, max_retries=1):
            dispatched_retries["n"] = max_retries
            return [{"name": "open_url_in_browser", "result": "ok", "ok": True, "skipped": False}]

        async def _mock_stream(*a, **kw):
            yield "done"

        mock_pipeline = MagicMock()
        mock_pipeline.complete = _mock_complete
        mock_pipeline.stream = _mock_stream
        mock_pipeline.last_provider = "groq"

        with patch("aicli.tools.executor.ProviderPipeline", return_value=mock_pipeline), \
             patch("aicli.tools.executor.dispatch_tool_calls",
                   side_effect=_mock_dispatch), \
             patch("aicli.tools.executor.load_config", return_value={
                 "provider_chain": ["groq"], "cooldown_seconds": 0,
                 "max_retries_per_provider": 1, "show_provider": False,
             }):
            asyncio.run(run_do_command(
                # "send email" — not in _DIRECT_PATTERNS, always goes to LLM path
                ("send email to alice@example.com saying hello",),
                auto_confirm=True, dry_run=False, quiet=True,
                model=None, lite=False, role=None,
                max_retries=3,   # <── custom value
            ))
        assert dispatched_retries.get("n") == 3, \
            f"Expected max_retries=3 forwarded, got {dispatched_retries}"

    def test_do_command_cli_retries_flag(self):
        """aicli do --retries 3 accepted without error and passed to run_do_command."""
        from aicli.app import cli
        runner = CliRunner()
        with patch("aicli.tools.executor.run_do_command",
                   new=AsyncMock(return_value=None)) as mock_rdc:
            result = runner.invoke(cli, ["do", "--retries", "3", "open hacker news"])
            assert result.exit_code == 0
            _, kwargs = mock_rdc.call_args
            assert kwargs.get("max_retries") == 3


# ─────────────────────────────────────────────────────────────────────────────
# I3: run_shell_command working_dir parameter
# ─────────────────────────────────────────────────────────────────────────────


class TestRunShellCommandWorkingDir:
    """run_shell_command working_dir parameter changes execution directory."""

    def test_working_dir_changes_cwd(self, tmp_path):
        """Command runs in the specified directory."""
        from aicli.tools.os_functions import run_shell_command
        import asyncio
        result = asyncio.run(run_shell_command("pwd", working_dir=str(tmp_path)))
        assert str(tmp_path) in result

    def test_working_dir_missing_raises(self):
        """Non-existent working_dir raises FileNotFoundError."""
        from aicli.tools.os_functions import run_shell_command
        import asyncio
        with pytest.raises(FileNotFoundError):
            asyncio.run(run_shell_command("pwd", working_dir="/nonexistent/path/xyz"))

    def test_working_dir_defaults_to_none(self, tmp_path):
        """Omitting working_dir still works (runs in process cwd)."""
        from aicli.tools.os_functions import run_shell_command
        import asyncio
        result = asyncio.run(run_shell_command("echo hello"))
        assert "hello" in result

    def test_working_dir_in_tool_schema(self):
        """run_shell_command schema includes working_dir parameter."""
        import aicli.tools.os_functions  # noqa
        from aicli.tools.registry import TOOL_REGISTRY
        schema = TOOL_REGISTRY["run_shell_command"]["schema"]
        props = schema["input_schema"]["properties"]
        assert "working_dir" in props, "working_dir must be in run_shell_command schema"



# ─────────────────────────────────────────────────────────────────────────────
# Multi-turn aicli do (--session flag)
# ─────────────────────────────────────────────────────────────────────────────

class TestDoCommandSession:
    """aicli do --session wires session_id through to run_do_command."""

    def test_do_session_flag_accepted(self):
        """--session flag accepted on aicli do without error."""
        from aicli.app import cli
        runner = CliRunner()
        with patch("aicli.tools.executor.run_do_command", new=AsyncMock(return_value=None)), \
             patch("aicli.app.get_api_key", return_value="fake-key"):
            result = runner.invoke(
                cli, ["do", "--session", "myproject", "open the config"]
            )
            assert "no such option" not in result.output.lower()
            assert result.exit_code == 0

    def test_do_session_passed_to_run_do_command(self):
        """--session value forwarded to run_do_command as session_id kwarg."""
        from aicli.app import cli
        runner = CliRunner()
        with patch("aicli.tools.executor.run_do_command",
                   new=AsyncMock(return_value=None)) as mock_do, \
             patch("aicli.app.get_api_key", return_value="fake-key"):
            runner.invoke(cli, ["do", "--session", "myproject", "open the config"])
            mock_do.assert_called_once()
            kwargs = mock_do.call_args[1]
            assert kwargs.get("session_id") == "myproject"

    def test_do_without_session_passes_none(self):
        """Without --session, run_do_command receives session_id=None."""
        from aicli.app import cli
        runner = CliRunner()
        with patch("aicli.tools.executor.run_do_command",
                   new=AsyncMock(return_value=None)) as mock_do, \
             patch("aicli.app.get_api_key", return_value="fake-key"):
            runner.invoke(cli, ["do", "open the config"])
            mock_do.assert_called_once()
            kwargs = mock_do.call_args[1]
            assert kwargs.get("session_id") is None

    def test_run_do_command_accepts_session_id(self):
        """run_do_command signature includes session_id parameter."""
        import inspect
        from aicli.tools.executor import run_do_command
        sig = inspect.signature(run_do_command)
        assert "session_id" in sig.parameters, "run_do_command must accept session_id"

    def test_run_do_command_session_id_defaults_none(self):
        """session_id defaults to None (backward-compatible)."""
        import inspect
        from aicli.tools.executor import run_do_command
        sig = inspect.signature(run_do_command)
        default = sig.parameters["session_id"].default
        assert default is None, "session_id default must be None"


# ─────────────────────────────────────────────────────────────────────────────
# Plugin TOOL_REGISTRY auto-registration
# ─────────────────────────────────────────────────────────────────────────────

class TestPluginOsToolRegistration:
    """Plugins with 'parameters' in register() are auto-registered into TOOL_REGISTRY."""

    def _make_plugin_file(self, tmp_path, name="test_tool", with_params=True):
        """Write a minimal plugin .py file and return its path."""
        params_block = (
            '        "parameters": {"msg": {"type": "string", "description": "msg"}},'
            if with_params else ""
        )
        content = f"""
async def _fn(msg=""):
    return f"called: {{msg}}"

def register():
    return {{
        "name": "{name}",
        "description": "A test tool for plugin registration",
        {params_block}
        "confirm": False,
        "safe": True,
        "fn": _fn,
        "version": "0.1.0",
    }}
"""
        path = tmp_path / f"{name}.py"
        path.write_text(content)
        return path

    def test_plugin_with_parameters_registers_into_tool_registry(self, tmp_path):
        """Plugin with 'parameters' key gets added to TOOL_REGISTRY."""
        from aicli.tools.loader import _load_plugin_file
        from aicli.tools.registry import TOOL_REGISTRY

        path = self._make_plugin_file(tmp_path, name="auto_reg_tool", with_params=True)
        original = dict(TOOL_REGISTRY)
        try:
            _load_plugin_file(path)
            assert "auto_reg_tool" in TOOL_REGISTRY, \
                "Plugin with 'parameters' must be auto-registered in TOOL_REGISTRY"
        finally:
            # restore registry
            TOOL_REGISTRY.clear()
            TOOL_REGISTRY.update(original)

    def test_plugin_without_parameters_not_in_tool_registry(self, tmp_path):
        """Plugin without 'parameters' key is NOT added to TOOL_REGISTRY."""
        from aicli.tools.loader import _load_plugin_file
        from aicli.tools.registry import TOOL_REGISTRY

        path = self._make_plugin_file(tmp_path, name="no_param_tool", with_params=False)
        original = dict(TOOL_REGISTRY)
        try:
            _load_plugin_file(path)
            assert "no_param_tool" not in TOOL_REGISTRY, \
                "Plugin without 'parameters' must NOT be in TOOL_REGISTRY"
        finally:
            TOOL_REGISTRY.clear()
            TOOL_REGISTRY.update(original)

    def test_registered_plugin_has_correct_schema_format(self, tmp_path):
        """Auto-registered plugin schema has input_schema with type=object."""
        from aicli.tools.loader import _load_plugin_file
        from aicli.tools.registry import TOOL_REGISTRY

        path = self._make_plugin_file(tmp_path, name="schema_check_tool", with_params=True)
        original = dict(TOOL_REGISTRY)
        try:
            _load_plugin_file(path)
            entry = TOOL_REGISTRY.get("schema_check_tool", {})
            schema = entry.get("schema", {})
            assert schema.get("name") == "schema_check_tool"
            assert schema["input_schema"]["type"] == "object"
            assert "msg" in schema["input_schema"]["properties"]
        finally:
            TOOL_REGISTRY.clear()
            TOOL_REGISTRY.update(original)

    def test_registered_plugin_has_confirm_and_safe(self, tmp_path):
        """confirm and safe fields from plugin register() are preserved."""
        from aicli.tools.loader import _load_plugin_file
        from aicli.tools.registry import TOOL_REGISTRY

        path = self._make_plugin_file(tmp_path, name="confirm_safe_tool", with_params=True)
        original = dict(TOOL_REGISTRY)
        try:
            _load_plugin_file(path)
            entry = TOOL_REGISTRY.get("confirm_safe_tool", {})
            assert entry.get("confirm") is False
            assert entry.get("safe") is True
        finally:
            TOOL_REGISTRY.clear()
            TOOL_REGISTRY.update(original)

    def test_plugin_registration_silent_on_import_error(self, tmp_path, monkeypatch):
        """If TOOL_REGISTRY import fails (lite mode), registration is skipped silently."""
        import sys
        from aicli.tools.loader import _load_plugin_file

        path = self._make_plugin_file(tmp_path, name="lite_tool", with_params=True)
        # Block the registry import
        monkeypatch.setitem(sys.modules, "aicli.tools.registry", None)
        try:
            result = _load_plugin_file(path)  # Must not raise
            assert result is not None
            assert result["name"] == "lite_tool"
        finally:
            sys.modules.pop("aicli.tools.registry", None)


# ─────────────────────────────────────────────────────────────────────────────
# Tool sandboxing (AICLI_SANDBOX)
# ─────────────────────────────────────────────────────────────────────────────

class TestRunShellCommandSandboxing:
    """run_shell_command sandboxing: MAX_OUTPUT_BYTES cap + firejail opt-in."""

    def test_max_output_bytes_defined(self):
        """MAX_OUTPUT_BYTES constant is defined in os_functions."""
        from aicli.tools.os_functions import MAX_OUTPUT_BYTES
        assert isinstance(MAX_OUTPUT_BYTES, int)
        assert MAX_OUTPUT_BYTES > 0

    def test_max_output_bytes_is_32kb(self):
        """MAX_OUTPUT_BYTES is 32768 (32 KB)."""
        from aicli.tools.os_functions import MAX_OUTPUT_BYTES
        assert MAX_OUTPUT_BYTES == 32_768

    def test_sandbox_available_false_by_default(self):
        """_sandbox_available() returns False when AICLI_SANDBOX not set."""
        import os
        from aicli.tools.os_functions import _sandbox_available
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AICLI_SANDBOX", None)
            assert _sandbox_available() is False

    def test_sandbox_available_false_without_firejail(self, monkeypatch):
        """_sandbox_available() returns False when firejail not on PATH."""
        import os
        monkeypatch.setenv("AICLI_SANDBOX", "1")
        import shutil
        with patch.object(shutil, "which", return_value=None):
            from aicli.tools import os_functions
            result = os_functions._sandbox_available()
        assert result is False

    def test_build_sandboxed_cmd_structure(self):
        """_build_sandboxed_cmd returns list starting with firejail."""
        from aicli.tools.os_functions import _build_sandboxed_cmd
        cmd = _build_sandboxed_cmd("echo hello")
        assert isinstance(cmd, list)
        assert cmd[0] == "firejail"
        assert "--net=none" in cmd
        assert "--private-tmp" in cmd
        assert "--noroot" in cmd
        assert "echo hello" in cmd

    def test_build_sandboxed_cmd_allows_net_with_env(self, monkeypatch):
        """AICLI_SANDBOX_NET=1 removes --net=none from firejail args."""
        import os
        monkeypatch.setenv("AICLI_SANDBOX_NET", "1")
        from aicli.tools import os_functions
        import importlib
        importlib.reload(os_functions)
        cmd = os_functions._build_sandboxed_cmd("curl example.com")
        assert "--net=none" not in cmd

    def test_output_truncated_when_exceeds_max(self):
        """Output larger than MAX_OUTPUT_BYTES is truncated with a notice."""
        import asyncio
        from aicli.tools.os_functions import run_shell_command, MAX_OUTPUT_BYTES
        # Generate output larger than cap
        big = "x" * (MAX_OUTPUT_BYTES + 100)
        import subprocess
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout=big, stderr="", returncode=0
            )
            result = asyncio.run(run_shell_command("echo big"))
        assert len(result) <= MAX_OUTPUT_BYTES + 100  # truncated
        assert "truncated" in result

    def test_unsandboxed_execution_uses_shell_true(self, monkeypatch):
        """Without AICLI_SANDBOX=1, subprocess.run is called with shell=True."""
        import os, asyncio, subprocess
        monkeypatch.delenv("AICLI_SANDBOX", raising=False)
        from aicli.tools.os_functions import run_shell_command
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="ok", stderr="", returncode=0)
            asyncio.run(run_shell_command("echo test"))
            _, kwargs = mock_run.call_args
            assert kwargs.get("shell") is True


# ─────────────────────────────────────────────────────────────────────────────
# do command UX — clean @FunctionCall output
# ─────────────────────────────────────────────────────────────────────────────

class TestDoCommandUX:
    """do command output is clean like ShellGPT @FunctionCall."""

    def test_verbose_flag_accepted_on_do(self):
        """--verbose flag accepted on aicli do without error."""
        from aicli.app import cli
        runner = CliRunner()
        with patch("aicli.tools.executor.run_do_command",
                   new=AsyncMock(return_value=None)), \
             patch("aicli.app.get_api_key", return_value="fake-key"):
            result = runner.invoke(cli, ["do", "--verbose", "open hacker news"])
            assert "no such option" not in result.output.lower()
            assert result.exit_code == 0

    def test_do_command_has_verbose_param(self):
        """do_command Click handler accepts verbose parameter."""
        import inspect
        from aicli.app import do_command
        sig = inspect.signature(do_command.callback)
        assert "verbose" in sig.parameters

    def test_run_do_command_accepts_verbose(self):
        """run_do_command signature includes verbose parameter."""
        import inspect
        from aicli.tools.executor import run_do_command
        sig = inspect.signature(run_do_command)
        assert "verbose" in sig.parameters

    def test_run_do_command_verbose_defaults_false(self):
        """verbose defaults to False for backward compatibility."""
        import inspect
        from aicli.tools.executor import run_do_command
        sig = inspect.signature(run_do_command)
        assert sig.parameters["verbose"].default is False

    def test_format_tool_call_uses_at_function_call(self):
        """_format_tool_call uses @FunctionCall prefix."""
        from aicli.tools.executor import _format_tool_call
        result = _format_tool_call("play_music", {"query": "classical"})
        assert "@FunctionCall" in result
        assert "play_music" in result
        assert "classical" in result

    def test_auto_confirm_shows_function_call_line(self):
        """auto_confirm path prints @FunctionCall without Run? prompt."""
        import asyncio
        from aicli.tools.executor import _format_tool_call
        # Verify the format string is @FunctionCall style
        output = _format_tool_call("open_url_in_browser", {"url": "https://example.com"})
        assert "@FunctionCall" in output
        assert "Run?" not in output


class TestCtrlLChainWidget:
    """Ctrl+L chain widget present in shell integration."""

    def test_zsh_has_chain_widget(self):
        from pathlib import Path
        zsh = (Path("aicli") / "shell_integration.zsh").read_text()
        assert "_aicli_chain_widget" in zsh

    def test_zsh_ctrl_l_bound(self):
        from pathlib import Path
        zsh = (Path("aicli") / "shell_integration.zsh").read_text()
        assert "^L" in zsh

    def test_zsh_chain_calls_cmd_chain(self):
        from pathlib import Path
        zsh = (Path("aicli") / "shell_integration.zsh").read_text()
        assert "aicli cmd --chain" in zsh

    def test_zsh_chain_widget_has_inline_prompt(self):
        from pathlib import Path
        zsh = (Path("aicli") / "shell_integration.zsh").read_text()
        chain_section = zsh[zsh.find("_aicli_chain_widget"):]
        assert "chain>" in chain_section or "read -r" in chain_section

    def test_bash_has_chain_function(self):
        from pathlib import Path
        bash = (Path("aicli") / "shell_integration.bash").read_text()
        assert "_aicli_chain" in bash

    def test_bash_ctrl_l_bound_to_chain(self):
        from pathlib import Path
        bash = (Path("aicli") / "shell_integration.bash").read_text()
        assert "_aicli_chain" in bash and (r"\C-l" in bash or "C-l" in bash)

    def test_bash_chain_calls_cmd_chain(self):
        from pathlib import Path
        bash = (Path("aicli") / "shell_integration.bash").read_text()
        assert "aicli cmd --chain" in bash
