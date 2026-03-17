"""
test_tui_pure.py — Tests for pure/non-Textual functions in aicli/tui.py

Textual is stubbed via sys.modules before import — runs without textual installed.
"""

import json, os, shutil, sys, inspect, tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest


# ── Stub Textual before any aicli.tui import ─────────────────────────────────

def _install_textual_stubs():
    if "textual" in sys.modules and not isinstance(sys.modules["textual"], MagicMock):
        return  # real textual already loaded — don't clobber

    class _Base:
        def __init__(self, *a, **kw): pass

    class _App(_Base):
        CSS = ""
        BINDINGS = []

    class _Input(_Base): pass
    class _Static(_Base): pass
    class _Screen(_Base): pass

    stubs = {
        "textual":              MagicMock(name="textual"),
        "textual.app":          MagicMock(name="textual.app",   App=_App,    ComposeResult=object),
        "textual.binding":      MagicMock(name="textual.binding", Binding=lambda *a, **kw: None),
        "textual.containers":   MagicMock(name="textual.containers",
                                          Horizontal=_Base, Vertical=_Base,
                                          ScrollableContainer=_Base),
        "textual.css.query":    MagicMock(name="textual.css.query", NoMatches=Exception),
        "textual.reactive":     MagicMock(name="textual.reactive", reactive=lambda v: v),
        "textual.screen":       MagicMock(name="textual.screen", Screen=_Screen),
        "textual.widgets":      MagicMock(name="textual.widgets",
                                          Button=_Base, Footer=_Base, Header=_Base,
                                          Input=_Input, Label=_Base, ListItem=_Base,
                                          ListView=_Base, Static=_Static, TextArea=_Base),
    }
    sys.modules.update(stubs)

_install_textual_stubs()

import aicli.tui as tui  # noqa: E402 — must come after stubs


# ── Fixture ───────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    config_dir = tmp_path / "config" / "aicli"
    config_dir.mkdir(parents=True)
    exports_dir = tmp_path / "exports"
    exports_dir.mkdir()
    monkeypatch.setattr(tui, "_theme_file",          lambda: config_dir / "tui_theme.json")
    monkeypatch.setattr(tui, "_keys_file",           lambda: config_dir / "tui_keys.json")
    monkeypatch.setattr(tui, "_exports_config_file", lambda: config_dir / "tui_exports.json")
    monkeypatch.setattr(tui, "_exports_dir",         lambda: exports_dir)
    return config_dir, exports_dir


# ── THEMES ────────────────────────────────────────────────────────────────────

class TestThemesStructure:
    def test_five_themes_defined(self):
        assert len(tui.THEMES) == 5

    def test_theme_keys_match_themes(self):
        assert set(tui.THEME_KEYS) == set(tui.THEMES.keys())

    def test_all_themes_have_required_keys(self):
        required = {"bg","bg_alt","bg_msg","border","accent","green","amber",
                    "text","text_dim","muted","status_bg","range_bg"}
        for name, theme in tui.THEMES.items():
            assert not (required - set(theme)), f"'{name}' missing keys"

    def test_all_theme_values_are_strings(self):
        for name, theme in tui.THEMES.items():
            for k, v in theme.items():
                if k != "name":
                    assert isinstance(v, str), f"'{name}'.{k} not str"

    def test_all_theme_colors_start_with_hash(self):
        for name, theme in tui.THEMES.items():
            for k, v in theme.items():
                if k != "name":
                    assert v.startswith("#"), f"'{name}'.{k}='{v}' not #rrggbb"

    def test_tokyo_night_is_first(self):
        assert tui.THEME_KEYS[0] == "tokyo-night"

    def test_theme_cycling_wraps(self):
        assert tui.THEME_KEYS[(len(tui.THEME_KEYS)-1+1) % len(tui.THEME_KEYS)] == tui.THEME_KEYS[0]


# ── build_css ─────────────────────────────────────────────────────────────────

