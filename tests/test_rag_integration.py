"""
test_rag_integration.py — End-to-end ChromaDB roundtrip tests.

These tests exercise the REAL embedding + retrieval pipeline (no ChromaDB mocks).
They are marked @pytest.mark.slow and excluded from `pytest -m "not slow"` so
they never affect the main 777-test count.

Run explicitly with:
    pytest tests/test_rag_integration.py -v
    pytest tests/ -m slow -v

Requirements: pip install aicli[rag]  (chromadb + sentence-transformers)
"""

import pytest
from pathlib import Path


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _retriever(tmp_path):
    """Build a fresh ContextRetriever against a temp chroma dir."""
    from aicli.context.retriever import ContextRetriever
    return ContextRetriever(tmp_path / "chroma")


# ─────────────────────────────────────────────────────────────────────────────
# Basic roundtrip
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.slow
class TestRAGRoundtrip:
    """Core index → retrieve roundtrip with real ChromaDB."""

    def test_index_and_retrieve_chat_session(self, tmp_path):
        """Index a session then retrieve it with a matching query."""
        r = _retriever(tmp_path)
        r.index_session("s1", [
            {"role": "user",      "content": "How does async/await work in Python?"},
            {"role": "assistant", "content": "async/await enables non-blocking coroutines in Python."},
        ])
        result = r.retrieve("async programming coroutines", include_files=False)
        assert result is not None
        assert "async" in result.lower()

    def test_retrieve_returns_none_when_empty(self, tmp_path):
        """Empty store returns None, not an exception."""
        r = _retriever(tmp_path)
        result = r.retrieve("anything", include_files=False, include_chat=True)
        assert result is None

    def test_index_returns_chunk_count(self, tmp_path):
        """index_session returns a positive int (number of chunks indexed)."""
        r = _retriever(tmp_path)
        count = r.index_session("s2", [
            {"role": "user",      "content": "Explain decorators in Python."},
            {"role": "assistant", "content": "Decorators wrap functions to modify their behaviour."},
        ])
        assert isinstance(count, int)
        assert count >= 1

    def test_status_reflects_indexed_data(self, tmp_path):
        """status() shows non-zero chat_chunks after indexing."""
        r = _retriever(tmp_path)
        r.index_session("s3", [
            {"role": "user",      "content": "What is a Python generator?"},
            {"role": "assistant", "content": "A generator yields values lazily using the yield keyword."},
        ])
        s = r.status()
        assert s["chat_chunks"] >= 1

    def test_retrieve_context_block_format(self, tmp_path):
        """Retrieved context starts with 'RELEVANT CONTEXT:' header."""
        r = _retriever(tmp_path)
        r.index_session("s4", [
            {"role": "user",      "content": "Tell me about Docker containers."},
            {"role": "assistant", "content": "Docker containers package apps with their dependencies."},
        ])
        result = r.retrieve("Docker", include_files=False)
        assert result is not None
        assert result.startswith("RELEVANT CONTEXT:")


# ─────────────────────────────────────────────────────────────────────────────
# Multi-session retrieval
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.slow
class TestRAGMultiSession:
    """Cross-session retrieval — the core value of RAG in aicli."""

    def test_retrieves_from_correct_session(self, tmp_path):
        """Query returns content from the semantically matching session."""
        r = _retriever(tmp_path)
        r.index_session("python-session", [
            {"role": "user",      "content": "How do I use list comprehensions?"},
            {"role": "assistant", "content": "List comprehensions provide a concise way to build lists in Python."},
        ])
        r.index_session("docker-session", [
            {"role": "user",      "content": "How do I write a Dockerfile?"},
            {"role": "assistant", "content": "A Dockerfile defines the image build steps using FROM, RUN, COPY instructions."},
        ])
        result = r.retrieve("list comprehension Python syntax", include_files=False)
        assert result is not None
        assert "list" in result.lower() or "comprehension" in result.lower()

    def test_multiple_sessions_both_indexed(self, tmp_path):
        """Both sessions appear in status after indexing."""
        r = _retriever(tmp_path)
        r.index_session("sess-a", [
            {"role": "user", "content": "What is Redis?"},
            {"role": "assistant", "content": "Redis is an in-memory key-value store."},
        ])
        r.index_session("sess-b", [
            {"role": "user", "content": "What is PostgreSQL?"},
            {"role": "assistant", "content": "PostgreSQL is a relational database system."},
        ])
        s = r.status()
        assert s["chat_chunks"] >= 2

    def test_retrieve_with_min_score_filters_weak_matches(self, tmp_path):
        """High min_score filters out poor matches, returning None."""
        r = _retriever(tmp_path)
        r.index_session("s-filter", [
            {"role": "user",      "content": "Explain quantum entanglement."},
            {"role": "assistant", "content": "Quantum entanglement links particle states non-locally."},
        ])
        # Query completely unrelated to indexed content — should be filtered
        result = r.retrieve("chocolate cake recipe", include_files=False, min_score=0.95)
        assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# Summary injection
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.slow
class TestRAGSummary:
    """Summary-preferring retrieval strategy."""

    def test_session_with_summary_indexed(self, tmp_path):
        """index_session accepts summary= and indexes it."""
        r = _retriever(tmp_path)
        count = r.index_session(
            "summarized-session",
            [
                {"role": "user",      "content": "How does garbage collection work in Python?"},
                {"role": "assistant", "content": "Python uses reference counting plus a cyclic GC."},
            ],
            summary="Session about Python memory management and garbage collection.",
        )
        assert count >= 1

    def test_summary_preferred_over_raw_messages(self, tmp_path):
        """When summary is indexed, retrieval context includes summary content."""
        r = _retriever(tmp_path)
        summary = "Discussion about Python garbage collection and memory management strategies."
        r.index_session(
            "gc-session",
            [
                {"role": "user",      "content": "Tell me about Python GC."},
                {"role": "assistant", "content": "Python GC handles cyclic references."},
            ],
            summary=summary,
        )
        result = r.retrieve("Python memory garbage collection", include_files=False)
        assert result is not None
        # Result should contain something semantically related
        assert any(word in result.lower() for word in ["python", "memory", "garbage", "gc", "summary"])


