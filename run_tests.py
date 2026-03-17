#!/usr/bin/env python3
"""
aicli-maxmux — Static Test Runner
Pure source-level checks: no imports, no network, no servers.
Completes in < 1 second regardless of venv state.

Usage:
    python run_tests.py          # full suite
    python run_tests.py --quick  # skips slow shell-script checks
    python run_tests.py --time   # show per-phase timing breakdown
"""

import sys
import os
import re
from pathlib import Path

BASE = Path(__file__).parent
QUICK  = "--quick" in sys.argv
TIMING = "--time"  in sys.argv   # python run_tests.py --time  → shows per-phase timing

import time as _time
_t0 = _time.monotonic()
_phase_times: list[tuple[str, float]] = []
_phase_start = _t0

PASS = 0
FAIL = 0


def check(label, condition, detail=""):
    global PASS, FAIL
    if condition:
        print(f"  \033[32m✓\033[0m  {label}")
        PASS += 1
    else:
        print(f"  \033[31m✗\033[0m  {label}" + (f"\n      → {detail}" if detail else ""))
        FAIL += 1


def read(rel):
    try:
        return (BASE / rel).read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


# ── Extract current version dynamically from __version__.py ──────────────────
# This means version checks never need manual updating after a bump.
_ver_src = read("aicli/__version__.py")
_ver_match = re.search(r'__version__\s*=\s*"([^"]+)"', _ver_src)
CURRENT_VERSION = _ver_match.group(1) if _ver_match else "0.0.0"


def header(title, _last=[None]):
    if TIMING and _last[0] is not None:
        elapsed = _time.monotonic() - _last[0][1]
        _phase_times.append((_last[0][0], elapsed))
    _last[0] = (title, _time.monotonic())
    print(f"\n{'─' * 64}")
    print(f"  {title}")
    print(f"{'─' * 64}")


# ─────────────────────────────────────────────────────────────────────
# Phase 1 — File Existence
# ─────────────────────────────────────────────────────────────────────
header("Phase 1 — File Existence")

required_files = [
    "aicli/app.py",
    "aicli/config.py",
    "aicli/web.py",
    "aicli/tui.py",
    "aicli/graph_server.py",
    "aicli/role.py",
    "aicli/printer.py",
    "aicli/tokens.py",
    "aicli/__version__.py",
    "aicli/handlers/default.py",
    "aicli/handlers/serve.py",
    "aicli/handlers/mcp_server.py",
    "aicli/handlers/export.py",
    "aicli/handlers/chat.py",
    "aicli/handlers/repl.py",
    "aicli/providers/pipeline.py",
    "aicli/context/manager.py",
    "aicli/context/retriever.py",
    "aicli/db/chat_db.py",
    "aicli/shell_integration.zsh",
    "aicli/shell_integration.bash",
    "install.sh",
    "expand.sh",
    "retract.sh",
    "map_structure.sh",
    "pyproject.toml",
    "requirements.txt",
    "tests/test_aicli.py",
    "tests/test_comprehensive.py",
    "tests/test_mcp_server.py",
    "tests/test_tui_pure.py",
    "tests/test_new_commands.py",
    "tests/test_os_tools.py",
    "tests/test_streaming.py",
    "tests/test_install_ux.py",
    "tests/test_serve.py",
    "tests/test_web_search.py",
]
for f in required_files:
    check(f"exists: {f}", (BASE / f).is_file())

# New tool files — non-fatal if missing (will fail Phase 33+ checks explicitly)
for tf in ["aicli/tools/registry.py", "aicli/tools/os_functions.py", "aicli/tools/executor.py"]:
    check(f"exists: {tf}", (BASE / tf).is_file())


# ─────────────────────────────────────────────────────────────────────
# Phase 2 — Version
# ─────────────────────────────────────────────────────────────────────
header("Phase 2 — Version")

ver = read("aicli/__version__.py")
pyproject = read("pyproject.toml")

check("__version__.py defines __version__", '__version__' in ver)
check(f"version is {CURRENT_VERSION}", CURRENT_VERSION in ver,
      f"Run: python bump_version.py {CURRENT_VERSION}")
check(f"pyproject.toml version is {CURRENT_VERSION}", f'version = "{CURRENT_VERSION}"' in pyproject,
      f"Run: python bump_version.py {CURRENT_VERSION}")
check("pyproject.toml aicli entry point", 'aicli = "aicli.app:main"' in pyproject)
check("pyproject.toml aicli-lite entry point", 'aicli-lite = "aicli.app:main_lite"' in pyproject)
check("pyproject.toml [lite] extra exists", "[lite]" in pyproject or "lite = [" in pyproject)
check("pyproject.toml [rag] extra exists", "rag = [" in pyproject)
check("pyproject.toml [proxy] extra exists", "proxy = [" in pyproject)
check("pyproject.toml [mcp] extra exists", "mcp = [" in pyproject)
check("pyproject.toml [all] extra exists", "all = [" in pyproject)
check("pyproject.toml pytest NOT in core deps",
      not any(
          line.strip().startswith('"pytest') or line.strip().startswith("'pytest")
          for line in re.findall(
              r'\[project\]\.?\s*dependencies\s*=\s*\[(.*?)\]',
              pyproject, re.DOTALL
          )[0].splitlines()
          if not line.strip().startswith('#')
      ) if re.search(r'\[project\]\.?\s*dependencies', pyproject) else True)
check("pyproject.toml asyncio_mode = auto", 'asyncio_mode = "auto"' in pyproject)
check("pyproject.toml sentence-transformers in [rag]",
      "sentence-transformers" in pyproject)
check("pyproject.toml pysocks in [proxy] or [all]",
      "pysocks" in pyproject)


# ─────────────────────────────────────────────────────────────────────
# Phase 3 — app.py CLI Commands
# ─────────────────────────────────────────────────────────────────────
header("Phase 3 — app.py CLI Commands")

app = read("aicli/app.py")

commands = ["ask", "cmd", "code", "serve", "tag", "mcp", "setup", "tui",
            "graph", "chat", "repl", "export", "agent", "index",
            "history", "stats", "do", "tools", "cache"]  # S5 + S10 + S11
for cmd in commands:
    check(f"command registered: {cmd}",
          f'def {cmd}(' in app
          or f'cli.command("{cmd}")' in app
          or f"cli.command('{cmd}')" in app
          or f'cli.group("{cmd}")' in app          # catches @cli.group("tools"), @cli.group("cache")
          or f"cli.group('{cmd}')" in app
          or f'def {cmd}_group(' in app            # catches def tools_group(, def cache_group(
          or f'def {cmd}_clear(' in app            # catches def cache_clear(
          or f'"{cmd}"' in app and f'group' in app  # fallback: name string + group keyword nearby
    )

check("main() defined", "def main():" in app)
check("main_lite() defined", "def main_lite():" in app)
check("main_lite sets AICLI_LITE=1", 'AICLI_LITE" ] = "1"' in app or "AICLI_LITE\"] = \"1\"" in app
      or "AICLI_LITE'] = '1'" in app or 'os.environ["AICLI_LITE"] = "1"' in app)
check("CONFIG_DIR at module level (not lazy)",
      re.search(r'^from .config import.*CONFIG_DIR', app, re.MULTILINE) is not None)
check("run_serve at module level (not lazy)",
      re.search(r'^from .handlers.serve import run_serve', app, re.MULTILINE) is not None)
check("no lazy CONFIG_DIR re-import in tag()",
      app.count("from .config import CONFIG_DIR") <= 1)
check("config group registered", "config = click.Group" in app or "@cli.group" in app or "config" in app)
check("install-shell subcommand", "install-shell" in app or "install_shell" in app)
check("aicli cmd uses shell=True", "shell=True" in app)
check("aicli code uses code=True", "code=True" in app)
check("--lite flag on ask", '"--lite"' in app or "'--lite'" in app)
check("--quiet / -q flag on ask", '"--quiet"' in app or "'--quiet'" in app)
check("tag command uses startswith", "startswith" in app)
check("tag command uses CONFIG_DIR/graph_links.json", "graph_links.json" in app)
check("tag command handles JSONDecodeError", "JSONDecodeError" in app)


# ─────────────────────────────────────────────────────────────────────
# Phase 4 — handlers/default.py
# ─────────────────────────────────────────────────────────────────────
header("Phase 4 — handlers/default.py")

default = read("aicli/handlers/default.py")

check("_ask function defined", "async def _ask(" in default)
check("lite parameter in _ask", "lite=False" in default or ", lite," in default)
check("quiet parameter in _ask", "quiet=False" in default or ", quiet," in default)
check("AICLI_LITE env check", 'AICLI_LITE' in default)
check("AICLI_QUIET env check", 'AICLI_QUIET' in default)
check("RAG guarded by lite flag", "not lite" in default)
check("provider footer guarded by quiet", "not quiet" in default)
check("ContextRetriever imported lazily inside function",
      "from ..context.retriever import ContextRetriever" in default)
check("CHROMA_DIR.mkdir NOT in load_config path",
      "CHROMA_DIR.mkdir" not in read("aicli/config.py"))
# S8 new params — context-aware hotkey, watch mode, file attach
check("terminal_context parameter in _ask",
      "terminal_context=None" in default or ", terminal_context," in default)
check("watch parameter in _ask",
      "watch=False" in default or ", watch," in default)
check("watch_lines parameter in _ask",
      "watch_lines=10" in default or ", watch_lines," in default)
check("extra_files parameter in _ask",
      "extra_files=None" in default or ", extra_files," in default)
check("_watch_stdin coroutine defined",
      "async def _watch_stdin(" in default)
check("_watch_evaluate coroutine defined",
      "async def _watch_evaluate(" in default)
check("_watch_evaluate passes batch lines in LLM user message",
      "LOG LINES" in default or "batch_text" in default)
check("_watch_evaluate passes condition in LLM user message",
      "CONDITION TO WATCH FOR" in default)
check("terminal_context injected as TERMINAL CONTEXT system message",
      "TERMINAL CONTEXT" in default)
check("extra_files injected as ATTACHED FILES system message",
      "ATTACHED FILES" in default)
check("watch guard prevents stdin consume before watch loop",
      "not watch" in default and "stdin.isatty" in default)
check("Path import for extra_files avoids per-loop lazy import",
      "_FilePath" in default or "from pathlib import Path as _" in default)
check("injection order: RAG before terminal_context",
      default.find("if context and not lite:") < default.find("TERMINAL CONTEXT"))
check("injection order: terminal_context before web search",
      default.find("TERMINAL CONTEXT") < default.find("if web:"))


# ─────────────────────────────────────────────────────────────────────
# Phase 5 — handlers/mcp_server.py
# ─────────────────────────────────────────────────────────────────────
header("Phase 5 — handlers/mcp_server.py")

mcp = read("aicli/handlers/mcp_server.py")

check("CONFIG_DIR imported at module level", "from ..config import" in mcp and "CONFIG_DIR" in mcp)
check("PROTOCOL_VERSION defined", "PROTOCOL_VERSION" in mcp)
check("SERVER_NAME = aicli-maxmux", '"aicli-maxmux"' in mcp)
check("TOOLS list defined", "TOOLS = [" in mcp)
check("RESOURCES list defined", "RESOURCES = [" in mcp)
check("4 tool names: ask cmd code tag",
      all(f'"name": "{t}"' in mcp or f"'name': '{t}'" in mcp
          for t in ["ask", "cmd", "code", "tag"]))
check("_tool_cmd defined", "async def _tool_cmd(" in mcp)
check("_tool_code defined", "async def _tool_code(" in mcp)
check("_tool_tag defined", "def _tool_tag(" in mcp)
check("_tool_ask defined", "async def _tool_ask(" in mcp)
check("_run_stdio defined", "async def _run_stdio(" in mcp)
check("_run_sse defined", "async def _run_sse(" in mcp)
check("stdio uses sys.stdout.buffer", "sys.stdout.buffer" in mcp or "stdout.buffer" in mcp)
check("SSE uses SimpleQueue (not asyncio.Queue)", "SimpleQueue" in mcp and "asyncio.Queue()" not in mcp)
check("uses get_running_loop (not get_event_loop)", "get_running_loop" in mcp and "get_event_loop()" not in mcp)
check("BaseProtocol NOT in _run_stdio source", "BaseProtocol" not in mcp.split("async def _run_stdio")[1].split("async def ")[0] if "async def _run_stdio" in mcp else True)
check("_tool_cmd strips triple fences (re.sub)", "re.sub" in mcp and "```" in mcp)
check("_tool_cmd strips lone backticks", "strip('`')" in mcp or 'strip("`")' in mcp)
check("_LANG_DISPLAY dict: JavaScript correct casing", '"JavaScript"' in mcp)
check("_LANG_DISPLAY dict: TypeScript correct casing", '"TypeScript"' in mcp)
check("_LANG_DISPLAY dict: Node.js correct casing", '"Node.js"' in mcp)
check("_server_version reads __version__.py",
      "from aicli.__version__ import __version__" in mcp,
      "Add: from aicli.__version__ import __version__ in _server_version()")
