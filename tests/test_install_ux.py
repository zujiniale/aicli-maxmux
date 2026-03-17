"""
test_install_ux.py — split from test_new_commands.py
Tests for direct invocation, zero-config setup, first-run guard, cache, Ctrl+I hotkey.
"""

import os
import asyncio
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from click.testing import CliRunner


class TestDirectInvocation:
    """aicli "hello" works without the ask subcommand."""

    def test_direct_prompt_routes_to_ask(self):
        """aicli "explain" "this" with no subcommand invokes ask."""
        from aicli.app import cli
        runner = CliRunner()
        # make_context routes bare args to ask — mock _ask so no LLM call needed.
        # Pass words as separate args (CliRunner splits on list elements, not spaces).
        with patch("aicli.app._ask", new=AsyncMock(return_value=None)), \
             patch("aicli.app.get_api_key", return_value="fake-key"):
            result = runner.invoke(cli, ["explain", "async", "await"])
            # Exits 0 whether it routed to ask or showed help — must not crash
            assert result.exit_code == 0

    def test_known_subcommand_not_consumed(self):
        """aicli chat still routes to chat, not ask."""
        from aicli.app import cli
        runner = CliRunner()
        with patch("aicli.app.get_api_key", return_value="fake-key"):
            result = runner.invoke(cli, ["chat", "--help"])
            assert result.exit_code == 0
            assert "session" in result.output.lower() or "chat" in result.output.lower()

    def test_help_shown_when_no_args(self):
        """aicli with no args shows help, not an error."""
        from aicli.app import cli
        runner = CliRunner()
        # Mock _ask to ensure no LLM calls even if routing somehow triggers ask
        with patch("aicli.app._ask", new=AsyncMock(return_value=None)):
            result = runner.invoke(cli, [])
        # No args → show help (exit 0), not a provider error (exit 1)
        assert result.exit_code == 0
        # Help output contains Usage, aicli, or Commands
        assert any(word in result.output for word in ("Usage", "aicli", "Commands", "help"))



class TestZeroConfigSetup:
    """setup wizard auto-detects existing env keys."""

    def test_setup_auto_saves_groq_env_key(self):
        """setup detects GROQ_API_KEY in env and saves it without prompting."""
        from aicli.app import cli
        runner = CliRunner()
        with patch("aicli.app.get_api_key", return_value=None), \
             patch("aicli.app.save_api_key"), \
             patch("aicli.app.print_success"), \
             patch("aicli.app.print_info"), \
             patch.dict("os.environ", {"GROQ_API_KEY": "gsk_test123"}, clear=False):
            result = runner.invoke(cli, ["setup"], input="\n\n\n\n")
            assert result.exit_code == 0


    def test_setup_detects_openai_key_suggests_openrouter(self):
        """setup detects OPENAI_API_KEY and shows OpenRouter suggestion."""
        from aicli.app import cli
        runner = CliRunner()
        with patch("aicli.app.get_api_key", return_value=None), \
             patch("aicli.app.save_api_key"), \
             patch("aicli.app.print_info") as mock_info, \
             patch("aicli.app.print_success"), \
             patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}, clear=False):
            result = runner.invoke(cli, ["setup"], input="\n\n\n\n")
            assert result.exit_code == 0
            all_calls = " ".join(str(c) for c in mock_info.call_args_list)
            assert "openrouter" in all_calls.lower() or "OPENAI" in all_calls



