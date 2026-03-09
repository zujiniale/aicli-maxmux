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