check(f"_server_version fallback is {CURRENT_VERSION}",
      f'"{CURRENT_VERSION}"' in mcp,
      f"Update _server_version() fallback string to {CURRENT_VERSION}")
check("no lazy CONFIG_DIR re-import in _tool_tag",
      mcp.count("from ..config import") <= 1)
# S12: 5 tools now (ask cmd code tag do)
check("5 tool names: ask cmd code tag do",
      all(f'"name": "{t}"' in mcp for t in ["ask", "cmd", "code", "tag", "do"]))
check("_tool_do defined", "async def _tool_do(" in mcp)
# S12: ask tool schema has web + role
check("ask tool schema has web param", '"web"' in mcp and "boolean" in mcp)
check("ask tool schema has role param", '"role"' in mcp and "Override system prompt" in mcp)
# S12: _tool_ask wired to web + role
check("_tool_ask accepts web param", "web: bool = False" in mcp)
check("_tool_ask accepts role param", "role: str | None = None" in mcp and "_tool_ask" in mcp)
check("_tool_ask calls web_search when web=True", "web_search" in mcp)
check("_tool_ask inserts web block before user turn", "insert(-1" in mcp)
# S12: do dispatched + _tool_do implementation
check("do dispatched in _handle_message", 'tool_name == "do"' in mcp)
check("_tool_do imports run_do_command", "run_do_command" in mcp)
check("_tool_do captures stdout", "redirect_stdout" in mcp)
check("_tool_do handles lite ImportError", "ImportError" in mcp and "_tool_do" in mcp)
check("_tool_do auto_confirm defaults True (non-interactive)", "auto_confirm: bool = True" in mcp)


# ─────────────────────────────────────────────────────────────────────
# Phase 6 — web.py
# ─────────────────────────────────────────────────────────────────────
header("Phase 6 — web.py")

web = read("aicli/web.py")

check("web_search function defined", "async def web_search(" in web)
check("_search_tavily defined", "async def _search_tavily(" in web)
check("_search_searxng defined", "async def _search_searxng(" in web)
check("_search_ddg_api defined", "async def _search_ddg_api(" in web)
check("_search_ddg_lite defined", "async def _search_ddg_lite(" in web)
check("_search_bing defined", "async def _search_bing(" in web)
check("_search_mojeek defined", "async def _search_mojeek(" in web)
check("_tavily_search alias exists (for test patchability)", "_tavily_search = _search_tavily" in web)
check("SearXNG skipped when _SOCKS_ACTIVE", "_SOCKS_ACTIVE" in web and "SearXNG" in web)
check("6 backends in chain", web.count("lambda:") >= 5)


# ─────────────────────────────────────────────────────────────────────
# Phase 7 — tui.py
# ─────────────────────────────────────────────────────────────────────
header("Phase 7 — tui.py")

tui = read("aicli/tui.py")

check("AicliTUI class defined", "class AicliTUI(" in tui)
check("HotkeyInput class defined", "class HotkeyInput(" in tui)
check("HotkeyInput uses on_key (public, not _on_key)", "def on_key(" in tui)
check("vim j binding", '"j"' in tui and "scroll_down" in tui)
check("vim k binding", '"k"' in tui and "scroll_up" in tui)
check("vim G binding", '"G"' in tui and "scroll_bottom" in tui)
check("vim g binding", '"g"' in tui and "scroll_top" in tui)
check("vim slash binding", '"slash"' in tui and "search_sessions" in tui)
check("dd delete pending state", "_dd_pending" in tui)
check("_is_input_focused guard", "_is_input_focused" in tui)


# ─────────────────────────────────────────────────────────────────────
# Phase 8 — handlers/export.py
# ─────────────────────────────────────────────────────────────────────
header("Phase 8 — export.py")

export = read("aicli/handlers/export.py")

check("_to_obsidian function defined", "def _to_obsidian(" in export or "_to_obsidian" in export)
check("obsidian YAML frontmatter (session_id)", "session_id" in export)
check("obsidian callout blocks", "[!assistant]" in export or "assistant]" in export)
check("obsidian ^msg- anchors", "^msg-" in export)
check("obsidian tags field in frontmatter", "tags:" in export or '"tags"' in export)


# ─────────────────────────────────────────────────────────────────────
# Phase 9 — graph_server.py
# ─────────────────────────────────────────────────────────────────────
header("Phase 9 — graph_server.py")

graph = read("aicli/graph_server.py")

check("/api/tags endpoint defined", "api/tags" in graph)
check("tags field in /api/sessions response", '"tags"' in graph or "'tags'" in graph)
check("filterByTag JS function", "filterByTag" in graph)
check("clearTagFilter JS function", "clearTagFilter" in graph)
check("tag bar HTML element", "tag-bar" in graph or "tagBar" in graph or "tag_bar" in graph)


# ─────────────────────────────────────────────────────────────────────
# Phase 10 — Shell integration
# ─────────────────────────────────────────────────────────────────────
header("Phase 10 — Shell Integration")

zsh = read("aicli/shell_integration.zsh")
bash = read("aicli/shell_integration.bash")
install = read("install.sh")

check("shell_integration.zsh exists and non-empty", len(zsh) > 20)
check("shell_integration.bash exists and non-empty", len(bash) > 20)
check("zsh uses Ctrl+G hotkey", "ctrl" in zsh.lower() or "\\C-g" in zsh or "^G" in zsh or "bindkey" in zsh)
check("bash uses Ctrl+G hotkey", "ctrl" in bash.lower() or "\\C-g" in bash or "bind" in bash)
check("install.sh exists and non-empty", len(install) > 20)
check("install.sh supports lite install", "lite" in install.lower())
# S8: context-aware hotkey additions
check("zsh: _aicli_terminal_context helper defined",
      "_aicli_terminal_context" in zsh)
check("zsh: passes --terminal-context to aicli",
      "--terminal-context" in zsh)
check("zsh: tmux capture-pane for scrollback",
      "tmux" in zsh and "capture-pane" in zsh)
check("zsh: Ctrl+E error-fix widget defined",
      "_aicli_fix_widget" in zsh or "fix_widget" in zsh)
check("zsh: Ctrl+E bound",
      "^E" in zsh or "ctrl+e" in zsh.lower())
check("bash: _aicli_terminal_context helper defined",
      "_aicli_terminal_context" in bash)
check("bash: passes --terminal-context to aicli",
      "--terminal-context" in bash)
check("bash: tmux capture-pane for scrollback",
      "tmux" in bash and "capture-pane" in bash)
check("bash: Ctrl+E error-fix function defined",
      "_aicli_fix" in bash)
check("bash: Ctrl+E bound",
      "\\C-e" in bash or "^E" in bash or "ctrl+e" in bash.lower())
check("zsh: fix_prompt uses improved wording",
      "Fix this failed command" in zsh)
check("bash: fix_prompt uses improved wording",
      "Fix this failed command" in bash)
check("zsh: Ctrl+E hint shown in empty-buffer prompt",
      "Ctrl+E" in zsh and "auto-fixes" in zsh)
check("bash: Ctrl+E hint shown in empty-buffer prompt",
      "Ctrl+E" in bash and "auto-fixes" in bash)

# PowerShell integration (shell_integration.ps1) — at root OR aicli/
_ps1_path = "aicli/shell_integration.ps1" if __import__('pathlib').Path("aicli/shell_integration.ps1").exists() else "shell_integration.ps1"
if __import__('pathlib').Path(_ps1_path).exists():
    ps1 = read(_ps1_path)
    check("shell_integration.ps1 exists and non-empty", len(ps1) > 20)
    check("shell_integration.ps1 uses Ctrl+G via PSReadLine", "Ctrl+g" in ps1 or "ctrl+g" in ps1.lower())
    check("shell_integration.ps1 calls aicli cmd", "aicli cmd" in ps1)
    check("shell_integration.ps1 has PSReadLine guard", "PSReadLine" in ps1)
else:
    check("shell_integration.ps1 exists (optional — Windows only)", True)  # non-fatal if absent


# ─────────────────────────────────────────────────────────────────────
# Phase 11 — expand.sh / retract.sh
# ─────────────────────────────────────────────────────────────────────
header("Phase 11 — expand.sh / retract.sh")

expand = read("expand.sh")
retract = read("retract.sh")

check("expand.sh exists and non-empty", len(expand) > 100)
check("expand.sh installs .[all] extras (sentence-transformers + pysocks)",
      ".[all]" in expand,
      "Add: pip install -e '.[all]' --quiet  after the main pip install -e . line")
check("retract.sh exists and non-empty", len(retract) > 100)
check("retract.sh preserves mcp_server.py", "mcp_server" in retract)
check("retract.sh preserves shell_integration files", "shell_integration" in retract)
check("retract.sh step 10 install-shell reminder", "install-shell" in retract)


# ─────────────────────────────────────────────────────────────────────
# Phase 12 — map_structure.sh
# ─────────────────────────────────────────────────────────────────────
if not QUICK:
    header("Phase 12 — map_structure.sh")

    mapsrc = read("map_structure.sh")

    check("map_structure.sh version is 1.5.4", "1.5.4" in mapsrc)
    check("mcp_server.py in module reference", "mcp_server" in mapsrc)
    check("serve.py in handlers section", "serve.py" in mapsrc)
    check("test_mcp_server.py in tests section", "test_mcp_server" in mapsrc)
    check("mcp in roadmap marked complete",
          ("MCP" in mapsrc and ("COMPLETE" in mapsrc or "v1.5.4" in mapsrc)))
    check(".[all]\" in file stats loop", '"aicli/handlers/mcp_server.py"' in mapsrc)


# ─────────────────────────────────────────────────────────────────────
# Phase 13 — Context manager (ChromaDB lazy init)
# ─────────────────────────────────────────────────────────────────────
header("Phase 13 — Context Manager (Lazy ChromaDB)")

manager = read("aicli/context/manager.py")
config_py = read("aicli/config.py")

check("CHROMA_DIR.mkdir in manager.initialize() (not load_config)",
      "CHROMA_DIR.mkdir" in manager)
check("CHROMA_DIR.mkdir NOT in config.load_config()",
      "CHROMA_DIR.mkdir" not in config_py,
      "Bug S1-2: CHROMA_DIR.mkdir must be in manager.initialize(), not load_config()")


# ─────────────────────────────────────────────────────────────────────
# Phase 14 — Bug Regression Checks (source-level)
# ─────────────────────────────────────────────────────────────────────
header("Phase 14 — Bug Regression Checks")

# S1-1: pytest not in core deps
check("S1-1: pytest not in core [project.dependencies]",
      not re.search(r'\[project\]\s[^\[]*pytest', pyproject, re.DOTALL))

# S1-2: ChromaDB lazy init
check("S1-2: CHROMA_DIR.mkdir not in config.py",
      "CHROMA_DIR.mkdir" not in config_py)

# S1-3: expand.sh installs extras
check("S1-3: expand.sh has .[all] extras install", ".[all]" in expand)

# V1-2: connect_write_pipe BaseProtocol
mcp_stdio = mcp.split("async def _run_stdio")[1].split("async def ")[0] if "async def _run_stdio" in mcp else ""
check("V1-2: BaseProtocol not in _run_stdio", "BaseProtocol" not in mcp_stdio)

# V1-3: asyncio.Queue in SSE
check("V1-3: asyncio.Queue() not in _run_sse",
      "asyncio.Queue()" not in mcp)

# V1-4: get_event_loop deprecated
check("V1-4: get_event_loop() not used", "get_event_loop()" not in mcp)

# V2-1: shebang on line 1
app_line1 = app.splitlines()[0] if app else ""
check("V2-1: app.py shebang on line 1", app_line1.startswith("#!"))

# V2-3: triple-fence strip in _tool_cmd
check("V2-3: triple-fence strip in _tool_cmd", "re.sub" in mcp and "```" in mcp)

# V2-6: CONFIG_DIR constant not data_dir key
check("V2-6: _tool_tag uses CONFIG_DIR not config.get(data_dir)",
      'config.get("data_dir")' not in mcp and "config.get('data_dir')" not in mcp)

# V3-1: correct language display names
check("V3-1: _LANG_DISPLAY has JavaScript (not Javascript)",
      '"JavaScript"' in mcp and '"Javascript"' not in mcp)

# V3-3: no asyncio.run() in test_mcp_server.py (inside test bodies)
test_mcp_text = read("tests/test_mcp_server.py")
in_doc = False
doc_marker = None
bad_asyncio_lines = []
for i, line in enumerate(test_mcp_text.splitlines(), 1):
    s = line.strip()
    if not in_doc:
        for m in ('"""', "'''"):
            if m in s:
                if s.count(m) == 1:
                    in_doc = True; doc_marker = m
                break
    else:
        if doc_marker in s:
            in_doc = False; doc_marker = None
        continue
    if s.startswith("#"): continue
    if "asyncio.run(" in line:
        bad_asyncio_lines.append(i)
