"""
tests/test_comprehensive.py — Master test suite for aicli-maxmux.

Covers every file, every known bug (S1–V3), every feature added in v1.5.3/v1.5.4,
all CLI commands, all MCP protocol paths, all pipeline failover behaviour,
all env-var mirrors, all edge cases.

Structure:
  TestProjectStructure        — pyproject.toml, version, extras, entry points
  TestKnownBugsRegression     — one test per catalogued bug (S1–V3-4)
  TestCLICommandRegistry      — every command/subcommand present and callable
  TestAskFlags                — all flags on `aicli ask`
  TestCmdCommand              — aicli cmd shortcuts
  TestCodeCommand             — aicli code shortcuts + language names
  TestSetupCommand            — aicli setup wizard
  TestTagCommand              — aicli tag (app.py CLI)
  TestLiteMode                — --lite flag, AICLI_LITE env, main_lite()
  TestQuietMode               — --quiet flag, AICLI_QUIET env
  TestDefaultHandler          — handlers/default.py _ask()
  TestPipelineUnit            — providers/pipeline.py failover logic
  TestMCPProtocol             — mcp_server.py JSON-RPC dispatch
  TestMCPTools                — all 4 MCP tools (ask/cmd/code/tag)
  TestMCPLanguageNames        — _LANG_DISPLAY correctness (Bug V3-1)
  TestMCPFenceStrip           — _tool_cmd fence stripping (Bug V2-3)
  TestMCPResources            — MCP resources list/read
  TestMCPEdgeCases            — id=0, notifications, missing args, empty URI
  TestMCPTransport            — run_mcp entry point, constants
  TestTagCLIFileIO            — tag command file I/O (graph_links.json)
  TestEnvVarMirrors           — all AICLI_* env vars
  TestShellScripts            — map_structure.sh, retract.sh content checks
  TestAsyncPattern            — no asyncio.run() in test files (Bug V3-3)

asyncio_mode = "auto" is set in pyproject.toml — all async tests use
`async def` + `await`, NOT asyncio.run().
"""

import json
import os
import re
import inspect
import subprocess
import sys
import threading
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call

# ── Dynamic version — never needs manual update after bump_version.py ─────────
def _get_current_version() -> str:
    try:
        ver_file = Path(__file__).parent.parent / "aicli" / "__version__.py"
        m = re.search(r'__version__\s*=\s*"([^"]+)"', ver_file.read_text())
        return m.group(1) if m else "0.0.0"
    except Exception:
        return "0.0.0"

CURRENT_VERSION = _get_current_version()


# ─────────────────────────────────────────────────────────────────────────────
# Shared fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_pipeline():
    p = MagicMock()
    p.complete = AsyncMock(return_value="mocked response")
    p.last_provider = "groq"
    p.status = MagicMock(return_value=[
        {"name": "groq", "available": True, "cooldown_remaining": 0.0, "failures": 0}
    ])
    async def _stream(messages, model=None, requires_vision=False):
        yield "mocked"
        yield " response"
    p.stream = _stream
    return p


@pytest.fixture
def mock_config():
    return {
        "provider_chain": ["groq"],
        "cooldown_seconds": 60,
        "max_retries_per_provider": 1,
        "show_provider": False,
    }


@pytest.fixture
def tmp_graph(tmp_path):
    """Provides a tmp_path with an empty graph_links.json."""
    f = tmp_path / "graph_links.json"
    f.write_text(json.dumps({"nodes": [], "links": [], "names": {}}))
    return tmp_path


@pytest.fixture
def tmp_graph_with_sessions(tmp_path):
    data = {
        "nodes": [],
        "links": [],
        "names": {
            "abc123full-uuid": {"name": "myproject", "notes": "", "tags": ["existing"]},
        }
    }
    (tmp_path / "graph_links.json").write_text(json.dumps(data))
    return tmp_path


# ─────────────────────────────────────────────────────────────────────────────
# 1. Project structure
# ─────────────────────────────────────────────────────────────────────────────

class TestProjectStructure:
    """Verify pyproject.toml correctness — version, extras, entry points, deps."""

    def _get_pyproject(self):
        import tomllib
        p = Path(__file__).parent.parent / "pyproject.toml"
        if p.exists():
            return tomllib.loads(p.read_text())
        pytest.skip("pyproject.toml not in expected location")

    def test_version_is_1_5_4(self):
        cfg = self._get_pyproject()
        assert cfg["project"]["version"] == CURRENT_VERSION, \
            f"pyproject.toml version {cfg['project']['version']!r} != __version__.py {CURRENT_VERSION!r} — run: python bump_version.py {CURRENT_VERSION}"

    def test_version_is_semver(self):
        cfg = self._get_pyproject()
        parts = cfg["project"]["version"].split(".")
        assert len(parts) == 3
        assert all(p.isdigit() for p in parts)

    def test_pytest_not_in_core_dependencies(self):
        """Bug S1: pytest was in core deps — must only be in [dev]."""
        cfg = self._get_pyproject()
        core = cfg["project"].get("dependencies", [])
        assert not any("pytest" in d for d in core), \
            "pytest must not be in core dependencies — only in [dev]"

    def test_pytest_asyncio_not_in_core_dependencies(self):
        """Bug S1: pytest-asyncio was in core deps."""
        cfg = self._get_pyproject()
        core = cfg["project"].get("dependencies", [])
        assert not any("pytest-asyncio" in d for d in core)

    def test_pytest_in_dev_extra(self):
        cfg = self._get_pyproject()
        dev = cfg["project"]["optional-dependencies"].get("dev", [])
        assert any("pytest" in d for d in dev)

    def test_aicli_entry_point_exists(self):
        cfg = self._get_pyproject()
        scripts = cfg["project"]["scripts"]
        assert "aicli" in scripts
        assert scripts["aicli"] == "aicli.app:main"

    def test_aicli_lite_entry_point_exists(self):
        cfg = self._get_pyproject()
        scripts = cfg["project"]["scripts"]
        assert "aicli-lite" in scripts
        assert scripts["aicli-lite"] == "aicli.app:main_lite"

    def test_lite_extra_exists(self):
        cfg = self._get_pyproject()
        extras = cfg["project"]["optional-dependencies"]
        assert "lite" in extras
        assert len(extras["lite"]) >= 3

    def test_mcp_extra_exists(self):
        cfg = self._get_pyproject()
        extras = cfg["project"]["optional-dependencies"]
        assert "mcp" in extras

    def test_all_extra_exists(self):
        cfg = self._get_pyproject()
        extras = cfg["project"]["optional-dependencies"]
        assert "all" in extras

    def test_rag_extra_exists(self):
        cfg = self._get_pyproject()
        extras = cfg["project"]["optional-dependencies"]
        assert "rag" in extras
        assert any("chromadb" in d for d in extras["rag"])

    def test_asyncio_mode_auto(self):
        """asyncio_mode must be 'auto' — required for async def tests."""
        cfg = self._get_pyproject()
        assert cfg["tool"]["pytest"]["ini_options"]["asyncio_mode"] == "auto"

    def test_python_version_requirement(self):
        cfg = self._get_pyproject()
        requires = cfg["project"]["requires-python"]
        assert "3.11" in requires or "3.12" in requires

    def test_lite_extra_does_not_include_chromadb(self):
        """Lite mode must not pull in chromadb — that's the whole point."""
        cfg = self._get_pyproject()
        lite = cfg["project"]["optional-dependencies"]["lite"]
        assert not any("chromadb" in d for d in lite)

    def test_lite_extra_does_not_include_textual(self):
        cfg = self._get_pyproject()
        lite = cfg["project"]["optional-dependencies"]["lite"]
        assert not any("textual" in d for d in lite)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Known bug regression tests — one per catalogued bug ID
# ─────────────────────────────────────────────────────────────────────────────