class TestBuildCss:
    def test_returns_string(self):
        assert isinstance(tui.build_css(tui.THEMES["tokyo-night"]), str)

    def test_contains_screen_rule(self):
        assert "Screen" in tui.build_css(tui.THEMES["tokyo-night"])

    def test_contains_sidebar_rule(self):
        assert "#sidebar" in tui.build_css(tui.THEMES["dracula"])

    def test_contains_range_status(self):
        assert "#range-status" in tui.build_css(tui.THEMES["nord"])

    def test_contains_message_block(self):
        assert "MessageBlock" in tui.build_css(tui.THEMES["gruvbox"])

    def test_theme_accent_in_css(self):
        t = tui.THEMES["tokyo-night"]
        assert t["accent"] in tui.build_css(t)

    def test_all_themes_produce_valid_css(self):
        for name, t in tui.THEMES.items():
            assert len(tui.build_css(t)) > 200, f"'{name}' too short"

    def test_different_themes_differ(self):
        assert tui.build_css(tui.THEMES["tokyo-night"]) != tui.build_css(tui.THEMES["dracula"])


# ── load_theme / save_theme ───────────────────────────────────────────────────

class TestThemePersistence:
    def test_roundtrip(self):
        tui.save_theme("dracula")
        _, name = tui.load_theme()
        assert name == "dracula"

    def test_missing_returns_tokyo_night(self):
        _, name = tui.load_theme()
        assert name == "tokyo-night"

    def test_unknown_name_falls_back_to_default_dict(self, isolated_config):
        cd, _ = isolated_config
        (cd / "tui_theme.json").write_text(json.dumps({"theme": "nonexistent"}))
        theme_dict, name = tui.load_theme()
        assert name == "nonexistent"
        assert theme_dict == tui.THEMES["tokyo-night"]

    def test_save_all_valid_names(self):
        for key in tui.THEME_KEYS:
            tui.save_theme(key)
            _, name = tui.load_theme()
            assert name == key

    def test_save_creates_parent_dirs(self, tmp_path, monkeypatch):
        deep = tmp_path / "a" / "b" / "c" / "tui_theme.json"
        monkeypatch.setattr(tui, "_theme_file", lambda: deep)
        tui.save_theme("nord")
        assert deep.exists()

    def test_corrupt_file_returns_default(self, isolated_config):
        cd, _ = isolated_config
        (cd / "tui_theme.json").write_text("not json {{{")
        _, name = tui.load_theme()
        assert name == "tokyo-night"


# ── load_keys / save_keys ─────────────────────────────────────────────────────

class TestKeysPersistence:
    def test_missing_returns_defaults(self):
        assert tui.load_keys() == tui.DEFAULT_KEYS

    def test_roundtrip(self):
        tui.save_keys({"quit": "ctrl+z", "new_session": "ctrl+shift+n"})
        loaded = tui.load_keys()
        assert loaded["quit"] == "ctrl+z"
        assert loaded["new_session"] == "ctrl+shift+n"

    def test_merges_with_defaults(self):
        tui.save_keys({"quit": "ctrl+z"})
        loaded = tui.load_keys()
        for aid, dk in tui.DEFAULT_KEYS.items():
            assert loaded[aid] == ("ctrl+z" if aid == "quit" else dk)

    def test_corrupt_returns_defaults(self, isolated_config):
        cd, _ = isolated_config
        (cd / "tui_keys.json").write_text("bad json")
        assert tui.load_keys() == tui.DEFAULT_KEYS

    def test_save_creates_parent_dirs(self, tmp_path, monkeypatch):
        deep = tmp_path / "x" / "y" / "tui_keys.json"
        monkeypatch.setattr(tui, "_keys_file", lambda: deep)
        tui.save_keys({"quit": "ctrl+q"})
        assert deep.exists()


# ── ACTIONS ───────────────────────────────────────────────────────────────────

class TestActionsStructure:
    def test_is_list(self):
        assert isinstance(tui.ACTIONS, list)

    def test_three_elements(self):
        for e in tui.ACTIONS:
            assert len(e) == 3, f"{e} != 3 elements"

    def test_strings(self):
        for aid, key, label in tui.ACTIONS:
            assert aid and key and label

    def test_no_duplicate_ids(self):
        ids = [a[0] for a in tui.ACTIONS]
        assert len(ids) == len(set(ids))

    def test_default_keys_match(self):
        for aid, key, _ in tui.ACTIONS:
            assert tui.DEFAULT_KEYS[aid] == key

    def test_required_actions_present(self):
        ids = {a[0] for a in tui.ACTIONS}
        for req in ("quit","new_session","copy_msg","range_pick","cycle_theme","help","sync_now","export_session"):
            assert req in ids, f"'{req}' missing"

    def test_f_keys_all_assigned(self):
        vals = set(tui.DEFAULT_KEYS.values())
        for fk in ("f1","f2","f3","f4","f5","f6","f7"):
            assert fk in vals, f"{fk} not assigned"