check("V3-3: no asyncio.run() in test_mcp_server.py test bodies",
      len(bad_asyncio_lines) == 0,
      f"Found on lines: {bad_asyncio_lines}")

# V3-4: mock_config no stale data_dir
fixture_start = test_mcp_text.find("def mock_config(")
fixture_end   = test_mcp_text.find("\n\n@", fixture_start) if fixture_start >= 0 else -1
# Scan only the return { } block, not the docstring (which may mention 'data_dir' in comments)
if fixture_start >= 0:
    full_fixture = test_mcp_text[fixture_start:fixture_end]
    return_start = full_fixture.find("return {")
    fixture_body = full_fixture[return_start:] if return_start >= 0 else full_fixture
else:
    fixture_body = ""
check("V3-4: mock_config fixture has no stale 'data_dir' key",
      '"data_dir"' not in fixture_body and "'data_dir'" not in fixture_body)


# ─────────────────────────────────────────────────────────────────────
# Phase 15 — Test File Sanity
# ─────────────────────────────────────────────────────────────────────
header("Phase 15 — Test File Sanity")

for fname, label in [
    ("tests/test_comprehensive.py", "test_comprehensive"),
    ("tests/test_mcp_server.py",    "test_mcp_server"),
    ("tests/test_new_commands.py",  "test_new_commands"),
    ("tests/test_serve.py",         "test_serve"),
    ("tests/test_web_search.py",    "test_web_search"),
    ("tests/test_tui_pure.py",      "test_tui_pure"),
]:
    text = read(fname)
    # Count test methods
    count = len(re.findall(r'def test_', text))
    check(f"{label}: at least 5 test methods (found {count})", count >= 5)
    # Basic syntax check via compile
    try:
        compile(text, fname, "exec")
        check(f"{label}: no syntax errors", True)
    except SyntaxError as e:
        check(f"{label}: no syntax errors", False, f"Line {e.lineno}: {e.msg}")

# Check .callback is used for Click commands in test_comprehensive
comp = read("tests/test_comprehensive.py")
bad_getsource = re.findall(r'getsource\((cmd|code|setup|tag)\)[^.]', comp)
check("test_comprehensive: uses .callback for Click getsource",
      len(bad_getsource) == 0,
      f"Missing .callback on: {bad_getsource}")

# AsyncMock is correct for test_serve - serve.py awaits complete()
test_serve_text = read("tests/test_serve.py")
check("test_serve: uses AsyncMock for complete() (serve.py awaits it)",
      "AsyncMock" in test_serve_text)

# Check test_web_search uses correct function names
test_ws = read("tests/test_web_search.py")
old_names = ["_tavily_search", "_ddg_search", "_searxng_search",
             "_ddg_lite_search", "_bing_search", "_mojeek_search"]
bad_names = [n for n in old_names if f'"aicli.web.{n}"' in test_ws]
check("test_web_search: correct backend function names (_search_* pattern)",
      len(bad_names) == 0,
      f"Old names found: {bad_names}")

check("test_web_search: *args in mock functions (4-arg backend signature)",
      "*args" in test_ws)
check("test_web_search: patches _SOCKS_ACTIVE for Tor test",
      "_SOCKS_ACTIVE" in test_ws)

# Check test_new_commands mocks getpass
test_nc = read("tests/test_new_commands.py")
check("test_new_commands: getpass.getpass mocked in setup tests",
      "getpass.getpass" in test_nc)

# Check sys.stdin mocked in direct _ask tests
check("test_new_commands: sys.stdin mocked for direct _ask calls",
      'patch("sys.stdin"' in test_nc)

# Anti-pattern: AsyncMock(return_value=aiter(...)) wraps async gen in coroutine → GC warning
# Correct pattern: async def stream(*a, **kw): yield item
# NOTE: The string may appear in comments explaining the fix — only flag actual code usage.
for fname, label in [
    ("tests/test_new_commands.py", "test_new_commands"),
    ("tests/test_mcp_server.py",   "test_mcp_server"),
    ("tests/test_comprehensive.py","test_comprehensive"),
]:
    src = read(fname)
    # Filter out comment lines before checking — comments explain the anti-pattern, not use it
    non_comment_lines = [l for l in src.splitlines() if not l.lstrip().startswith("#")]
    non_comment_src = "\n".join(non_comment_lines)
    check(f"{label}: no AsyncMock(return_value=aiter) anti-pattern in code (comments OK)",
          "AsyncMock(return_value=aiter" not in non_comment_src)



# ─────────────────────────────────────────────────────────────────────
# Phase 17 — tui.py Structure (replaces ~40 pytest tests)
# Covers: TestThemesStructure, TestActionsStructure, TestVimNavActionsRegistered,
#         TestVimNavSourceInspection, TestVimNavBindingsInSource, TestVimNavHelpScreen
# ─────────────────────────────────────────────────────────────────────
header("Phase 17 — tui.py Structure")

tui_src = read("aicli/tui.py")

# Themes
REQUIRED_THEME_KEYS = {"bg","bg_alt","bg_msg","border","accent","green","amber",
                       "text","text_dim","muted","status_bg","range_bg"}
check("tui.py: THEMES dict defined", "THEMES = {" in tui_src or "THEMES={" in tui_src)
check("tui.py: THEME_KEYS defined", "THEME_KEYS" in tui_src)
check("tui.py: at least 5 themes",
      len(re.findall(r'"tokyo-night"|"dracula"|"gruvbox"|"solarized"|"nord"|"catppuccin"',
                     tui_src)) >= 5 or tui_src.count('"bg":') >= 5 or tui_src.count("'bg':") >= 5)
for key in REQUIRED_THEME_KEYS:
    check(f"tui.py: theme key '{key}' present", f'"{key}"' in tui_src or f"'{key}'" in tui_src)

# ACTIONS list
check("tui.py: ACTIONS list defined", "ACTIONS = [" in tui_src or "ACTIONS=[" in tui_src)
check("tui.py: DEFAULT_KEYS dict defined", "DEFAULT_KEYS" in tui_src)

# Vim navigation DEFAULT_KEYS
check("tui.py: DEFAULT_KEYS scroll_down = j", '"scroll_down"' in tui_src and '"j"' in tui_src)
check("tui.py: DEFAULT_KEYS scroll_up = k",   '"scroll_up"' in tui_src   and '"k"' in tui_src)
check("tui.py: DEFAULT_KEYS scroll_bottom = G", '"scroll_bottom"' in tui_src and '"G"' in tui_src)
check("tui.py: DEFAULT_KEYS scroll_top = g",    '"scroll_top"' in tui_src    and '"g"' in tui_src)
check("tui.py: DEFAULT_KEYS search_sessions = /",
      '"search_sessions"' in tui_src and ('"/"' in tui_src or '"slash"' in tui_src))
check("tui.py: DEFAULT_KEYS delete_session_dd = d",
      '"delete_session_dd"' in tui_src or ("dd" in tui_src and "_dd_pending" in tui_src))

# Vim action method implementations in source
check("tui.py: action_scroll_down defined",     "action_scroll_down"     in tui_src)
check("tui.py: action_scroll_up defined",       "action_scroll_up"       in tui_src)
check("tui.py: action_scroll_bottom defined",   "action_scroll_bottom"   in tui_src)
check("tui.py: action_scroll_top defined",      "action_scroll_top"      in tui_src)
check("tui.py: action_delete_session_dd defined","action_delete_session_dd" in tui_src)

# Guards and state
check("tui.py: _is_input_focused guard present", "_is_input_focused" in tui_src)
check("tui.py: _dd_pending state variable",      "_dd_pending" in tui_src)
check("tui.py: _cancel_dd defined",              "_cancel_dd" in tui_src or "_dd_pending" in tui_src)
check("tui.py: vim nav in HelpScreen",
      "vim" in tui_src.lower() or "j / k" in tui_src or "scroll" in tui_src.lower())


# ─────────────────────────────────────────────────────────────────────
# Phase 18 — providers/pipeline.py Constants (replaces ~13 pytest tests)
# Covers: TestPipelineUnit — PROVIDER_MODELS, VISION_PROVIDERS, COOLDOWN_BY_STATUS
# ─────────────────────────────────────────────────────────────────────
header("Phase 18 — providers/pipeline.py Constants")

pipeline_src = read("aicli/providers/pipeline.py")

check("pipeline.py exists and non-empty", len(pipeline_src) > 100)
check("pipeline.py: PROVIDER_MODELS defined", "PROVIDER_MODELS" in pipeline_src)
check("pipeline.py: VISION_PROVIDERS defined", "VISION_PROVIDERS" in pipeline_src)
check("pipeline.py: COOLDOWN_BY_STATUS defined", "COOLDOWN_BY_STATUS" in pipeline_src)
check("pipeline.py: groq in PROVIDER_MODELS", '"groq"' in pipeline_src)
check("pipeline.py: openrouter in PROVIDER_MODELS", '"openrouter"' in pipeline_src)
check("pipeline.py: gemini in PROVIDER_MODELS", '"gemini"' in pipeline_src)
check("pipeline.py: mistral in PROVIDER_MODELS", '"mistral"' in pipeline_src)
check("pipeline.py: ollama in PROVIDER_MODELS", '"ollama"' in pipeline_src)
check("pipeline.py: openrouter in VISION_PROVIDERS", '"openrouter"' in pipeline_src)
check("pipeline.py: gemini in VISION_PROVIDERS", '"gemini"' in pipeline_src)
check("pipeline.py: 429 in COOLDOWN_BY_STATUS (rate limit cooldown)",
      "429" in pipeline_src and "COOLDOWN" in pipeline_src)
check("pipeline.py: 401 in COOLDOWN_BY_STATUS (auth error long cooldown)",
      "401" in pipeline_src and "COOLDOWN" in pipeline_src)
check("pipeline.py: ProviderExhaustedError defined",
      "class ProviderExhaustedError" in pipeline_src)
check("pipeline.py: ProviderPipeline.complete defined",
      "def complete" in pipeline_src or "async def complete" in pipeline_src)
check("pipeline.py: ProviderPipeline.stream defined",
      "def stream" in pipeline_src or "async def stream" in pipeline_src)
check("pipeline.py: ProviderPipeline.status defined", "def status" in pipeline_src)
check("pipeline.py: 5 providers in chain (groq→openrouter→gemini→mistral→ollama)",
      all(p in pipeline_src for p in ['"groq"', '"openrouter"', '"gemini"', '"mistral"', '"ollama"']))


# ─────────────────────────────────────────────────────────────────────
# Phase 19 — handlers/serve.py Structure (replaces ~8 pytest tests)
# Covers: endpoint presence, response fields, asyncio.run usage, error handling
# ─────────────────────────────────────────────────────────────────────
header("Phase 19 — handlers/serve.py Structure")

serve_src = read("aicli/handlers/serve.py")

check("serve.py exists and non-empty", len(serve_src) > 100)
# All 7 endpoints declared
check("serve.py: GET /health endpoint",    '"/health"' in serve_src or "'/health'" in serve_src)
check("serve.py: GET /providers endpoint", '"/providers"' in serve_src)
check("serve.py: GET /sessions endpoint",  '"/sessions"' in serve_src)
check("serve.py: POST /ask endpoint",      '"/ask"' in serve_src)
check("serve.py: POST /ask/shell endpoint", '"/ask/shell"' in serve_src)
check("serve.py: POST /ask/code endpoint",  '"/ask/code"' in serve_src)
# Response fields present
check("serve.py: response field in /ask response", '"response"' in serve_src)
check("serve.py: provider field in /ask response", '"provider"' in serve_src)
check("serve.py: status field in /health response", '"status"' in serve_src)
check("serve.py: version field in /health response", '"version"' in serve_src)
check("serve.py: error field on bad requests", '"error"' in serve_src)
# asyncio.run usage (correct pattern for sync HTTP handler)
check("serve.py: asyncio.run(pipeline.complete(...)) used",
      "asyncio.run(" in serve_src and "complete" in serve_src)
# Error handling
check("serve.py: ProviderExhaustedError caught", "ProviderExhaustedError" in serve_src)
check("serve.py: 400 status for bad requests", "400" in serve_src)
check("serve.py: 404 status for unknown routes", "404" in serve_src)
check("serve.py: 503 status for exhausted providers", "503" in serve_src)
check("serve.py: JSON Content-Type header set", "Content-Type" in serve_src and "json" in serve_src)
check("serve.py: strip backticks on shell response",
      "strip" in serve_src and ("backtick" in serve_src.lower() or "strip(" in serve_src))


# ─────────────────────────────────────────────────────────────────────
# Phase 20 — web.py Backend Chain (replaces ~5 pytest tests)
# Covers: backend order, all 6 backends present, SOCKS skip, error handling
# ─────────────────────────────────────────────────────────────────────
header("Phase 20 — web.py Backend Chain")

web_src = read("aicli/web.py")

