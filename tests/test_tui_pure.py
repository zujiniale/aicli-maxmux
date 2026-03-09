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
    return inspect.getsource(tui.HotkeyInput._on_key)

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