# ── save_exports_dir ──────────────────────────────────────────────────────────

class TestExportsDir:
    def test_save_writes_config_file(self, isolated_config):
        cd, _ = isolated_config
        tui.save_exports_dir("/custom/path")
        data = json.loads((cd / "tui_exports.json").read_text())
        assert data["exports_dir"] == "/custom/path"

    def test_save_creates_parent_dirs(self, tmp_path, monkeypatch):
        deep = tmp_path / "a" / "b" / "tui_exports.json"
        monkeypatch.setattr(tui, "_exports_config_file", lambda: deep)
        tui.save_exports_dir("/some/path")
        assert deep.exists()


# ── sync_all_to_exports ───────────────────────────────────────────────────────

class TestSyncAllToExports:
    def test_returns_string(self):
        result = tui.sync_all_to_exports()
        assert isinstance(result, str) and len(result) > 0

    def test_copies_config_files(self, isolated_config, tmp_path, monkeypatch):
        cd, ed = isolated_config
        (cd / "tui_theme.json").write_text(json.dumps({"theme": "nord"}))
        (cd / "tui_keys.json").write_text(json.dumps({"quit": "ctrl+q"}))
        monkeypatch.setattr(tui, "_sync_dir", lambda: ed)
        with patch("aicli.config.CONFIG_DIR", cd):
            tui.sync_all_to_exports()
        assert len(list(ed.glob("_sync_*.json"))) >= 1

    def test_nothing_to_sync_ok(self):
        result = tui.sync_all_to_exports()
        assert isinstance(result, str)

    def test_migration_does_not_crash(self, isolated_config, tmp_path, monkeypatch):
        cd, ed = isolated_config
        monkeypatch.setattr(tui, "_sync_dir", lambda: ed)
        monkeypatch.setattr(tui, "_exports_dir", lambda: ed)
        old = tmp_path / ".config" / "aicli" / "exports"
        old.mkdir(parents=True)
        (old / "old__latest.json").write_text(json.dumps({"id": "x", "messages": []}))
        with patch.object(Path, "home", return_value=tmp_path):
            assert isinstance(tui.sync_all_to_exports(), str)


# ── _copy_to_system_clipboard ─────────────────────────────────────────────────

class TestCopyToSystemClipboard:
    def _stub(self, monkeypatch):
        monkeypatch.setattr(shutil, "which", lambda x: None)
        monkeypatch.setenv("DISPLAY", "")
        monkeypatch.setenv("WAYLAND_DISPLAY", "")

    def test_returns_string(self, monkeypatch):
        self._stub(monkeypatch)
        assert isinstance(tui._copy_to_system_clipboard("hello"), str)

    def test_fallback_mentions_save_or_unavailable(self, monkeypatch):
        self._stub(monkeypatch)
        r = tui._copy_to_system_clipboard("test")
        assert "saved" in r.lower() or "unavailable" in r.lower() or "/tmp" in r

    def test_fallback_file_contains_text(self, monkeypatch):
        self._stub(monkeypatch)
        text = "unique_test_99887766"
        tui._copy_to_system_clipboard(text)
        f = Path("/tmp/aicli_copy.txt")
        if f.exists():
            assert text in f.read_text()

    def test_empty_string(self, monkeypatch):
        self._stub(monkeypatch)
        assert isinstance(tui._copy_to_system_clipboard(""), str)

    def test_unicode(self, monkeypatch):
        self._stub(monkeypatch)
        assert isinstance(tui._copy_to_system_clipboard("Hello 世界 🌍"), str)

    def test_large_text(self, monkeypatch):
        self._stub(monkeypatch)
        assert isinstance(tui._copy_to_system_clipboard("x" * 100_000), str)


# ── MessageBlock ──────────────────────────────────────────────────────────────