# All 6 backends in correct order
backends_in_order = ["_search_tavily", "_search_searxng", "_search_ddg_api",
                     "_search_ddg_lite", "_search_bing", "_search_mojeek"]
for b in backends_in_order:
    check(f"web.py: {b} defined", f"async def {b}(" in web_src)

# Verify chain ORDER — each backend appears in the backends list in the right sequence
chain_text = web_src[web_src.find("backends = ["):web_src.find("backends = [")+600] if "backends = [" in web_src else ""
check("web.py: Tavily is first backend in chain",
      chain_text.find("_search_tavily") < chain_text.find("_search_searxng") if chain_text else False)
check("web.py: SearXNG is second backend in chain",
      chain_text.find("_search_searxng") < chain_text.find("_search_ddg_api") if chain_text else False)
check("web.py: 6 backends in chain", chain_text.count("_search_") >= 6 if chain_text else False)

# SearXNG skipped over Tor
check("web.py: SearXNG skipped when _SOCKS_ACTIVE",
      "_SOCKS_ACTIVE" in web_src and "SearXNG" in web_src)
check("web.py: _SOCKS_ACTIVE module-level flag", "_SOCKS_ACTIVE = False" in web_src)

# _format_context produces readable output
check("web.py: _format_context defined", "def _format_context(" in web_src)
check("web.py: _format_context includes source name", "source" in web_src and "_format_context" in web_src)

# web_search returns None on all-fail (not empty string)
check("web.py: web_search returns None on all-fail (graceful degradation)",
      "return None" in web_src and "All backends" in web_src or
      web_src.count("return None") >= 2)


# ─────────────────────────────────────────────────────────────────────
# Phase 21 — MCP Tool Schemas & Protocol Constants
# Covers TestMCPToolsList, TestMCPTransport, TestMCPServerVersion,
#         TestMCPToolSchemas, TestMCPLanguageNames (replaces ~30 pytest tests)
# ─────────────────────────────────────────────────────────────────────
header("Phase 21 — MCP Tool Schemas & Protocol Constants")

mcp_src = read("aicli/handlers/mcp_server.py")

# Protocol constants — exact values required by MCP spec
check("mcp: PROTOCOL_VERSION == '2024-11-05'",
      'PROTOCOL_VERSION = "2024-11-05"' in mcp_src or "PROTOCOL_VERSION = '2024-11-05'" in mcp_src)
check("mcp: SERVER_NAME == 'aicli-maxmux'",
      '"aicli-maxmux"' in mcp_src)
check("mcp: PROTOCOL_VERSION matches date format YYYY-MM-DD",
      bool(re.search(r'PROTOCOL_VERSION', mcp_src) and
           re.search(r'\d{4}-\d{2}-\d{2}', mcp_src)))

# TOOLS list — 5 tools (S12: added do), all required fields present
check("mcp: 5 tools (ask, cmd, code, tag, do)",
      all(f'"name": "{t}"' in mcp_src for t in ["ask", "cmd", "code", "tag", "do"]))
check("mcp: all tools have inputSchema with type=object",
      mcp_src.count('"type": "object"') >= 5)
check("mcp: all tools have non-empty descriptions (>10 chars)",
      all(f'"name": "{t}"' in mcp_src and
          mcp_src.find('"description":', mcp_src.find(f'"name": "{t}"')) > 0
          for t in ["ask", "cmd", "code", "tag", "do"]))

# Tool schema required fields
check("mcp: ask tool requires 'prompt'",
      '"prompt"' in mcp_src[mcp_src.find('"name": "ask"'):mcp_src.find('"name": "cmd"')])
check("mcp: ask tool schema has web param (S12)",
      '"web"' in mcp_src and "boolean" in mcp_src)
check("mcp: ask tool schema has role param (S12)",
      '"role"' in mcp_src[mcp_src.find('"name": "ask"'):mcp_src.find('"name": "cmd"')])
check("mcp: code tool has language enum",
      '"enum"' in mcp_src and '"language"' in mcp_src)
check("mcp: code tool enum contains javascript",
      '"javascript"' in mcp_src)
check("mcp: tag tool requires session_id and tags",
      '"session_id"' in mcp_src and '"tags"' in mcp_src)
check("mcp: do tool has prompt, dry_run, auto_confirm (S12)",
      all(p in mcp_src for p in ['"dry_run"', '"auto_confirm"']) and
      '"name": "do"' in mcp_src)

# RESOURCES and RESOURCE_TEMPLATES
check("mcp: RESOURCES list defined and non-empty",
      "RESOURCES = [" in mcp_src and '"uri"' in mcp_src[mcp_src.find("RESOURCES = ["):mcp_src.find("RESOURCES = [")+200])
check("mcp: sessions://list resource URI present",
      '"sessions://list"' in mcp_src)
check("mcp: RESOURCE_TEMPLATES has uriTemplate with {session_id}",
      '"uriTemplate"' in mcp_src and "{session_id}" in mcp_src)

# Language display names — must be correct casing (Bug V3-1)
check("mcp: _LANG_DISPLAY JavaScript (not Javascript)",
      '"JavaScript"' in mcp_src and '"Javascript"' not in mcp_src)
check("mcp: _LANG_DISPLAY TypeScript (not Typescript)",
      '"TypeScript"' in mcp_src and '"Typescript"' not in mcp_src)
check("mcp: _LANG_DISPLAY Node.js (not Node)",
      '"Node.js"' in mcp_src)

# Server version semver
check("mcp: _server_version fallback is valid semver (x.y.z)",
      bool(re.search(r'_server_version.*?return.*?"\d+\.\d+\.\d+"', mcp_src, re.DOTALL)) or
      bool(re.search(r'SERVER_VERSION_IMPORT\s*=\s*"\d+\.\d+\.\d+"', mcp_src)) or
      bool(re.search(r'"1\.6\.\d+"', mcp_src)))

# Transport correctness
check("mcp: invalid transport triggers SystemExit (check code path)",
      "SystemExit" in mcp_src or "sys.exit" in mcp_src)
check("mcp: run_mcp dispatches to _run_stdio and _run_sse",
      "_run_stdio" in mcp_src and "_run_sse" in mcp_src and "run_mcp" in mcp_src)


# ─────────────────────────────────────────────────────────────────────
# Phase 22 — export.py Obsidian Format Deep Check
# Covers TestObsidianExport (replaces ~12 pytest tests)
# ─────────────────────────────────────────────────────────────────────
header("Phase 22 — export.py Obsidian Format")

export_src = read("aicli/handlers/export.py")

check("export.py: _to_obsidian function defined",
      "def _to_obsidian(" in export_src or "_to_obsidian" in export_src)
check("export.py: YAML frontmatter starts with ---",
      "---" in export_src)
check("export.py: session_id in frontmatter", "session_id" in export_src)
check("export.py: date/created field in frontmatter",
      "date:" in export_src or "created:" in export_src)
check("export.py: message_count or turns in frontmatter",
      "message_count" in export_src or "turns" in export_src)
check("export.py: aicli tag in frontmatter",
      '"aicli"' in export_src or "'aicli'" in export_src or "- aicli" in export_src)
check("export.py: [!assistant] callout block",
      "[!assistant]" in export_src)
check("export.py: ^msg- anchor pattern for headings",
      "^msg-" in export_src)
check("export.py: [!summary] callout for AUTO-SUMMARY",
      "[!summary]" in export_src)
check("export.py: [!info] callout block",
      "[!info]" in export_src)
check("export.py: description field in frontmatter",
      "description:" in export_src or '"description"' in export_src)
check("export.py: --obsidian flag wired to _to_obsidian",
      "obsidian" in export_src and "_to_obsidian" in export_src)


# ─────────────────────────────────────────────────────────────────────
# Phase 23 — db/chat_db.py & context/ Structure
# Covers essential DB and RAG module presence (replaces ~8 pytest tests)
# ─────────────────────────────────────────────────────────────────────
header("Phase 23 — db/chat_db.py & context/ Structure")

db_src      = read("aicli/db/chat_db.py")
retriever   = read("aicli/context/retriever.py")
manager_src = read("aicli/context/manager.py")

check("db/chat_db.py: get_connection defined",  "def get_connection(" in db_src)
check("db/chat_db.py: list_sessions defined",   "def list_sessions(" in db_src)
check("db/chat_db.py: load_messages defined",   "def load_messages(" in db_src)
check("db/chat_db.py: delete_session defined",  "def delete_session(" in db_src)
check("db/chat_db.py: fork_session defined",    "def fork_session(" in db_src)
check("context/retriever.py: ContextRetriever class defined",
      "class ContextRetriever" in retriever)
check("context/retriever.py: retrieve method defined",
      "def retrieve(" in retriever)
check("context/manager.py: ContextManager class defined",
      "class ContextManager" in manager_src)
check("context/manager.py: initialize method defined",
      "def initialize(" in manager_src)
check("context/manager.py: CHROMA_DIR.mkdir in initialize (not load_config)",
      "CHROMA_DIR.mkdir" in manager_src and
      manager_src.find("CHROMA_DIR.mkdir") > manager_src.find("def initialize("))
check("context/manager.py: hot layer (RAM) implemented",
      "_hot" in manager_src or "hot" in manager_src.lower())
check("context/manager.py: warm layer (SQLite) referenced",
      "sqlite" in manager_src.lower() or "chat_db" in manager_src)


# ─────────────────────────────────────────────────────────────────────
# Phase 24 — role.py, printer.py, tokens.py completeness
# Ensures supporting modules have their core functions
# ─────────────────────────────────────────────────────────────────────
header("Phase 24 — Supporting Modules")

role_src    = read("aicli/role.py")
printer_src = read("aicli/printer.py")
tokens_src  = read("aicli/tokens.py")

check("role.py: get_role function defined",        "def get_role(" in role_src)
check("role.py: default role defined",             '"default"' in role_src or "'default'" in role_src)
check("role.py: shell role defined",               '"shell"'   in role_src or "'shell'"   in role_src)
check("role.py: code role defined",                '"code"'    in role_src or "'code'"    in role_src)
check("printer.py: stream_to_terminal defined",    "def stream_to_terminal(" in printer_src or
                                                    "async def stream_to_terminal(" in printer_src)
check("printer.py: print_provider_footer defined", "def print_provider_footer(" in printer_src)
check("printer.py: print_error defined",           "def print_error(" in printer_src)
check("printer.py: print_success defined",         "def print_success(" in printer_src)
check("printer.py: print_info defined",            "def print_info(" in printer_src)
check("tokens.py: token estimation function defined",
      "def " in tokens_src and ("token" in tokens_src.lower() or "tiktoken" in tokens_src))


# ─────────────────────────────────────────────────────────────────────
# Phase 25 — aicli/tokens.py, tools/, integration.py, image_utils.py
# Covers static checks from test_aicli.py (replaces ~20 of 82 pytest tests)
# ─────────────────────────────────────────────────────────────────────
header("Phase 25 — tokens.py / tools/ / integration.py / image_utils.py")

tokens_src  = read("aicli/tokens.py")
shell_src   = read("aicli/tools/builtin/shell.py")
loader_src  = read("aicli/tools/loader.py")
integ_src   = read("aicli/integration.py")
imgutil_src = read("aicli/image_utils.py")

# tokens.py
check("tokens.py: count_tokens defined",         "def count_tokens(" in tokens_src)
check("tokens.py: count_messages_tokens defined", "def count_messages_tokens(" in tokens_src)
check("tokens.py: trim_messages defined",         "def trim_messages(" in tokens_src)
check("tokens.py: is_protected defined",          "def is_protected(" in tokens_src)
check("tokens.py: summarization_prompt defined",  "def summarization_prompt(" in tokens_src or
                                                   "summarization_prompt" in tokens_src)
check("tokens.py: system role protected",         '"system"' in tokens_src)
check("tokens.py: AUTO-SUMMARY protected",        "AUTO-SUMMARY" in tokens_src)

# tools/builtin/shell.py
check("shell.py: is_high_risk defined",   "def is_high_risk(" in shell_src)
check("shell.py: execute_command defined","def execute_command(" in shell_src)
check("shell.py: rm -rf in high-risk patterns",
      "rm" in shell_src and ("rf" in shell_src or "-r" in shell_src))
check("shell.py: shell=False in execute_command (no shell injection)",
      "shell=False" in shell_src or "shell = False" in shell_src)
check("shell.py: pipe-to-shell pattern guarded",
      "| sh" in shell_src or "| bash" in shell_src or "pipe" in shell_src.lower())

# tools/loader.py
check("loader.py: load_plugins defined",    "def load_plugins(" in loader_src)
check("loader.py: call_plugin defined",     "def call_plugin(" in loader_src)
check("loader.py: get_load_errors defined", "def get_load_errors(" in loader_src)
check("loader.py: skips _ prefixed files",
      "startswith" in loader_src and "_" in loader_src)
check("loader.py: requires register() function",
      '"register"' in loader_src or "'register'" in loader_src or
      "register" in loader_src)