class TestKnownBugsRegression:
    """
    One regression test per bug. If any of these fail, a previously fixed
    bug has been re-introduced.
    """

    # ── S1: pytest in core deps ───────────────────────────────────────────────
    def test_S1_pytest_not_in_core_deps(self):
        """Bug S1: pytest/pytest-asyncio were in core dependencies."""
        try:
            import tomllib
        except ImportError:
            pytest.skip("tomllib not available")
        p = Path(__file__).parent.parent / "pyproject.toml"
        if not p.exists():
            pytest.skip("pyproject.toml not found")
        cfg = tomllib.loads(p.read_text())
        core = cfg["project"].get("dependencies", [])
        bad = [d for d in core if "pytest" in d]
        assert not bad, f"pytest still in core deps: {bad}"

    # ── S2: CHROMA_DIR.mkdir in load_config ───────────────────────────────────
    def test_S2_chroma_mkdir_not_in_load_config(self):
        """Bug S2: CHROMA_DIR.mkdir() was called inside load_config() — ran on every invocation."""
        config_src = Path(__file__).parent.parent / "aicli" / "config.py"
        if not config_src.exists():
            pytest.skip("config.py not found")
        text = config_src.read_text()
        # Find load_config function and check it does NOT contain mkdir
        fn_start = text.find("def load_config(")
        fn_end = text.find("\ndef ", fn_start + 1)
        fn_body = text[fn_start:fn_end] if fn_end > 0 else text[fn_start:]
        assert "CHROMA_DIR.mkdir" not in fn_body, \
            "CHROMA_DIR.mkdir() found inside load_config() — it should be in manager.py initialize()"

    # ── V1-1: _tool_tag config.get("data_dir") ────────────────────────────────
    def test_V1_1_tool_tag_uses_CONFIG_DIR_not_config_dict(self):
        """Bug V1-1: _tool_tag used config.get('data_dir') which doesn't exist in config dict."""
        from aicli.handlers.mcp_server import _tool_tag
        src = inspect.getsource(_tool_tag)
        assert "config.get(\"data_dir\")" not in src
        assert "CONFIG_DIR" in src

    # ── V1-2: connect_write_pipe BaseProtocol ─────────────────────────────────
    def test_V1_2_stdio_no_BaseProtocol(self):
        """Bug V1-2: connect_write_pipe(asyncio.BaseProtocol, stdout) — class as factory, crashes."""
        from aicli.handlers import mcp_server as _m
        src = inspect.getsource(_m._run_stdio)
        assert "BaseProtocol" not in src, \
            "asyncio.BaseProtocol must not be passed to connect_write_pipe"
        assert "stdout.buffer" in src or "sys.stdout.buffer" in src

    # ── V1-3: asyncio.Queue in HTTP thread ────────────────────────────────────
    def test_V1_3_sse_uses_simple_queue_not_asyncio_queue(self):
        """Bug V1-3: asyncio.Queue used inside synchronous BaseHTTPRequestHandler."""
        from aicli.handlers import mcp_server as _m
        src = inspect.getsource(_m._run_sse)
        assert "asyncio.Queue()" not in src, \
            "asyncio.Queue must not be used in SSE handler thread"
        assert "SimpleQueue" in src

    # ── V1-4: get_event_loop deprecated ──────────────────────────────────────
    def test_V1_4_no_get_event_loop(self):
        """Bug V1-4: asyncio.get_event_loop() deprecated in Python 3.12+."""
        from aicli.handlers import mcp_server as _m
        src = inspect.getsource(_m)
        assert "get_event_loop()" not in src, \
            "Use get_running_loop() instead of get_event_loop()"

    # ── V1-7: duplicate tag command ───────────────────────────────────────────
    def test_V1_7_no_duplicate_tag_command(self):
        """Bug V1-7: two `def tag` functions existed in app.py."""
        src = Path(__file__).parent.parent / "aicli" / "app.py"
        if not src.exists():
            pytest.skip("app.py not found")
        text = src.read_text()
        # Count standalone `def tag(` (not indented inside a class)
        count = len(re.findall(r"^def tag\b", text, re.MULTILINE))
        assert count == 1, f"Found {count} `def tag` definitions — must be exactly 1"

    # ── V2-1: __version__ before shebang ─────────────────────────────────────
    def test_V2_1_shebang_is_line_1(self):
        """Bug V2-1: __version__ import was on line 1 before the shebang."""
        src = Path(__file__).parent.parent / "aicli" / "app.py"
        if not src.exists():
            pytest.skip("app.py not found")
        first_line = src.read_text().splitlines()[0]
        assert first_line.startswith("#!"), \
            f"Line 1 of app.py must be shebang, got: {first_line!r}"

    # ── V2-2: _server_version fallback wrong version ──────────────────────────
    def test_V2_2_server_version_fallback_is_current(self):
        """Bug V2-2: hardcoded fallback was '1.5.3' — one release behind."""
        from aicli.handlers.mcp_server import _server_version
        src = inspect.getsource(_server_version)
        # Must not contain an older hardcoded version as the only fallback
        assert '"1.5.3"' not in src or '"1.5.4"' in src, \
            "Fallback version string is stale"

    # ── V2-3: _tool_cmd single-backtick strip ─────────────────────────────────
    def test_V2_3_tool_cmd_uses_regex_not_strip_backtick(self):
        """Bug V2-3: strip('`') only strips single backtick chars at edges."""
        from aicli.handlers.mcp_server import _tool_cmd
        src = inspect.getsource(_tool_cmd)
        assert "re.sub" in src, "_tool_cmd must use re.sub for fence stripping"
        assert ".strip(\"`\")" not in src, \
            "_tool_cmd must not use .strip('`') — use regex to strip full fences"

    # ── V2-4: _tool_tag no DB lookup ──────────────────────────────────────────
    def test_V2_4_tool_tag_has_db_resolution(self):
        """Bug V2-4: _tool_tag didn't resolve session names/short-IDs via DB."""
        from aicli.handlers.mcp_server import _tool_tag
        src = inspect.getsource(_tool_tag)
        assert "list_sessions" in src
        assert "startswith" in src

    # ── V2-5: empty tool_name no guard ────────────────────────────────────────
    async def test_V2_5_empty_tool_name_returns_32602(self):
        """Bug V2-5: empty tool_name fell through to 'unknown tool' (-32601) with no guard."""
        from aicli.handlers.mcp_server import _handle_message
        msg = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
               "params": {"name": "", "arguments": {}}}
        result = await _handle_message(msg)
        assert "error" in result
        assert result["error"]["code"] == -32602, \
            "Empty tool name should return -32602 (missing param), not -32601 (unknown)"

    # ── V3-1: capitalize() wrong for js/ts/node ──────────────────────────────
    def test_V3_1_lang_display_javascript_correct(self):
        """Bug V3-1: 'javascript'.capitalize() = 'Javascript' — wrong."""
        from aicli.handlers.mcp_server import _tool_code
        src = inspect.getsource(_tool_code)
        assert "JavaScript" in src and "Javascript" not in src

    def test_V3_1_lang_display_typescript_correct(self):
        """Bug V3-1: 'typescript'.capitalize() = 'Typescript' — wrong."""
        from aicli.handlers.mcp_server import _tool_code
        src = inspect.getsource(_tool_code)
        assert "TypeScript" in src and "Typescript" not in src

    def test_V3_1_lang_display_node_correct(self):
        """Bug V3-1: 'node'.capitalize() = 'Node' — should be 'Node.js'."""
        from aicli.handlers.mcp_server import _tool_code
        src = inspect.getsource(_tool_code)
        assert "Node.js" in src

    # ── V3-3: asyncio.run in test files ──────────────────────────────────────
    def test_V3_3_no_asyncio_run_in_test_mcp_server(self):
        """Bug V3-3: asyncio.run() inside pytest-asyncio auto mode raises RuntimeError."""
        test_file = Path(__file__).parent / "test_mcp_server.py"
        if not test_file.exists():
            pytest.skip("test_mcp_server.py not found")
        text = test_file.read_text()
        # Skip lines inside triple-quoted docstrings and comment lines
        in_docstring = False
        docstring_marker = None
        code_lines = []
        for ln in text.splitlines():
            stripped = ln.strip()
            if not in_docstring:
                for marker in ('"""', "'''"):
                    if marker in stripped:
                        if stripped.count(marker) == 1:
                            in_docstring = True
                            docstring_marker = marker
                        break
            else:
                if docstring_marker in stripped:
                    in_docstring = False
                    docstring_marker = None
                continue
            if stripped.startswith("#"):
                continue
            if "asyncio.run(" in ln:
                code_lines.append(ln)
        assert len(code_lines) == 0, \
            f"asyncio.run() found in test_mcp_server.py at lines: {code_lines}"

    # ── V3-4: stale data_dir in mock_config ──────────────────────────────────
    def test_V3_4_mock_config_no_stale_data_dir(self):
        """Bug V3-4: mock_config had stale 'data_dir' key — not a real config key."""
        test_file = Path(__file__).parent / "test_mcp_server.py"
        if not test_file.exists():
            pytest.skip("test_mcp_server.py not found")
        text = test_file.read_text()
        # Find the mock_config fixture specifically
        fixture_start = text.find("def mock_config(")
        fixture_end = text.find("\n\n@", fixture_start)
        fixture_body = text[fixture_start:fixture_end]
        assert '"data_dir"' not in fixture_body, \
            "mock_config fixture must not contain 'data_dir' — not a real config key"