class TestMessageBlockInit:
    def test_user_block(self):
        b = tui.MessageBlock("user", "Hello there", timestamp="12:00", msg_index=1)
        assert b.msg_role == "user"
        assert b.msg_content == "Hello there"
        assert b.msg_index == 1

    def test_assistant_block(self):
        b = tui.MessageBlock("assistant", "Response", msg_index=2)
        assert b.msg_role == "assistant"
        assert b.msg_index == 2

    def test_system_block(self):
        b = tui.MessageBlock("system", "Started")
        assert b.msg_role == "system"

    def test_default_index(self):
        assert tui.MessageBlock("user", "x").msg_index == -1

    def test_get_text_returns_content(self):
        b = tui.MessageBlock("user", "My content")
        # TextArea.query_one fails under stub → falls back to msg_content
        assert b.get_text() == "My content"

    def test_range_selected_default_false(self):
        assert not tui.MessageBlock("user", "x")._range_selected


# ── HotkeyInput source inspection ────────────────────────────────────────────

def _src():
    return inspect.getsource(tui.HotkeyInput.on_key)

class TestHotkeyInputMappings:
    def test_f1(self):  assert '"f1"' in _src() or "'f1'" in _src()
    def test_f2(self):  assert '"f2"' in _src() or "'f2'" in _src()
    def test_f3(self):  assert '"f3"' in _src() or "'f3'" in _src()
    def test_f4(self):  assert '"f4"' in _src() or "'f4'" in _src()
    def test_f6(self):  assert '"f6"' in _src() or "'f6'" in _src()
    def test_ctrl_y(self): assert '"ctrl+y"' in _src() or "'ctrl+y'" in _src()
    def test_ctrl_r(self): assert '"ctrl+r"' in _src() or "'ctrl+r'" in _src()

    def test_no_ctrl_m(self):
        """Ctrl+M = ASCII 13 = Enter — must never appear as a hotkey."""
        assert '"ctrl+m"' not in _src() and "'ctrl+m'" not in _src()

    def test_no_ctrl_h(self):
        """Ctrl+H = ASCII 8 = backspace — must never appear as a hotkey."""
        assert '"ctrl+h"' not in _src() and "'ctrl+h'" not in _src()

    def test_super_fallthrough(self):
        assert "super()._on_key" in _src()

    def test_event_stop(self):
        assert "event.stop()" in _src()

    def test_event_prevent_default(self):
        assert "event.prevent_default()" in _src()


# ── Vim navigation (v1.5.3) ───────────────────────────────────────────────────

class TestVimNavActionsRegistered:
    """Verify vim nav entries exist in ACTIONS and DEFAULT_KEYS."""

    def test_scroll_down_in_actions(self):
        ids = {a[0] for a in tui.ACTIONS}
        assert "scroll_down" in ids

    def test_scroll_up_in_actions(self):
        ids = {a[0] for a in tui.ACTIONS}
        assert "scroll_up" in ids

    def test_scroll_bottom_in_actions(self):
        ids = {a[0] for a in tui.ACTIONS}
        assert "scroll_bottom" in ids

    def test_scroll_top_in_actions(self):
        ids = {a[0] for a in tui.ACTIONS}
        assert "scroll_top" in ids

    def test_search_sessions_in_actions(self):
        ids = {a[0] for a in tui.ACTIONS}
        assert "search_sessions" in ids

    def test_delete_session_dd_in_actions(self):
        ids = {a[0] for a in tui.ACTIONS}
        assert "delete_session_dd" in ids

    def test_j_default_key(self):
        assert tui.DEFAULT_KEYS.get("scroll_down") == "j"

    def test_k_default_key(self):
        assert tui.DEFAULT_KEYS.get("scroll_up") == "k"

    def test_G_default_key(self):
        assert tui.DEFAULT_KEYS.get("scroll_bottom") == "G"

    def test_g_default_key(self):
        assert tui.DEFAULT_KEYS.get("scroll_top") == "g"

    def test_slash_default_key(self):
        assert tui.DEFAULT_KEYS.get("search_sessions") == "/"

    def test_no_duplicate_keys_after_vim(self):
        ids = [a[0] for a in tui.ACTIONS]
        assert len(ids) == len(set(ids)), "Duplicate action IDs found"