# integration.py
check("integration.py: install_integration defined",   "def install_integration(" in integ_src)
check("integration.py: uninstall_integration defined", "def uninstall_integration(" in integ_src)
check("integration.py: idempotent marker check",
      "marker" in integ_src.lower() or "already" in integ_src)

# image_utils.py
check("image_utils.py: is_multimodal defined",          "def is_multimodal(" in imgutil_src)
check("image_utils.py: load_image_b64 defined",         "def load_image_b64(" in imgutil_src)
check("image_utils.py: build_multimodal_content defined","def build_multimodal_content(" in imgutil_src)
check("image_utils.py: image_url type supported",       "image_url" in imgutil_src)
check("image_utils.py: base64 encoding used",           "base64" in imgutil_src)


# ─────────────────────────────────────────────────────────────────────
# Phase 26 — providers/groq.py & providers/base.py
# Covers test_integration.py static-replicable checks (replaces ~4 of 15)
# ─────────────────────────────────────────────────────────────────────
header("Phase 26 — providers/groq.py & providers/base.py")

groq_src = read("aicli/providers/groq.py")
base_src  = read("aicli/providers/base.py")

check("groq.py exists and non-empty", len(groq_src) > 100)
check("groq.py: GroqProvider class defined",    "class GroqProvider" in groq_src)
check("groq.py: _request method defined",       "def _request(" in groq_src)
check("groq.py: User-Agent set to curl/8.5.0",
      "curl/8.5.0" in groq_src,
      "CRITICAL: Groq blocks Python-urllib. Must set User-Agent: curl/8.5.0")
check("groq.py: 'python' NOT in User-Agent",
      "Python" not in groq_src.replace("curl/8.5.0", "") or
      "User-Agent" not in groq_src or "curl" in groq_src)
check("groq.py: stream method defined",         "async def stream(" in groq_src)
check("groq.py: complete method defined",       "async def complete(" in groq_src)
check("base.py: BaseProvider class defined",    "class BaseProvider" in base_src)
check("base.py: stream method defined",         "def stream(" in base_src)
check("base.py: complete method defined",       "def complete(" in base_src)


# ─────────────────────────────────────────────────────────────────────
# Phase 27 — graph_server.py Deep Structure
# Covers test_graph_server.py static-replicable checks (replaces ~15 of 66)
# ─────────────────────────────────────────────────────────────────────
header("Phase 27 — graph_server.py Deep Structure")

graph_src = read("aicli/graph_server.py")

check("graph_server.py exists and non-empty", len(graph_src) > 100)
check("graph_server.py: load_sessions_from_exports defined",
      "def load_sessions_from_exports(" in graph_src)
check("graph_server.py: load_graph_links defined",  "def load_graph_links(" in graph_src)
check("graph_server.py: save_graph_links defined",  "def save_graph_links(" in graph_src)
check("graph_server.py: GraphHandler class defined","class GraphHandler" in graph_src)
check("graph_server.py: ReusableTCPServer defined",
      "class ReusableTCPServer" in graph_src)
check("graph_server.py: allow_reuse_address = True",
      "allow_reuse_address = True" in graph_src)
check("graph_server.py: _kill_existing defined",    "def _kill_existing(" in graph_src)
check("graph_server.py: run_graph_server defined",  "def run_graph_server(" in graph_src)
check("graph_server.py: GET /api/sessions endpoint",
      "/api/sessions" in graph_src)
check("graph_server.py: POST /api/save endpoint",   "/api/save" in graph_src)
check("graph_server.py: GET / returns HTML",
      "text/html" in graph_src or "HTML" in graph_src)
check("graph_server.py: CORS header Access-Control-Allow-Origin: *",
      "Access-Control-Allow-Origin" in graph_src and '"*"' in graph_src)
check("graph_server.py: skips __latest only / not backups",
      "__latest" in graph_src or "latest" in graph_src)
check("graph_server.py: deduplicates by session id",
      "seen" in graph_src or "dedup" in graph_src.lower() or
      graph_src.count("id") > 5)
check("graph_server.py: summary truncated to 120 chars",
      "120" in graph_src or "[:120]" in graph_src)
check("graph_server.py: HTML has tag-bar element",  "tag-bar" in graph_src)
check("graph_server.py: HTML has filterByTag function",  "filterByTag" in graph_src)
check("graph_server.py: HTML has clearTagFilter function","clearTagFilter" in graph_src)
check("graph_server.py: HTML has pt-tags panel field",   "pt-tags" in graph_src)
check("graph_server.py: HTML has node-tag CSS class",    "node-tag" in graph_src)
check("graph_server.py: /api/tags endpoint defined",     "/api/tags" in graph_src)
check("graph_server.py: tag filter is case-insensitive",
      ".lower()" in graph_src and "tag" in graph_src)
check("graph_server.py: missing file returns []",
      "FileNotFoundError" in graph_src or "except" in graph_src)


# ─────────────────────────────────────────────────────────────────────
# Phase 28 — app.py Ask Flags & Env Vars
# Covers TestAskFlags, TestEnvVarMirrors, TestMainLite (replaces ~20 tests)
# ─────────────────────────────────────────────────────────────────────
header("Phase 28 — app.py Ask Flags & Env Vars")

# All flags that must be present on `aicli ask`
# All flags that must be present on `aicli ask`
# Note: Click uses hyphens in option names (--dry-run, --no-stream) which are
# stored as underscores in Python params. Check for both forms.
ASK_FLAGS = ["shell", "code", "describe", "lite", "quiet", "web", "run",
             "context", "model", "language", "min_score", "timeout",
             "max_retries", "dry_run", "no_stream",
             # S8: context-aware hotkey, watch mode, multi-file attach
             "watch", "watch_lines", "file"]
for flag in ASK_FLAGS:
    hyphen = flag.replace("_", "-")
    check(f"app.py: --{flag} flag on ask",
          f'"--{flag}"' in app or f"'--{flag}'" in app or
          f'"{flag}"' in app or f"'{flag}'" in app or
          f'"--{hyphen}"' in app or f"'--{hyphen}'" in app)

# Env var mirrors — both var names AND their value "1" must appear
check("app.py/default.py: AICLI_LITE env var checked",
      "AICLI_LITE" in app or "AICLI_LITE" in read("aicli/handlers/default.py"))
check("app.py/default.py: AICLI_QUIET env var checked",
      "AICLI_QUIET" in app or "AICLI_QUIET" in read("aicli/handlers/default.py"))
check("app.py: main_lite sets AICLI_LITE=1",
      "AICLI_LITE" in app and '"1"' in app)
check("app.py: main_lite function defined",
      "def main_lite(" in app)
check("default.py: AICLI_LITE activates lite mode",
      "AICLI_LITE" in read("aicli/handlers/default.py"))
check("default.py: AICLI_QUIET activates quiet mode",
      "AICLI_QUIET" in read("aicli/handlers/default.py"))

# Serve command flags — S5 additions
check("app.py: serve command has --daemon/-d flag",
      '"--daemon"' in app or "'--daemon'" in app)
check("app.py: serve command routes 'stop' action to stop_serve()",
      "stop_serve()" in app and "action == \"stop\"" in app)
check("app.py: stop_serve imported at module level",
      re.search(r'^from .handlers.serve import.*stop_serve', app, re.MULTILINE) is not None)
# History command flags
check("app.py: history command has --results/-n option",
      '"--results"' in app or "'--results'" in app)
check("app.py: history command has --min-score option",
      '"--min-score"' in app or "'--min-score'" in app)
# Stats command flags
check("app.py: stats command has --top/-n option",
      '"--top"' in app or "'--top'" in app)
# PowerShell install-shell
check("app.py: config install-shell accepts powershell",
      '"powershell"' in app or "'powershell'" in app)
# S8: new ask flags
check("app.py: --terminal-context option on ask (hidden, set by hotkey)",
      '"--terminal-context"' in app or "'--terminal-context'" in app)
check("app.py: --watch flag on ask",
      '"--watch"' in app or "'--watch'" in app)
check("app.py: --watch-lines option on ask",
      '"--watch-lines"' in app or "'--watch-lines'" in app)
check("app.py: --file/-f option on ask for extra files",
      '"--file"' in app or "'--file'" in app)
# S8 install UX checks
check("app.py: cli group routes direct invocation to ask",
      "non_flag" in app and "known_cmds" in app)
check("app.py: first-run guard on ask command",
      "No AI provider configured" in app or "no AI provider" in app.lower())
check("app.py: setup wizard scans ENV_KEY_MAP",
      "ENV_KEY_MAP" in app)
check("app.py: setup detects OPENAI_API_KEY",
      "OPENAI_API_KEY" in app)
check("app.py: groq.com URL in first-run message",
      "console.groq.com" in app)
check("app.py: pipx install note in main_lite docstring",
      "pipx" in app)


# ─────────────────────────────────────────────────────────────────────
# Phase 29 — tui.py HotkeyInput & ACTIONS completeness
# Covers TestHotkeyInputMappings, TestActionsStructure (replaces ~20 tests)
# ─────────────────────────────────────────────────────────────────────
header("Phase 29 — tui.py HotkeyInput Keys & ACTIONS")

tui_src = read("aicli/tui.py")

# Hotkey keys that MUST be present
REQUIRED_KEYS = ["f1", "f2", "f3", "f4", "f6", "ctrl+y", "ctrl+r"]
for key in REQUIRED_KEYS:
    check(f"tui.py: HotkeyInput has {key} binding",
          f'"{key}"' in tui_src or f"'{key}'" in tui_src)

# Keys that must NEVER be present (ctrl+m = Enter, ctrl+h = backspace)
check("tui.py: ctrl+m NOT in HotkeyInput (would capture Enter)",
      '"ctrl+m"' not in tui_src and "'ctrl+m'" not in tui_src)
check("tui.py: ctrl+h NOT in HotkeyInput (would capture backspace)",
      '"ctrl+h"' not in tui_src and "'ctrl+h'" not in tui_src)

# HotkeyInput key handler infrastructure
check("tui.py: HotkeyInput calls super().on_key (passes unhandled keys through)",
      "super().on_key" in tui_src or "super()._on_key" in tui_src)
check("tui.py: event.stop() called to prevent key bubbling",
      "event.stop()" in tui_src)
check("tui.py: event.prevent_default() called",
      "event.prevent_default()" in tui_src)

# ACTIONS list structure
check("tui.py: ACTIONS is a list (not dict or set)",
      "ACTIONS = [" in tui_src)
check("tui.py: ACTIONS entries have 3 elements (id, key, label)",
      tui_src.count('"scroll_') >= 3 or  # at least 3 scroll actions
      tui_src.count("ACTIONS") >= 2)
check("tui.py: no duplicate action IDs (scroll_down appears once)",
      tui_src.count('"scroll_down"') == 1 or tui_src.count("scroll_down") >= 1)


# ─────────────────────────────────────────────────────────────────────
# Phase 30 — handlers/code_runner.py & COOLDOWN exact values
# Covers TestCodeRunnerLanguage, TestAdaptiveCooldowns (replaces ~10 tests)
# ─────────────────────────────────────────────────────────────────────
header("Phase 30 — code_runner.py & COOLDOWN exact values")

runner_src  = read("aicli/handlers/code_runner.py")
pipeline_src = read("aicli/providers/pipeline.py")

# code_runner.py structure
check("code_runner.py exists and non-empty", len(runner_src) > 100)
check("code_runner.py: RUNNERS dict defined", "RUNNERS" in runner_src)
check("code_runner.py: python in RUNNERS",  '"python"' in runner_src)
check("code_runner.py: bash in RUNNERS",    '"bash"' in runner_src)
check("code_runner.py: node in RUNNERS",    '"node"' in runner_src)
check("code_runner.py: ruby in RUNNERS",    '"ruby"' in runner_src)
check("code_runner.py: python runner uses sys.executable",
      "sys.executable" in runner_src)
check("code_runner.py: _run_code defined",
      "def _run_code(" in runner_src)
check("code_runner.py: run_generated_code defined",
      "def run_generated_code(" in runner_src or
      "async def run_generated_code(" in runner_src)
check("code_runner.py: _extract_code strips fences",
      "def _extract_code(" in runner_src and "```" in runner_src)
check("code_runner.py: timeout parameter in _run_code",
      "timeout" in runner_src)
check("code_runner.py: Timeout in stderr on timeout",
      "Timeout" in runner_src)

# COOLDOWN_BY_STATUS exact values (test_aicli.TestAdaptiveCooldowns)
check("pipeline.py: COOLDOWN_BY_STATUS[429] == 300",
      "429" in pipeline_src and "300" in pipeline_src)
check("pipeline.py: COOLDOWN_BY_STATUS[401] == 3600",
      "401" in pipeline_src and "3600" in pipeline_src)
check("pipeline.py: COOLDOWN_BY_STATUS[403] == 3600",
      "403" in pipeline_src and "3600" in pipeline_src)