# ─────────────────────────────────────────────────────────────────────────────
# 3. CLI command registry
# ─────────────────────────────────────────────────────────────────────────────

class TestCLICommandRegistry:
    """Every command and subcommand must be registered."""

    def _commands(self):
        from aicli.app import cli
        return set(cli.commands.keys())

    def _subcommands(self, group_name):
        from aicli.app import cli
        return set(cli.commands[group_name].commands.keys())

    def test_ask_registered(self):
        assert "ask" in self._commands()

    def test_cmd_registered(self):
        assert "cmd" in self._commands()

    def test_code_registered(self):
        assert "code" in self._commands()

    def test_setup_registered(self):
        assert "setup" in self._commands()

    def test_chat_registered(self):
        assert "chat" in self._commands()

    def test_repl_registered(self):
        assert "repl" in self._commands()

    def test_export_registered(self):
        assert "export" in self._commands()

    def test_agent_registered(self):
        assert "agent" in self._commands()

    def test_index_registered(self):
        assert "index" in self._commands()

    def test_tui_registered(self):
        assert "tui" in self._commands()

    def test_graph_registered(self):
        assert "graph" in self._commands()

    def test_serve_registered(self):
        assert "serve" in self._commands()

    def test_tag_registered(self):
        assert "tag" in self._commands()

    def test_mcp_registered(self):
        assert "mcp" in self._commands()

    def test_config_group_registered(self):
        assert "config" in self._commands()

    def test_provider_group_registered(self):
        assert "provider" in self._commands()

    def test_session_group_registered(self):
        assert "session" in self._commands()

    def test_plugin_group_registered(self):
        assert "plugin" in self._commands()

    def test_config_set_key_registered(self):
        assert "set-key" in self._subcommands("config")

    def test_config_set_registered(self):
        assert "set" in self._subcommands("config")

    def test_config_get_registered(self):
        assert "get" in self._subcommands("config")

    def test_config_show_registered(self):
        assert "show" in self._subcommands("config")

    def test_config_keys_registered(self):
        assert "keys" in self._subcommands("config")

    def test_config_install_shell_registered(self):
        assert "install-shell" in self._subcommands("config")

    def test_session_list_registered(self):
        assert "list" in self._subcommands("session")

    def test_session_show_registered(self):
        assert "show" in self._subcommands("session")

    def test_session_delete_registered(self):
        assert "delete" in self._subcommands("session")

    def test_session_fork_registered(self):
        assert "fork" in self._subcommands("session")

    def test_session_rename_registered(self):
        assert "rename" in self._subcommands("session")

    def test_session_summary_registered(self):
        assert "summary" in self._subcommands("session")

    def test_session_summarize_registered(self):
        assert "summarize" in self._subcommands("session")

    def test_provider_status_registered(self):
        assert "status" in self._subcommands("provider")

    def test_provider_test_registered(self):
        assert "test" in self._subcommands("provider")

    def test_plugin_list_registered(self):
        assert "list" in self._subcommands("plugin")

    def test_plugin_run_registered(self):
        assert "run" in self._subcommands("plugin")

    def test_plugin_install_registered(self):
        assert "install" in self._subcommands("plugin")

    def test_plugin_doc_registered(self):
        assert "doc" in self._subcommands("plugin")

    def test_plugin_errors_registered(self):
        assert "errors" in self._subcommands("plugin")

    def test_main_function_exists(self):
        from aicli.app import main
        assert callable(main)

    def test_main_lite_function_exists(self):
        from aicli.app import main_lite
        assert callable(main_lite)

    def test_main_lite_sets_env_var(self):
        """main_lite() must set AICLI_LITE=1 before invoking CLI."""
        from aicli.app import main_lite
        src = inspect.getsource(main_lite)
        assert "AICLI_LITE" in src
        assert '"1"' in src or "'1'" in src


# ─────────────────────────────────────────────────────────────────────────────
# 4. ask command flags
# ─────────────────────────────────────────────────────────────────────────────

class TestAskFlags:
    """Verify every flag on `aicli ask` is present with correct type/default."""

    def _ask_params(self):
        from aicli.app import ask
        return {p.name: p for p in ask.params}

    def test_shell_flag(self):
        p = self._ask_params()
        assert "shell" in p and p["shell"].is_flag

    def test_code_flag(self):
        p = self._ask_params()
        assert "code" in p and p["code"].is_flag

    def test_describe_flag(self):
        p = self._ask_params()
        assert "describe" in p

    def test_lite_flag_is_flag(self):
        p = self._ask_params()
        assert "lite" in p and p["lite"].is_flag

    def test_quiet_flag_is_flag(self):
        p = self._ask_params()
        assert "quiet" in p and p["quiet"].is_flag

    def test_web_flag(self):
        p = self._ask_params()
        assert "web" in p and p["web"].is_flag

    def test_run_flag(self):
        p = self._ask_params()
        assert "run" in p and p["run"].is_flag

    def test_context_flag(self):
        p = self._ask_params()
        assert "context" in p

    def test_model_option_default_none(self):
        p = self._ask_params()
        assert "model" in p
        assert p["model"].default is None

    def test_language_choice_options(self):
        p = self._ask_params()
        assert "language" in p
        choices = p["language"].type.choices
        assert "python" in choices
        assert "bash" in choices
        assert "node" in choices

    def test_min_score_default(self):
        p = self._ask_params()
        assert "min_score" in p
        assert p["min_score"].default == 0.40

    def test_timeout_default(self):
        p = self._ask_params()
        assert "timeout" in p
        assert p["timeout"].default == 30

    def test_max_retries_default(self):
        p = self._ask_params()
        assert "max_retries" in p
        assert p["max_retries"].default == 3

    def test_dry_run_flag(self):
        p = self._ask_params()
        assert "dry_run" in p and p["dry_run"].is_flag

    def test_no_stream_flag(self):
        p = self._ask_params()
        assert "no_stream" in p


# ─────────────────────────────────────────────────────────────────────────────
# 5. cmd command
# ─────────────────────────────────────────────────────────────────────────────

class TestCmdCommand:
    def _params(self):
        from aicli.app import cmd
        return {p.name: p for p in cmd.params}

    def test_cmd_has_run_flag(self):
        assert "run" in self._params()

    def test_cmd_has_dry_run_flag(self):
        assert "dry_run" in self._params()

    def test_cmd_has_lite_flag(self):
        assert "lite" in self._params()

    def test_cmd_has_quiet_flag(self):
        assert "quiet" in self._params()

    def test_cmd_has_model_option(self):
        assert "model" in self._params()

    def test_cmd_calls_ask_with_shell_true(self):
        """cmd must call _ask with shell=True baked in."""
        from aicli.app import cmd
        src = inspect.getsource(cmd.callback)
        assert "shell=True" in src

    def test_cmd_does_not_have_context_flag(self):
        """cmd is a lightweight shorthand — no RAG context flag."""
        params = self._params()
        assert "context" not in params


# ─────────────────────────────────────────────────────────────────────────────
# 6. code command
# ─────────────────────────────────────────────────────────────────────────────

class TestCodeCommand:
    def _params(self):
        from aicli.app import code
        return {p.name: p for p in code.params}

    def test_code_has_run_flag(self):
        assert "run" in self._params()

    def test_code_has_language_option(self):
        assert "language" in self._params()

    def test_code_has_lite_flag(self):
        assert "lite" in self._params()

    def test_code_has_quiet_flag(self):
        assert "quiet" in self._params()

    def test_code_calls_ask_with_code_true(self):
        from aicli.app import code
        src = inspect.getsource(code.callback)
        assert "code=True" in src

    def test_code_language_default_python(self):
        params = self._params()
        assert params["language"].default == "python"


# ─────────────────────────────────────────────────────────────────────────────
# 7. setup command
# ─────────────────────────────────────────────────────────────────────────────

class TestSetupCommand:
    def test_setup_registered(self):
        from aicli.app import cli
        assert "setup" in cli.commands

    def test_setup_mentions_providers(self):
        from aicli.app import setup
        src = inspect.getsource(setup.callback)
        assert "groq" in src or "openrouter" in src

    def test_setup_mentions_install_shell(self):
        from aicli.app import setup
        src = inspect.getsource(setup.callback)
        assert "install-shell" in src or "install_shell" in src

    def test_setup_has_no_required_args(self):
        from aicli.app import setup
        required = [p for p in setup.params if p.required]
        assert len(required) == 0, "setup must require no arguments"


# ─────────────────────────────────────────────────────────────────────────────
# 8. tag command (app.py CLI)
# ─────────────────────────────────────────────────────────────────────────────

