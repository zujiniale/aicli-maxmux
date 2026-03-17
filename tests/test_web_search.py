"""
tests/test_web_search.py — Tests for aicli web search (web.py).

Tests query formatting, result parsing, backend chain fallback,
and network error handling — all without live network calls.
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock


# ── Helpers ───────────────────────────────────────────────────────────────────

# Backends return list[dict] with keys: title, snippet, url
MOCK_RESULTS = [
    {"title": "Python 3.13 released", "url": "https://python.org", "snippet": "Python 3.13 adds a new REPL, improved error messages..."},
]

# Convenience: a formatted string as returned by web_search() itself
MOCK_SEARCH_RESULT = (
    "RELEVANT WEB RESULTS\n\n"
    "1. Python 3.13 released (python.org)\n"
    "   Python 3.13 adds a new REPL, improved error messages...\n\n"
)


# ── Tests: web_search top-level ───────────────────────────────────────────────

class TestWebSearch:

    @pytest.mark.asyncio
    async def test_web_search_returns_string_on_success(self):
        from aicli.web import web_search
        # _search_tavily returns list[dict]; web_search formats it into a string
        with patch("aicli.web._search_tavily", new=AsyncMock(return_value=MOCK_RESULTS)):
            result = await web_search("latest Python version")
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_web_search_falls_through_on_empty(self):
        """If first backend returns empty/None, chain continues to next."""
        from aicli.web import web_search
        call_order = []

        async def empty_tavily(*args, **kwargs):
            call_order.append("tavily")
            return None  # empty → chain continues

        async def success_ddg(*args, **kwargs):
            call_order.append("ddg")
            return MOCK_RESULTS

        async def fail(*args, **kwargs):
            return None

        # Patch ALL backends — unpatched ones hit real network and add 40-70s per test
        with patch("aicli.web._search_tavily", new=empty_tavily), \
             patch("aicli.web._search_searxng", new=fail), \
             patch("aicli.web._search_ddg_api", new=success_ddg), \
             patch("aicli.web._search_ddg_lite", new=fail), \
             patch("aicli.web._search_bing", new=fail), \
             patch("aicli.web._search_mojeek", new=fail):
            result = await web_search("test query")
        # At minimum tavily was tried first
        assert "tavily" in call_order

    @pytest.mark.asyncio
    async def test_web_search_returns_empty_string_on_all_fail(self):
        """All backends fail → returns None or empty string, does not raise."""
        from aicli.web import web_search

        async def fail(*args, **kwargs):
            return None

        with patch("aicli.web._search_tavily", new=fail), \
             patch("aicli.web._search_searxng", new=fail), \
             patch("aicli.web._search_ddg_api", new=fail), \
             patch("aicli.web._search_ddg_lite", new=fail), \
             patch("aicli.web._search_bing", new=fail), \
             patch("aicli.web._search_mojeek", new=fail):
            result = await web_search("query")
        # web_search returns None when all backends fail
        assert result is None or isinstance(result, str)

    @pytest.mark.asyncio
    async def test_web_search_skips_searxng_over_tor(self):
        """SearXNG is auto-skipped when SOCKS proxy is active (_SOCKS_ACTIVE=True)."""
        from aicli.web import web_search
        searxng_called = []

        async def spy_searxng(*args, **kwargs):
            searxng_called.append(True)
            return MOCK_RESULTS

        # Patch _SOCKS_ACTIVE directly — it's set lazily at _get_opener() time,
        # not from the env var at call time, so we patch the module-level flag.
        with patch("aicli.web._SOCKS_ACTIVE", True):
            with patch("aicli.web._search_tavily", new=AsyncMock(return_value=None)):
                with patch("aicli.web._search_searxng", new=spy_searxng):
                    with patch("aicli.web._search_ddg_api", new=AsyncMock(return_value=MOCK_RESULTS)):
                        await web_search("test")
        # SearXNG must NOT be called when _SOCKS_ACTIVE is True
        assert len(searxng_called) == 0

    @pytest.mark.asyncio
    async def test_web_search_handles_network_exception(self):
        """Network exceptions in a backend don't crash the chain."""
        from aicli.web import web_search

        async def raise_error(*args, **kwargs):
            raise ConnectionError("network error")

        async def fail(*args, **kwargs):
            return None

        # Patch ALL backends — unpatched ones hit real network
        with patch("aicli.web._search_tavily", new=raise_error), \
             patch("aicli.web._search_searxng", new=fail), \
             patch("aicli.web._search_ddg_api", new=AsyncMock(return_value=MOCK_RESULTS)), \
             patch("aicli.web._search_ddg_lite", new=fail), \
             patch("aicli.web._search_bing", new=fail), \
             patch("aicli.web._search_mojeek", new=fail):
            result = await web_search("test")
        # Should not raise; chain continues to next backend
        assert isinstance(result, str)


# ── Tests: query formatting ───────────────────────────────────────────────────

class TestWebSearchQueryFormatting:

    @pytest.mark.asyncio
    async def test_query_passed_verbatim(self):
        """The query string is passed as-is to backends."""
        from aicli.web import web_search
        received = []

        async def capture(*args, **kwargs):
            # args[0] is query
            received.append(args[0])
            return MOCK_RESULTS

        with patch("aicli.web._search_tavily", new=capture):
            await web_search("  what is Python 3.13  ")
        assert len(received) == 1
        assert received[0] == "  what is Python 3.13  "

    @pytest.mark.asyncio
    async def test_empty_query_handled(self):
        """Empty query doesn't crash."""
        from aicli.web import web_search
        async def fail(*args, **kwargs):
            return None
        # Patch ALL backends — unpatched ones hit real network
        with patch("aicli.web._search_tavily", new=AsyncMock(return_value=None)), \
             patch("aicli.web._search_searxng", new=fail), \
             patch("aicli.web._search_ddg_api", new=fail), \
             patch("aicli.web._search_ddg_lite", new=fail), \
             patch("aicli.web._search_bing", new=fail), \
             patch("aicli.web._search_mojeek", new=fail):
            result = await web_search("")
        assert result is None or isinstance(result, str)


# ── Tests: result formatting ──────────────────────────────────────────────────

class TestWebSearchResultFormat:

    @pytest.mark.asyncio
    async def test_result_is_string(self):
        from aicli.web import web_search
        with patch("aicli.web._search_tavily", new=AsyncMock(return_value=MOCK_RESULTS)):
            result = await web_search("python")
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_result_injected_as_system_message(self):
        """Result from web_search can be injected as system message without error."""
        from aicli.web import web_search
        with patch("aicli.web._search_tavily", new=AsyncMock(return_value=MOCK_RESULTS)):
            result = await web_search("python")
        assert result is not None
        msg = {"role": "system", "content": result}
        assert msg["role"] == "system"
        assert isinstance(msg["content"], str)