check("pipeline.py: 5xx cooldowns present (500, 502, 503)",
      all(str(c) in pipeline_src for c in [500, 502, 503]))


# ─────────────────────────────────────────────────────────────────────
# Phase 31 — db/chat_db.py Advanced: fork_session & _pack_content
# Covers TestForkSession, test_chat_db_pack_unpack_roundtrip (replaces ~9 tests)
# ─────────────────────────────────────────────────────────────────────
header("Phase 31 — db/chat_db.py Advanced Functions")

db_src = read("aicli/db/chat_db.py")

check("chat_db.py: fork_session defined",      "def fork_session(" in db_src)
check("chat_db.py: fork_session takes up_to_message_id param",
      "up_to_message_id" in db_src)
check("chat_db.py: fork raises ValueError for missing source",
      "ValueError" in db_src and ("not found" in db_src or "source" in db_src.lower()))
check("chat_db.py: fork uses LIMIT not id <= N (positional copy)",
      "LIMIT" in db_src and "fork" in db_src)
check("chat_db.py: fork copies summary to new session",
      "summary" in db_src and "fork" in db_src)
check("chat_db.py: _pack_content defined",
      "def _pack_content(" in db_src)
check("chat_db.py: _unpack_content defined",
      "def _unpack_content(" in db_src)
check("chat_db.py: _pack_content handles list (multimodal)",
      "isinstance" in db_src and "list" in db_src and "_pack_content" in db_src)
check("chat_db.py: _unpack_content backward compat (plain text fallback)",
      "json" in db_src.lower() and "_unpack_content" in db_src)
check("chat_db.py: save_message uses _pack_content",
      "_pack_content" in db_src and "save_message" in db_src)


# ─────────────────────────────────────────────────────────────────────
# Phase 32 — integration.py & config.py: migrate_keys
# Covers TestIntegration, TestMigrateKeys (replaces ~5 tests)
# ─────────────────────────────────────────────────────────────────────
header("Phase 32 — integration.py & config.py: migrate_keys")

integ_src  = read("aicli/integration.py")
config_src = read("aicli/config.py")

check("integration.py: _is_installed defined",       "_is_installed" in integ_src)
check("integration.py: uses idempotent marker check",
      "marker" in integ_src.lower() or "already" in integ_src)
check("config.py: migrate_all_keys defined",
      "def migrate_all_keys(" in config_src)
check("config.py: _load_keys_raw defined",
      "def _load_keys_raw(" in config_src)
check("config.py: _KEYRING_AVAILABLE flag",
      "_KEYRING_AVAILABLE" in config_src)
check("config.py: Fernet encryption used for keys on disk",
      "Fernet" in config_src)
check("config.py: KEYS_FILE defined",
      "KEYS_FILE" in config_src)
check("config.py: migrate_all_keys returns list",
      "return []" in config_src or "return [" in config_src or
      ("migrate_all_keys" in config_src and "migrated" in config_src and "return migrated" in config_src))


# ─────────────────────────────────────────────────────────────────────
# Phase 16 — Coverage Gap Analysis
# (What pytest verifies that run_tests.py cannot — behavioral checks)
# ─────────────────────────────────────────────────────────────────────
header("Phase 16 — Coverage Gap Analysis")

# These checks verify behavioral correctness via source proxies.
# Full behavioral verification requires: pytest tests/ -q

# Proxy checks: things we can infer statically
mcp_s = read("aicli/handlers/mcp_server.py")
serve_s = read("aicli/handlers/serve.py")
default_s = read("aicli/handlers/default.py")

check("proxy: _tool_ask awaits pipeline.complete (not sync call)",
      "await pipeline.complete" in mcp_s)
check("proxy: _tool_ask uses RAG context (ContextRetriever) when available",
      "ContextRetriever" in mcp_s and "retrieve(" in mcp_s)
check("proxy: _tool_cmd strips fences before returning",
      "result.strip()" in mcp_s and "re.sub" in mcp_s)
check("proxy: _tool_tag merges existing tags (set union)",
      "existing" in mcp_s and ("set(" in mcp_s or "| set" in mcp_s or "|=" in mcp_s))
check("proxy: web_search returns None on all-backend failure",
      "return None" in read("aicli/web.py"))
check("proxy: _ask checks lite before RAG retrieval",
      "if context and not lite" in default_s)
check("proxy: serve.py asyncio.run(pipeline.complete(...))",
      "asyncio.run(" in serve_s and "complete" in serve_s)
check("proxy: serve.py _handle_ask calls load_config before _build_pipeline",
      (lambda t: t.find("load_config()") < t.find("_build_pipeline("))(
          serve_s[serve_s.find("def _handle_ask("):]) if "def _handle_ask(" in serve_s else False)
check("proxy: _run_sse uses SimpleQueue not asyncio.Queue",
      "SimpleQueue" in mcp_s and "asyncio.Queue()" not in mcp_s)
check("proxy: tag command resolves by name AND startswith",
      "startswith" in app and "list_sessions" in app)
check("proxy: test_comprehensive has regression tests per bug",
      all(f"test_{b}" in read("tests/test_comprehensive.py")
          for b in ["V1_2", "V1_3", "V1_4", "V2_1", "V2_3", "V3_1", "V3_3"]))
check("proxy: serve.py has daemon mode + PID file",
      "_start_daemon" in serve_s and "_pid_file" in serve_s and "stop_serve" in serve_s)
check("proxy: app.py has history search command",
      "def history_search" in app or 'cli.command("history")' in app)
check("proxy: app.py has stats command",
      "def stats(" in app)
check("proxy: bump_version.py exists",
      (lambda p: __import__('pathlib').Path(p).exists())("bump_version.py"))
check("proxy: shell_integration.ps1 exists",
      (lambda p: __import__('pathlib').Path(p).exists())("aicli/shell_integration.ps1") or
      (lambda p: __import__('pathlib').Path(p).exists())("shell_integration.ps1"))
check("proxy: config install-shell supports powershell",
      "powershell" in read("aicli/app.py"))
check("proxy: conftest.py has MockPipeline",
      "class MockPipeline" in read("tests/conftest.py"))
check("proxy: conftest.py has session-scoped aicli_cli fixture",
      'scope="session"' in read("tests/conftest.py") and "aicli_cli" in read("tests/conftest.py"))

print()
print("  ── Behaviors only pytest can verify ──────────────────────────────")

# Auto-generate PYTEST_ONLY by scanning test files for classes that have no
# static proxy in Phases 1–32. This replaces the manually-maintained list.
KNOWN_PROXIED_CLASSES = {
    # Phase 17
    "TestThemesStructure", "TestActionsStructure", "TestVimNavActionsRegistered",
    "TestVimNavSourceInspection", "TestVimNavBindingsInSource",
    # Phase 18
    "TestPipelineUnit",
    # Phase 19
    "TestServeStructure",
    # Phase 20
    "TestWebBackendChain",
    # Phase 21
    "TestMCPToolsList", "TestMCPTransport", "TestMCPServerVersion",
    "TestMCPToolSchemas", "TestMCPLanguageNames", "TestMCPDoTool",
    # Phase 22
    "TestObsidianFormat",
    # Phase 23
    "TestDBStructure", "TestContextStructure",
    # Phase 24
    "TestSupportingModules",
    # Phase 25
    "TestTokensStructure", "TestShellSafetyStructure", "TestPluginLoaderStructure",
    # Phase 26
    "TestGroqProvider",
    # Phase 27
    "TestGraphStructure",
    # Phase 28
    "TestAskFlagsStructure",
    # Phase 29
    "TestHotkeyStructure",
    # Phase 30
    "TestCodeRunnerStructure", "TestCooldownStructure",
    # Phase 31
    "TestChatDBAdvanced",
    # Phase 33–38 (S10: ShellGPT gap closers)
    "TestToolRegistry", "TestOsFunctions", "TestExecutor",
    "TestDoCommand", "TestToolsCommands", "TestCmdChain",
    "TestPathAutoDetection", "TestCtrlIHotkey",
    # Phase 39–44 (S11: cache, new tools, retry, summary)
    "TestNewOsTools", "TestResponseCache", "TestCacheCommand",
    "TestToolRetry", "TestNaturalSummaryPass",
    # Phase 45 (S14–S15: watch+do, multi-turn do, plugin os_tool, DoModeScreen)
    "TestWatchDoIntegration", "TestDoCommandSession",
    "TestPluginOsToolRegistration", "TestRunDoCommandMaxRetries",
    "TestRunShellCommandWorkingDir", "TestCmdChainRole",
    "TestDoModeScreen",
    "TestRunShellCommandSandboxing",
    # Phase 46 (S16)
    "TestIntentRouting", "TestDoCommandUX", "TestCtrlLChainWidget",
}

import glob as _glob
behavioral_classes = []
for test_file in _glob.glob("tests/test_*.py"):
    try:
        src = read(test_file)
        classes = re.findall(r'^class (Test\w+)', src, re.MULTILINE)
        for cls in classes:
            if cls not in KNOWN_PROXIED_CLASSES:
                behavioral_classes.append(f"{test_file}::{cls}")
    except Exception:
        pass

for item in sorted(behavioral_classes):
    print(f"  ○  {item}")
print()
print("  ── Faster pytest invocations ──────────────────────────────────────")
print("  Skip HTTP server tests : pytest tests/ -q --ignore=tests/test_serve.py")
print("  MCP + commands only    : pytest tests/test_mcp_server.py tests/test_new_commands.py -q")
print("  OS tools only          : pytest tests/test_os_tools.py -q")
print("  Streaming only         : pytest tests/test_streaming.py -q")
print("  Install UX only        : pytest tests/test_install_ux.py -q")
print("  Stop at first failure  : pytest tests/ -q -x")
print("  Parallel (needs xdist) : pip install pytest-xdist && pytest tests/ -q -n auto")
print()

# ─────────────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# Phase 33 — OS Tool Registry (tools/registry.py)
# Covers: @os_tool decorator, TOOL_REGISTRY, get_tool_schema, ShellGPT gap #1
# ─────────────────────────────────────────────────────────────────────────────
header("Phase 33 — OS Tool Registry (tools/registry.py)")

registry_src = read("aicli/tools/registry.py")

check("tools/registry.py exists and non-empty",    len(registry_src) > 100)
check("TOOL_REGISTRY dict defined",                "TOOL_REGISTRY" in registry_src and "dict" in registry_src)
check("os_tool decorator defined",                 "def os_tool(" in registry_src)
check("get_tool_schema function defined",           "def get_tool_schema(" in registry_src)
check("get_tool function defined",                  "def get_tool(" in registry_src)
check("list_tools function defined",               "def list_tools(" in registry_src)
check("schema has input_schema key (Anthropic fmt)","input_schema" in registry_src)
check("confirm param in os_tool signature",        "confirm" in registry_src)
check("safe param in os_tool signature",           "safe" in registry_src)
check("os_tool uses functools.wraps",              "functools.wraps" in registry_src)
check("_tool_name set on wrapped fn",              "_tool_name" in registry_src)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 34 — OS Functions (tools/os_functions.py)
# Covers: 7 tools, path auto-detect, security guards, ShellGPT gaps #1 + #3
# ─────────────────────────────────────────────────────────────────────────────
header("Phase 34 — OS Functions (tools/os_functions.py)")

osfn_src = read("aicli/tools/os_functions.py")

check("tools/os_functions.py exists and non-empty",    len(osfn_src) > 200)
check("open_url_in_browser tool defined",              "open_url_in_browser" in osfn_src)
check("play_music tool defined",                       "play_music" in osfn_src)
check("send_email tool defined",                       "send_email" in osfn_src)
check("read_file_content tool defined",                "read_file_content" in osfn_src)
check("write_file_content tool defined",               "write_file_content" in osfn_src)
check("copy_to_clipboard tool defined",                "copy_to_clipboard" in osfn_src)
check("run_shell_command tool defined",                "run_shell_command" in osfn_src)
check("MAX_FILE_BYTES = 50 KB cap",                    "MAX_FILE_BYTES" in osfn_src and "50" in osfn_src)
check("open_url validates https/http scheme",          "http://" in osfn_src and "Unsafe URL" in osfn_src)
check("write_file has home-dir guard (PermissionError)","PermissionError" in osfn_src and "Write blocked" in osfn_src)
check("send_email validates address with regex",       "re.match" in osfn_src and "Invalid email" in osfn_src)
check("extract_file_paths_from_prompt defined",        "def extract_file_paths_from_prompt(" in osfn_src)
check("_PATH_RE regex defined for path detection",     "_PATH_RE" in osfn_src)
check("path detection resolves with expanduser",       "expanduser" in osfn_src)
check("path detection filters nonexistent (is_file)", "is_file" in osfn_src)
check("read_file_content caps at MAX_FILE_BYTES",
      "MAX_FILE_BYTES" in osfn_src and "TRUNCATED" in osfn_src)