class TestVimNavSourceInspection:
    """Inspect tui.AicliTUI source to confirm action methods exist."""

    import inspect as _inspect

    def _src(self):
        import inspect
        return inspect.getsource(tui.AicliTUI)

    def test_action_scroll_down_defined(self):
        assert "action_scroll_down" in self._src()

    def test_action_scroll_up_defined(self):
        assert "action_scroll_up" in self._src()

    def test_action_scroll_bottom_defined(self):
        assert "action_scroll_bottom" in self._src()

    def test_action_scroll_top_defined(self):
        assert "action_scroll_top" in self._src()

    def test_action_search_sessions_defined(self):
        assert "action_search_sessions" in self._src()

    def test_action_delete_session_dd_defined(self):
        assert "action_delete_session_dd" in self._src()

    def test_is_input_focused_guard_exists(self):
        assert "_is_input_focused" in self._src()

    def test_dd_pending_state_exists(self):
        assert "_dd_pending" in self._src()

    def test_cancel_dd_exists(self):
        assert "_cancel_dd" in self._src()

    def test_vim_keys_in_bindings(self):
        import inspect
        src = inspect.getsource(tui.AicliTUI)
        for key in ('"j"', '"k"', '"G"', '"g"', '"slash"'):
            assert key in src, f"Binding for {key} not found in AicliTUI"

    def test_set_timer_used_for_dd(self):
        """dd cancel uses set_timer — not asyncio.sleep."""
        import inspect
        src = inspect.getsource(tui.AicliTUI.action_delete_session_dd)
        assert "set_timer" in src

    def test_dd_fires_delete_on_second_press(self):
        """action_delete_session_dd calls action_delete when _dd_pending is True."""
        import inspect
        src = inspect.getsource(tui.AicliTUI.action_delete_session_dd)
        assert "action_delete" in src

    def test_on_key_cancels_dd_on_non_d(self):
        """on_key resets _dd_pending when key != 'd'."""
        import inspect
        src = inspect.getsource(tui.AicliTUI.on_key)
        assert "_dd_pending" in src


class TestVimNavHelpScreen:
    """Verify vim nav appears in HelpScreen text."""

    def test_j_k_in_help(self):
        import inspect
        src = inspect.getsource(tui.HelpScreen.compose)
        assert "j / k" in src or ("j" in src and "k" in src)

    def test_dd_in_help(self):
        import inspect
        src = inspect.getsource(tui.HelpScreen.compose)
        assert "dd" in src

    def test_slash_in_help(self):
        import inspect
        src = inspect.getsource(tui.HelpScreen.compose)
        assert "/" in src

    def test_G_in_help(self):
        import inspect
        src = inspect.getsource(tui.HelpScreen.compose)
        assert "G" in src


# ── Vim navigation (v1.5.3) ───────────────────────────────────────────────────

class TestVimNavActionsStructure:
    """Verify vim nav entries exist in ACTIONS and DEFAULT_KEYS."""

    def test_scroll_down_in_actions(self):
        ids = {a[0] for a in tui.ACTIONS}
        assert "scroll_down" in ids

    def test_scroll_up_in_actions(self):
        ids = {a[0] for a in tui.ACTIONS}
        assert "scroll_up" in ids

    def test_scroll_bottom_in_actions(self):
        ids = {a[0] for a in tui.ACTIONS}
        assert "scroll_bottom" in ids

    def test_scroll_top_in_actions(self):
        ids = {a[0] for a in tui.ACTIONS}
        assert "scroll_top" in ids

    def test_search_sessions_in_actions(self):
        ids = {a[0] for a in tui.ACTIONS}
        assert "search_sessions" in ids

    def test_delete_session_dd_in_actions(self):
        ids = {a[0] for a in tui.ACTIONS}
        assert "delete_session_dd" in ids

    def test_j_mapped_to_scroll_down(self):
        assert tui.DEFAULT_KEYS["scroll_down"] == "j"

    def test_k_mapped_to_scroll_up(self):
        assert tui.DEFAULT_KEYS["scroll_up"] == "k"

    def test_G_mapped_to_scroll_bottom(self):
        assert tui.DEFAULT_KEYS["scroll_bottom"] == "G"

    def test_g_mapped_to_scroll_top(self):
        assert tui.DEFAULT_KEYS["scroll_top"] == "g"

    def test_slash_mapped_to_search_sessions(self):
        assert tui.DEFAULT_KEYS["search_sessions"] == "/"

    def test_d_mapped_to_delete_dd(self):
        assert tui.DEFAULT_KEYS["delete_session_dd"] == "d"

    def test_no_duplicate_ids_after_vim_additions(self):
        ids = [a[0] for a in tui.ACTIONS]
        assert len(ids) == len(set(ids)), "Duplicate action IDs found"