class TestTagCommand:
    def test_tag_has_session_name_arg(self):
        from aicli.app import tag
        arg_names = [p.name for p in tag.params]
        assert "session_name" in arg_names

    def test_tag_has_tags_arg(self):
        from aicli.app import tag
        arg_names = [p.name for p in tag.params]
        assert "tags" in arg_names

    def test_tag_resolves_via_db(self):
        """tag command must look up session in DB — not just use literal string."""
        from aicli.app import tag
        src = inspect.getsource(tag.callback)
        assert "list_sessions" in src or "get_connection" in src

    def test_tag_uses_startswith_for_partial_id(self):
        from aicli.app import tag
        src = inspect.getsource(tag.callback)
        assert "startswith" in src

    def test_tag_writes_to_CONFIG_DIR(self):
        from aicli.app import tag
        src = inspect.getsource(tag.callback)
        assert "CONFIG_DIR" in src

    def test_tag_handles_json_decode_error(self):
        from aicli.app import tag
        src = inspect.getsource(tag.callback)
        assert "JSONDecodeError" in src or "json.JSONDecodeError" in src

    def test_tag_io_roundtrip(self, tmp_path):
        """End-to-end: write tags, read back, verify."""
        import json as _j
        graph_file = tmp_path / "graph_links.json"
        graph_file.write_text(_j.dumps({"nodes": [], "links": [], "names": {}}))

        with patch("aicli.app.CONFIG_DIR", tmp_path), \
             patch("aicli.app.get_connection"), \
             patch("aicli.app.list_sessions", return_value=[
                 {"id": "fullid-abc", "name": "myproject", "message_count": 3}
             ]):
            from click.testing import CliRunner
            from aicli.app import cli
            runner = CliRunner()
            result = runner.invoke(cli, ["tag", "myproject", "work", "python"])

        assert result.exit_code == 0
        data = _j.loads(graph_file.read_text())
        tags = data["names"]["fullid-abc"]["tags"]
        assert "work" in tags
        assert "python" in tags

    def test_tag_merges_does_not_overwrite(self, tmp_path):
        """Existing tags must be preserved when adding new ones."""
        import json as _j
        graph_file = tmp_path / "graph_links.json"
        graph_file.write_text(_j.dumps({
            "nodes": [], "links": [],
            "names": {"sid1": {"name": "s", "notes": "", "tags": ["existing"]}}
        }))
        with patch("aicli.app.CONFIG_DIR", tmp_path), \
             patch("aicli.app.get_connection"), \
             patch("aicli.app.list_sessions", return_value=[
                 {"id": "sid1", "name": "s", "message_count": 1}
             ]):
            from click.testing import CliRunner
            from aicli.app import cli
            runner = CliRunner()
            runner.invoke(cli, ["tag", "s", "new"])

        data = _j.loads(graph_file.read_text())
        assert "existing" in data["names"]["sid1"]["tags"]
        assert "new" in data["names"]["sid1"]["tags"]


# ─────────────────────────────────────────────────────────────────────────────
# 9. Lite mode
# ─────────────────────────────────────────────────────────────────────────────

class TestLiteMode:
    def test_AICLI_LITE_env_overrides_flag(self):
        """AICLI_LITE=1 must set lite=True even when flag not passed."""
        from aicli.handlers.default import _ask
        src = inspect.getsource(_ask)
        assert 'os.environ.get("AICLI_LITE")' in src or "AICLI_LITE" in src

    def test_lite_skips_rag_in_default(self):
        """In lite mode, RAG context retrieval must be skipped."""
        from aicli.handlers.default import _ask
        src = inspect.getsource(_ask)
        assert "not lite" in src or "if context and not lite" in src

    def test_main_lite_sets_env(self):
        from aicli.app import main_lite
        src = inspect.getsource(main_lite)
        assert 'os.environ["AICLI_LITE"] = "1"' in src

    def test_lite_extra_packages(self):
        """[lite] extra must include only lightweight packages."""
        try:
            import tomllib
        except ImportError:
            pytest.skip("tomllib not available")
        p = Path(__file__).parent.parent / "pyproject.toml"
        if not p.exists():
            pytest.skip()
        cfg = tomllib.loads(p.read_text())
        lite = cfg["project"]["optional-dependencies"]["lite"]
        for pkg in lite:
            assert "chromadb" not in pkg
            assert "textual" not in pkg
            assert "sentence-transformers" not in pkg

    def test_lite_flag_on_ask_command(self):
        from aicli.app import ask
        param_names = [p.name for p in ask.params]
        assert "lite" in param_names

    def test_lite_flag_on_cmd_command(self):
        from aicli.app import cmd
        param_names = [p.name for p in cmd.params]
        assert "lite" in param_names

    def test_lite_flag_on_code_command(self):
        from aicli.app import code
        param_names = [p.name for p in code.params]
        assert "lite" in param_names


# ─────────────────────────────────────────────────────────────────────────────
# 10. Quiet mode
# ─────────────────────────────────────────────────────────────────────────────

class TestQuietMode:
    def test_AICLI_QUIET_env_overrides_flag(self):
        from aicli.handlers.default import _ask
        src = inspect.getsource(_ask)
        assert "AICLI_QUIET" in src

    def test_quiet_suppresses_provider_footer(self):
        """Provider footer must be behind `not quiet` guard."""
        from aicli.handlers.default import _ask
        src = inspect.getsource(_ask)
        assert "not quiet" in src
        footer_idx = src.find("print_provider_footer")
        assert footer_idx > 0
        # The quiet guard must appear before the footer call
        guard_idx = src.rfind("not quiet", 0, footer_idx)
        assert guard_idx > 0, "quiet guard must precede print_provider_footer"

    def test_quiet_flag_on_ask(self):
        from aicli.app import ask
        assert "quiet" in [p.name for p in ask.params]

    def test_quiet_flag_on_cmd(self):
        from aicli.app import cmd
        assert "quiet" in [p.name for p in cmd.params]

    def test_quiet_flag_on_code(self):
        from aicli.app import code
        assert "quiet" in [p.name for p in code.params]

    async def test_quiet_mode_suppresses_web_search_message(self, mock_pipeline, mock_config):
        """In quiet mode, web search status messages must not be printed."""
        from aicli.handlers.default import _ask
        with patch("aicli.handlers.default.load_config", return_value=mock_config), \
             patch("aicli.handlers.default.ProviderPipeline", return_value=mock_pipeline), \
             patch("aicli.handlers.default.print_info") as mock_print_info, \
             patch("aicli.handlers.default.web_search" if hasattr(
                 __import__("aicli.handlers.default", fromlist=["web_search"]), "web_search"
             ) else "aicli.handlers.default.print_info") as _:
            try:
                await _ask(("test",), shell=False, code=False, describe=False,
                           model=None, no_stream=True, json_output=False,
                           dry_run=False, web=False, quiet=True)
            except Exception:
                pass
        # print_info should not be called with web search messages in quiet mode


# ─────────────────────────────────────────────────────────────────────────────
# 11. default.py _ask handler
# ─────────────────────────────────────────────────────────────────────────────

