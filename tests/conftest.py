"""
tests/conftest.py — Shared pytest fixtures for the full aicli test suite.

Covers:
  - tmp_db         : temporary SQLite database path
  - tmp_config_dir : temporary config directory
  - mock_pipeline  : MockPipeline (no API calls)
  - tmp_chroma     : temporary ChromaDB ContextRetriever (skipped if absent)
  - session_factory: factory for writing session JSON files in tmp_path
  - graph_links_factory: factory for writing graph_links.json in tmp_path
"""
import json
import os
import tempfile
import pytest
from pathlib import Path


# ── Database / config ─────────────────────────────────────────────────────────

@pytest.fixture
def tmp_db():
    """Temporary SQLite database file. Deleted after test."""
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    yield Path(f.name)
    os.unlink(f.name)


@pytest.fixture
def tmp_config_dir(tmp_path):
    """Temporary config directory (plain tmp_path alias for clarity)."""
    return tmp_path


# ── Mock pipeline ─────────────────────────────────────────────────────────────

class MockPipeline:
    """Mock ProviderPipeline — no actual API calls.

    Used in: test_aicli.py, test_integration.py, test_tui_pure.py
    """
    last_provider = "mock"

    async def stream(self, messages, model=None, requires_vision=False):
        for chunk in ["Mock ", "response."]:
            yield chunk

    async def complete(self, messages, model=None):
        return "Mock summary: user discussed topic X, AI responded with Y."


@pytest.fixture
def mock_pipeline():
    """Pytest fixture version of MockPipeline."""
    return MockPipeline()


# ── ChromaDB ──────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_chroma(tmp_path):
    """Temporary ChromaDB ContextRetriever. Skipped if chromadb not installed."""
    try:
        from aicli.context.retriever import ContextRetriever
        return ContextRetriever(tmp_path / "chroma")
    except ImportError:
        pytest.skip("chromadb not installed")


# ── Session JSON factory ──────────────────────────────────────────────────────