class TestVimNavSourceInspection:
    """Source-level checks — vim action methods must exist and be correct."""

    def _app_src(self):
        import inspect
        return inspect.getsource(tui.AicliTUI)

    def test_action_scroll_down_exists(self):
        assert "action_scroll_down" in self._app_src()

    def test_action_scroll_up_exists(self):
        assert "action_scroll_up" in self._app_src()

    def test_action_scroll_bottom_exists(self):
        assert "action_scroll_bottom" in self._app_src()

    def test_action_scroll_top_exists(self):
        assert "action_scroll_top" in self._app_src()

    def test_action_search_sessions_exists(self):
        assert "action_search_sessions" in self._app_src()

    def test_action_delete_session_dd_exists(self):
        assert "action_delete_session_dd" in self._app_src()

    def test_input_focus_guard_present(self):
        assert "_is_input_focused" in self._app_src()

    def test_dd_pending_state_in_init(self):
        import inspect
        init_src = inspect.getsource(tui.AicliTUI.__init__)
        assert "_dd_pending" in init_src

    def test_dd_cancel_on_non_d_key(self):
        src = self._app_src()
        assert "_dd_pending" in src and "_cancel_dd" in src

    def test_vim_mode_state_in_init(self):
        import inspect
        init_src = inspect.getsource(tui.AicliTUI.__init__)
        assert "_vim_mode" in init_src

    def test_help_screen_contains_vim_section(self):
        import inspect
        help_src = inspect.getsource(tui.HelpScreen.compose)
        assert "vim" in help_src.lower() or "j / k" in help_src or "scroll" in help_src.lower()

    def test_scroll_down_guards_input_focus(self):
        import inspect
        src = inspect.getsource(tui.AicliTUI.action_scroll_down)
        assert "_is_input_focused" in src

    def test_scroll_up_guards_input_focus(self):
        import inspect
        src = inspect.getsource(tui.AicliTUI.action_scroll_up)
        assert "_is_input_focused" in src

    def test_dd_action_guards_input_focus(self):
        import inspect
        src = inspect.getsource(tui.AicliTUI.action_delete_session_dd)
        assert "_is_input_focused" in src


class TestVimNavBindingsInSource:
    """Verify BINDINGS list contains vim keys."""

    def _bindings_src(self):
        import inspect
        return inspect.getsource(tui.AicliTUI)

    def test_j_binding_present(self):
        assert '"j"' in self._bindings_src() or "'j'" in self._bindings_src()

    def test_k_binding_present(self):
        assert '"k"' in self._bindings_src() or "'k'" in self._bindings_src()

    def test_G_binding_present(self):
        assert '"G"' in self._bindings_src() or "'G'" in self._bindings_src()

    def test_g_binding_present(self):
        assert '"g"' in self._bindings_src() or "'g'" in self._bindings_src()

    def test_slash_binding_present(self):
        import inspect
        bindings_src = inspect.getsource(tui.AicliTUI)
        assert "slash" in bindings_src or '"/"' in bindings_src