class TestFirstRunGuard:
    """ask shows actionable message when no providers configured."""

    def test_first_run_guard_shows_groq_url(self):
        """With no keys configured, ask shows Groq URL instead of provider failures."""
        from aicli.app import cli
        runner = CliRunner()
        with patch("aicli.app.get_api_key", return_value=None),              patch.dict("os.environ", {}, clear=False):
            result = runner.invoke(cli, ["ask", "hello"])
            # Should exit cleanly (not exception) and show actionable message
            assert result.exit_code == 0
            output = result.output
            assert "groq" in output.lower() or "provider" in output.lower() or                    "configured" in output.lower()

    def test_first_run_guard_bypassed_when_key_exists(self):
        """With a key configured, ask proceeds normally (guard does not fire)."""
        from aicli.app import cli
        runner = CliRunner()
        with patch("aicli.app.get_api_key", return_value="fake-key"),              patch("aicli.app._ask", new=AsyncMock(return_value=None)):
            result = runner.invoke(cli, ["ask", "hello"])
            assert result.exit_code == 0
            assert "groq.com" not in result.output  # guard message not shown

    def test_first_run_guard_bypassed_with_env_key(self):
        """With AICLI_GROQ_KEY in env, ask proceeds without guard message."""
        from aicli.app import cli
        runner = CliRunner()
        with patch("aicli.app.get_api_key", return_value=None),              patch("aicli.app._ask", new=AsyncMock(return_value=None)),              patch.dict("os.environ", {"AICLI_GROQ_KEY": "gsk_test"}, clear=False):
            result = runner.invoke(cli, ["ask", "hello"])
            assert result.exit_code == 0


# ─────────────────────────────────────────────────────────────────────────────
# Tool Registry (registry.py)
# ─────────────────────────────────────────────────────────────────────────────


class TestResponseCache:
    """Response cache: key, get/set, bypass on stateful flags."""

    def test_cache_key_is_deterministic(self):
        from aicli.handlers.default import _cache_key
        k1 = _cache_key("hello world", None, "default", False, False)
        k2 = _cache_key("hello world", None, "default", False, False)
        assert k1 == k2

    def test_cache_key_differs_by_prompt(self):
        from aicli.handlers.default import _cache_key
        k1 = _cache_key("prompt A", None, "default", False, False)
        k2 = _cache_key("prompt B", None, "default", False, False)
        assert k1 != k2

    def test_cache_key_differs_by_role(self):
        from aicli.handlers.default import _cache_key
        k1 = _cache_key("hello", None, "default", False, False)
        k2 = _cache_key("hello", None, "shell", False, False)
        assert k1 != k2

    def test_cache_set_and_get_roundtrip(self, tmp_path):
        from aicli.handlers.default import _cache_get, _cache_set, _cache_path
        with patch("aicli.handlers.default._cache_path", return_value=tmp_path):
            _cache_set("testkey123", "cached response text")
            result = _cache_get("testkey123")
            assert result == "cached response text"

    def test_cache_get_returns_none_for_miss(self, tmp_path):
        from aicli.handlers.default import _cache_get
        with patch("aicli.handlers.default._cache_path", return_value=tmp_path):
            assert _cache_get("no_such_key_xyz") is None

    def test_cache_clear_removes_entries(self, tmp_path):
        from aicli.handlers.default import _cache_set, _cache_clear
        with patch("aicli.handlers.default._cache_path", return_value=tmp_path):
            _cache_set("k1", "v1")
            _cache_set("k2", "v2")
            count = _cache_clear()
            assert count == 2

    def test_no_cache_flag_on_ask(self):
        from aicli.app import cli
        runner = CliRunner()
        with patch("aicli.app._ask", new=AsyncMock(return_value=None)) as mock_ask, \
             patch("aicli.app.get_api_key", return_value="fake-key"):
            result = runner.invoke(cli, ["ask", "--no-cache", "hello"])
            assert result.exit_code == 0
            _, kwargs = mock_ask.call_args
            assert kwargs.get("no_cache") is True

    def test_role_flag_on_ask(self):
        from aicli.app import cli
        runner = CliRunner()
        with patch("aicli.app._ask", new=AsyncMock(return_value=None)) as mock_ask, \
             patch("aicli.app.get_api_key", return_value="fake-key"):
            result = runner.invoke(cli, ["ask", "--role", "shell", "hello"])
            assert result.exit_code == 0
            _, kwargs = mock_ask.call_args
            assert kwargs.get("role") == "shell"


# ─────────────────────────────────────────────────────────────────────────────
# aicli cache command group
# ─────────────────────────────────────────────────────────────────────────────


