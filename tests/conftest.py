"""
tests/conftest.py — Shared pytest fixtures.
"""
import pytest
import tempfile
import os
from pathlib import Path


@pytest.fixture
def tmp_db():
    """Temporary SQLite database for tests."""
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    yield Path(f.name)
    os.unlink(f.name)


@pytest.fixture
def tmp_config_dir(tmp_path):
    """Temporary config directory."""
    return tmp_path


class MockPipeline:
    """Mock ProviderPipeline — no API calls."""
    last_provider = "mock"

    async def stream(self, messages, model=None):
        for chunk in ["Mock ", "response."]:
            yield chunk

    async def complete(self, messages, model=None):
        return "Mock summary: user discussed topic X, AI responded with Y."


@pytest.fixture
def mock_pipeline():
    return MockPipeline()


@pytest.fixture
def tmp_chroma(tmp_path):
    """Temporary ChromaDB instance for cold-layer tests."""
    try:
        from aicli.context.retriever import ContextRetriever
        return ContextRetriever(tmp_path / "chroma")
    except ImportError:
        pytest.skip("chromadb not installed")