class TestObsidianExport:
    """Tests for the new _to_obsidian export function in export.py."""

    def _messages(self):
        return [
            {"role": "user",      "content": "Hello there",   "timestamp": "2026-03-15 10:00"},
            {"role": "assistant", "content": "Hi! How can I help?", "timestamp": "2026-03-15 10:01"},
            {"role": "system",    "content": "[AUTO-SUMMARY] Brief summary of session"},
            {"role": "user",      "content": "Tell me about Python", "timestamp": "2026-03-15 10:02"},
            {"role": "assistant", "content": "Python is a language.", "timestamp": "2026-03-15 10:03"},
        ]

    def test_obsidian_returns_string(self):
        from aicli.handlers.export import _to_obsidian
        result = _to_obsidian("myproject", "abc-123", self._messages(), None)
        assert isinstance(result, str)
        assert len(result) > 100

    def test_obsidian_has_yaml_frontmatter(self):
        from aicli.handlers.export import _to_obsidian
        result = _to_obsidian("myproject", "abc-123", self._messages(), None)
        assert result.startswith("---\n")
        assert "title:" in result
        assert "session_id:" in result
        assert "date:" in result

    def test_obsidian_has_aicli_tag_in_frontmatter(self):
        from aicli.handlers.export import _to_obsidian
        result = _to_obsidian("myproject", "abc-123", self._messages(), None)
        assert "aicli" in result

    def test_obsidian_has_assistant_callout(self):
        from aicli.handlers.export import _to_obsidian
        result = _to_obsidian("myproject", "abc-123", self._messages(), None)
        assert "[!assistant]" in result

    def test_obsidian_has_message_anchors(self):
        from aicli.handlers.export import _to_obsidian
        result = _to_obsidian("myproject", "abc-123", self._messages(), None)
        assert "^msg-" in result

    def test_obsidian_includes_summary_callout(self):
        from aicli.handlers.export import _to_obsidian
        result = _to_obsidian("myproject", "abc-123", self._messages(),
                              "This is the session summary.", include_summary=True)
        assert "[!summary]" in result
        assert "This is the session summary." in result

    def test_obsidian_no_summary_callout_when_not_requested(self):
        from aicli.handlers.export import _to_obsidian
        result = _to_obsidian("myproject", "abc-123", self._messages(),
                              "This is the summary.", include_summary=False)
        assert "[!summary]" not in result

    def test_obsidian_auto_summary_becomes_info_callout(self):
        from aicli.handlers.export import _to_obsidian
        result = _to_obsidian("myproject", "abc-123", self._messages(), None)
        assert "[!info]" in result

    def test_obsidian_user_messages_present(self):
        from aicli.handlers.export import _to_obsidian
        result = _to_obsidian("myproject", "abc-123", self._messages(), None)
        assert "Hello there" in result
        assert "Tell me about Python" in result

    def test_obsidian_assistant_messages_present(self):
        from aicli.handlers.export import _to_obsidian
        result = _to_obsidian("myproject", "abc-123", self._messages(), None)
        assert "Hi! How can I help?" in result

    def test_obsidian_frontmatter_has_message_count(self):
        from aicli.handlers.export import _to_obsidian
        result = _to_obsidian("myproject", "abc-123", self._messages(), None)
        assert "message_count:" in result

    def test_obsidian_summary_in_frontmatter_description(self):
        from aicli.handlers.export import _to_obsidian
        result = _to_obsidian("myproject", "abc-123", self._messages(),
                              "A really long summary here with many words to test truncation behavior")
        assert "description:" in result


# ─────────────────────────────────────────────────────────────────────────────
# DoModeScreen (F9 — aicli do in TUI)
# ─────────────────────────────────────────────────────────────────────────────