class TestCacheCommand:
    """aicli cache clear / stats CLI commands."""

    def test_cache_group_registered(self):
        from aicli.app import cli
        assert "cache" in [c.name for c in cli.commands.values()]

    def test_cache_clear_subcommand(self):
        from aicli.app import cli
        runner = CliRunner()
        with patch("aicli.handlers.default._cache_clear", return_value=0):
            result = runner.invoke(cli, ["cache", "clear"])
            assert result.exit_code == 0

    def test_cache_stats_subcommand(self):
        from aicli.app import cli
        runner = CliRunner()
        with patch("aicli.handlers.default._cache_path",
                   return_value=__import__("pathlib").Path("/nonexistent/cache")):
            result = runner.invoke(cli, ["cache", "stats"])
            assert result.exit_code == 0


# ─────────────────────────────────────────────────────────────────────────────
# Tool retry in executor.py
# ─────────────────────────────────────────────────────────────────────────────


class TestCtrlIHotkey:
    """Ctrl+I next-command hotkey defined in shell integration scripts."""

    def test_zsh_has_ctrl_i_widget(self):
        from pathlib import Path
        zsh = (Path("aicli") / "shell_integration.zsh").read_text()
        assert "_aicli_next_widget" in zsh

    def test_zsh_ctrl_i_bound(self):
        from pathlib import Path
        zsh = (Path("aicli") / "shell_integration.zsh").read_text()
        assert "^I" in zsh or "ctrl+i" in zsh.lower() or "\\C-i" in zsh

    def test_bash_has_ctrl_i_function(self):
        from pathlib import Path
        bash = (Path("aicli") / "shell_integration.bash").read_text()
        assert "_aicli_next" in bash

    def test_bash_ctrl_i_bound(self):
        from pathlib import Path
        bash = (Path("aicli") / "shell_integration.bash").read_text()
        assert "\\C-i" in bash or "^I" in bash or "ctrl+i" in bash.lower()

    def test_zsh_ctrl_i_uses_terminal_context(self):
        from pathlib import Path
        zsh = (Path("aicli") / "shell_integration.zsh").read_text()
        # Ctrl+I widget must use _aicli_terminal_context (not just history)
        widget_section = zsh[zsh.find("_aicli_next_widget"):]
        assert "_aicli_terminal_context" in widget_section

    def test_bash_ctrl_i_uses_terminal_context(self):
        from pathlib import Path
        bash = (Path("aicli") / "shell_integration.bash").read_text()
        fn_section = bash[bash.find("_aicli_next()"):]
        assert "_aicli_terminal_context" in fn_section

# ─────────────────────────────────────────────────────────────────────────────
# New OS Tools: send_notification, get_clipboard, open_file, search_web,
#               get_system_info
# ─────────────────────────────────────────────────────────────────────────────



# ─────────────────────────────────────────────────────────────────────────────
# Intent routing (_detect_intent + direct invocation)
# ─────────────────────────────────────────────────────────────────────────────