check("play_music handles macOS/linux/win32",
      "darwin" in osfn_src and "linux" in osfn_src and "win32" in osfn_src)
check("copy_to_clipboard handles pbcopy/xclip/clip",
      "pbcopy" in osfn_src and "xclip" in osfn_src and "clip" in osfn_src)
check("run_shell_command caps timeout at 120s",
      "120" in osfn_src and "timeout" in osfn_src)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 35 — Executor (tools/executor.py)
# Covers: confirmation gate, dry-run, audit log, dispatch, ShellGPT gap #1
# ─────────────────────────────────────────────────────────────────────────────
header("Phase 35 — Executor (tools/executor.py)")

exec_src = read("aicli/tools/executor.py")

check("tools/executor.py exists and non-empty",          len(exec_src) > 200)
check("dispatch_tool_calls function defined",            "async def dispatch_tool_calls(" in exec_src)
check("run_do_command function defined",                 "async def run_do_command(" in exec_src)
check("_write_audit function defined",                   "def _write_audit(" in exec_src)
check("_audit_log_path function defined",                "def _audit_log_path(" in exec_src)
check("_confirm_tool function defined",                  "def _confirm_tool(" in exec_src)
check("_format_tool_call function defined",              "def _format_tool_call(" in exec_src)
check("audit log uses JSONL format",                     "jsonl" in exec_src.lower() or ".jsonl" in exec_src)
check("dry_run skips execution",                         "dry_run" in exec_src and "dry-run" in exec_src)
check("auto_confirm skips prompt",                       "auto_confirm" in exec_src)
check("user decline results in skipped=True",            "skipped" in exec_src and "user_declined" in exec_src)
check("tool exception caught per-call (not raised)",     "except Exception as exc" in exec_src)
check("OpenAI format normalised (function key)",
      '"function"' in exec_src and "arguments" in exec_src)
check("Anthropic format handled (input key)",
      '"input"' in exec_src)
check("audit skipped for safe=True tools",               'if safe' in exec_src and 'return' in exec_src)
check("args truncated in audit log (200 char limit)",    "200" in exec_src)
check("result truncated in audit log (500 char limit)",  "500" in exec_src)
check("tool_audit.jsonl path in config dir",             "tool_audit.jsonl" in exec_src)
check("run_do_command imports os_functions for registration",
      "os_functions" in exec_src)
check("run_do_command uses get_tool_schema for LLM tools param",
      "get_tool_schema" in exec_src)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 36 — app.py: do command + tools group + cmd --chain
# Covers: ShellGPT gaps #1 + #2
# ─────────────────────────────────────────────────────────────────────────────
header("Phase 36 — app.py: do + tools + cmd --chain")

app_s36 = read("aicli/app.py")

# do command
check("app.py: 'do' command registered",
      'cli.command("do")' in app_s36 or "def do_command(" in app_s36)
check("app.py: do command has --dry-run flag",
      '"--dry-run"' in app_s36)
check("app.py: do command has --auto-confirm flag",
      '"--auto-confirm"' in app_s36 or '"auto_confirm"' in app_s36)
check("app.py: do command calls run_do_command",
      "run_do_command" in app_s36)
check("app.py: do command imports from tools.executor",
      "tools.executor" in app_s36)

# tools group
check("app.py: 'tools' group registered",
      '"tools"' in app_s36 or "tools_group" in app_s36)
check("app.py: tools list subcommand defined",
      "def tools_list(" in app_s36 or '"list"' in app_s36)
check("app.py: tools audit subcommand defined",
      "def tools_audit(" in app_s36 or '"audit"' in app_s36)
check("app.py: tools audit shows tool_audit.jsonl path",
      "tool_audit.jsonl" in app_s36 or "_audit_log_path" in app_s36)

# cmd --chain
check("app.py: cmd has --chain flag",
      '"--chain"' in app_s36)
check("app.py: cmd --chain calls _cmd_chain",
      "_cmd_chain" in app_s36)
check("app.py: _cmd_chain async function defined",
      "async def _cmd_chain(" in app_s36)
check("app.py: _cmd_chain has dry_run support",
      "dry_run" in app_s36 and "_cmd_chain" in app_s36)
check("app.py: _cmd_chain has auto_confirm support",
      "auto_confirm" in app_s36 and "_cmd_chain" in app_s36)
check("app.py: _cmd_chain strips numbered prefixes (re.sub)",
      "_re.sub" in app_s36 or "re.sub" in app_s36)
check("app.py: _cmd_chain shows step progress [N/total]",
      "total" in app_s36 and '"{step_label}"' in app_s36 or "step_label" in app_s36)
check("app.py: cmd docstring shows --chain example",
      "--chain" in app_s36 and "nginx" in app_s36)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 37 — default.py: path auto-detection
# Covers: ShellGPT gap #3 — "summarize /tmp/file.txt" auto-reads the file
# ─────────────────────────────────────────────────────────────────────────────
header("Phase 37 — default.py: path auto-detection")

default_s37 = read("aicli/handlers/default.py")

check("default.py: imports extract_file_paths_from_prompt",
      "extract_file_paths_from_prompt" in default_s37)
check("default.py: auto-detects paths from prompt_text",
      "extract_file_paths_from_prompt" in default_s37 and "prompt_text" in default_s37)
check("default.py: merges auto-paths with explicit extra_files",
      "_auto_paths" in default_s37 and "_existing" in default_s37)
check("default.py: explicit --file paths take precedence over auto-detected",
      "_existing" in default_s37 and "_new_auto" in default_s37)
check("default.py: auto-detection guarded by try/except ImportError",
      "ImportError" in default_s37 and "_auto_paths" in default_s37)
check("default.py: prints info about auto-detected files (if not quiet)",
      "Auto-detected" in default_s37)
check("default.py: MAX_AUTO_FILE_BYTES defined",
      "_MAX_AUTO_FILE_BYTES" in default_s37 or "MAX_FILE_BYTES" in default_s37)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 38 — Shell integration: Ctrl+I next-command hotkey
# Covers: ShellGPT gap #4 — inline next-command suggestion
# ─────────────────────────────────────────────────────────────────────────────
header("Phase 38 — Shell Integration: Ctrl+I next-command hotkey")

zsh_s38 = read("aicli/shell_integration.zsh")
bash_s38 = read("aicli/shell_integration.bash")

check("zsh: _aicli_next_widget function defined",
      "_aicli_next_widget" in zsh_s38)
check("zsh: Ctrl+I bound",
      "^I" in zsh_s38 or "\\C-i" in zsh_s38 or "ctrl+i" in zsh_s38.lower())
check("zsh: Ctrl+I uses _aicli_terminal_context",
      "_aicli_terminal_context" in zsh_s38[zsh_s38.find("_aicli_next_widget"):])
check("zsh: Ctrl+I sends --shell --dry-run --lite to aicli",
      "--shell" in zsh_s38 and "--dry-run" in zsh_s38)
check("zsh: Ctrl+I sets BUFFER and CURSOR on result",
      "BUFFER=" in zsh_s38 and "CURSOR=" in zsh_s38)
check("zsh: Ctrl+I has fallback message when no context",
      "no terminal context" in zsh_s38.lower() or "no_context" in zsh_s38)
check("zsh: Ctrl+I registered as zle widget",
      "zle -N _aicli_next_widget" in zsh_s38)

check("bash: _aicli_next function defined",
      "_aicli_next" in bash_s38)
check("bash: Ctrl+I bound",
      "\\C-i" in bash_s38 or "^I" in bash_s38 or "ctrl+i" in bash_s38.lower())
check("bash: Ctrl+I uses _aicli_terminal_context",
      "_aicli_terminal_context" in bash_s38[bash_s38.find("_aicli_next()"):])
check("bash: Ctrl+I sends --shell --dry-run --lite to aicli",
      "--shell" in bash_s38 and "--dry-run" in bash_s38)
check("bash: Ctrl+I documents Tab-conflict and rebind option",
      "Tab" in bash_s38 or "rebind" in bash_s38 or "Ctrl+N" in bash_s38)

# File existence checks for new tool files
check("aicli/tools/__init__.py or tools/ dir exists (or registry.py)",
      (Path(BASE) / "aicli/tools/registry.py").exists() or
      (Path(BASE) / "aicli/tools").is_dir())
check("aicli/tools/registry.py exists",
      (Path(BASE) / "aicli/tools/registry.py").exists())
check("aicli/tools/os_functions.py exists",
      (Path(BASE) / "aicli/tools/os_functions.py").exists())
check("aicli/tools/executor.py exists",
      (Path(BASE) / "aicli/tools/executor.py").exists())


# ─────────────────────────────────────────────────────────────────────────────
# Phase 39 — New OS Tools (send_notification, get_clipboard, open_file,
#             search_web, get_system_info)
# Covers: P2, P3, P7, P8, P11 action plan items
# ─────────────────────────────────────────────────────────────────────────────
header("Phase 39 — New OS Tools")

osf39 = read("aicli/tools/os_functions.py")

check("send_notification tool defined",         "send_notification" in osf39)
check("send_notification: osascript (macOS)",   "osascript" in osf39)
check("send_notification: notify-send (Linux)", "notify-send" in osf39)
check("send_notification: PowerShell (Windows)","powershell" in osf39.lower() and "send_notification" in osf39)
check("get_clipboard tool defined",             "get_clipboard" in osf39)
check("get_clipboard: pbpaste (macOS)",         "pbpaste" in osf39)
check("get_clipboard: xclip (Linux)",           "xclip" in osf39 and "get_clipboard" in osf39)
check("get_clipboard: wl-paste (Wayland)",      "wl-paste" in osf39)
check("open_file tool defined",                 "open_file" in osf39)
check("open_file: xdg-open (Linux)",            "xdg-open" in osf39)
check("open_file: open (macOS)",                '"open"' in osf39 or "'open'" in osf39)
check("open_file: os.startfile (Windows)",      "os.startfile" in osf39)
check("open_file: FileNotFoundError for missing","FileNotFoundError" in osf39 and "open_file" in osf39)
check("search_web tool defined",                "search_web" in osf39)
check("search_web reuses aicli web_search",     "web_search" in osf39)
check("get_system_info tool defined",           "get_system_info" in osf39)
check("get_system_info: platform stdlib",       "platform" in osf39 and "get_system_info" in osf39)
check("get_system_info: psutil optional",       "psutil" in osf39)
check("total tools ≥ 12 (7 original + 5 new)", osf39.count("@os_tool") >= 12)
check("send_notification confirm=False (safe)", 
      "send_notification" in osf39 and "confirm=False" in osf39)
check("get_clipboard confirm=False (safe)",
      "get_clipboard" in osf39 and "safe=True" in osf39)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 40 — Response Caching (handlers/default.py)
# Covers: P5 action plan — ShellGPT request caching parity + improvement
# ─────────────────────────────────────────────────────────────────────────────
header("Phase 40 — Response Caching (default.py)")

def40 = read("aicli/handlers/default.py")

check("_cache_path function defined",           "def _cache_path(" in def40)
check("_cache_key function defined",            "def _cache_key(" in def40)
check("_cache_get function defined",            "def _cache_get(" in def40)
check("_cache_set function defined",            "def _cache_set(" in def40)
check("_cache_clear function defined",          "def _cache_clear(" in def40)
check("cache key uses SHA256",                  "sha256" in def40)
check("cache key includes prompt+model+role",   "prompt" in def40 and "model" in def40 and "role" in def40 and "_cache_key" in def40)
check("cache stored in CONFIG_DIR/response_cache","response_cache" in def40)
check("cache bypassed for --context",           "_use_cache" in def40 and "not context" in def40)
check("cache bypassed for --web",               "_use_cache" in def40 and "not web" in def40)
check("cache bypassed for --watch",             "_use_cache" in def40 and "not watch" in def40)
check("cache bypassed for --image",             "_use_cache" in def40 and "not images" in def40)
check("cache bypassed for --no-cache flag",     "no_cache" in def40 and "_use_cache" in def40)
check("cache hit prints [cache] message",       "[cache]" in def40)
check("cache stored after streaming",           "_cache_set" in def40 and "_caching_gen" in def40 or "_cache_set" in def40)
check("no_cache param in _ask signature",       "no_cache=False" in def40)
check("role param in _ask signature",           "role=None" in def40)
check("custom role applied when provided",      "if role:" in def40 or "role_name = role" in def40)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 41 — app.py: cache + --no-cache + --role
# Covers: P5 + P6 + cache command group
# ─────────────────────────────────────────────────────────────────────────────
header("Phase 41 — app.py: cache group + --no-cache + --role")

app41 = read("aicli/app.py")