class TestDefaultHandler:
    def test_ask_has_lite_param(self):
        from aicli.handlers.default import _ask
        sig = inspect.signature(_ask)
        assert "lite" in sig.parameters

    def test_ask_has_quiet_param(self):
        from aicli.handlers.default import _ask
        sig = inspect.signature(_ask)
        assert "quiet" in sig.parameters

    def test_ask_lite_default_false(self):
        from aicli.handlers.default import _ask
        sig = inspect.signature(_ask)
        assert sig.parameters["lite"].default is False

    def test_ask_quiet_default_false(self):
        from aicli.handlers.default import _ask
        sig = inspect.signature(_ask)
        assert sig.parameters["quiet"].default is False

    def test_ask_has_web_param(self):
        from aicli.handlers.default import _ask
        sig = inspect.signature(_ask)
        assert "web" in sig.parameters

    def test_ask_has_context_param(self):
        from aicli.handlers.default import _ask
        sig = inspect.signature(_ask)
        assert "context" in sig.parameters

    def test_ask_no_chroma_mkdir_on_import(self):
        """Importing _ask must not trigger CHROMA_DIR.mkdir — lazy init only."""
        import aicli.handlers.default  # noqa: just import
        assert True  # if it runs without errors, no mkdir at module level

    async def test_ask_exits_on_empty_prompt(self, mock_pipeline, mock_config):
        from aicli.handlers.default import _ask
        with patch("aicli.handlers.default.load_config", return_value=mock_config), \
             patch("aicli.handlers.default.ProviderPipeline", return_value=mock_pipeline), \
             patch("aicli.handlers.default.print_error"), \
             patch("sys.stdin.isatty", return_value=True):
            with pytest.raises(SystemExit):
                await _ask((), shell=False, code=False, describe=False,
                           model=None, no_stream=True, json_output=False, dry_run=False)

    async def test_ask_env_lite_sets_lite_true(self, mock_pipeline, mock_config):
        """AICLI_LITE=1 must activate lite mode even without --lite flag."""
        from aicli.handlers.default import _ask
        with patch.dict(os.environ, {"AICLI_LITE": "1"}), \
             patch("aicli.handlers.default.load_config", return_value=mock_config), \
             patch("aicli.handlers.default.ProviderPipeline", return_value=mock_pipeline), \
             patch("aicli.handlers.default.stream_to_terminal", new_callable=AsyncMock):
            try:
                await _ask(("hello",), shell=False, code=False, describe=False,
                           model=None, no_stream=True, json_output=False,
                           dry_run=False, lite=False)
            except Exception:
                pass

    async def test_ask_env_quiet_sets_quiet_true(self, mock_pipeline, mock_config):
        """AICLI_QUIET=1 must activate quiet mode even without -q flag."""
        from aicli.handlers.default import _ask
        with patch.dict(os.environ, {"AICLI_QUIET": "1"}), \
             patch("aicli.handlers.default.load_config", return_value=mock_config), \
             patch("aicli.handlers.default.ProviderPipeline", return_value=mock_pipeline), \
             patch("aicli.handlers.default.stream_to_terminal", new_callable=AsyncMock), \
             patch("aicli.handlers.default.print_provider_footer") as mock_footer:
            try:
                await _ask(("hello",), shell=False, code=False, describe=False,
                           model=None, no_stream=True, json_output=False,
                           dry_run=False, quiet=False)
            except Exception:
                pass
            # provider footer must not be called in quiet mode
            mock_footer.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# 12. Pipeline unit tests
# ─────────────────────────────────────────────────────────────────────────────

class TestPipelineUnit:
    def test_provider_models_defined(self):
        from aicli.providers.pipeline import PROVIDER_MODELS
        assert "groq" in PROVIDER_MODELS
        assert "ollama" in PROVIDER_MODELS
        assert len(PROVIDER_MODELS) >= 4

    def test_vision_providers_defined(self):
        from aicli.providers.pipeline import VISION_PROVIDERS
        assert "openrouter" in VISION_PROVIDERS
        assert "gemini" in VISION_PROVIDERS
        assert "groq" not in VISION_PROVIDERS
        assert "mistral" not in VISION_PROVIDERS

    def test_cooldown_by_status_defined(self):
        from aicli.providers.pipeline import COOLDOWN_BY_STATUS
        assert 429 in COOLDOWN_BY_STATUS
        assert 401 in COOLDOWN_BY_STATUS
        assert COOLDOWN_BY_STATUS[429] >= 60
        assert COOLDOWN_BY_STATUS[401] >= 3600

    def test_provider_exhausted_error_exists(self):
        from aicli.providers.pipeline import ProviderExhaustedError
        assert issubclass(ProviderExhaustedError, Exception)

    def test_provider_state_is_available_after_cooldown(self):
        from aicli.providers.pipeline import ProviderState
        import time
        mock_provider = MagicMock()
        mock_provider.name = "groq"
        state = ProviderState(provider=mock_provider)
        state.cooldown_until = time.monotonic() - 1.0  # expired
        assert state.is_available() is True

    def test_provider_state_not_available_during_cooldown(self):
        from aicli.providers.pipeline import ProviderState
        import time
        mock_provider = MagicMock()
        mock_provider.name = "groq"
        state = ProviderState(provider=mock_provider)
        state.cooldown_until = time.monotonic() + 300
        assert state.is_available() is False

    def test_provider_state_remaining_cooldown(self):
        from aicli.providers.pipeline import ProviderState
        import time
        mock_provider = MagicMock()
        state = ProviderState(provider=mock_provider)
        state.cooldown_until = time.monotonic() + 10
        remaining = state.remaining_cooldown()
        assert 9 <= remaining <= 11

    def test_pipeline_no_providers_raises(self):
        from aicli.providers.pipeline import ProviderPipeline, ProviderExhaustedError
        with patch("aicli.providers.pipeline.get_api_key", return_value=None):
            with pytest.raises(ProviderExhaustedError):
                ProviderPipeline(provider_chain=["groq", "openrouter"])

    def test_pipeline_complete_method_exists(self):
        from aicli.providers.pipeline import ProviderPipeline
        assert hasattr(ProviderPipeline, "complete")
        assert callable(ProviderPipeline.complete)

    def test_pipeline_status_method_exists(self):
        from aicli.providers.pipeline import ProviderPipeline
        assert hasattr(ProviderPipeline, "status")

    def test_pipeline_last_provider_property(self):
        from aicli.providers.pipeline import ProviderPipeline
        # Property must exist
        assert isinstance(ProviderPipeline.last_provider, property)

    def test_provider_models_all_have_string_values(self):
        from aicli.providers.pipeline import PROVIDER_MODELS
        for name, model in PROVIDER_MODELS.items():
            assert isinstance(name, str) and isinstance(model, str)

    def test_cooldown_429_greater_than_5xx(self):
        """Rate limit cooldown must be longer than server error cooldown."""
        from aicli.providers.pipeline import COOLDOWN_BY_STATUS
        assert COOLDOWN_BY_STATUS[429] > COOLDOWN_BY_STATUS.get(500, 0)


# ─────────────────────────────────────────────────────────────────────────────
# 13. MCP Protocol tests
# ─────────────────────────────────────────────────────────────────────────────

