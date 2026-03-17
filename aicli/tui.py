"""
tui.py — aicli TUI v1.4.1

Fixes vs previous:
- ctrl+h → ctrl+f1 / F1  (Ctrl+H = backspace in many terminals)
- ctrl+, → ctrl+9         (Ctrl+, = zoom in terminals)
- Linux clipboard via xclip/xsel/wl-copy subprocess (Textual's
  copy_to_clipboard is internal-only on Linux, doesn't reach system clipboard)
- Theme fix: TextArea uses theme="css" AND inline CSS overrides on the widget
  itself so the colors actually apply (not just the surrounding container)
- Help and Settings screens are kept in sync from one shared ACTIONS list
- Exports go to ~/.config/aicli/exports/ (organised, not ~/Desktop scatter)
- All keybindings exposed in Settings with working defaults
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.css.query import NoMatches
from textual.reactive import reactive
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Label, ListItem, ListView, Static, TextArea

# ── Single source of truth for all actions ────────────────────────────────────
# (key_id, default_key, label)  — used by BINDINGS, HelpScreen, SettingsScreen
ACTIONS = [
    ("quit",           "ctrl+q",  "Quit"),
    ("new_session",    "ctrl+n",  "New session"),
    ("delete",         "ctrl+d",  "Delete session"),
    ("pin",            "ctrl+k",  "Pin session"),
    ("bulk",           "ctrl+b",  "Bulk select"),
    ("export_md",      "ctrl+e",  "Export markdown"),
    ("export_json",    "ctrl+j",  "Backup JSON"),
    ("import_json",    "ctrl+i",  "Import JSON"),
    ("toggle_web",     "ctrl+w",  "Toggle web search"),
    ("toggle_ctx",     "ctrl+x",  "Toggle RAG ctx"),
    ("summarize",      "ctrl+s",  "Summarize session"),
    ("copy_msg",       "ctrl+y",  "Copy message text"),
    ("open_location",  "ctrl+o",  "Open exports folder"),
    ("export_session",  "f4",     "Export session to .md + .json"),
    ("import_session",  "f5",     "Import session from .json file"),
    ("sync_now",        "f6",     "Sync all data to exports folder"),
    ("open_graph",      "f7",     "Open graph viewer in browser"),
    ("send",            "f8",     "Send message"),
    ("send_ctrl",        "ctrl+g",  "Send message (Ctrl+G)"),
    ("range_pick",     "f2",  "Range select mode"),
    ("cycle_theme",    "f3",  "Cycle theme (5 built-in themes)"),
    ("copy_range",     "ctrl+r",  "Copy typed range (type 3-7 then Ctrl+R)"),
    ("help",           "f1",      "Help (this screen)"),
    ("settings",       "ctrl+9",  "Settings"),
    # ── Vim-style navigation (v1.5.3) ─────────────────────────────────────────
    ("scroll_down",    "j",       "Scroll chat down (vim)"),
    ("scroll_up",      "k",       "Scroll chat up (vim)"),
    ("scroll_bottom",  "G",       "Jump to bottom (vim)"),
    ("scroll_top",     "g",       "Jump to top (vim)"),
    ("search_sessions", "/",      "Search sessions (vim)"),
    ("delete_session_dd", "d",    "Delete session (vim dd — press twice)"),
    # ── aicli do (v1.5.7) ─────────────────────────────────────────────────────
    ("do_mode",        "f9",      "aicli do — OS function calling"),
]

# CSS is generated dynamically from the active theme (see build_css)


# ── Key config ────────────────────────────────────────────────────────────────

DEFAULT_KEYS = {kid: key for kid, key, _ in ACTIONS}

# ── Themes ───────────────────────────────────────────────────────────────────

THEMES = {
    "tokyo-night": {
        "name": "Tokyo Night",
        "bg":        "#1a1b26",
        "bg_alt":    "#16213e",
        "bg_msg":    "#1e2030",
        "border":    "#2a2b3d",
        "accent":    "#7aa2f7",
        "green":     "#9ece6a",
        "amber":     "#e0af68",
        "text":      "#c0caf5",
        "text_dim":  "#a9b1d6",
        "muted":     "#565f89",
        "status_bg": "#0f1117",
        "range_bg":  "#1e1a10",
    },
    "dracula": {
        "name": "Dracula",
        "bg":        "#282a36",
        "bg_alt":    "#21222c",
        "bg_msg":    "#2d2f3f",
        "border":    "#44475a",
        "accent":    "#bd93f9",
        "green":     "#50fa7b",
        "amber":     "#ffb86c",
        "text":      "#f8f8f2",
        "text_dim":  "#e0e0e0",
        "muted":     "#6272a4",
        "status_bg": "#191a21",
        "range_bg":  "#3a2a10",
    },
    "gruvbox": {
        "name": "Gruvbox",
        "bg":        "#282828",
        "bg_alt":    "#1d2021",
        "bg_msg":    "#32302f",
        "border":    "#504945",
        "accent":    "#83a598",
        "green":     "#b8bb26",
        "amber":     "#fabd2f",
        "text":      "#ebdbb2",
        "text_dim":  "#d5c4a1",
        "muted":     "#928374",
        "status_bg": "#1d2021",
        "range_bg":  "#3c3423",
    },
    "nord": {
        "name": "Nord",
        "bg":        "#2e3440",
        "bg_alt":    "#272c36",
        "bg_msg":    "#3b4252",
        "border":    "#434c5e",
        "accent":    "#88c0d0",
        "green":     "#a3be8c",
        "amber":     "#ebcb8b",
        "text":      "#eceff4",
        "text_dim":  "#d8dee9",
        "muted":     "#616e88",
        "status_bg": "#242933",
        "range_bg":  "#3b3a2e",
    },
    "solarized": {
        "name": "Solarized Dark",
        "bg":        "#002b36",
        "bg_alt":    "#00212b",
        "bg_msg":    "#073642",
        "border":    "#094454",
        "accent":    "#268bd2",
        "green":     "#859900",
        "amber":     "#b58900",
        "text":      "#839496",
        "text_dim":  "#93a1a1",
        "muted":     "#586e75",
        "status_bg": "#001e26",
        "range_bg":  "#1a2a1a",
    },
}
THEME_KEYS = list(THEMES.keys())

def _theme_file() -> Path:
    try:
        from aicli.config import CONFIG_DIR
        return CONFIG_DIR / "tui_theme.json"
    except Exception:
        return Path.home() / ".config" / "aicli" / "tui_theme.json"

def load_theme() -> dict:
    try:
        name = json.loads(_theme_file().read_text()).get("theme", "tokyo-night")
        return THEMES.get(name, THEMES["tokyo-night"]), name
    except Exception:
        return THEMES["tokyo-night"], "tokyo-night"

def save_theme(name: str) -> None:
    try:
        f = _theme_file(); f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"theme": name}))
    except Exception:
        pass

def build_css(t: dict) -> str:
    """Build the full CSS string from a theme dict."""
    return f"""
Screen {{ background: {t['bg']}; }}
Header {{ background: {t['status_bg']}; color: {t['accent']}; text-style: bold; height: 1; }}
Footer {{ background: {t['status_bg']}; color: {t['muted']}; }}