# ─────────────────────────────────────────────────────────────────────────────
# File indexing
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.slow
class TestRAGFileIndexing:
    """index_directory + file retrieval."""

    def test_index_directory_returns_chunk_count(self, tmp_path):
        """index_directory indexes .txt/.md files and returns chunk count."""
        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "readme.md").write_text(
            "# aicli\naicli is a terminal AI assistant with multi-provider support.\n"
            "It supports Groq, OpenRouter, Gemini, Mistral, and Ollama.\n"
        )
        (docs / "notes.txt").write_text(
            "Session notes: discussed provider failover chain.\n"
            "Groq is the primary provider, OpenRouter is the fallback.\n"
        )
        r = _retriever(tmp_path)
        count = r.index_directory(docs)
        assert isinstance(count, int)
        assert count >= 1

    def test_retrieve_from_indexed_files(self, tmp_path):
        """After indexing a directory, file content is retrievable."""
        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "providers.md").write_text(
            "Provider failover: Groq → OpenRouter → Gemini → Mistral → Ollama.\n"
            "Each provider has adaptive cooldown on rate limit errors.\n"
        )
        r = _retriever(tmp_path)
        r.index_directory(docs)
        result = r.retrieve("provider failover chain", include_chat=False)
        assert result is not None
        assert "file:" in result  # context block labels file sources

    def test_status_reflects_file_chunks(self, tmp_path):
        """status() shows local_chunks after indexing a directory."""
        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "content.txt").write_text(
            "The executor dispatches tool calls to registered OS functions.\n"
        )
        r = _retriever(tmp_path)
        r.index_directory(docs)
        s = r.status()
        assert s["local_chunks"] >= 1


# ─────────────────────────────────────────────────────────────────────────────
# Depth scaling
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.slow
class TestRAGDepthScaling:
    """depth= parameter scales n_files and n_chat linearly."""

    def test_depth_2_returns_more_results(self, tmp_path):
        """depth=2 retrieves up to 2x as many chunks as depth=1."""
        r = _retriever(tmp_path)
        # Index 6 sessions with distinct content
        topics = [
            ("sess-1", "Python asyncio event loop and coroutines"),
            ("sess-2", "Docker Compose multi-service orchestration"),
            ("sess-3", "Kubernetes pod scheduling and autoscaling"),
            ("sess-4", "PostgreSQL indexing and query optimisation"),
            ("sess-5", "Redis pub/sub and caching patterns"),
            ("sess-6", "Nginx reverse proxy and load balancing"),
        ]
        for sid, content in topics:
            r.index_session(sid, [
                {"role": "user",      "content": f"Tell me about {content}."},
                {"role": "assistant", "content": f"{content} is an important topic in modern infrastructure."},
            ])
        result_d1 = r.retrieve("infrastructure deployment", include_files=False, depth=1)
        result_d2 = r.retrieve("infrastructure deployment", include_files=False, depth=2)
        # depth=2 should return at least as many results as depth=1
        len_d1 = len(result_d1) if result_d1 else 0
        len_d2 = len(result_d2) if result_d2 else 0
        assert len_d2 >= len_d1