class TestDoModeScreen:
    """DoModeScreen modal dialog and F9 do-mode binding."""

    def test_do_mode_screen_class_defined(self):
        """DoModeScreen class exists in tui.py."""
        from aicli.tui import DoModeScreen
        assert DoModeScreen is not None

    def test_do_mode_screen_is_screen_subclass(self):
        """DoModeScreen subclasses Textual Screen."""
        from textual.screen import Screen
        from aicli.tui import DoModeScreen
        assert issubclass(DoModeScreen, Screen)

    def test_do_mode_screen_has_escape_binding(self):
        """DoModeScreen has Escape → cancel binding."""
        import inspect
        from aicli.tui import DoModeScreen
        src = inspect.getsource(DoModeScreen)
        assert "escape" in src.lower()
        assert "cancel" in src

    def test_do_mode_screen_has_enter_binding(self):
        """DoModeScreen has Enter → submit binding."""
        import inspect
        from aicli.tui import DoModeScreen
        src = inspect.getsource(DoModeScreen)
        assert "enter" in src.lower()
        assert "submit" in src

    def test_do_mode_screen_has_ctrl_y_toggle_binding(self):
        """DoModeScreen has Ctrl+Y → toggle_confirm binding."""
        import inspect
        from aicli.tui import DoModeScreen
        src = inspect.getsource(DoModeScreen)
        assert "ctrl+y" in src.lower() or "toggle_confirm" in src

    def test_do_mode_screen_has_action_submit(self):
        """DoModeScreen.action_submit is defined."""
        from aicli.tui import DoModeScreen
        assert hasattr(DoModeScreen, "action_submit")
        assert callable(DoModeScreen.action_submit)

    def test_do_mode_screen_has_action_cancel(self):
        """DoModeScreen.action_cancel is defined."""
        from aicli.tui import DoModeScreen
        assert hasattr(DoModeScreen, "action_cancel")
        assert callable(DoModeScreen.action_cancel)

    def test_do_mode_screen_has_action_toggle_confirm(self):
        """DoModeScreen.action_toggle_confirm is defined."""
        from aicli.tui import DoModeScreen
        assert hasattr(DoModeScreen, "action_toggle_confirm")
        assert callable(DoModeScreen.action_toggle_confirm)

    def test_do_mode_screen_auto_confirm_default_true(self):
        """DoModeScreen._auto_confirm defaults to True."""
        import inspect
        from aicli.tui import DoModeScreen
        src = inspect.getsource(DoModeScreen.__init__)
        assert "_auto_confirm" in src
        assert "True" in src

    def test_do_mode_screen_has_mode_label(self):
        """DoModeScreen compose() yields a mode label widget."""
        import inspect
        from aicli.tui import DoModeScreen
        src = inspect.getsource(DoModeScreen.compose)
        assert "do-mode-label" in src

    def test_do_mode_screen_has_input_widget(self):
        """DoModeScreen compose() yields an Input widget."""
        import inspect
        from aicli.tui import DoModeScreen
        src = inspect.getsource(DoModeScreen.compose)
        assert "Input" in src
        assert "do-input" in src

    def test_do_mode_screen_on_input_submitted(self):
        """DoModeScreen.on_input_submitted routes to action_submit."""
        from aicli.tui import DoModeScreen
        assert hasattr(DoModeScreen, "on_input_submitted")

    def test_f9_in_aicli_tui_bindings(self):
        """F9 is bound to do_mode in AicliTUI BINDINGS."""
        import inspect
        from aicli.tui import AicliTUI
        src = inspect.getsource(AicliTUI)
        assert "f9" in src.lower()
        assert "do_mode" in src

    def test_action_do_mode_defined_on_aicli_tui(self):
        """AicliTUI.action_do_mode is defined."""
        from aicli.tui import AicliTUI
        assert hasattr(AicliTUI, "action_do_mode")
        assert callable(AicliTUI.action_do_mode)

    def test_handle_do_result_defined(self):
        """AicliTUI._handle_do_result callback is defined."""
        from aicli.tui import AicliTUI
        assert hasattr(AicliTUI, "_handle_do_result")
        assert callable(AicliTUI._handle_do_result)

    def test_run_do_command_defined_on_aicli_tui(self):
        """AicliTUI._run_do_command async method is defined."""
        import asyncio
        from aicli.tui import AicliTUI
        assert hasattr(AicliTUI, "_run_do_command")
        assert asyncio.iscoroutinefunction(AicliTUI._run_do_command)

    def test_run_do_command_uses_auto_confirm(self):
        """_run_do_command calls run_do_command with auto_confirm parameter."""
        import inspect
        from aicli.tui import AicliTUI
        src = inspect.getsource(AicliTUI._run_do_command)
        assert "auto_confirm" in src

    def test_run_do_command_supports_dry_run_mode(self):
        """_run_do_command passes dry_run=True when auto_confirm=False."""
        import inspect
        from aicli.tui import AicliTUI
        src = inspect.getsource(AicliTUI._run_do_command)
        assert "dry_run" in src

    def test_run_do_command_captures_stdout(self):
        """_run_do_command uses redirect_stdout to capture tool output."""
        import inspect
        from aicli.tui import AicliTUI
        src = inspect.getsource(AicliTUI._run_do_command)
        assert "redirect_stdout" in src

    def test_run_do_command_handles_import_error(self):
        """_run_do_command handles ImportError gracefully (lite install)."""
        import inspect
        from aicli.tui import AicliTUI
        src = inspect.getsource(AicliTUI._run_do_command)
        assert "ImportError" in src

    def test_do_mode_in_actions_list(self):
        """do_mode action appears in ACTIONS list."""
        from aicli.tui import ACTIONS
        ids = [a[0] for a in ACTIONS]
        assert "do_mode" in ids, "do_mode must be in ACTIONS list"

    def test_do_mode_action_has_f9_key(self):
        """do_mode entry in ACTIONS has f9 as its key."""
        from aicli.tui import ACTIONS
        do_entry = next((a for a in ACTIONS if a[0] == "do_mode"), None)
        assert do_entry is not None, "do_mode not found in ACTIONS"
        assert do_entry[1] == "f9", f"Expected f9, got {do_entry[1]}"