@pytest.fixture
def session_factory(tmp_path):
    """Factory that writes session JSON files to tmp_path.

    Usage:
        def test_something(session_factory):
            path, sid = session_factory("My Project")
            path, sid = session_factory("Other", messages=[...], latest=False)

    Returns: (Path, session_id)
    """
    counter = [0]

    def _make(
        name: str,
        messages: list = None,
        session_id: str = None,
        summary: str = "",
        exported_at: str = "2026-03-08T12:00:00",
        latest: bool = True,
    ):
        counter[0] += 1
        sid = session_id or f"sess-{counter[0]:04d}"
        msgs = messages or [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        safe_name = name.lower().replace(" ", "-")
        suffix = "__latest.json" if latest else f"__20260308-{counter[0]:06d}.json"
        p = tmp_path / f"{safe_name}{suffix}"
        p.write_text(
            json.dumps({
                "id": sid,
                "name": name,
                "messages": msgs,
                "summary": summary,
                "exported_at": exported_at,
            }),
            encoding="utf-8",
        )
        return p, sid

    return _make


# ── Graph links factory ───────────────────────────────────────────────────────

@pytest.fixture
def graph_links_factory(tmp_path):
    """Write graph_links.json to tmp_path and return its Path.

    Usage:
        def test_something(graph_links_factory):
            p = graph_links_factory(
                links=[{"id": "l1", "source": "a", "target": "b"}],
                names={"a": {"name": "Session A", "notes": ""}},
            )
    """
    def _make(links=None, names=None):
        data = {
            "links": links or [],
            "names": names or {},
            "saved": "2026-03-08T14:00:00",
        }
        p = tmp_path / "graph_links.json"
        p.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return p

    return _make


# ── Performance: session-scoped imports ───────────────────────────────────────
#
# WHY THIS EXISTS:
# importing aicli.app triggers chromadb, textual, rich, httpx, tiktoken.
# Without a session fixture each test file reimports the whole stack.
# With `aicli_cli` below, the import happens once per `pytest` run.
#
# USAGE in any test:
#   def test_something(aicli_cli):
#       runner = CliRunner()
#       result = runner.invoke(aicli_cli, ["ask", "--help"])

import sys
from unittest.mock import MagicMock as _MagicMock


def _maybe_stub_textual():
    """Install MagicMock stubs for textual if not already present.

    Called at conftest load time so test_tui_pure and test_comprehensive
    can import aicli.tui without textual being installed.
    The stubs match the real textual API surface used by tui.py.
    """
    if "textual" in sys.modules:
        return  # already loaded (real or existing stub)

    class _Base:
        def __init__(self, *a, **kw): pass
    class _App(_Base):
        CSS = ""
        BINDINGS = []
    class _Input(_Base): pass
    class _Static(_Base): pass
    class _Screen(_Base): pass

    # Binding stub: plain object with .key — no MagicMock to avoid coroutine GC warnings
    class _BindingStub:
        __slots__ = ("key", "action", "description", "show", "priority")
        def __init__(self, *a, **kw):
            self.key         = a[0] if a else kw.get("key", "")
            self.action      = a[1] if len(a) > 1 else kw.get("action", "")
            self.description = a[2] if len(a) > 2 else kw.get("description", "")
            self.show        = kw.get("show", True)
            self.priority    = kw.get("priority", False)
        def __repr__(self):
            return f"Binding(key={self.key!r})"

    stubs = {
        "textual":              _MagicMock(name="textual"),
        "textual.app":          _MagicMock(name="textual.app", App=_App, ComposeResult=object),
        "textual.binding":      _MagicMock(name="textual.binding", Binding=_BindingStub),
        "textual.containers":   _MagicMock(name="textual.containers",
                                           Horizontal=_Base, Vertical=_Base,
                                           ScrollableContainer=_Base),
        "textual.css.query":    _MagicMock(name="textual.css.query", NoMatches=Exception),
        "textual.reactive":     _MagicMock(name="textual.reactive", reactive=lambda v: v),
        "textual.screen":       _MagicMock(name="textual.screen", Screen=_Screen),
        "textual.widgets":      _MagicMock(name="textual.widgets",
                                           Button=_Base, Footer=_Base, Header=_Base,
                                           Input=_Input, Label=_Base, ListItem=_Base,
                                           ListView=_Base, Static=_Static, TextArea=_Base),
    }
    sys.modules.update(stubs)

_maybe_stub_textual()

# ── Module-level preload ───────────────────────────────────────────────────────
#
# Import aicli.app NOW at conftest load time (before any test file is collected).
# This populates sys.modules with aicli.app + all transitive imports
# (chromadb, textual, rich, httpx, tiktoken) exactly ONCE per pytest run.
#
# Without this, every test file that does `from aicli.app import cli` pays
# the full cold-import cost independently (3–8 s each × 9 files = up to 70 s).
# The noqa suppresses F401 "imported but unused" — it's used via sys.modules.
try:
    import aicli.app as _aicli_app_preload  # noqa: F401
except Exception:
    pass  # skip if editable install not ready


@pytest.fixture(scope="session")
def aicli_cli():
    """
    Import aicli.app.cli once per pytest session — the main performance win.

    Without this, each test file does its own cold import of aicli.app which
    re-triggers chromadb, textual, rich, httpx, tiktoken loading.
    Using this fixture cuts 3–8s from a full pytest run.

    Usage:
        def test_something(aicli_cli):
            from click.testing import CliRunner
            result = CliRunner().invoke(aicli_cli, ["cmd", "--help"])
    """
    from aicli.app import cli
    return cli


@pytest.fixture(scope="session")
def aicli_app():
    """Import aicli.app module once per session for patching module-level names."""
    import aicli.app as _app
    return _app


# ── Pytest markers ────────────────────────────────────────────────────────────

def pytest_configure(config):
    """Register custom markers for selective test runs.

    Usage:
        pytest tests/ -q -m "not slow"        # skip HTTP server tests
        pytest tests/ -q -m "fast"            # only unit tests
        pytest tests/ -q -m "serve"           # only serve tests
    """
    config.addinivalue_line("markers", "slow: marks tests as slow (HTTP servers, real I/O)")
    config.addinivalue_line("markers", "fast: marks tests as fast pure unit tests")
    config.addinivalue_line("markers", "serve: marks tests that start HTTP servers")