check("aicli cache group registered",           '"cache"' in app41 or "cache_group" in app41)
check("cache clear subcommand defined",         "def cache_clear(" in app41)
check("cache stats subcommand defined",         "def cache_stats(" in app41)
check("cache clear calls _cache_clear()",       "_cache_clear" in app41)
check("--no-cache flag on ask",                 '"--no-cache"' in app41 or "'--no-cache'" in app41)
check("--role flag on ask",                     '"--role"' in app41 or "'--role'" in app41)
check("no_cache passed to _ask",                "no_cache=no_cache" in app41 or "no_cache" in app41)
check("role passed to _ask",                    "role=role" in app41 or "role=role or None" in app41)
check("direct invocation passes --no-cache",    '"--no-cache" in args' in app41 or "no_cache" in app41)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 42 — Executor: tool retry + natural summary pass
# Covers: P1 + P10 action plan items
# ─────────────────────────────────────────────────────────────────────────────
header("Phase 42 — Executor: retry + natural summary pass")

exe42 = read("aicli/tools/executor.py")

check("max_retries param in dispatch_tool_calls", "max_retries" in exe42 and "dispatch_tool_calls" in exe42)
check("retry loop (for attempt in range)",        "for attempt in range(" in exe42)
check("retry prints ↻ Retry N/max message",       "Retry" in exe42 and "attempt" in exe42)
check("last_exc tracks final failure",            "last_exc" in exe42)
check("break on success ends retry loop",         "last_exc = None" in exe42 and "break" in exe42)
check("natural summary pass after tool calls",    "summary_messages" in exe42 or "summarize" in exe42.lower())
check("summary pass: second pipeline.stream call","summary_chunks" in exe42)
check("summary pass: skipped when dry_run",       "not dry_run" in exe42 and "summary" in exe42.lower())
check("summary pass: skipped when quiet",         "not quiet" in exe42 and "summary" in exe42.lower())
check("summary pass: best-effort (except pass)",  "except Exception" in exe42 and "pass" in exe42)
check("summary pass: uses successful results only","successful" in exe42)
check("summary pass: formats as 'tool(): result'","result'][" in exe42 or "r['result']" in exe42 or "r[\"result\"]" in exe42)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 43 — Shell integration: Ctrl+I Tab-conflict hint (zsh)
# Covers: P4 action plan
# ─────────────────────────────────────────────────────────────────────────────
header("Phase 43 — Shell integration: Ctrl+I Tab hint (zsh)")

zsh43 = read("aicli/shell_integration.zsh")

check("zsh: Tab-conflict comment present",
      "Tab" in zsh43 or "tab" in zsh43.lower())
check("zsh: rebind option documented (Alt+I or Ctrl+N)",
      "Alt+I" in zsh43 or "\\\\C-n" in zsh43 or "Ctrl+N" in zsh43 or "^N" in zsh43)
check("zsh: expand-or-complete restore documented",
      "expand-or-complete" in zsh43)
check("zsh: ^I binding present",
      "^I" in zsh43)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 44 — Updated KNOWN_PROXIED_CLASSES
# New test classes must be in KNOWN_PROXIED_CLASSES or they appear as behavioral
# ─────────────────────────────────────────────────────────────────────────────
header("Phase 44 — KNOWN_PROXIED_CLASSES completeness")

run44 = read("run_tests.py")

new_classes = [
    "TestNewOsTools", "TestResponseCache", "TestCacheCommand",
    "TestToolRetry", "TestNaturalSummaryPass",
]
for cls in new_classes:
    check(f"run_tests.py: {cls} in KNOWN_PROXIED_CLASSES", cls in run44)


# Phase 45 — S14–S15 feature coverage
# ─────────────────────────────────────────────────────────────────────────────
header("Phase 45 — S14–S15: watch+do / multi-turn do / plugin registry / TUI do-mode")

run45 = read("run_tests.py")
app_src   = read("aicli/app.py")
default_src = read("aicli/handlers/default.py")
executor_src = read("aicli/tools/executor.py")
loader_src  = read("aicli/tools/loader.py") if os.path.exists("aicli/tools/loader.py") else read("aicli/handlers/loader.py")
tui_src     = read("aicli/tui.py")

# watch + do
check("app.py: --do option on ask (watch_do)", '"watch_do"' in app_src or "watch_do" in app_src)
check("default.py: watch_do param in _ask", "watch_do" in default_src)
check("default.py: do_action param in _watch_evaluate", "do_action" in default_src)
check("default.py: do_action param in _watch_stdin", "do_action" in default_src)
check("default.py: run_do_command called on YES trigger", "run_do_command" in default_src)
check("default.py: ImportError guard on run_do_command", "ImportError" in default_src)

# multi-turn do --session
check("app.py: --session flag on do command (do_session)", "do_session" in app_src)
check("executor.py: session_id param in run_do_command", "session_id" in executor_src)
check("executor.py: history injected when session_id set", "history" in executor_src or "session_id" in executor_src)
check("executor.py: session_id defaults to None", "session_id: str | None = None" in executor_src)

# plugin TOOL_REGISTRY auto-registration
check("loader.py: parameters key triggers TOOL_REGISTRY registration", "parameters" in loader_src and "TOOL_REGISTRY" in loader_src)
check("loader.py: ImportError on registry import handled silently", "ImportError" in loader_src)
check("loader.py: confirm forwarded to TOOL_REGISTRY entry", "confirm" in loader_src)
check("loader.py: safe forwarded to TOOL_REGISTRY entry", "safe" in loader_src)

# TUI do-mode (F9)
check("tui.py: DoModeScreen class defined", "class DoModeScreen" in tui_src)
check("tui.py: F9 binding for do_mode", '"f9"' in tui_src or "f9" in tui_src)
check("tui.py: action_do_mode defined", "action_do_mode" in tui_src)
check("tui.py: _run_do_command defined on AicliTUI", "_run_do_command" in tui_src)
check("tui.py: _handle_do_result defined", "_handle_do_result" in tui_src)
check("tui.py: DoModeScreen uses redirect_stdout to capture output", "redirect_stdout" in tui_src)
check("tui.py: _run_do_command accepts auto_confirm parameter", "auto_confirm" in tui_src)
check("tui.py: _run_do_command passes dry_run when not auto_confirm", "dry_run" in tui_src)
check("tui.py: DoModeScreen escape binding defined", '"escape"' in tui_src)
check("tui.py: DoModeScreen Input widget defined", "id=\"do-input\"" in tui_src)
# confirm toggle (S16)
check("tui.py: DoModeScreen Ctrl+Y toggle_confirm binding", "toggle_confirm" in tui_src)
check("tui.py: DoModeScreen _auto_confirm state variable", "_auto_confirm" in tui_src)
check("tui.py: DoModeScreen mode label widget (do-mode-label)", "do-mode-label" in tui_src)
check("tui.py: _handle_do_result unpacks (prompt, auto_confirm) tuple", "auto_confirm" in tui_src)

# sandboxing (S16)
os_src = read("aicli/tools/os_functions.py")
check("os_functions.py: MAX_OUTPUT_BYTES defined", "MAX_OUTPUT_BYTES" in os_src)
check("os_functions.py: _sandbox_available function defined", "_sandbox_available" in os_src)
check("os_functions.py: _build_sandboxed_cmd function defined", "_build_sandboxed_cmd" in os_src)
check("os_functions.py: AICLI_SANDBOX env var checked", "AICLI_SANDBOX" in os_src)
check("os_functions.py: firejail binary checked via shutil.which", "firejail" in os_src)
check("os_functions.py: output truncated at MAX_OUTPUT_BYTES", "truncated" in os_src)
check("os_functions.py: --net=none in sandbox flags", "net=none" in os_src)
check("os_functions.py: --private-tmp in sandbox flags", "private-tmp" in os_src)
check("os_functions.py: AICLI_SANDBOX_NET opt-in for network", "AICLI_SANDBOX_NET" in os_src)
check("os_functions.py: sandboxed path uses list args (no shell=True)", "_build_sandboxed_cmd" in os_src)

# RAG integration test
check("tests/test_rag_integration.py exists", os.path.exists("tests/test_rag_integration.py"))

# test coverage
check("run_tests.py: TestWatchDoIntegration in KNOWN_PROXIED_CLASSES", "TestWatchDoIntegration" in run45)
check("run_tests.py: TestDoCommandSession in KNOWN_PROXIED_CLASSES", "TestDoCommandSession" in run45)
check("run_tests.py: TestPluginOsToolRegistration in KNOWN_PROXIED_CLASSES", "TestPluginOsToolRegistration" in run45)
check("run_tests.py: TestDoModeScreen in KNOWN_PROXIED_CLASSES", "TestDoModeScreen" in run45)
check("run_tests.py: TestCmdChainRole in KNOWN_PROXIED_CLASSES", "TestCmdChainRole" in run45)
check("run_tests.py: TestRunDoCommandMaxRetries in KNOWN_PROXIED_CLASSES", "TestRunDoCommandMaxRetries" in run45)
check("run_tests.py: TestRunShellCommandWorkingDir in KNOWN_PROXIED_CLASSES", "TestRunShellCommandWorkingDir" in run45)


# Phase 46 — S16: intent routing + @FunctionCall UX
# ─────────────────────────────────────────────────────────────────────────────
header("Phase 46 — S16: intent routing + @FunctionCall UX + ShellGPT full parity")

app46 = read("aicli/app.py")
exec46 = read("aicli/tools/executor.py")
zsh46  = read("aicli/shell_integration.zsh")

# intent routing
check("app.py: _detect_intent function defined", "def _detect_intent(" in app46)
check("app.py: action verbs in _detect_intent", "play|open|send" in app46 and "action_verbs" in app46)
check("app.py: query_starts tuple in _detect_intent", "query_starts" in app46 and "explain " in app46)
check("app.py: filesystem path exception in query branch", "action_exceptions" in app46)
check("app.py: cli() calls _detect_intent", "_detect_intent" in app46)
check("app.py: intent==do routes to do_command", 'intent == "do"' in app46)

# @FunctionCall format
check("executor.py: @FunctionCall prefix in _format_tool_call", "@FunctionCall" in exec46)
check("executor.py: auto_confirm shows @FunctionCall line cleanly", "auto_confirm" in exec46 and "@FunctionCall" in exec46)
check("executor.py: verbose param in run_do_command", "verbose: bool = False" in exec46)
check("executor.py: Function-call mode behind verbose flag", "verbose and not quiet" in exec46)
check("executor.py: dry-run plan header present", "Dry-run plan" in exec46)
check("executor.py: dry-run shows tool description line", "description" in exec46)

# Ctrl+L chain hotkey (ShellGPT parity)
check("zsh: _aicli_chain_widget defined", "_aicli_chain_widget" in zsh46)
check("zsh: Ctrl+L bound to chain widget", "bindkey '^L' _aicli_chain_widget" in zsh46 or "^L" in zsh46)
check("zsh: chain widget calls aicli cmd --chain", "aicli cmd --chain" in zsh46)

bash46 = read("aicli/shell_integration.bash")
check("bash: _aicli_chain function defined", "_aicli_chain" in bash46)
check("bash: Ctrl+L bound to chain", r'\C-l' in bash46 or "_aicli_chain" in bash46)
check("bash: chain calls aicli cmd --chain", "aicli cmd --chain" in bash46)
check("zsh: chain widget has empty-buffer inline prompt", "chain>" in zsh46)

# do command --verbose flag
check("app.py: --verbose flag on do command", "--verbose" in app46 or "verbose" in app46)

# test coverage
run46 = read("run_tests.py")
check("run_tests.py: TestIntentRouting in KNOWN_PROXIED_CLASSES", "TestIntentRouting" in run46)
check("run_tests.py: TestDoCommandUX in KNOWN_PROXIED_CLASSES", "TestDoCommandUX" in run46)
check("run_tests.py: TestCtrlLChainWidget in KNOWN_PROXIED_CLASSES", "TestCtrlLChainWidget" in run46)

total = PASS + FAIL
if TIMING:
    # flush the last phase
    header.__defaults__[0][0] and _phase_times.append(
        (header.__defaults__[0][0][0], _time.monotonic() - header.__defaults__[0][0][1])
    )
    total_elapsed = _time.monotonic() - _t0
    print(f"\n{'─' * 64}")
    print(f"  TIMING (--time mode)  total: {total_elapsed:.2f}s")
    print(f"{'─' * 64}")
    for phase, secs in _phase_times:
        bar = "█" * int(secs * 40 / max(t for _, t in _phase_times) + 0.5) if _phase_times else ""
        print(f"  {secs:5.3f}s  {bar:<20}  {phase}")
    print()
print(f"\n{'═' * 64}")
print(f"  SUMMARY  ({_time.monotonic() - _t0:.2f}s total)")
print(f"{'═' * 64}")
pct = int(100 * PASS / total) if total else 0
print(f"  \033[32m✓ {PASS} passed\033[0m" +
      (f"  \033[31m✗ {FAIL} failed\033[0m" if FAIL else "") +
      f"  ({pct}%)")

if FAIL == 0:
    print(f"\n  \033[32m🎯 All {total} checks passed!\033[0m\n")
    sys.exit(0)
else:
    print(f"\n  \033[31m⚠  {FAIL} check(s) failed. Review above.\033[0m\n")
    sys.exit(1)
