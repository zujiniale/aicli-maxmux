"""
tools/loader.py — F6: Plugin system for aicli.

Auto-discovers and loads *.py plugin files from ~/.config/aicli/plugins/.
Each plugin must expose a register() function returning a tool dict:

    def register() -> dict:
        return {
            "name":        "my_tool",
            "description": "What this does",
            "fn":          callable,
        }

Optional: "version", "author"

Example plugin (~/.config/aicli/plugins/calculator.py):

    def register():
        return {
            "name": "calculator",
            "description": "Evaluate a Python math expression safely",
            "fn": lambda expr: str(eval(expr, {"__builtins__": {}}, {})),
        }
"""

import importlib.util
import sys
from pathlib import Path


def _plugins_dir() -> Path:
    from aicli.config import CONFIG_DIR
    return CONFIG_DIR / "plugins"


_loaded_plugins: list[dict] | None = None
_load_errors: list[str] = []


def load_plugins(plugins_dir: Path | None = None, force_reload: bool = False) -> list[dict]:
    """
    Discover and load all *.py files in the plugins directory.
    Results cached — call with force_reload=True to re-scan.
    """
    global _loaded_plugins, _load_errors

    if _loaded_plugins is not None and not force_reload:
        return _loaded_plugins

    _loaded_plugins = []
    _load_errors = []

    target_dir = plugins_dir or _plugins_dir()
    target_dir.mkdir(parents=True, exist_ok=True)

    for path in sorted(target_dir.glob("*.py")):
        if path.name.startswith("_"):
            continue
        try:
            plugin = _load_plugin_file(path)
            if plugin:
                _loaded_plugins.append(plugin)
        except Exception as e:
            _load_errors.append(f"[plugin] Failed to load {path.name}: {e}")

    return _loaded_plugins


def _load_plugin_file(path: Path) -> dict | None:
    module_name = f"aicli_plugin_{path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not create module spec for {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    if not hasattr(module, "register"):
        raise AttributeError(f"{path.name} has no register() function")

    tool = module.register()
    if not isinstance(tool, dict):
        raise TypeError(f"register() must return dict, got {type(tool).__name__}")
    for field in ("name", "description", "fn"):
        if field not in tool:
            raise ValueError(f"register() dict missing required field: '{field}'")
    if not callable(tool["fn"]):
        raise TypeError(f"tool['fn'] must be callable")

    tool["_source"] = str(path)
    return tool


def get_plugin_tools(plugins_dir: Path | None = None) -> list[dict]:
    """Return all successfully loaded plugin tool dicts."""
    return load_plugins(plugins_dir=plugins_dir)


def get_load_errors() -> list[str]:
    load_plugins()
    return list(_load_errors)


def list_plugins(plugins_dir: Path | None = None) -> None:
    """Print formatted plugin list to stdout."""
    tools = load_plugins(plugins_dir=plugins_dir, force_reload=True)
    errors = get_load_errors()
    plugins_dir_path = plugins_dir or _plugins_dir()

    print(f"\n\033[1mPlugin directory:\033[0m {plugins_dir_path}\n")

    if not tools and not errors:
        print("  No plugins installed.\n")
        print(f"  Drop a .py file into: {plugins_dir_path}/\n")
        print("  Each file must expose:\n")
        print("    def register():")
        print('        return {"name": "...", "description": "...", "fn": callable}\n')
        return

    if tools:
        print(f"\033[1mLoaded plugins ({len(tools)}):\033[0m\n")
        for tool in tools:
            name   = tool.get("name", "unknown")
            desc   = tool.get("description", "")
            src    = Path(tool.get("_source", "")).name
            ver    = f" v{tool['version']}" if tool.get("version") else ""
            author = f" by {tool['author']}" if tool.get("author") else ""
            print(f"  \033[32m{name}\033[0m{ver}{author}")
            print(f"    {desc}")
            print(f"    \033[90m{src}\033[0m\n")

    if errors:
        print(f"\033[1mFailed to load ({len(errors)}):\033[0m\n")
        for err in errors:
            print(f"  \033[31m{err}\033[0m\n")


def call_plugin(name: str, arg: str, plugins_dir: Path | None = None) -> str | None:
    """Call a plugin by name. Returns string result or None if not found."""
    for tool in get_plugin_tools(plugins_dir=plugins_dir):
        if tool["name"] == name:
            return str(tool["fn"](arg))
    return None