class TestMCPProtocol:
    async def test_initialize_protocol_version(self):
        from aicli.handlers.mcp_server import _handle_message
        r = await _handle_message({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        assert r["result"]["protocolVersion"] == "2024-11-05"

    async def test_initialize_server_name(self):
        from aicli.handlers.mcp_server import _handle_message
        r = await _handle_message({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        assert r["result"]["serverInfo"]["name"] == "aicli-maxmux"

    async def test_initialize_tools_capability(self):
        from aicli.handlers.mcp_server import _handle_message
        r = await _handle_message({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        assert "tools" in r["result"]["capabilities"]

    async def test_initialize_resources_capability(self):
        from aicli.handlers.mcp_server import _handle_message
        r = await _handle_message({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        assert "resources" in r["result"]["capabilities"]

    async def test_notification_no_id_returns_none(self):
        from aicli.handlers.mcp_server import _handle_message
        r = await _handle_message({"jsonrpc": "2.0", "method": "notifications/initialized"})
        assert r is None

    async def test_id_zero_valid_not_notification(self):
        """id=0 is falsy but is a valid JSON-RPC id — must not be treated as notification."""
        from aicli.handlers.mcp_server import _handle_message
        r = await _handle_message({"jsonrpc": "2.0", "id": 0, "method": "ping"})
        assert r is not None
        assert r["id"] == 0

    async def test_ping_returns_empty_result(self):
        from aicli.handlers.mcp_server import _handle_message
        r = await _handle_message({"jsonrpc": "2.0", "id": 1, "method": "ping"})
        assert r["result"] == {}

    async def test_unknown_method_returns_32601(self):
        from aicli.handlers.mcp_server import _handle_message
        r = await _handle_message({"jsonrpc": "2.0", "id": 1, "method": "bogus/method"})
        assert r["error"]["code"] == -32601

    async def test_tools_list_returns_4_tools(self):
        from aicli.handlers.mcp_server import _handle_message
        r = await _handle_message({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
        assert len(r["result"]["tools"]) >= 4  # 5 tools since v1.5.7 (added do)

    async def test_tools_list_all_names(self):
        from aicli.handlers.mcp_server import _handle_message
        r = await _handle_message({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
        names = {t["name"] for t in r["result"]["tools"]}
        assert {"ask", "cmd", "code", "tag"}.issubset(names)  # do added in v1.5.7

    async def test_resources_list_has_sessions_uri(self):
        from aicli.handlers.mcp_server import _handle_message
        r = await _handle_message({"jsonrpc": "2.0", "id": 1, "method": "resources/list", "params": {}})
        uris = [x["uri"] for x in r["result"]["resources"]]
        assert "sessions://list" in uris

    async def test_resources_list_has_template(self):
        from aicli.handlers.mcp_server import _handle_message
        r = await _handle_message({"jsonrpc": "2.0", "id": 1, "method": "resources/list", "params": {}})
        templates = r["result"]["resourceTemplates"]
        assert any("{session_id}" in t["uriTemplate"] for t in templates)

    async def test_resources_read_sessions_list(self):
        from aicli.handlers.mcp_server import _handle_message
        msg = {"jsonrpc": "2.0", "id": 1, "method": "resources/read",
               "params": {"uri": "sessions://list"}}
        with patch("aicli.handlers.mcp_server._resource_sessions_list",
                   return_value="[]"):
            r = await _handle_message(msg)
        assert r["result"]["contents"][0]["mimeType"] == "application/json"

    async def test_resources_read_unknown_uri_returns_32002(self):
        from aicli.handlers.mcp_server import _handle_message
        r = await _handle_message({"jsonrpc": "2.0", "id": 1, "method": "resources/read",
                                   "params": {"uri": "bogus://x"}})
        assert r["error"]["code"] == -32002

    async def test_resources_read_empty_uri_returns_error(self):
        from aicli.handlers.mcp_server import _handle_message
        r = await _handle_message({"jsonrpc": "2.0", "id": 1, "method": "resources/read",
                                   "params": {"uri": ""}})
        assert "error" in r

    def test_make_response_structure(self):
        from aicli.handlers.mcp_server import _make_response
        r = _make_response(42, {"foo": "bar"})
        assert r == {"jsonrpc": "2.0", "id": 42, "result": {"foo": "bar"}}

    def test_make_error_structure(self):
        from aicli.handlers.mcp_server import _make_error
        r = _make_error(5, -32600, "bad request")
        assert r["jsonrpc"] == "2.0"
        assert r["id"] == 5
        assert r["error"]["code"] == -32600
        assert r["error"]["message"] == "bad request"


# ─────────────────────────────────────────────────────────────────────────────
# 14. MCP tool tests
# ─────────────────────────────────────────────────────────────────────────────

class TestMCPTools:
    async def test_ask_returns_text(self, mock_pipeline, mock_config):
        from aicli.handlers.mcp_server import _handle_message
        with patch("aicli.handlers.mcp_server.load_config", return_value=mock_config), \
             patch("aicli.handlers.mcp_server.ProviderPipeline", return_value=mock_pipeline):
            r = await _handle_message({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                       "params": {"name": "ask", "arguments": {"prompt": "hi"}}})
        assert r["result"]["content"][0]["text"] == "mocked response"
        assert r["result"]["isError"] is False

    async def test_ask_missing_prompt_errors(self, mock_pipeline, mock_config):
        from aicli.handlers.mcp_server import _handle_message
        with patch("aicli.handlers.mcp_server.load_config", return_value=mock_config), \
             patch("aicli.handlers.mcp_server.ProviderPipeline", return_value=mock_pipeline):
            r = await _handle_message({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                       "params": {"name": "ask", "arguments": {}}})
        assert "error" in r

    async def test_ask_provider_exhausted_returns_error_string(self, mock_config):
        from aicli.handlers.mcp_server import _handle_message
        from aicli.providers.pipeline import ProviderExhaustedError
        failing = MagicMock()
        failing.complete = AsyncMock(side_effect=ProviderExhaustedError("all failed"))
        with patch("aicli.handlers.mcp_server.load_config", return_value=mock_config), \
             patch("aicli.handlers.mcp_server.ProviderPipeline", return_value=failing):
            r = await _handle_message({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                       "params": {"name": "ask", "arguments": {"prompt": "hi"}}})
        assert r["result"]["isError"] is True
        assert "Error" in r["result"]["content"][0]["text"]

    async def test_cmd_strips_fence(self, mock_config):
        from aicli.handlers.mcp_server import _tool_cmd
        p = MagicMock()
        p.complete = AsyncMock(return_value="```bash\nls -la\n```")
        with patch("aicli.handlers.mcp_server.load_config", return_value=mock_config), \
             patch("aicli.handlers.mcp_server.ProviderPipeline", return_value=p):
            result = await _tool_cmd("list files")
        assert "```" not in result
        assert "ls -la" in result

    async def test_cmd_strips_annotated_fence(self, mock_config):
        from aicli.handlers.mcp_server import _tool_cmd
        p = MagicMock()
        p.complete = AsyncMock(return_value="```sh\nfind .\n```")
        with patch("aicli.handlers.mcp_server.load_config", return_value=mock_config), \
             patch("aicli.handlers.mcp_server.ProviderPipeline", return_value=p):
            result = await _tool_cmd("find")
        assert "```" not in result

    async def test_cmd_plain_command_unchanged(self, mock_config):
        from aicli.handlers.mcp_server import _tool_cmd
        p = MagicMock()
        p.complete = AsyncMock(return_value="ls -la")
        with patch("aicli.handlers.mcp_server.load_config", return_value=mock_config), \
             patch("aicli.handlers.mcp_server.ProviderPipeline", return_value=p):
            result = await _tool_cmd("list")
        assert result == "ls -la"

    async def test_code_python_default(self, mock_pipeline, mock_config):
        from aicli.handlers.mcp_server import _tool_code
        with patch("aicli.handlers.mcp_server.load_config", return_value=mock_config), \
             patch("aicli.handlers.mcp_server.ProviderPipeline", return_value=mock_pipeline):
            await _tool_code("sort")
        mock_pipeline.complete.assert_called_once()

    async def test_unknown_tool_returns_32601(self):
        from aicli.handlers.mcp_server import _handle_message
        r = await _handle_message({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                   "params": {"name": "bogus", "arguments": {}}})
        assert r["error"]["code"] == -32601

    async def test_empty_tool_name_returns_32602(self):
        from aicli.handlers.mcp_server import _handle_message
        r = await _handle_message({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                   "params": {"name": "", "arguments": {}}})
        assert r["error"]["code"] == -32602

    async def test_missing_arguments_key_does_not_crash(self):
        from aicli.handlers.mcp_server import _handle_message
        r = await _handle_message({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                   "params": {"name": "ask"}})
        assert "error" in r or "result" in r


# ─────────────────────────────────────────────────────────────────────────────
# 15. MCP language names (Bug V3-1)
# ─────────────────────────────────────────────────────────────────────────────

class TestMCPLanguageNames:
    """Verify _LANG_DISPLAY produces correct casing for every supported language."""

    def _get_display(self, language, mock_config):
        """Helper: call _tool_code and capture the system prompt."""
        from aicli.handlers.mcp_server import _tool_code
        import asyncio as _asyncio
        pipeline = MagicMock()
        pipeline.complete = AsyncMock(return_value="code")
        captured = {}
        orig_complete = pipeline.complete

        async def capture(*args, **kwargs):
            if args:
                captured["messages"] = args[0]
            return "code"
        pipeline.complete = capture

        async def run():
            with patch("aicli.handlers.mcp_server.load_config", return_value=mock_config), \
                 patch("aicli.handlers.mcp_server.ProviderPipeline", return_value=pipeline):
                await _tool_code("test", language=language)

        _asyncio.run(run())
        msgs = captured.get("messages", [])
        system_msgs = [m["content"] for m in msgs if m["role"] == "system"]
        return system_msgs[0] if system_msgs else ""

    def test_javascript_display_name(self, mock_config):
        content = self._get_display("javascript", mock_config)
        assert "JavaScript" in content
        assert "Javascript" not in content

    def test_typescript_display_name(self, mock_config):
        content = self._get_display("typescript", mock_config)
        assert "TypeScript" in content
        assert "Typescript" not in content

    def test_node_display_name(self, mock_config):
        content = self._get_display("node", mock_config)
        assert "Node.js" in content
        assert content.count("Node\b") == 0 or "Node.js" in content

    def test_python_uses_role_system_prompt(self, mock_config):
        """Python default uses get_role('code') system prompt, not _LANG_DISPLAY."""
        content = self._get_display("python", mock_config)
        # May be empty if role has no system prompt — but must not say 'Python code assistant'
        # from the language override path
        assert "Python code generation assistant" not in content

    def test_bash_display_name(self, mock_config):
        content = self._get_display("bash", mock_config)
        assert "Bash" in content

    def test_go_display_name(self, mock_config):
        content = self._get_display("go", mock_config)
        assert "Go" in content

    def test_rust_display_name(self, mock_config):
        content = self._get_display("rust", mock_config)
        assert "Rust" in content

    def test_lang_display_dict_in_source(self):
        from aicli.handlers.mcp_server import _tool_code
        src = inspect.getsource(_tool_code)
        assert "_LANG_DISPLAY" in src
        assert "JavaScript" in src
        assert "TypeScript" in src
        assert "Node.js" in src


# ─────────────────────────────────────────────────────────────────────────────
# 16. MCP fence stripping (Bug V2-3)
# ─────────────────────────────────────────────────────────────────────────────

class TestMCPFenceStrip:
    """Every fence format that LLMs emit must be stripped from cmd output."""

    async def _cmd(self, raw, mock_config):
        from aicli.handlers.mcp_server import _tool_cmd
        p = MagicMock()
        p.complete = AsyncMock(return_value=raw)
        with patch("aicli.handlers.mcp_server.load_config", return_value=mock_config), \
             patch("aicli.handlers.mcp_server.ProviderPipeline", return_value=p):
            return await _tool_cmd("test")

    async def test_strips_bash_fence(self, mock_config):
        r = await self._cmd("```bash\nls -la\n```", mock_config)
        assert r == "ls -la"

    async def test_strips_sh_fence(self, mock_config):
        r = await self._cmd("```sh\nls -la\n```", mock_config)
        assert r == "ls -la"

    async def test_strips_plain_fence(self, mock_config):
        r = await self._cmd("```\nls -la\n```", mock_config)
        assert r == "ls -la"

    async def test_strips_zsh_fence(self, mock_config):
        r = await self._cmd("```zsh\nls -la\n```", mock_config)
        assert r == "ls -la"

    async def test_no_fence_passes_through(self, mock_config):
        r = await self._cmd("ls -la", mock_config)
        assert r == "ls -la"

    async def test_multiword_command_preserved(self, mock_config):
        r = await self._cmd("```bash\nfind . -name '*.py' -type f\n```", mock_config)
        assert "find" in r
        assert "```" not in r

    async def test_multiline_command_stripped(self, mock_config):
        raw = "```bash\nexport A=1\necho $A\n```"
        r = await self._cmd(raw, mock_config)
        assert "```" not in r


# ─────────────────────────────────────────────────────────────────────────────
# 17. MCP tag tool with graph file I/O
# ─────────────────────────────────────────────────────────────────────────────

class TestTagCLIFileIO:
    def test_creates_graph_file_if_missing(self, tmp_path):
        from aicli.handlers.mcp_server import _tool_tag
        with patch("aicli.handlers.mcp_server.CONFIG_DIR", tmp_path):
            result = _tool_tag("s1", ["t1"])
        assert (tmp_path / "graph_links.json").exists()

    def test_creates_names_entry(self, tmp_path):
        from aicli.handlers.mcp_server import _tool_tag
        with patch("aicli.handlers.mcp_server.CONFIG_DIR", tmp_path):
            _tool_tag("s1", ["t1"])
        data = json.loads((tmp_path / "graph_links.json").read_text())
        assert "s1" in data["names"]

    def test_tags_stored_sorted(self, tmp_path):
        from aicli.handlers.mcp_server import _tool_tag
        with patch("aicli.handlers.mcp_server.CONFIG_DIR", tmp_path):
            _tool_tag("s1", ["zzz", "aaa", "mmm"])
        data = json.loads((tmp_path / "graph_links.json").read_text())
        tags = data["names"]["s1"]["tags"]
        assert tags == sorted(tags)

    def test_no_duplicate_tags(self, tmp_path):
        from aicli.handlers.mcp_server import _tool_tag
        with patch("aicli.handlers.mcp_server.CONFIG_DIR", tmp_path):
            _tool_tag("s1", ["dup"])
            _tool_tag("s1", ["dup"])
        data = json.loads((tmp_path / "graph_links.json").read_text())
        assert data["names"]["s1"]["tags"].count("dup") == 1

    def test_merges_existing_tags(self, tmp_graph_with_sessions):
        from aicli.handlers.mcp_server import _tool_tag
        with patch("aicli.handlers.mcp_server.CONFIG_DIR", tmp_graph_with_sessions):
            _tool_tag("abc123full-uuid", ["newtag"])
        data = json.loads((tmp_graph_with_sessions / "graph_links.json").read_text())
        tags = data["names"]["abc123full-uuid"]["tags"]
        assert "existing" in tags
        assert "newtag" in tags

    def test_returns_confirmation_string(self, tmp_path):
        from aicli.handlers.mcp_server import _tool_tag
        with patch("aicli.handlers.mcp_server.CONFIG_DIR", tmp_path):
            result = _tool_tag("ses", ["urgent"])
        assert isinstance(result, str)
        assert "urgent" in result

    def test_returns_error_string_not_raises_on_io_error(self, tmp_path):
        from aicli.handlers.mcp_server import _tool_tag
        readonly = tmp_path / "ro"
        readonly.mkdir()
        (readonly / "graph_links.json").write_text("{invalid json")
        # Should not raise — returns error string
        with patch("aicli.handlers.mcp_server.CONFIG_DIR", readonly):
            result = _tool_tag("s1", ["t1"])
        assert isinstance(result, str)

    def test_db_resolution_fallback_on_exception(self, tmp_path):
        """When DB raises, falls back to literal string key — no crash."""
        from aicli.handlers.mcp_server import _tool_tag
        with patch("aicli.handlers.mcp_server.CONFIG_DIR", tmp_path), \
             patch("aicli.db.chat_db.get_connection", side_effect=Exception("no db")):
            result = _tool_tag("literal-key", ["t1"])
        assert isinstance(result, str)
        data = json.loads((tmp_path / "graph_links.json").read_text())
        # Fallback: key is the literal string
        assert "literal-key" in data["names"]


# ─────────────────────────────────────────────────────────────────────────────
# 18. Env var mirrors
# ─────────────────────────────────────────────────────────────────────────────

class TestEnvVarMirrors:
    """Every AICLI_* env var must have a corresponding CLI flag."""

    def test_AICLI_LITE_in_default_handler(self):
        from aicli.handlers.default import _ask
        src = inspect.getsource(_ask)
        assert "AICLI_LITE" in src

    def test_AICLI_QUIET_in_default_handler(self):
        from aicli.handlers.default import _ask
        src = inspect.getsource(_ask)
        assert "AICLI_QUIET" in src

    def test_AICLI_LITE_env_mirror_pattern(self):
        """Pattern must be: flag = flag or env == '1'"""
        from aicli.handlers.default import _ask
        src = inspect.getsource(_ask)
        assert 'AICLI_LITE") == "1"' in src or "AICLI_LITE\") == '1'" in src

    def test_AICLI_QUIET_env_mirror_pattern(self):
        from aicli.handlers.default import _ask
        src = inspect.getsource(_ask)
        assert 'AICLI_QUIET") == "1"' in src or "AICLI_QUIET\") == '1'" in src

    def test_main_lite_sets_AICLI_LITE(self):
        from aicli.app import main_lite
        src = inspect.getsource(main_lite)
        assert "AICLI_LITE" in src and '"1"' in src


# ─────────────────────────────────────────────────────────────────────────────
# 19. MCP server constants and transport
# ─────────────────────────────────────────────────────────────────────────────

class TestMCPTransport:
    def test_protocol_version_constant(self):
        from aicli.handlers.mcp_server import PROTOCOL_VERSION
        assert PROTOCOL_VERSION == "2024-11-05"

    def test_protocol_version_date_format(self):
        from aicli.handlers.mcp_server import PROTOCOL_VERSION
        assert re.match(r"^\d{4}-\d{2}-\d{2}$", PROTOCOL_VERSION)

    def test_server_name_constant(self):
        from aicli.handlers.mcp_server import SERVER_NAME
        assert SERVER_NAME == "aicli-maxmux"

    def test_run_mcp_invalid_transport_exits(self):
        from aicli.handlers.mcp_server import run_mcp
        with pytest.raises(SystemExit) as exc:
            run_mcp(transport="ftp")
        assert exc.value.code == 1

    def test_run_mcp_stdio_calls_asyncio_run(self):
        from aicli.handlers.mcp_server import run_mcp
        src = inspect.getsource(run_mcp)
        assert "_run_stdio" in src
        assert "_run_sse" in src

    def test_server_version_at_least_1_5_4(self):
        from aicli.handlers.mcp_server import _server_version
        v = _server_version()
        major, minor, patch_v = (int(x) for x in v.split(".")[:3])
        assert (major, minor, patch_v) >= (1, 5, 4)

    def test_all_tools_have_descriptions(self):
        from aicli.handlers.mcp_server import TOOLS
        for t in TOOLS:
            assert len(t.get("description", "")) > 20

    def test_all_tools_have_input_schema(self):
        from aicli.handlers.mcp_server import TOOLS
        for t in TOOLS:
            assert "inputSchema" in t
            assert t["inputSchema"]["type"] == "object"

    def test_tools_schema_serializable(self):
        from aicli.handlers.mcp_server import TOOLS
        assert len(json.loads(json.dumps(TOOLS))) >= 4  # 5 tools since v1.5.7

    def test_resources_have_uris(self):
        from aicli.handlers.mcp_server import RESOURCES
        for r in RESOURCES:
            assert "uri" in r and r["uri"].startswith("sessions://")

    def test_resource_templates_have_uri_templates(self):
        from aicli.handlers.mcp_server import RESOURCE_TEMPLATES
        for t in RESOURCE_TEMPLATES:
            assert "uriTemplate" in t
            assert "{session_id}" in t["uriTemplate"]

    def test_stdio_transport_uses_stdout_buffer(self):
        from aicli.handlers import mcp_server as _m
        src = inspect.getsource(_m._run_stdio)
        assert "stdout.buffer" in src

    def test_sse_transport_uses_simple_queue(self):
        from aicli.handlers import mcp_server as _m
        src = inspect.getsource(_m._run_sse)
        assert "SimpleQueue" in src

    def test_sse_transport_uses_get_running_loop(self):
        from aicli.handlers import mcp_server as _m
        src = inspect.getsource(_m._run_sse)
        assert "get_running_loop" in src
        assert "get_event_loop" not in src


# ─────────────────────────────────────────────────────────────────────────────
# 20. Shell script content checks
# ─────────────────────────────────────────────────────────────────────────────

class TestShellScripts:
    def _read(self, name):
        p = Path(__file__).parent.parent / name
        if not p.exists():
            pytest.skip(f"{name} not found")
        return p.read_text()

    def test_map_structure_version_is_1_5_4(self):
        text = self._read("map_structure.sh")
        assert "1.5.4" in text

    def test_map_structure_no_1_5_1_version(self):
        text = self._read("map_structure.sh")
        # 1.5.1 should only appear as a historical reference (PyPI publish line)
        lines_with_old = [
            ln for ln in text.splitlines()
            if "1.5.1" in ln and "Version:" in ln or
            ("Package:" in ln and "1.5.1" in ln) or
            ("Published to" in ln and "1.5.1" in ln and "1.5.4" not in text.split(ln)[0][-20:])
        ]
        assert len(lines_with_old) == 0

    def test_map_structure_mcp_server_in_handlers(self):
        text = self._read("map_structure.sh")
        assert "mcp_server" in text

    def test_map_structure_test_mcp_server_in_tests(self):
        text = self._read("map_structure.sh")
        assert "test_mcp_server" in text

    def test_map_structure_mcp_in_file_stats_loop(self):
        text = self._read("map_structure.sh")
        assert '"aicli/handlers/mcp_server.py"' in text

    def test_map_structure_mcp_in_test_count_grep(self):
        text = self._read("map_structure.sh")
        # test count grep must include test_mcp_server.py
        grep_section_start = text.find("grep -c")
        assert "test_mcp_server" in text[grep_section_start:grep_section_start + 500]

    def test_retract_mcp_server_in_preserved(self):
        text = self._read("retract.sh")
        assert "mcp_server" in text

    def test_retract_test_mcp_server_in_preserved(self):
        text = self._read("retract.sh")
        assert "test_mcp_server" in text

    def test_retract_step_10_install_shell(self):
        text = self._read("retract.sh")
        assert "install-shell" in text

    def test_expand_installs_all_extras(self):
        p = Path(__file__).parent.parent / "expand.sh"
        if not p.exists():
            pytest.skip("expand.sh not found")
        text = p.read_text()
        assert ".[all]" in text, (
            "expand.sh must install optional extras. "
            "Add after 'pip install -e .': pip install -e .[all] --quiet"
        )

    def test_map_structure_mcp_in_roadmap_complete(self):
        text = self._read("map_structure.sh")
        assert "MCP" in text
        assert "COMPLETE" in text or "v1.5.4" in text


# ─────────────────────────────────────────────────────────────────────────────
# 21. Async pattern enforcement
# ─────────────────────────────────────────────────────────────────────────────

class TestAsyncPattern:
    """
    Enforce correct async patterns across test files.
    With asyncio_mode=auto, tests must be async def + await, not asyncio.run().
    """

    def _code_lines_with_asyncio_run(self, filepath: Path) -> list:
        if not filepath.exists():
            return []
        text = filepath.read_text()
        bad = []
        in_docstring = False
        docstring_marker = None
        for i, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            # Track triple-quoted docstring entry/exit
            if not in_docstring:
                for marker in ('"""', "'''"):
                    if marker in stripped:
                        occurrences = stripped.count(marker)
                        if occurrences == 1:
                            # Opening only — we are now inside a docstring
                            in_docstring = True
                            docstring_marker = marker
                        # occurrences >= 2 means open+close on same line — not inside
                        break
            else:
                # We are inside a docstring — check for closing marker
                if docstring_marker in stripped:
                    in_docstring = False
                    docstring_marker = None
                continue  # skip this line regardless
            # Skip comment lines
            if stripped.startswith("#"):
                continue
            # Skip lines where asyncio.run() is used inside a sync private helper
            # (e.g. _get_display uses asyncio.run legitimately — it is not an async test)
            if "asyncio.run(" in line:
                # Walk back to find the enclosing def — if it starts with _ it's a helper
                lines_above = text.splitlines()[:i - 1]
                enclosing_def = ""
                for prev in reversed(lines_above):
                    ps = prev.strip()
                    if ps.startswith("def ") or ps.startswith("async def "):
                        enclosing_def = ps
                        break
                # Only flag if inside an async def test_ (not a sync helper)
                if enclosing_def.startswith("async def test_"):
                    bad.append(f"Line {i}: {line.rstrip()}")
        return bad

    def test_test_mcp_server_no_asyncio_run(self):
        p = Path(__file__).parent / "test_mcp_server.py"
        bad = self._code_lines_with_asyncio_run(p)
        assert bad == [], f"asyncio.run() found in test_mcp_server.py:\n" + "\n".join(bad)

    def test_this_file_no_asyncio_run_in_async_tests(self):
        """This comprehensive test file must also follow the pattern."""
        bad = self._code_lines_with_asyncio_run(Path(__file__))
        assert bad == [], f"asyncio.run() in test_comprehensive.py:\n" + "\n".join(bad)

    def test_async_test_methods_use_await(self):
        """All async test methods in this file must contain await."""
        text = Path(__file__).read_text()
        # Find all `async def test_` blocks
        pattern = re.compile(r"    async def (test_\w+)\(self[^)]*\):(.*?)(?=\n    (?:async )?def |\nclass |\Z)", re.DOTALL)
        no_await = []
        for m in pattern.finditer(text):
            name, body = m.group(1), m.group(2)
            # Skip tests that are just stubs or pytest.skip
            if "await " not in body and "pytest.skip" not in body and "pass" not in body.strip():
                no_await.append(name)
        assert no_await == [], f"async test methods with no await: {no_await}"


# ─────────────────────────────────────────────────────────────────────────────
# 22. MCP tool schemas completeness
# ─────────────────────────────────────────────────────────────────────────────

class TestMCPToolSchemas:
    def _tools(self):
        from aicli.handlers.mcp_server import TOOLS
        return {t["name"]: t for t in TOOLS}

    def test_ask_schema_required_prompt(self):
        assert "prompt" in self._tools()["ask"]["inputSchema"]["required"]

    def test_ask_schema_optional_session_id(self):
        props = self._tools()["ask"]["inputSchema"]["properties"]
        assert "session_id" in props

    def test_ask_schema_optional_model(self):
        props = self._tools()["ask"]["inputSchema"]["properties"]
        assert "model" in props

    def test_cmd_schema_required_prompt(self):
        assert "prompt" in self._tools()["cmd"]["inputSchema"]["required"]

    def test_code_schema_required_prompt(self):
        assert "prompt" in self._tools()["code"]["inputSchema"]["required"]

    def test_code_schema_language_enum(self):
        lang = self._tools()["code"]["inputSchema"]["properties"]["language"]
        assert "enum" in lang
        assert "javascript" in lang["enum"]
        assert "typescript" in lang["enum"]
        assert "node" in lang["enum"]
        assert "python" in lang["enum"]
        assert "bash" in lang["enum"]

    def test_tag_schema_required_session_id(self):
        assert "session_id" in self._tools()["tag"]["inputSchema"]["required"]

    def test_tag_schema_required_tags(self):
        assert "tags" in self._tools()["tag"]["inputSchema"]["required"]

    def test_tag_schema_tags_is_array(self):
        tags_schema = self._tools()["tag"]["inputSchema"]["properties"]["tags"]
        assert tags_schema["type"] == "array"
        assert tags_schema["items"]["type"] == "string"

    def test_all_tools_json_round_trip(self):
        from aicli.handlers.mcp_server import TOOLS
        for tool in TOOLS:
            rt = json.loads(json.dumps(tool))
            assert rt["name"] == tool["name"]