#sidebar {{
    width: 32; min-width: 32;
    border-right: solid {t['border']};
    background: {t['bg_alt']};
}}
#sidebar-header {{
    height: 1; background: {t['status_bg']}; color: {t['accent']};
    text-style: bold; content-align: center middle;
}}
#session-search {{
    height: 3; background: {t['bg_alt']}; color: {t['text']};
    border: none; border-bottom: solid {t['border']}; padding: 0 1;
}}
#session-search:focus {{ border-bottom: solid {t['accent']}; }}
#bulk-toolbar {{
    height: 1; background: {t['bg_msg']}; color: {t['amber']};
    padding: 0 1; content-align: left middle; display: none;
}}
#bulk-toolbar.visible {{ display: block; }}
#session-list {{ height: 1fr; background: {t['bg_alt']}; }}
#session-list > ListItem {{
    padding: 0 1; height: 4;
    border-bottom: solid {t['bg']}; background: {t['bg_alt']};
}}
#session-list > ListItem.--highlight {{ background: {t['bg_msg']}; border-left: tall {t['accent']}; }}
#session-list > ListItem:hover {{ background: {t['bg_msg']}; }}
#session-list > ListItem.pinned {{ border-left: tall {t['amber']}; }}
#session-list > ListItem.selected-bulk {{ background: {t['bg_msg']}; border-left: tall {t['green']}; }}
.session-pin-icon {{ color: {t['amber']}; width: 2; }}
.session-name {{ color: {t['text']}; text-style: bold; width: 1fr; }}
.session-count {{ color: {t['muted']}; width: 1fr; }}
#provider-status {{
    height: auto; border-top: solid {t['border']};
    background: {t['status_bg']}; padding: 1 1; color: {t['muted']};
}}
#main {{ width: 1fr; background: {t['bg']}; }}
#chat-scroll {{ height: 1fr; background: {t['bg']}; padding: 1 2; }}
MessageBlock {{ height: auto; background: {t['bg']}; margin-bottom: 1; }}
.msg-user-header {{
    background: {t['bg']}; color: {t['accent']}; text-style: bold; height: 1;
}}
.msg-user-body {{
    background: {t['bg_msg']}; color: {t['text']};
    border-left: solid {t['accent']};
    height: auto; min-height: 1; max-height: 30; padding: 0 1;
}}
.msg-user-body > TextArea {{ background: {t['bg_msg']}; color: {t['text']}; }}
.msg-assistant-header {{
    background: {t['bg']}; color: {t['green']}; text-style: bold; height: 1;
}}
.msg-assistant-body {{
    background: {t['bg']}; color: {t['text_dim']};
    border-left: solid {t['green']};
    height: auto; min-height: 1; max-height: 60; padding: 0 1;
}}
.msg-assistant-body > TextArea {{ background: {t['bg']}; color: {t['text_dim']}; }}
.msg-system {{ background: {t['bg']}; color: {t['amber']}; text-style: italic; height: auto; padding: 0 2; }}
.msg-summary {{ background: {t['bg']}; color: {t['amber']}; text-style: italic; height: auto; padding: 0 2; margin: 1 0; }}
#flags-bar {{ height: 1; background: {t['status_bg']}; color: {t['muted']}; padding: 0 2; }}
#range-status {{ height: 1; background: {t['bg_msg']}; color: {t['amber']}; padding: 0 2; display: none; }}
#range-status.visible {{ display: block; }}
#thinking {{ height: 1; background: {t['bg']}; color: {t['amber']}; text-style: italic; padding: 0 2; display: none; }}
#thinking.visible {{ display: block; }}
#input-area {{ height: 5; border-top: solid {t['border']}; background: {t['bg_alt']}; padding: 0; }}
#send-arrow {{
    width: 5; height: 5; min-width: 5;
    background: {t['accent']}; color: {t['bg']};
    border: none; text-style: bold;
}}
#send-arrow:hover {{ background: {t['green']}; }}
#send-arrow:focus {{ background: {t['accent']}; border: none; }}
#prompt-input {{
    height: 5; width: 1fr; border: solid {t['border']};
    background: {t['bg_msg']}; color: {t['text']}; padding: 0 1;
}}
#prompt-input:focus {{ border: solid {t['accent']}; }}
#send-btn {{
    height: 3; width: 12; min-width: 12;
    background: {t['accent']}; color: {t['bg']};
    text-style: bold;
}}
#send-btn:hover {{ background: {t['green']}; }}
#status-bar {{ height: 1; background: {t['status_bg']}; color: {t['muted']}; padding: 0 2; content-align: left middle; }}
HelpScreen, SettingsScreen {{ background: {t['bg']}99; align: center middle; }}
#help-box, #settings-box {{
    width: 66; height: auto; max-height: 46;
    background: {t['bg_alt']}; border: solid {t['accent']}; padding: 1 2;
}}
#settings-box {{ border: solid {t['amber']}; }}
.overlay-title {{ color: {t['accent']}; text-style: bold; height: 2; content-align: center middle; width: 1fr; }}
.settings-title {{ color: {t['amber']}; text-style: bold; height: 2; content-align: center middle; width: 1fr; }}
#help-body {{ color: {t['text']}; background: {t['bg_alt']}; height: auto; }}
.overlay-close {{ margin-top: 1; width: 1fr; background: {t['accent']}; color: {t['bg']}; text-style: bold; }}
.settings-row {{ height: 3; margin-bottom: 0; }}
.settings-label {{ width: 24; color: {t['text_dim']}; content-align: left middle; height: 3; }}
.settings-input {{ width: 1fr; height: 3; border: solid {t['border']}; background: {t['bg_msg']}; color: {t['text']}; }}
.settings-input:focus {{ border: solid {t['amber']}; }}
#settings-save {{ margin-top: 1; width: 1fr; background: {t['green']}; color: {t['bg']}; text-style: bold; }}
#settings-cancel {{ width: 1fr; background: {t['border']}; color: {t['text']}; }}
"""

def _keys_file() -> Path:
    try:
        from aicli.config import CONFIG_DIR
        return CONFIG_DIR / "tui_keys.json"
    except Exception:
        return Path.home() / ".config" / "aicli" / "tui_keys.json"

def load_keys() -> dict:
    try:
        merged = dict(DEFAULT_KEYS)
        merged.update(json.loads(_keys_file().read_text()))
        return merged
    except Exception:
        return dict(DEFAULT_KEYS)

def save_keys(keys: dict) -> None:
    try:
        f = _keys_file(); f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(keys, indent=2))
    except Exception:
        pass

def _exports_config_file() -> Path:
    try:
        from aicli.config import CONFIG_DIR
        return CONFIG_DIR / "tui_exports.json"
    except Exception:
        return Path.home() / ".config" / "aicli" / "tui_exports.json"

def save_exports_dir(path: str) -> None:
    try:
        f = _exports_config_file(); f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"exports_dir": path}))
    except Exception:
        pass

def _exports_dir() -> Path:
    """Return configured path, defaulting to ~/Music/aicli/exports."""
    try:
        cfg = json.loads(_exports_config_file().read_text())
        p = Path(cfg.get("exports_dir", "")).expanduser()
        if p and str(p) != ".":
            p.mkdir(parents=True, exist_ok=True)
            return p
    except Exception:
        pass
    d = Path.home() / "Music" / "aicli" / "exports"
    d.mkdir(parents=True, exist_ok=True)
    return d

def get_exports_dir() -> Path:
    return _exports_dir()

# ── Sync helpers ─────────────────────────────────────────────────────────────

def _sync_dir() -> Path:
    """Canonical sync target — ~/Music/aicli/exports (same as exports)."""
    return _exports_dir()

def sync_all_to_exports() -> str:
    """
    Copy every important config/data file to the exports dir.
    Returns a short status string.
    """
    import shutil
    d = _sync_dir()
    copied = []
    # Files to sync: sessions DB + all config JSONs
    try:
        from aicli.config import CONFIG_DIR
        src_dir = CONFIG_DIR
    except Exception:
        src_dir = Path.home() / ".config" / "aicli"
    files_to_sync = [
        src_dir / "sessions.db",
        src_dir / "tui_keys.json",
        src_dir / "tui_theme.json",
        src_dir / "tui_pinned.json",
        src_dir / "tui_exports.json",
    ]
    for src in files_to_sync:
        if src.exists():
            dst = d / f"_sync_{src.name}"
            shutil.copy2(src, dst)
            copied.append(src.name)
    # Migrate any old exports from ~/.config/aicli/exports
    try:
        old_exports = Path.home() / ".config" / "aicli" / "exports"
        if old_exports.exists() and old_exports != d:
            for f in old_exports.iterdir():
                dst = d / f.name
                if not dst.exists():
                    shutil.copy2(f, dst)
                    copied.append(f"(migrated) {f.name}")
    except Exception:
        pass
    # Always keep graph viewer HTML up to date in exports
    try:
        import importlib.resources, os
        graph_src = Path(__file__).parent / "aicli_graph.html"
        if graph_src.exists():
            shutil.copy2(graph_src, d / "graph.html")
            copied.append("graph.html")
    except Exception:
        pass
    # Migrate any old exports from ~/.config/aicli/exports if different from target
    try:
        old_dir = Path.home() / ".config" / "aicli" / "exports"
        if old_dir.exists() and old_dir != d:
            for f in old_dir.iterdir():
                dst = d / f.name
                if not dst.exists():
                    shutil.copy2(f, dst)
                    copied.append(f"migrated:{f.name}")
    except Exception:
        pass
    return f"Synced: {', '.join(copied)}" if copied else "Nothing to sync"

# ── Clipboard helper ──────────────────────────────────────────────────────────

def _copy_to_system_clipboard(text: str) -> str:
    """
    Copy text to OS clipboard while Textual alternate screen is active.
    Uses start_new_session=True + file redirect so xclip/xsel are fully
    detached from Textual terminal fd (direct subprocess.run fails even
    when $DISPLAY is set because the terminal fd is locked by Textual).
    """
    import shutil, tempfile, time
    env = os.environ.copy()
    display = env.get("DISPLAY", "")
    wayland = env.get("WAYLAND_DISPLAY", "")
    tmp = Path(tempfile.mktemp(suffix=".txt", prefix="aicli_"))
    tmp.write_text(text, encoding="utf-8")

    def _shell(cmd: str) -> bool:
        try:
            p = subprocess.Popen(["bash", "-c", cmd],
                stdin=open(os.devnull,"rb"), stdout=open(os.devnull,"wb"),
                stderr=open(os.devnull,"wb"), env=env, start_new_session=True)
            time.sleep(0.15)
            return p.poll() is None or p.returncode == 0
        except Exception:
            return False

    if wayland and shutil.which("wl-copy"):
        if _shell(f"wl-copy < {tmp}"):
            tmp.unlink(missing_ok=True)
            return f"Copied {len(text)} chars (wl-copy)"
    if display and shutil.which("xclip"):
        if _shell(f"xclip -selection clipboard < {tmp}"):
            tmp.unlink(missing_ok=True)
            return f"Copied {len(text)} chars (xclip)"
    if display and shutil.which("xsel"):
        if _shell(f"xsel --clipboard --input < {tmp}"):
            tmp.unlink(missing_ok=True)
            return f"Copied {len(text)} chars (xsel)"
    if sys.platform == "darwin" and shutil.which("pbcopy"):
        if _shell(f"pbcopy < {tmp}"):
            tmp.unlink(missing_ok=True)
            return f"Copied {len(text)} chars (pbcopy)"
    permanent = Path("/tmp/aicli_copy.txt")
    permanent.write_text(text, encoding="utf-8")
    return f"Clipboard unavailable (DISPLAY='{display or 'unset'}') — saved to {permanent}"

# ── Help screen ───────────────────────────────────────────────────────────────

class HelpScreen(Screen):
    BINDINGS = [Binding("escape", "dismiss_screen", "Close", show=False, priority=True),
                Binding("f1",    "dismiss_screen", "Close", show=False, priority=True)]

    def __init__(self, keys: dict) -> None:
        super().__init__(); self._keys = keys

    def compose(self) -> ComposeResult:
        rows = [(label, self._keys.get(kid, key)) for kid, key, label in ACTIONS]
        lines = [
            "  {:<34} {}".format("Action", "Key"),
            "  " + "─"*34 + " " + "─"*14,
        ]
        for label, key in rows:
            lines.append("  {:<34} {}".format(label, key))
        lines += [
            "",
            "  ── Message copy ────────────────────────────",
            "  Ctrl+Y (precise): click into msg, drag to select, Ctrl+Y",
            "  Ctrl+Y (block):   click msg header, Ctrl+Y = whole block",
            "  Ctrl+Y (range):   F2 → click start → click end → Ctrl+Y",
            "  Ctrl+R (typed):   type  3-7  in input box, press Ctrl+R",
            "  Esc: cancel any active range selection",
            "",
            "  ── Vim navigation (when input not focused) ──",
            "  j / k     scroll chat down / up",
            "  G         jump to bottom",
            "  g         jump to top",
            "  /         focus session search",
            "  dd        delete current session (press d twice)",
            "",
            "  ── Session bulk ops (Ctrl+B) ────────────────",
            "  Enter bulk mode, click sessions to select,",
            "  then Ctrl+D=delete  Ctrl+E=export  Ctrl+K=pin",
            "",
            "  ── Clipboard ──────────────────────────────",
            "  Requires xclip:  sudo apt install xclip",
            "  Exports folder:  ~/.config/aicli/exports/",
        ]
        with Vertical(id="help-box"):
            yield Label("  aicli TUI — Help  (Esc to close)", classes="overlay-title")
            yield Static("\n".join(lines), id="help-body")
            yield Button("  Close  [Esc]  ", classes="overlay-close", id="help-close")

    def on_button_pressed(self, _): self.dismiss()
    def action_dismiss_screen(self): self.dismiss()

# ── Settings screen ───────────────────────────────────────────────────────────

class SettingsScreen(Screen):
    BINDINGS = [Binding("escape", "dismiss_screen", "Close", show=False, priority=True)]

    def __init__(self, keys: dict) -> None:
        super().__init__(); self._keys = dict(keys)

    def compose(self) -> ComposeResult:
        # ACTIONS drives settings too — same list, always in sync with help
        current_exports = str(get_exports_dir())
        with Vertical(id="settings-box"):
            yield Label("  aicli TUI  —  Settings  (Esc to cancel)", classes="settings-title")
            with Horizontal(classes="settings-row"):
                yield Label("  Export folder", classes="settings-label")
                yield Input(
                    value=current_exports,
                    placeholder="~/.config/aicli/exports",
                    id="skey-exports-dir", classes="settings-input",
                )
            yield Label("  ─── Hotkeys ───", classes="settings-label")
            for kid, default_key, label in ACTIONS:
                with Horizontal(classes="settings-row"):
                    yield Label(f"  {label}", classes="settings-label")
                    yield Input(
                        value=self._keys.get(kid, default_key),
                        placeholder=f"default: {default_key}",
                        id=f"skey-{kid}", classes="settings-input",
                    )
            yield Button("  Save & Close  ", id="settings-save")
            yield Button("  Cancel  ", id="settings-cancel")

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "settings-save":
            # Save export folder
            try:
                ep = self.query_one("#skey-exports-dir", Input).value.strip()
                if ep:
                    save_exports_dir(ep)
            except NoMatches:
                pass
            # Save hotkeys
            for kid, default_key, _ in ACTIONS:
                try:
                    v = self.query_one(f"#skey-{kid}", Input).value.strip()
                    self._keys[kid] = v if v else default_key
                except NoMatches:
                    pass
            save_keys(self._keys)
            self.dismiss(self._keys)
        else:
            self.dismiss(None)

    def action_dismiss_screen(self): self.dismiss(None)

# ── Widgets ───────────────────────────────────────────────────────────────────

class HotkeyInput(Input):
    """
    Input subclass that maps hotkeys directly to App actions.
    Uses on_key (public) not _on_key (internal) for Textual 0.89 compatibility.
    Also handles on_input_submitted for Enter key as a belt-and-suspenders approach.
    """
    def on_key(self, event) -> None:
        app = self.app
        key = event.key
        if key == "enter":
            if self.id == "prompt-input":
                event.stop(); event.prevent_default()
                app.action_send()
            else:
                super()._on_key(event)
        elif key == "ctrl+enter":
            if self.id == "prompt-input":
                event.stop(); event.prevent_default()
                app.action_newline()
        elif key == "f8":
            if self.id == "prompt-input":
                event.stop(); event.prevent_default()
                app.action_send()
        elif key == "f2":
            event.stop(); event.prevent_default()
            app.call_later(app.action_range_pick)
        elif key == "ctrl+r":
            event.stop(); event.prevent_default()
            app.call_later(app.action_copy_range)
        elif key == "ctrl+y":
            event.stop(); event.prevent_default()
            app.call_later(app.action_copy_msg)
        elif key == "ctrl+w":
            event.stop(); event.prevent_default()
            app.call_later(app.action_toggle_web)
        elif key == "ctrl+x":
            event.stop(); event.prevent_default()
            app.call_later(app.action_toggle_ctx)
        elif key == "ctrl+k":
            event.stop(); event.prevent_default()
            app.call_later(app.action_pin)
        elif key == "ctrl+b":
            event.stop(); event.prevent_default()
            app.call_later(app.action_bulk)
        elif key == "ctrl+e":
            event.stop(); event.prevent_default()
            app.call_later(app.action_export_md)
        elif key == "ctrl+j":
            event.stop(); event.prevent_default()
            app.call_later(app.action_export_json)
        elif key == "ctrl+s":
            event.stop(); event.prevent_default()
            app.call_later(app.action_summarize)
        elif key == "ctrl+o":
            event.stop(); event.prevent_default()
            app.call_later(app.action_open_location)
        elif key == "f4":
            event.stop(); event.prevent_default()
            app.call_later(app.action_export_session_file)
        elif key == "f5":
            event.stop(); event.prevent_default()
            app.call_later(app.action_import_session_file)
        elif key == "f6":
            event.stop(); event.prevent_default()
            app.call_later(app.action_sync_now)
        elif key == "f7":
            event.stop(); event.prevent_default()
            app.call_later(app.action_open_graph)
        elif key == "escape":
            event.stop(); event.prevent_default()
            app.call_later(app.action_clear_range)
        elif key == "f1":
            event.stop(); event.prevent_default()
            app.call_later(app.action_help)
        elif key == "f3":
            event.stop(); event.prevent_default()
            app.call_later(app.action_cycle_theme)
        elif key == "ctrl+9":
            event.stop(); event.prevent_default()
            app.call_later(app.action_settings)
        else:
            # Must pass unhandled keys to super so normal typing works
            super()._on_key(event)

    def on_input_submitted(self, event: "Input.Submitted") -> None:
        """Belt-and-suspenders: also catch Enter via the submitted event."""
        if self.id == "prompt-input":
            event.stop()
            self.app.action_send()


class StatusBar(Static):
    provider: reactive[str]  = reactive("—")
    web_on:   reactive[bool] = reactive(False)
    ctx_on:   reactive[bool] = reactive(False)

    def render(self) -> str:
        parts = [f"⚡ {self.provider}"]
        if self.web_on: parts.append("🌐 web")
        if self.ctx_on: parts.append("🧠 ctx")
        return "  " + "   ".join(parts)


class MessageBlock(Static):
    """
    Message block. TextArea uses theme="css" which is essential —
    without it Textual overrides your CSS background/color with its
    own internal monokai/dracula palette.
    The additional component-class CSS rules (.msg-user-body TextArea etc.)
    target the internal TextArea cells directly so colors actually appear.
    """
    def __init__(self, role: str, content: str, timestamp: str = "", msg_index: int = -1) -> None:
        super().__init__()
        self.msg_role    = role
        self.msg_content = content
        self.msg_ts      = timestamp[:16] if timestamp else ""
        self.msg_index   = msg_index
        self._range_selected = False

    def compose(self) -> ComposeResult:
        ts = f"  {self.msg_ts}" if self.msg_ts else ""
        if self.msg_role == "user":
            idx = f" #{self.msg_index}" if self.msg_index >= 0 else ""
            yield Label(f"▸ You{ts}{idx}", classes="msg-user-header")
            ta = TextArea(self.msg_content, theme="css", read_only=True,
                          show_line_numbers=False, classes="msg-user-body")
            yield ta
        elif self.msg_role == "assistant":
            idx = f" #{self.msg_index}" if self.msg_index >= 0 else ""
            yield Label(f"◆ Assistant{ts}{idx}", classes="msg-assistant-header")
            ta = TextArea(self.msg_content, theme="css", read_only=True,
                          show_line_numbers=False, classes="msg-assistant-body")
            yield ta
        else:
            if self.msg_content.startswith("[AUTO-SUMMARY]"):
                yield Label(f"  ∑ {self.msg_content[14:].strip()[:200]}", classes="msg-summary")
            else:
                yield Label(f"  {self.msg_content}", classes="msg-system")

    def update_content(self, text: str) -> None:
        try: self.query_one(TextArea).load_text(text)
        except NoMatches: pass

    def on_click(self, event) -> None:
        """Tell the App this block was clicked, passing self as the clicked block."""
        # Post a custom message up to the App
        self.app.handle_block_click(self, shift=getattr(event, "shift", False))

    def get_selected_text(self) -> str:
        try:
            sel = self.query_one(TextArea).selected_text
            return sel if sel else ""
        except (NoMatches, AttributeError):
            return ""

    def get_text(self) -> str:
        try: return self.query_one(TextArea).text
        except NoMatches: return self.msg_content

    def set_range_highlight(self, on: bool) -> None:
        self._range_selected = on
        if on:
            self.styles.border_left = ("tall", "#e0af68")
            self.styles.background  = "#1e1a10"
        else:
            # FIX: empty string is not a valid color — must use "transparent"
            self.styles.border_left = ("none", "transparent")
            self.styles.background  = "#1a1b26"

# ── DoModeScreen — aicli do prompt dialog (F9) ───────────────────────────────

class DoModeScreen(Screen):
    """Modal dialog for aicli do — OS function calling from the TUI.

    Press F9 to open. Type a natural language task (e.g. "play music and open
    hacker news"). Press Enter to execute, Escape to cancel.

    The result is shown as an assistant message in the active chat.
    Toggle Ctrl+Y to switch between auto-confirm and dry-run preview modes.
    """

    BINDINGS = [
        Binding("escape",  "cancel",         "Cancel",      priority=True),
        Binding("enter",   "submit",          "Execute",     priority=True),
        Binding("ctrl+y",  "toggle_confirm",  "Toggle confirm", priority=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._auto_confirm: bool = True   # default: auto-confirm (non-interactive)

    def compose(self) -> ComposeResult:
        with Vertical(id="do-modal"):
            yield Label("⚡ aicli do — OS Function Calling", id="do-title")
            yield Label(
                "Type a task for the AI to perform using OS tools:\n"
                "  'play music and open hacker news'\n"
                "  'send email to alice@example.com say hi'\n"
                "  'notify me the build is done'\n"
                "  'check system memory'\n\n"
                "Enter=run  Escape=cancel  Ctrl+Y=toggle confirm mode",
                id="do-hint",
            )
            yield Input(placeholder="e.g. play music and open hacker news", id="do-input")
            yield Label("⚡ Mode: auto-confirm (tools run immediately)", id="do-mode-label")

    def on_mount(self) -> None:
        self.query_one("#do-input", Input).focus()

    def action_toggle_confirm(self) -> None:
        """Ctrl+Y — toggle between auto-confirm and dry-run preview."""
        self._auto_confirm = not self._auto_confirm
        label = self.query_one("#do-mode-label", Label)
        if self._auto_confirm:
            label.update("⚡ Mode: auto-confirm (tools run immediately)")
        else:
            label.update("👁  Mode: dry-run preview (shows plan, no execution)")

    def action_submit(self) -> None:
        prompt = self.query_one("#do-input", Input).value.strip()
        if not prompt:
            self.dismiss(None)
            return
        # Pass (prompt, auto_confirm) tuple so caller knows which mode was chosen
        self.dismiss((prompt, self._auto_confirm))

    def action_cancel(self) -> None:
        self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.action_submit()


# ── Main App ──────────────────────────────────────────────────────────────────

class AicliTUI(App):
    # CSS is set in __init__ from the saved theme
    CSS = build_css(THEMES["tokyo-night"])  # default; overridden in __init__

    # priority=True forces these to fire even when Input/TextArea has focus.
    # Keys chosen to avoid terminal conflicts:
    #   F1        = help  (not ctrl+h which = backspace in many terminals)
    #   ctrl+9    = settings  (not ctrl+, which = zoom in many terminals)
    BINDINGS = [
        Binding("ctrl+q",  "quit",            "Quit",        priority=True),
        Binding("ctrl+n",  "new_session",     "New",         priority=True),
        Binding("ctrl+d",  "delete",          "Delete",      priority=True),
        Binding("ctrl+e",  "export_md",       "Export md",   priority=True),
        Binding("ctrl+j",  "export_json",     "Backup",      priority=True),
        Binding("ctrl+i",  "import_sessions", "Import",      priority=True),
        Binding("ctrl+w",  "toggle_web",      "Web",         priority=True),
        Binding("ctrl+x",  "toggle_ctx",      "Ctx",         priority=True),
        Binding("ctrl+s",  "summarize",       "Summarize",   priority=True),
        Binding("ctrl+k",  "pin",             "Pin",         priority=True),
        Binding("ctrl+b",  "bulk",            "Bulk",        priority=True),
        Binding("ctrl+y",  "copy_msg",        "Copy",        priority=True),
        Binding("ctrl+o",  "open_location",   "Exports",     priority=True),
        Binding("f1",      "help",            "Help",        priority=True),
        Binding("ctrl+9",  "settings",        "Settings",    priority=True),
        Binding("f2",  "range_pick",   "Range pick",  priority=True),
        Binding("f3",  "cycle_theme",  "Theme",        priority=True),
        Binding("ctrl+r",  "copy_range",   "Copy range",  priority=True),
        Binding("f4",      "export_session_file", "Export session", priority=True),
        Binding("f5",      "import_session_file", "Import session", priority=True),
        Binding("f6",      "sync_now",            "Sync",           priority=True),
        Binding("f7",      "open_graph",          "Graph",          priority=True),
        Binding("f8",      "send",         "Send",  priority=True),
        Binding("escape",  "clear_range",  "Clear", show=False),
        Binding("enter",      "send",    "Send",    show=False, priority=True),
        Binding("ctrl+enter", "newline",  "Newline", show=False),
        Binding("f9",      "do_mode",     "Do",      priority=True),  # aicli do
        # ── Vim-style navigation (v1.5.3) ─────────────────────────────────────
        Binding("j",       "scroll_down",        "↓",       show=False),
        Binding("k",       "scroll_up",          "↑",       show=False),
        Binding("G",       "scroll_bottom",      "⤓",       show=False),
        Binding("g",       "scroll_top",         "⤒",       show=False),
        Binding("slash",   "search_sessions",    "/",       show=False),
    ]

    active_session_id:   reactive[str | None] = reactive(None)
    active_session_name: reactive[str]        = reactive("—")
    web_enabled:  reactive[bool] = reactive(False)
    ctx_enabled:  reactive[bool] = reactive(False)
    is_thinking:  reactive[bool] = reactive(False)
    bulk_mode:    reactive[bool] = reactive(False)

    def __init__(self, initial_session=None, model=None, no_history=False):
        super().__init__()
        self._initial_session  = initial_session
        self._model            = model
        self._no_history       = no_history
        self._pipeline         = None
        self._config           = None
        self._conn             = None
        self._sessions: list[dict] = []
        self._search_filter    = ""
        self._pinned:   set[str] = set()
        self._selected: set[str] = set()
        self._keys             = load_keys()
        self._last_block: MessageBlock | None = None
        self._theme, self._theme_name = load_theme()
        # Apply saved theme at startup
        AicliTUI.CSS = build_css(self._theme)
        self._range_start: MessageBlock | None = None
        self._range_mode = False
        self._shift_held  = False
        self._range_picking = False  # True while user is click-picking a range (F2)
        self._dd_pending = False     # True after first 'd' — waiting for second 'd' (vim dd)
        self._vim_mode = True        # j/k/G/g active when prompt input is NOT focused

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def on_mount(self) -> None:
        self._load_backend()
        self._load_pinned()
        self._refresh_session_list()
        if self._initial_session:
            self._open_session_by_name(self._initial_session)
        elif self._sessions:
            self._open_session(self._sessions[0])
        self._update_status()
        # Focus the prompt input so Enter/F8 work immediately
        self.call_after_refresh(lambda: self.query_one("#prompt-input", Input).focus())

    def _load_backend(self) -> None:
        from aicli.config import load_config
        from aicli.db.chat_db import get_connection
        from aicli.providers.pipeline import ProviderPipeline
        self._config = load_config()
        self._conn   = get_connection()
        try:
            self._pipeline = ProviderPipeline(
                provider_chain=self._config["provider_chain"],
                cooldown_seconds=self._config["cooldown_seconds"],
                max_retries_per_provider=self._config["max_retries_per_provider"],
                show_provider=False,
            )
        except Exception:
            self._pipeline = None

    def _pinned_file(self) -> Path:
        try:
            from aicli.config import CONFIG_DIR
            return CONFIG_DIR / "tui_pinned.json"
        except Exception:
            return Path.home() / ".config" / "aicli" / "tui_pinned.json"

    def _load_pinned(self) -> None:
        try: self._pinned = set(json.loads(self._pinned_file().read_text()).get("pinned",[]))
        except Exception: self._pinned = set()

    def _save_pinned(self) -> None:
        try: self._pinned_file().write_text(json.dumps({"pinned":list(self._pinned)}))
        except Exception: pass

    def _db_path(self) -> Path:
        try:
            from aicli.config import CONFIG_DIR
            return CONFIG_DIR / "sessions.db"
        except Exception:
            return Path.home() / ".config" / "aicli" / "sessions.db"

    # ── Layout ─────────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal():
            with Vertical(id="sidebar"):
                yield Static("  aicli sessions", id="sidebar-header")
                yield HotkeyInput(placeholder="  Search sessions…", id="session-search")
                yield Static(" BULK: click=select  ^D=del  ^E=export  ^K=pin  ^B=exit", id="bulk-toolbar")
                yield ListView(id="session-list")
                yield Static("", id="provider-status")
            with Vertical(id="main"):
                yield ScrollableContainer(id="chat-scroll")
                yield Static("", id="thinking")
                yield Static(self._flags_text(), id="flags-bar")
                yield Static("", id="range-status")
                with Horizontal(id="input-area"):
                    yield HotkeyInput(placeholder="  Type a message and click ▶ to send", id="prompt-input")
                    yield Button("▶", id="send-arrow", variant="primary")
        yield StatusBar(id="status-bar")
        yield Footer()

    def _flags_text(self) -> str:
        parts = []
        if self.bulk_mode: parts.append(f"BULK — {len(self._selected)} selected")
        if self.web_enabled: parts.append("🌐 web ON")
        if self.ctx_enabled: parts.append("🧠 ctx ON")
        return "  " + "   ".join(parts) if parts else "  web off   ctx off   (F1=help  F2=range select  Ctrl+9=settings)"

    # ── Session management ──────────────────────────────────────────────────────

    def _sorted_sessions(self, sessions):
        return [s for s in sessions if s["id"] in self._pinned] + \
               [s for s in sessions if s["id"] not in self._pinned]

    def _refresh_session_list(self) -> None:
        from aicli.db.chat_db import list_sessions
        self._sessions = list_sessions(self._conn)
        lv = self.query_one("#session-list", ListView)
        lv.clear()
        q = self._search_filter.lower()
        for s in self._sorted_sessions(self._sessions):
            name = s["name"] or s["id"][:8]
            if q and q not in name.lower(): continue
            count = s.get("message_count", 0)
            is_pin = s["id"] in self._pinned
            is_sel = s["id"] in self._selected
            item = ListItem(
                Label("📌" if is_pin else "  ", classes="session-pin-icon"),
                Label(name[:19], classes="session-name"),
                Label(f"{count} msg{'s' if count!=1 else ''}", classes="session-count"),
            )
            item.data = s  # type: ignore
            if is_pin: item.add_class("pinned")
            if is_sel and self.bulk_mode: item.add_class("selected-bulk")
            lv.append(item)

    def _open_session(self, session: dict) -> None:
        self.active_session_id   = session["id"]
        self.active_session_name = session.get("name") or session["id"][:8]
        self._render_chat()
        self.sub_title = self.active_session_name

    def _open_session_by_name(self, name: str) -> None:
        for s in self._sessions:
            if s["name"] == name or s["id"] == name:
                self._open_session(s); return
        self._create_session(name)

    def _create_session(self, name=None) -> None:
        import uuid
        from aicli.db.chat_db import ensure_session
        new_id   = str(uuid.uuid4())
        new_name = name or f"session-{new_id[:8]}"
        ensure_session(self._conn, new_id, new_name)
        self._refresh_session_list()
        for s in self._sessions:
            if s["id"] == new_id: self._open_session(s); break

    def _render_chat(self) -> None:
        if not self.active_session_id: return
        from aicli.db.chat_db import load_messages
        scroll = self.query_one("#chat-scroll", ScrollableContainer)
        scroll.remove_children()
        if not self._no_history:
            for idx, msg in enumerate(load_messages(self._conn, self.active_session_id)):
                scroll.mount(MessageBlock(msg["role"], str(msg["content"]), msg.get("timestamp",""), msg_index=idx))
        self.call_after_refresh(scroll.scroll_end, animate=False)

    def _update_status(self) -> None:
        try:
            bar = self.query_one("#status-bar", StatusBar)
            bar.provider = (self._pipeline.last_provider if self._pipeline else None) or "—"
            bar.web_on = self.web_enabled; bar.ctx_on = self.ctx_enabled
        except NoMatches: pass
        try:
            panel = self.query_one("#provider-status", Static)
            if not self._pipeline: panel.update("  no providers"); return
            lines = []
            for st in self._pipeline.states:
                dot = "●" if st.is_available() else "○"
                extra = f" {st.remaining_cooldown():.0f}s" if not st.is_available() else ""
                extra += f" ({st.failure_count}✗)" if st.failure_count else ""
                lines.append(f"  {dot} {st.provider.name}{extra}")
            panel.update("\n".join(lines))
        except (NoMatches, AttributeError): pass

    def _set_range_status(self, msg: str) -> None:
        """Show/hide the range status bar above the input."""
        try:
            w = self.query_one("#range-status", Static)
            if msg:
                w.update(f"  ▶ {msg}")
                w.add_class("visible")
            else:
                w.update("")
                w.remove_class("visible")
        except Exception:
            pass

    def _update_flags_bar(self) -> None:
        try: self.query_one("#flags-bar", Static).update(self._flags_text())
        except NoMatches: pass

    def _append_message(self, role: str, content: str) -> None:
        scroll = self.query_one("#chat-scroll", ScrollableContainer)
        scroll.mount(MessageBlock(role, content))
        self.call_after_refresh(scroll.scroll_end, animate=False)

    # ── Events ─────────────────────────────────────────────────────────────────

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        session = getattr(event.item, "data", None)
        if not session: return
        if self.bulk_mode:
            sid = session["id"]
            self._selected.discard(sid) if sid in self._selected else self._selected.add(sid)
            self._refresh_session_list(); self._update_flags_bar()
        else:
            self._open_session(session)

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "session-search":
            self._search_filter = event.value
            self._refresh_session_list()

    def handle_block_click(self, clicked: "MessageBlock", shift: bool = False) -> None:
        """Called by MessageBlock.on_click — reliable widget-level context."""
        is_shift = shift or self._shift_held

        try:
            scroll = self.query_one("#chat-scroll", ScrollableContainer)
            all_blocks = list(scroll.query(MessageBlock))
        except Exception:
            all_blocks = []

        def _complete_range(start_block, end_block):
            a, b = start_block.msg_index, end_block.msg_index
            lo, hi = min(a, b), max(a, b)
            for blk in all_blocks:
                blk.set_range_highlight(lo <= blk.msg_index <= hi)
            self._range_mode    = True
            self._range_picking = False
            self._range_start   = None
            n = hi - lo + 1
            self._set_range_status(
                f"Range #{lo}–#{hi} ({n} blocks) — Ctrl+Y copies  |  Esc clears")

        if self._range_picking:
            if self._range_start is None:
                self._range_start = clicked
                clicked.set_range_highlight(True)
                self._set_range_status(
                    f"Start: #{clicked.msg_index} — now click the END message")
            elif clicked is self._range_start:
                return
            else:
                _complete_range(self._range_start, clicked)
        elif is_shift and self._range_start is not None and clicked is not self._range_start:
            _complete_range(self._range_start, clicked)
        else:
            if self._range_mode:
                for blk in all_blocks:
                    blk.set_range_highlight(False)
                self._range_mode    = False
                self._range_picking = False
            self._range_start = clicked

    def on_descendant_focus(self, event) -> None:
        node = event.widget
        while node:
            if isinstance(node, MessageBlock):
                self._last_block = node
                break
            node = getattr(node, "parent", None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Fires when user presses Enter in any Input widget."""
        if event.input.id == "prompt-input":
            event.stop()
            self.action_send()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Send button and ▶ arrow click."""
        if event.button.id in ("send-btn", "send-arrow"):
            self.action_send()


    def action_send(self) -> None:
        inp = self.query_one("#prompt-input", Input)
        prompt = inp.value.strip()
        if not prompt or self.is_thinking or not self.active_session_id: return
        inp.value = ""
        self.run_worker(self._send_message(prompt), exclusive=False)

    def action_newline(self) -> None:
        inp = self.query_one("#prompt-input", Input)
        inp.value += "\n"

    def action_do_mode(self) -> None:
        """F9 — open aicli do prompt dialog for OS function calling."""
        self.push_screen(DoModeScreen(), self._handle_do_result)

    def _handle_do_result(self, result: tuple | None) -> None:
        """Callback from DoModeScreen — run the do command and show output in chat.

        result is either None (cancelled) or (prompt, auto_confirm) tuple.
        """
        if not result:
            return
        prompt, auto_confirm = result
        if not prompt:
            return
        self.run_worker(self._run_do_command(prompt, auto_confirm=auto_confirm), exclusive=False)

    async def _run_do_command(self, prompt: str, *, auto_confirm: bool = True) -> None:
        """Execute aicli do in a worker thread and display result as a chat message.

        auto_confirm=True  — tools execute immediately (default, non-interactive)
        auto_confirm=False — dry_run=True, shows the plan without executing
        """
        mode_label = "[do]" if auto_confirm else "[do dry-run]"
        self._append_message("user", f"{mode_label} {prompt}")
        try:
            import io
            import contextlib
            from aicli.tools.executor import run_do_command
            output_buf = io.StringIO()
            with contextlib.redirect_stdout(output_buf):
                await run_do_command(
                    prompt_parts=(prompt,),
                    auto_confirm=auto_confirm,
                    dry_run=not auto_confirm,   # dry_run when not auto-confirming
                    quiet=False,
                    model=None,
                    lite=False,
                    role=None,
                )
            result = output_buf.getvalue().strip()
            self._append_message("assistant", result or "(do: no output)")
        except ImportError:
            self._append_message("system", "[do] OS tools not available (lite install)")
        except Exception as exc:
            self._append_message("system", f"[do error] {exc}")

    async def _send_message(self, prompt: str) -> None:
        if not self._pipeline:
            self._append_message("system", "[Error: no provider available]"); return
        from aicli.db.chat_db import save_message, load_messages
        save_message(self._conn, self.active_session_id, "user", prompt)
        scroll = self.query_one("#chat-scroll", ScrollableContainer)
        _existing = list(scroll.query(MessageBlock))
        scroll.mount(MessageBlock("user", prompt, msg_index=len(_existing)))
        self.call_after_refresh(scroll.scroll_end, animate=False)
        self.is_thinking = True
        try:
            t = self.query_one("#thinking", Static)
            t.update("  ◌ thinking..."); t.add_class("visible")
        except NoMatches: pass

        from aicli.role import get_role
        role = get_role("default")
        msgs = []
        if role.system_prompt: msgs.append({"role":"system","content":role.system_prompt})
        if self.web_enabled:
            try:
                from aicli.web import web_search
                wb = await web_search(prompt)
                if wb: msgs.append({"role":"system","content":wb})
            except Exception: pass
        if self.ctx_enabled:
            try:
                from aicli.config import CHROMA_DIR
                from aicli.context.retriever import ContextRetriever
                cb = ContextRetriever(CHROMA_DIR).retrieve(prompt)
                if cb: msgs.append({"role":"system","content":cb})
            except Exception: pass
        for m in load_messages(self._conn, self.active_session_id):
            if isinstance(m["content"], str): msgs.append({"role":m["role"],"content":m["content"]})

        _existing2 = list(scroll.query(MessageBlock))
        stream_block = MessageBlock("assistant", "", msg_index=len(_existing2))
        await scroll.mount(stream_block)
        self.call_after_refresh(scroll.scroll_end, animate=False)
        acc = []
        try:
            async for chunk in self._pipeline.stream(msgs, model=self._model):
                acc.append(chunk)
                stream_block.update_content("".join(acc))
                self.call_after_refresh(scroll.scroll_end, animate=False)
        except Exception as e:
            acc = [f"[Error: {e}]"]; stream_block.update_content(acc[0])

        response = "".join(acc).strip()
        save_message(self._conn, self.active_session_id, "assistant", response)
        try: self.query_one("#thinking", Static).remove_class("visible")
        except NoMatches: pass
        self.is_thinking = False
        self.call_after_refresh(scroll.scroll_end, animate=False)
        self._refresh_session_list(); self._update_status()
        # Auto-sync to exports after every exchange
        self.call_later(self._auto_sync)

    # ── Actions ────────────────────────────────────────────────────────────────

    def action_new_session(self): self._create_session()

    def action_delete(self) -> None:
        from aicli.db.chat_db import delete_session
        targets = list(self._selected) if self.bulk_mode and self._selected \
                  else ([self.active_session_id] if self.active_session_id else [])
        if not targets: return
        for sid in targets: delete_session(self._conn, sid); self._pinned.discard(sid)
        self._selected.clear(); self._save_pinned()
        self.active_session_id = None
        self._refresh_session_list()
        if self._sessions: self._open_session(self._sessions[0])
        else: self.query_one("#chat-scroll", ScrollableContainer).remove_children()
        self._append_message("system", f"[Deleted {len(targets)} session(s)]")

    def action_export_md(self) -> None:
        from aicli.db.chat_db import load_messages, load_latest_summary
        from aicli.handlers.export import _to_markdown
        targets = [s for s in self._sessions if s["id"] in self._selected] \
                  if self.bulk_mode and self._selected \
                  else ([s for s in self._sessions if s["id"]==self.active_session_id]
                        if self.active_session_id else [])
        if not targets: return
        d = _exports_dir()
        for s in targets:
            sid = s["id"]; name = s.get("name") or sid[:8]
            content = _to_markdown(name, sid, load_messages(self._conn, sid),
                                   load_latest_summary(self._conn, sid), include_summary=True)
            p = d / f"{name}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.md"
            p.write_text(content)
        self._append_message("system", f"[Exported {len(targets)} session(s) → {d}]")

    def action_export_json(self) -> None:
        from aicli.db.chat_db import load_messages, load_latest_summary
        data = []
        for s in self._sessions:
            sid = s["id"]
            msgs = load_messages(self._conn, sid)
            data.append({"id":sid,"name":s.get("name") or sid[:8],"pinned":sid in self._pinned,
                         "messages":[{"role":m["role"],"content":str(m["content"]),
                                      "timestamp":m.get("timestamp","")} for m in msgs],
                         "summary":load_latest_summary(self._conn, sid)})
        d = _exports_dir()
        p = d / f"backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
        p.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        self._append_message("system", f"[Backup → {p.name}  ({d})]")

    def action_import_sessions(self) -> None:
        import glob
        from aicli.db.chat_db import ensure_session, save_message, save_summary
        d = _exports_dir()
        files = sorted(glob.glob(str(d / "backup-*.json")))
        if not files: self._append_message("system","[No backup found. Use Ctrl+J first]"); return
        try: data = json.loads(Path(files[-1]).read_text())
        except Exception as e: self._append_message("system",f"[Import error: {e}]"); return
        existing = {s["id"] for s in self._sessions}
        imported = skipped = 0
        for entry in data:
            sid = entry["id"]
            if sid in existing: skipped+=1; continue
            ensure_session(self._conn, sid, entry.get("name",sid[:8]))
            for m in entry.get("messages",[]): save_message(self._conn,sid,m["role"],m["content"])
            if entry.get("summary"): save_summary(self._conn,sid,entry["summary"],0,len(entry.get("messages",[])))
            if entry.get("pinned"): self._pinned.add(sid)
            imported+=1
        self._save_pinned(); self._refresh_session_list()
        self._append_message("system",f"[Imported {imported}, skipped {skipped}]")

    def action_pin(self) -> None:
        targets = list(self._selected) if self.bulk_mode and self._selected \
                  else ([self.active_session_id] if self.active_session_id else [])
        for sid in targets:
            self._pinned.discard(sid) if sid in self._pinned else self._pinned.add(sid)
        self._save_pinned(); self._refresh_session_list()

    def action_bulk(self) -> None:
        self.bulk_mode = not self.bulk_mode
        if not self.bulk_mode: self._selected.clear()
        self._refresh_session_list(); self._update_flags_bar()
        try:
            tb = self.query_one("#bulk-toolbar", Static)
            tb.add_class("visible") if self.bulk_mode else tb.remove_class("visible")
        except NoMatches: pass

    def action_toggle_web(self):
        self.web_enabled = not self.web_enabled; self._update_flags_bar(); self._update_status()

    def action_toggle_ctx(self):
        self.ctx_enabled = not self.ctx_enabled; self._update_flags_bar(); self._update_status()

    def action_copy_msg(self) -> None:
        """Tier 0: range -> Tier 1: selection -> Tier 2: whole block -> Tier 3: last assistant."""
        try:
            scroll = self.query_one("#chat-scroll", ScrollableContainer)
            all_blocks = list(scroll.query(MessageBlock))
        except Exception:
            all_blocks = []
        text = ""

        if self._range_mode:
            parts = [b.get_text() for b in all_blocks if b._range_selected]
            text = "\n\n---\n\n".join(parts)
            for b in all_blocks:
                b.set_range_highlight(False)
            self._range_mode = False
            self._range_start = None

        if not text and self._last_block:
            text = self._last_block.get_selected_text()
        if not text and self._last_block:
            text = self._last_block.get_text()
        if not text:
            for b in reversed(all_blocks):
                if b.msg_role == "assistant":
                    text = b.get_text()
                    break
        if not text:
            self._append_message("system", "[Nothing to copy]")
            return

        status = _copy_to_system_clipboard(text)
        preview = text[:60].replace("\n", " ")
        if len(text) > 60:
            preview += "..."
        self._append_message("system", "[" + status + "  |  " + preview + "]")

    def action_copy_range(self) -> None:
        """Type a range like 3-7 in the input box then press Ctrl+R."""
        try:
            val = self.query_one("#prompt-input", Input).value.strip()
        except Exception:
            self._append_message("system", "[Type a range like 3-7 in the input box first]"); return

        import re
        # NOTE: use raw string so \d is a literal regex digit class, not escape
        m = re.match(r"^(\d+)[-](\d+)$", val)
        if not m:
            self._append_message("system",
                f"[Invalid range '{val}' — type e.g. 3-7 in the input box then Ctrl+R]"); return

        lo, hi = int(m.group(1)), int(m.group(2))
        if lo > hi: lo, hi = hi, lo

        try:
            scroll = self.query_one("#chat-scroll", ScrollableContainer)
            all_blocks = list(scroll.query(MessageBlock))
        except Exception:
            all_blocks = []

        selected = [b for b in all_blocks if lo <= b.msg_index <= hi]
        if not selected:
            self._append_message("system", f"[No messages in range #{lo}–#{hi}]"); return

        text = "\n\n---\n\n".join(b.get_text() for b in selected)
        try:
            self.query_one("#prompt-input", Input).value = ""
        except Exception:
            pass
        status = _copy_to_system_clipboard(text)
        self._append_message("system",
            f"[Copied #{lo}–#{hi} ({len(selected)} blocks)  |  {status}]")

    def action_export_session_file(self) -> None:
        """Ctrl+X: export current session as individual .md + .json files (Obsidian-style)."""
        from aicli.db.chat_db import load_messages, load_latest_summary
        if not self.active_session_id:
            self._set_range_status("No active session"); return
        sid  = self.active_session_id
        name = self.active_session_name or sid[:8]
        safe = "".join(c if c.isalnum() or c in "-_ " else "_" for c in name).strip()
        d    = _exports_dir()
        msgs = load_messages(self._conn, sid)
        summ = load_latest_summary(self._conn, sid)

        # Markdown file
        md_lines = [f"# {name}\n", f"session_id: {sid}\n\n---\n\n"]
        if summ: md_lines.append(f"> **Summary:** {summ}\n\n---\n\n")
        for m in msgs:
            role = "**You**" if m["role"] == "user" else "**Assistant**"
            ts   = m.get("timestamp","")[:16]
            md_lines.append(f"{role}  {ts}\n\n{m['content']}\n\n---\n\n")
        ts_str = datetime.now().strftime("%Y%m%d-%H%M%S")
        md_path = d / f"{safe}__{ts_str}.md"
        md_path.write_text("".join(md_lines), encoding="utf-8")

        import json as _json
        data = {"id": sid, "name": name, "summary": summ, "exported_at": ts_str,
                "messages": [{"role": m["role"], "content": str(m["content"]),
                               "timestamp": m.get("timestamp","")} for m in msgs]}
        json_path   = d / f"{safe}__{ts_str}.json"
        json_latest = d / f"{safe}__latest.json"
        json_path.write_text(_json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        json_latest.write_text(_json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

        self._append_message("system",
            f"[F4 Export \u2713  {safe}__{ts_str}  \u2192  {d}]")

    def action_import_session_file(self) -> None:
        """
        F5: import the most recent .json from exports INTO the current session.
        Clears current session messages and replaces with imported content.
        The session ID/name in the file is ignored — we write into whatever
        session is currently active.
        """
        import glob, json as _json
        from aicli.db.chat_db import save_message, save_summary, delete_session, ensure_session

        if not self.active_session_id:
            self._append_message("system", "[F5 Import: no active session — open a session first]")
            return

        d     = _exports_dir()
        files = sorted(glob.glob(str(d / "*.json")))
        files = [f for f in files if not Path(f).name.startswith("backup-")]
        if not files:
            self._append_message("system", "[F5 Import: no .json files in exports folder — use F4 to export first]")
            return

        latest = max(files, key=lambda f: Path(f).stat().st_mtime)
        try:
            data = _json.loads(Path(latest).read_text(encoding="utf-8"))
        except Exception as e:
            self._append_message("system", f"[F5 Import error reading file: {e}]")
            return

        messages = data.get("messages", [])
        if not messages:
            self._append_message("system", f"[F5 Import: file has no messages — {Path(latest).name}]")
            return

        # Overwrite current session: delete all its messages then re-save from file
        sid  = self.active_session_id
        name = self.active_session_name
        delete_session(self._conn, sid)
        ensure_session(self._conn, sid, name)
        for m in messages:
            save_message(self._conn, sid, m["role"], m["content"])
        if data.get("summary"):
            save_summary(self._conn, sid, data["summary"], 0, len(messages))

        # Re-render current session in place — no navigation
        self._render_chat()
        self._refresh_session_list()
        self._append_message("system",
            f"[F5 Import \u2713  {len(messages)} messages from '{data.get('name','?')}'  \u2190  {Path(latest).name}]")


    def _auto_sync(self) -> None:
        """Called after every message — silently sync to exports."""
        try:
            sync_all_to_exports()
        except Exception:
            pass

    def action_sync_now(self) -> None:
        """F6: manual full sync to exports folder."""
        try:
            status = sync_all_to_exports()
            d = _sync_dir()
            self._append_message("system", f"[F6 Sync \u2713  {status}  \u2192  {d}]")
        except Exception as e:
            self._append_message("system", f"[F6 Sync error: {e}]")

    def action_open_graph(self) -> None:
        """F7: open the graph server in the browser at localhost:7337."""
        graph_url = "http://localhost:7337/"
        try:
            subprocess.Popen(["xdg-open", graph_url])
            self._append_message("system", f"[F7 Graph → {graph_url}  (run: aicli graph)]")
        except Exception:
            self._append_message("system", f"[F7 Graph: open {graph_url} in browser  |  run: aicli graph]")

    def action_open_location(self) -> None:
        folder = str(_exports_dir())
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", folder])
            elif sys.platform.startswith("linux"):
                try:
                    subprocess.Popen(["xdg-open", folder])
                except FileNotFoundError:
                    self._append_message("system", f"[Exports folder: {folder}]"); return
            elif sys.platform == "win32":
                subprocess.Popen(["explorer", folder])
            self._append_message("system", f"[Opened: {folder}]")
        except Exception:
            self._append_message("system", f"[Exports folder: {folder}]")

    def action_summarize(self) -> None:
        if self.active_session_id: self.run_worker(self._run_summarize(), exclusive=False)

    async def _run_summarize(self) -> None:
        if not self._pipeline or not self.active_session_id: return
        from aicli.db.chat_db import load_messages, save_summary
        from aicli.context.manager import ContextManager
        messages = load_messages(self._conn, self.active_session_id)
        if len(messages) < 4: self._append_message("system","[Need ≥4 messages]"); return
        self._append_message("system","[ Summarizing… ]")
        ctx = ContextManager(session_id=self.active_session_id, pipeline=self._pipeline,
                             config=self._config or {}, db_path=None)
        try:
            summary = await ctx.summarize_now()
            if summary:
                save_summary(self._conn, self.active_session_id, summary, 0, len(messages))
                self._append_message("system",f"[AUTO-SUMMARY] {summary}")
        except Exception as e: self._append_message("system",f"[Summarize failed: {e}]")

    def on_key(self, event) -> None:
        # Cancel dd-pending on any key that isn't 'd'
        if self._dd_pending and event.key != "d":
            self._dd_pending = False
            self._set_range_status("")
        # Shift tracking — works because on_key fires for modifier-only keypresses
        if event.key in ("shift", "shift+shift"):
            self._shift_held = True
        # Force-handle keys that Input/TextArea swallow even with priority=True
        if event.key == "f1":
            event.stop(); event.prevent_default()
            self.push_screen(HelpScreen(self._keys))
        elif event.key == "f2":
            event.stop(); event.prevent_default()
            self.action_range_pick()
        elif event.key == "f3":
            event.stop(); event.prevent_default()
            self.action_cycle_theme()
        elif event.key == "f4":
            event.stop(); event.prevent_default()
            self.action_export_session_file()
        elif event.key == "f5":
            event.stop(); event.prevent_default()
            self.action_import_session_file()
        elif event.key == "f6":
            event.stop(); event.prevent_default()
            self.action_sync_now()
        elif event.key == "f7":
            event.stop(); event.prevent_default()
            self.action_open_graph()
        elif event.key == "f8":
            event.stop(); event.prevent_default()
            self.action_send()
        elif event.key == "ctrl+9":
            event.stop(); event.prevent_default()
            def _cb(k):
                if k:
                    self._keys = k
                    self._append_message("system","[Settings saved — restart to apply]")
            self.push_screen(SettingsScreen(self._keys), _cb)
        elif event.key == "f2":
            event.stop(); event.prevent_default()
            self.action_range_pick()

    def on_key_up(self, event) -> None:
        if "shift" in event.key:
            self._shift_held = False


    # ── Vim-style navigation (v1.5.3) ──────────────────────────────────────────

    def _is_input_focused(self) -> bool:
        """Return True if prompt input or session search has focus — vim keys disabled then."""
        try:
            focused = self.focused
            return focused is not None and getattr(focused, "id", "") in (
                "prompt-input", "session-search"
            )
        except Exception:
            return False

    def action_scroll_down(self) -> None:
        """j — scroll chat down one step."""
        if self._is_input_focused():
            return
        try:
            self.query_one("#chat-scroll").scroll_relative(y=3, animate=False)
        except Exception:
            pass

    def action_scroll_up(self) -> None:
        """k — scroll chat up one step."""
        if self._is_input_focused():
            return
        try:
            self.query_one("#chat-scroll").scroll_relative(y=-3, animate=False)
        except Exception:
            pass

    def action_scroll_bottom(self) -> None:
        """G — jump to bottom of chat."""
        if self._is_input_focused():
            return
        try:
            self.query_one("#chat-scroll").scroll_end(animate=False)
        except Exception:
            pass

    def action_scroll_top(self) -> None:
        """g — jump to top of chat (gg equivalent — single g for simplicity)."""
        if self._is_input_focused():
            return
        try:
            self.query_one("#chat-scroll").scroll_home(animate=False)
        except Exception:
            pass

    def action_search_sessions(self) -> None:
        """/ — focus the session search box."""
        try:
            self.query_one("#session-search", Input).focus()
        except Exception:
            pass

    def action_delete_session_dd(self) -> None:
        """d — first press arms dd; second press within 1s deletes (vim dd)."""
        if self._is_input_focused():
            return
        if self._dd_pending:
            # Second d — execute delete
            self._dd_pending = False
            self._set_range_status("")
            self.action_delete()
        else:
            # First d — arm and wait
            self._dd_pending = True
            self._set_range_status("dd — press d again to delete session  |  any other key cancels")
            # Auto-cancel after 1.5 seconds
            self.set_timer(1.5, self._cancel_dd)

    def _cancel_dd(self) -> None:
        if self._dd_pending:
            self._dd_pending = False
            self._set_range_status("")

    def action_range_pick(self) -> None:
        """F2: enter click-to-pick range mode. Click start then end message."""
        try:
            scroll = self.query_one("#chat-scroll", ScrollableContainer)
            for b in scroll.query(MessageBlock):
                b.set_range_highlight(False)
        except Exception:
            pass
        self._range_mode    = False
        self._range_picking = True
        self._range_start   = None
        self._set_range_status("Range pick ON — click the START message")

    def _apply_theme(self) -> None:
        """Reapply TextArea inline colors after a theme change."""
        t = self._theme
        try:
            scroll = self.query_one("#chat-scroll", ScrollableContainer)
            for block in scroll.query(MessageBlock):
                try:
                    ta = block.query_one(TextArea)
                    if block.msg_role == "user":
                        ta.styles.background = t["bg_msg"]
                        ta.styles.color = t["text"]
                    elif block.msg_role == "assistant":
                        ta.styles.background = t["bg"]
                        ta.styles.color = t["text_dim"]
                except Exception:
                    pass
        except Exception:
            pass
        self.refresh(layout=True)

    def action_cycle_theme(self) -> None:
        """F3: cycle to next theme and save."""
        idx = THEME_KEYS.index(self._theme_name) if self._theme_name in THEME_KEYS else 0
        next_name = THEME_KEYS[(idx + 1) % len(THEME_KEYS)]
        self._theme_name = next_name
        self._theme = THEMES[next_name]
        AicliTUI.CSS = build_css(self._theme)
        save_theme(next_name)
        self._apply_theme()
        self._set_range_status(f"Theme: {self._theme['name']}  (F3 to cycle)")
        self.call_later(lambda: self._set_range_status(""))

    def action_clear_range(self) -> None:
        try:
            for b in self.query_one("#chat-scroll", ScrollableContainer).query(MessageBlock):
                b.set_range_highlight(False)
        except Exception:
            pass
        self._range_mode    = False
        self._range_picking = False
        self._range_start   = None
        self._set_range_status("")

    def action_help(self) -> None:
        self.push_screen(HelpScreen(self._keys))

    def action_settings(self) -> None:
        def on_close(new_keys):
            if new_keys:
                self._keys = new_keys
                self._append_message("system","[Settings saved — restart TUI to apply new keys]")
        self.push_screen(SettingsScreen(self._keys), on_close)

# ── Entry point ───────────────────────────────────────────────────────────────

def run_tui(session=None, model=None, no_history=False):
    AicliTUI(initial_session=session, model=model, no_history=no_history).run()