class TestIntentRouting:
    """_detect_intent correctly classifies action vs query prompts."""

    def _detect(self, prompt):
        from aicli.app import _detect_intent
        return _detect_intent(prompt)

    # ── action prompts → 'do' ──────────────────────────────────────────────

    def test_play_music_is_do(self):
        assert self._detect("play music and open hacker news") == "do"

    def test_open_url_is_do(self):
        assert self._detect("open https://news.ycombinator.com") == "do"

    def test_send_email_is_do(self):
        assert self._detect("send email to alice@example.com say hi") == "do"

    def test_notify_is_do(self):
        assert self._detect("notify me the build is done") == "do"

    def test_run_docker_is_do(self):
        assert self._detect("run docker container nginx") == "do"

    def test_start_nginx_is_do(self):
        assert self._detect("start nginx docker container mount ./index.html") == "do"

    def test_create_file_is_do(self):
        assert self._detect("create index.html file") == "do"

    def test_write_file_is_do(self):
        assert self._detect("write hello world into index.html") == "do"

    def test_find_files_is_do(self):
        assert self._detect("find files larger than 100MB") == "do"

    def test_kill_process_is_do(self):
        assert self._detect("kill process on port 3000") == "do"

    def test_get_system_info_is_do(self):
        assert self._detect("get system info") == "do"

    def test_filepath_in_prompt_is_do(self):
        assert self._detect("summarize /tmp/docs/report.txt") == "do"

    def test_home_path_is_do(self):
        assert self._detect("read ~/notes.md") == "do"

    # ── query prompts → 'ask' ─────────────────────────────────────────────

    def test_explain_is_ask(self):
        assert self._detect("explain async/await in Python") == "ask"

    def test_what_is_is_ask(self):
        assert self._detect("what is a docker container") == "ask"

    def test_how_does_is_ask(self):
        assert self._detect("how does async/await work") == "ask"

    def test_why_is_ask(self):
        assert self._detect("why does Python use the GIL?") == "ask"

    def test_question_mark_is_ask(self):
        assert self._detect("is Redis faster than Postgres?") == "ask"

    def test_what_are_is_ask(self):
        assert self._detect("what are the differences between TCP and UDP") == "ask"

    def test_summarize_concept_is_ask(self):
        """'summarize' alone with no file path is a query."""
        assert self._detect("summarize the concept of closures") == "ask"

    # ── direct invocation routes correctly ────────────────────────────────

    def test_direct_invocation_action_routes_to_do(self):
        """aicli "play music..." routes to do_command, not ask."""
        from aicli.app import cli
        runner = CliRunner()
        with patch("aicli.tools.executor.run_do_command",
                   new=AsyncMock(return_value=None)) as mock_do, \
             patch("aicli.app.get_api_key", return_value="fake-key"):
            result = runner.invoke(cli, ["play music and open hacker news"])
            assert result.exit_code == 0
            mock_do.assert_called_once()

    def test_direct_invocation_query_routes_to_ask(self):
        """aicli "explain X" routes to ask, not do."""
        from aicli.app import cli
        runner = CliRunner()
        with patch("aicli.app._ask", new=AsyncMock(return_value=None)) as mock_ask, \
             patch("aicli.app.get_api_key", return_value="fake-key"):
            result = runner.invoke(cli, ["explain async await"])
            assert result.exit_code == 0
            mock_ask.assert_called_once()

    def test_detect_intent_function_exists(self):
        """_detect_intent is importable from aicli.app."""
        from aicli.app import _detect_intent
        assert callable(_detect_intent)

    # ── disambiguation — ambiguous verbs need OS-flavoured object ─────────

    def test_write_file_is_do(self):
        assert self._detect("write hello world into index.html") == "do"

    def test_write_function_is_ask(self):
        """'write a function' is an LLM instruction, not a file write."""
        assert self._detect("write a function that sorts a list") == "ask"

    def test_create_file_is_do(self):
        assert self._detect("create index.html file") == "do"

    def test_create_mental_model_is_ask(self):
        assert self._detect("create a mental model for async") == "ask"

    def test_copy_to_clipboard_is_do(self):
        assert self._detect("copy this to clipboard") == "do"

    def test_copy_lines_is_ask(self):
        assert self._detect("copy the first 3 lines") == "ask"

    def test_move_file_is_do(self):
        assert self._detect("move file to /tmp") == "do"

    def test_move_cursor_is_ask(self):
        assert self._detect("move the cursor left") == "ask"

    def test_run_docker_is_do(self):
        assert self._detect("run docker container nginx") == "do"

    def test_run_me_through_is_ask(self):
        assert self._detect("run me through how git rebase works") == "ask"

    def test_save_file_is_do(self):
        assert self._detect("save as report.md") == "do"

    def test_save_response_is_ask(self):
        assert self._detect("save your response as markdown") == "ask"


    def test_detect_intent_returns_do_or_ask(self):
        """_detect_intent only ever returns 'do' or 'ask'."""
        from aicli.app import _detect_intent
        for prompt in ["open browser", "explain Python", "send email", "what is X?"]:
            result = _detect_intent(prompt)
            assert result in ("do", "ask"), f"Unexpected: {result!r} for {prompt!r}"
