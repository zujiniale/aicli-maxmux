"""
web.py — Lightweight web search for aicli (F4).

Multi-backend search chain — tries each backend in order, returns first success.
Zero API keys required for the free tier. Optional key unlocks Tavily.

Backends (tried in order):
  1. Tavily       — AI-optimised search, 1000 req/month free (TAVILY_API_KEY)
  2. SearXNG      — public instances, JSON API, no key, rotates on failure
  3. DDG JSON API — Instant Answer / Wikipedia summaries, no key
  4. DDG lite     — HTML scrape with cookie jar (fixes the 403/homepage redirect)
  5. Bing scrape  — rotating User-Agent, no key
  6. Mojeek       — independent search engine, scrape-friendly, no key

Proxy / Tor support:
  Set AICLI_PROXY env var to route ALL backends through a proxy.
  Examples:
    AICLI_PROXY=socks5://127.0.0.1:9050   # Tor (requires PySocks: pip install pysocks)
    AICLI_PROXY=http://127.0.0.1:8118     # Privoxy / HTTP proxy
    AICLI_PROXY=socks5://user:pass@host:port

  Install PySocks once to enable SOCKS5:
    pip install pysocks

Usage:
    from .web import web_search
    context_block = await web_search("your query")
"""

import asyncio
import html
import http.cookiejar
import json
import os
import random
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

# Lazy import to avoid circular imports — called only at runtime
def _cfg(key: str) -> str:
    """Read a key from env or aicli encrypted config store."""
    # Always check env first — fast, no import needed
    env_val = os.environ.get(key, "")
    if env_val:
        return env_val
    # Then try the aicli config store (keyring / Fernet file)
    try:
        from .config import get_config_value
        return get_config_value(key) or ""
    except Exception:
        return ""


# ── Constants ─────────────────────────────────────────────────────────────────

_MAX_RESULTS     = 5
_MAX_SNIPPET_LEN = 300
_TIMEOUT         = 10

# Rotating User-Agent pool — avoids single-UA fingerprinting
_USER_AGENTS = [
    "curl/8.5.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
]

# SearXNG public instances — rotated randomly, skipped on failure
# See full list: https://searx.space/
# Updated 2026-03-07 — prior list was fully rate-limited / dead
_SEARXNG_INSTANCES = [
    "https://search.sapti.me",
    "https://searx.perennialte.ch",
    "https://search.hbubli.cc",
    "https://searx.work",
    "https://nyc1.sx.ggtyler.dev",
    "https://sx.ca.idealist.gay",
    "https://searx.sev.monster",
    "https://search.ononoki.org",
    "https://searx.fmac.xyz",
    "https://searx.hu",
    "https://copp.gg",
    "https://search.rowie.at",
    "https://priv.au",
    "https://searx.tiekoetter.com",   # kept — sometimes works
    "https://searx.be",               # kept — sometimes works
]

_DDG_API_URL  = "https://api.duckduckgo.com/"
_DDG_LITE_URL = "https://lite.duckduckgo.com/lite/"
_BING_URL     = "https://www.bing.com/search"
_MOJEEK_URL   = "https://www.mojeek.com/search"
_TAVILY_URL   = "https://api.tavily.com/search"


# ── Proxy / Tor support ───────────────────────────────────────────────────────

_SOCKS_ACTIVE = False  # set to True lazily on first _get_opener() call


def _get_opener() -> urllib.request.OpenerDirector:
    """
    Build a urllib opener with a cookie jar (required for DDG lite).
    Applies SOCKS proxy lazily here — NOT at import time — so that keyring
    is fully initialised and AICLI_PROXY stored there is readable.
    HTTP/HTTPS proxies are added as a ProxyHandler on the opener.
    """
    global _SOCKS_ACTIVE
    cj = http.cookiejar.CookieJar()
    handlers: list = [urllib.request.HTTPCookieProcessor(cj)]

    proxy_url = _cfg("AICLI_PROXY").strip()
    if not proxy_url:
        return urllib.request.build_opener(*handlers)

    scheme = proxy_url.split("://")[0].lower()
    if scheme.startswith("socks"):
        if not _SOCKS_ACTIVE:
            try:
                import socks  # type: ignore  (pip install pysocks)
                parsed     = urllib.parse.urlparse(proxy_url)
                socks_type = socks.SOCKS5 if scheme == "socks5" else socks.SOCKS4
                socks.set_default_proxy(
                    socks_type,
                    parsed.hostname,
                    parsed.port or 9050,
                    username=parsed.username,
                    password=parsed.password,
                )
                socket.socket = socks.socksocket  # type: ignore[assignment]
                _SOCKS_ACTIVE = True
            except ImportError:
                pass  # PySocks not installed — silent fallback to direct
    else:
        handlers.append(urllib.request.ProxyHandler({
            "http":  proxy_url,
            "https": proxy_url,
        }))

    return urllib.request.build_opener(*handlers)


def _ua() -> str:
    """Return a random User-Agent from the pool."""
    return random.choice(_USER_AGENTS)


def _fetch(req: urllib.request.Request, opener: Optional[urllib.request.OpenerDirector] = None) -> bytes:
    """Blocking fetch — runs in executor thread. Uses opener if provided."""
    if opener:
        return opener.open(req, timeout=_TIMEOUT).read()
    return urllib.request.urlopen(req, timeout=_TIMEOUT).read()


# ── HTML helpers ──────────────────────────────────────────────────────────────

def _strip_tags(text: str) -> str:
    """Remove HTML tags and decode entities."""
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()


def _format_context(query: str, results: list[dict], source: str = "") -> str:
    """Format search results as a context block for injection into messages."""
    if not results:
        return f"WEB SEARCH: No results found for: {query}"
    label = f"WEB SEARCH RESULTS for: {query}"
    if source:
        label += f" [via {source}]"
    lines = [label + "\n"]
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r['title']}")
        if r.get("snippet") and r["snippet"] != r["title"]:
            lines.append(f"   {r['snippet']}")
        if r.get("url"):
            lines.append(f"   Source: {r['url']}")
        lines.append("")
    return "\n".join(lines).rstrip()


# ── Backend 1: SearXNG ────────────────────────────────────────────────────────

def _parse_searxng_results(data: dict, max_results: int) -> list[dict]:
    results = []
    for item in data.get("results", [])[:max_results]:
        title   = _strip_tags(item.get("title", ""))
        url     = item.get("url", "")
        snippet = _strip_tags(item.get("content", ""))[:_MAX_SNIPPET_LEN]
        if title and url:
            results.append({"title": title[:120], "url": url[:200], "snippet": snippet})
    return results


async def _search_searxng(query: str, max_results: int, loop, opener) -> Optional[list[dict]]:
    """Try SearXNG public instances in random order until one works."""
    instances = _SEARXNG_INSTANCES.copy()
    random.shuffle(instances)
    for base in instances:
        try:
            params = urllib.parse.urlencode({
                "q": query, "format": "json", "language": "en",
                "time_range": "", "safesearch": "0", "categories": "general",
            })
            req = urllib.request.Request(
                f"{base}/search?{params}",
                headers={"User-Agent": _ua(), "Accept": "application/json"},
            )
            rb = await loop.run_in_executor(None, lambda r=req: _fetch(r, opener))
            data = json.loads(rb.decode("utf-8", errors="replace"))
            results = _parse_searxng_results(data, max_results)
            if results:
                return results
        except Exception:
            await asyncio.sleep(2)  # brief pause before trying next instance
            continue
    return None


# ── Backend 2: DDG Instant Answer JSON API ────────────────────────────────────

def _parse_ddg_api_results(data: dict, max_results: int) -> list[dict]:
    results = []
    if data.get("AbstractText"):
        results.append({
            "title":   data.get("Heading", "Summary"),
            "url":     data.get("AbstractURL", ""),
            "snippet": data["AbstractText"][:_MAX_SNIPPET_LEN],
        })
    for topic in data.get("RelatedTopics", []):
        if len(results) >= max_results:
            break
        if "Topics" in topic:
            for sub in topic["Topics"]:
                if len(results) >= max_results:
                    break
                text = _strip_tags(sub.get("Text", ""))
                url  = sub.get("FirstURL", "")
                if text and url:
                    results.append({"title": text[:80], "url": url, "snippet": text[:_MAX_SNIPPET_LEN]})
        else:
            text = _strip_tags(topic.get("Text", ""))
            url  = topic.get("FirstURL", "")
            if text and url:
                results.append({"title": text[:80], "url": url, "snippet": text[:_MAX_SNIPPET_LEN]})
    return results


async def _search_ddg_api(query: str, max_results: int, loop, opener) -> Optional[list[dict]]:
    try:
        params = urllib.parse.urlencode({"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"})
        req = urllib.request.Request(
            f"{_DDG_API_URL}?{params}",
            headers={"User-Agent": _ua(), "Accept": "application/json"},
        )
        rb   = await loop.run_in_executor(None, lambda r=req: _fetch(r, opener))
        data = json.loads(rb.decode("utf-8", errors="replace"))
        results = _parse_ddg_api_results(data, max_results)
        return results if results else None
    except Exception:
        return None


# ── Backend 3: DDG lite HTML (cookie jar fixes homepage redirect) ─────────────

def _parse_lite_results(html_body: str, max_results: int) -> list[dict]:
    results = []
    links    = re.findall(r'<a[^>]+href="([^"]+)"[^>]*class="result-link"[^>]*>(.*?)</a>', html_body, re.DOTALL)
    snippets = re.findall(r'class="result-snippet"[^>]*>(.*?)</span>', html_body, re.DOTALL)
    for i, (url, title) in enumerate(links[:max_results]):
        snippet = _strip_tags(snippets[i]) if i < len(snippets) else ""
        title   = _strip_tags(title)
        if title and url:
            results.append({"title": title[:120], "url": url[:200], "snippet": snippet[:_MAX_SNIPPET_LEN]})
    return results


async def _search_ddg_lite(query: str, max_results: int, loop, opener) -> Optional[list[dict]]:
    """
    DDG lite with cookie jar opener — the cookie jar is what was missing before.
    DDG lite requires a session cookie to return results instead of the homepage.
    """
    try:
        form_data = urllib.parse.urlencode({"q": query, "kl": "us-en"}).encode()
        req = urllib.request.Request(
            _DDG_LITE_URL,
            data=form_data,
            headers={
                "User-Agent": _ua(),
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9",
                "Origin": "https://lite.duckduckgo.com",
                "Referer": "https://lite.duckduckgo.com/",
            },
            method="POST",
        )
        rb = await loop.run_in_executor(None, lambda r=req: _fetch(r, opener))
        html_body = rb.decode("utf-8", errors="replace")
        results = _parse_lite_results(html_body, max_results)
        return results if results else None
    except Exception:
        return None


# ── Backend 4: Bing scrape ────────────────────────────────────────────────────

def _parse_bing_results(html_body: str, max_results: int) -> list[dict]:
    results = []
    # Bing wraps results in <li class="b_algo">
    blocks = re.findall(r'<li class="b_algo">(.*?)</li>', html_body, re.DOTALL)
    for block in blocks[:max_results]:
        title_m = re.search(r'<h2[^>]*><a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', block, re.DOTALL)
        snip_m  = re.search(r'<p[^>]*>(.*?)</p>', block, re.DOTALL)
        if title_m:
            url     = title_m.group(1)
            title   = _strip_tags(title_m.group(2))
            snippet = _strip_tags(snip_m.group(1)) if snip_m else ""
            if title and url and not url.startswith("javascript"):
                results.append({
                    "title":   title[:120],
                    "url":     url[:200],
                    "snippet": snippet[:_MAX_SNIPPET_LEN],
                })
    return results


async def _search_bing(query: str, max_results: int, loop, opener) -> Optional[list[dict]]:
    try:
        params = urllib.parse.urlencode({"q": query, "setlang": "en", "cc": "US"})
        req = urllib.request.Request(
            f"{_BING_URL}?{params}",
            headers={
                "User-Agent": _ua(),
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "identity",
            },
        )
        rb = await loop.run_in_executor(None, lambda r=req: _fetch(r, opener))
        html_body = rb.decode("utf-8", errors="replace")
        results = _parse_bing_results(html_body, max_results)
        return results if results else None
    except Exception:
        return None


# ── Backend 5: Mojeek scrape ──────────────────────────────────────────────────

def _parse_mojeek_results(html_body: str, max_results: int) -> list[dict]:
    results = []
    # Mojeek: results in <li> blocks with <a class="ob"> for title/url
    blocks = re.findall(r'<li[^>]*class="[^"]*result[^"]*"[^>]*>(.*?)</li>', html_body, re.DOTALL)
    for block in blocks[:max_results]:
        title_m = re.search(r'<a[^>]+href="([^"]+)"[^>]*class="[^"]*ob[^"]*"[^>]*>(.*?)</a>', block, re.DOTALL)
        snip_m  = re.search(r'<p[^>]*class="[^"]*s[^"]*"[^>]*>(.*?)</p>', block, re.DOTALL)
        if title_m:
            url     = title_m.group(1)
            title   = _strip_tags(title_m.group(2))
            snippet = _strip_tags(snip_m.group(1)) if snip_m else ""
            if title and url:
                results.append({
                    "title":   title[:120],
                    "url":     url[:200],
                    "snippet": snippet[:_MAX_SNIPPET_LEN],
                })
    return results


async def _search_mojeek(query: str, max_results: int, loop, opener) -> Optional[list[dict]]:
    try:
        params = urllib.parse.urlencode({"q": query, "lang": "en"})
        req = urllib.request.Request(
            f"{_MOJEEK_URL}?{params}",
            headers={
                "User-Agent": _ua(),
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        rb = await loop.run_in_executor(None, lambda r=req: _fetch(r, opener))
        html_body = rb.decode("utf-8", errors="replace")
        results = _parse_mojeek_results(html_body, max_results)
        return results if results else None
    except Exception:
        return None



# ── Backend 6: Tavily (optional — needs TAVILY_API_KEY) ──────────────────────

async def _search_tavily(query: str, max_results: int, loop, opener) -> Optional[list[dict]]:
    api_key = _cfg("TAVILY_API_KEY").strip()
    if not api_key:
        return None
    # Try both auth styles — Tavily has changed their API format over time.
    # Style A: key in JSON body (original free-tier format)
    # Style B: Bearer token in Authorization header (newer paid format)
    for auth_style in ("body", "bearer"):
        try:
            if auth_style == "body":
                body = {"api_key": api_key, "query": query,
                        "search_depth": "basic", "max_results": max_results,
                        "include_answer": False}
                headers = {"Content-Type": "application/json", "User-Agent": _ua()}
            else:
                body = {"query": query, "search_depth": "basic",
                        "max_results": max_results, "include_answer": False}
                headers = {"Content-Type": "application/json",
                           "Authorization": f"Bearer {api_key}", "User-Agent": _ua()}
            req = urllib.request.Request(
                _TAVILY_URL, data=json.dumps(body).encode(),
                headers=headers, method="POST",
            )
            rb   = await loop.run_in_executor(None, lambda r=req: _fetch(r, opener))
            data = json.loads(rb.decode("utf-8", errors="replace"))
            results = []
            for item in data.get("results", [])[:max_results]:
                title   = _strip_tags(item.get("title", ""))
                url     = item.get("url", "")
                snippet = _strip_tags(item.get("content", ""))[:_MAX_SNIPPET_LEN]
                if title and url:
                    results.append({"title": title[:120], "url": url[:200], "snippet": snippet})
            if results:
                return results
        except Exception:
            continue
    return None


# Alias for test patchability — tests patch aicli.web._tavily_search
_tavily_search = _search_tavily


# ── Main public API ───────────────────────────────────────────────────────────

async def web_search(query: str, max_results: int = _MAX_RESULTS) -> Optional[str]:
    """
    Multi-backend web search. Tries each backend in order, returns first success.
    Returns a formatted context block string, or None if all backends fail.

    Backend order:
      1. Tavily (if TAVILY_API_KEY set — AI-optimised, most accurate)
      2. SearXNG public instances (rotated)
      3. DDG Instant Answer JSON API
      4. DDG lite HTML (with cookie jar)
      5. Bing scrape
      6. Mojeek scrape

    Proxy: set AICLI_PROXY env var (e.g. socks5://127.0.0.1:9050 for Tor).
    """
    loop   = asyncio.get_event_loop()
    opener = _get_opener()

    # Backends as lazy callables — coroutines are only created when awaited.
    # This prevents "coroutine never awaited" warnings for skipped backends
    # (e.g. Tavily when no key is set) and ensures the chain never
    # breaks early due to a stale coroutine object raising on await.
    # SearXNG is skipped when a SOCKS/Tor proxy is active — all public
    # SearXNG instances block Tor exit nodes with 429/403.
    backends = [
        ("Tavily",   lambda: _search_tavily(query, max_results, loop, opener)),
        ("SearXNG",  lambda: _search_searxng(query, max_results, loop, opener)),
        ("DDG API",  lambda: _search_ddg_api(query, max_results, loop, opener)),
        ("DDG lite", lambda: _search_ddg_lite(query, max_results, loop, opener)),
        ("Bing",     lambda: _search_bing(query, max_results, loop, opener)),
        ("Mojeek",   lambda: _search_mojeek(query, max_results, loop, opener)),
    ]
    if _SOCKS_ACTIVE:
        backends = [(n, c) for n, c in backends if n != "SearXNG"]

    for name, make_coro in backends:
        try:
            results = await make_coro()
            if results:
                return _format_context(query, results, source=name)
        except Exception:
            continue

    return None  # All backends failed — graceful degradation


# ── Debug function (used by --web-debug flag) ─────────────────────────────────

async def web_search_debug(query: str, verbose: bool = False) -> None:
    """
    Print raw responses from all backends for diagnosis.
    Used by --web-debug flag — no LLM call made.
    Shows proxy status, which backends are active, and what each returns.

    verbose=False (default): only print backends that have results or are skipped
                             for a known reason. Empty/failed backends are suppressed.
    verbose=True  (--web-verbose): print every backend regardless of outcome.
    """
    loop   = asyncio.get_event_loop()
    opener = _get_opener()              # MUST be first — triggers SOCKS init + keyring context

    proxy  = _cfg("AICLI_PROXY")
    tavily = _cfg("TAVILY_API_KEY")     # reads keyring + Fernet, not just env
    # Under Tor (AICLI_PROXY set via env), keyring may need a second read
    # after _get_opener() has fully initialized the process context.
    if not tavily:
        tavily = _cfg("TAVILY_API_KEY")

    print(f"\n\033[1m[web debug] Query: {query}\033[0m")
    if proxy:
        socks_note = " (SOCKS active ✓)" if _SOCKS_ACTIVE else " (pip install pysocks to enable)"
        print(f"  Proxy:  {proxy}{socks_note if proxy.lower().startswith('socks') else ''}")
    else:
        print("  Proxy:  (none — direct connection)")
    print(f"  Tavily: {'key set ✓' if tavily else '(no TAVILY_API_KEY — skipped)'}")
    if not verbose:
        print("  (pass --web-verbose to show all backends including empty/failed)")
    print()

    async def _run(name, make_coro):
        """Run a backend. In non-verbose mode, suppress empty/failed output."""
        try:
            results = await make_coro()
            if results:
                print(f"── {name} {'─' * max(0, 44 - len(name))}")
                print(f"  ✓ {len(results)} result(s):")
                for r in results:
                    print(f"    [{r['title'][:55]}]")
                    if r.get("snippet"):
                        print(f"     {r['snippet'][:100]}")
                print()
            elif verbose:
                print(f"── {name} {'─' * max(0, 44 - len(name))}")
                print("  ✗ No results (backend returned empty)")
                print()
        except Exception as e:
            if verbose:
                print(f"── {name} {'─' * max(0, 44 - len(name))}")
                print(f"  ✗ FAILED: {e}")
                print()

    # SearXNG — show which instance wins (skipped under Tor — exit nodes are universally banned)
    if _SOCKS_ACTIVE:
        # Always show this — it's a meaningful status, not noise
        print("── SearXNG (rotating instances) ────────────────")
        print("  ~ Skipped — Tor exit nodes are blocked by all public SearXNG instances (429/403)")
        print("    Use Tavily (TAVILY_API_KEY) for reliable search over Tor.")
        print()
    else:
        instances = _SEARXNG_INSTANCES.copy()
        random.shuffle(instances)
        searxng_done = False
        searxng_errors = []
        for base in instances:
            try:
                params = urllib.parse.urlencode({
                    "q": query, "format": "json", "language": "en",
                    "time_range": "", "safesearch": "0", "categories": "general",
                })
                req = urllib.request.Request(
                    f"{base}/search?{params}",
                    headers={"User-Agent": _ua(), "Accept": "application/json"},
                )
                rb = await loop.run_in_executor(None, lambda r=req: _fetch(r, opener))
                data = json.loads(rb.decode("utf-8", errors="replace"))
                results = _parse_searxng_results(data, _MAX_RESULTS)
                if results:
                    print("── SearXNG (rotating instances) ────────────────")
                    print(f"  ✓ {base} → {len(results)} result(s)")
                    for r in results:
                        print(f"    [{r['title'][:55]}]")
                    print()
                    searxng_done = True
                    break
                else:
                    searxng_errors.append(f"  ~ {base} → 0 results")
            except Exception as e:
                searxng_errors.append(f"  ✗ {base} → {e}")
                await asyncio.sleep(2)  # brief pause before trying next instance
        if not searxng_done and verbose:
            print("── SearXNG (rotating instances) ────────────────")
            for line in searxng_errors:
                print(line)
            print("  ✗ All SearXNG instances failed or returned 0 results")
            print()

    await _run("DDG JSON API",
               lambda: _search_ddg_api(query, _MAX_RESULTS, loop, opener))
    await _run("DDG lite HTML (cookie jar)",
               lambda: _search_ddg_lite(query, _MAX_RESULTS, loop, opener))
    await _run("Bing scrape",
               lambda: _search_bing(query, _MAX_RESULTS, loop, opener))
    await _run("Mojeek scrape",
               lambda: _search_mojeek(query, _MAX_RESULTS, loop, opener))

    if tavily:
        print("── Tavily (raw debug) ──────────────────────────")
        _tavily_worked = False
        for _style in ("body", "bearer"):
            try:
                if _style == "body":
                    _body = {"api_key": tavily, "query": query, "search_depth": "basic",
                             "max_results": _MAX_RESULTS, "include_answer": False}
                    _hdrs = {"Content-Type": "application/json", "User-Agent": _ua()}
                else:
                    _body = {"query": query, "search_depth": "basic",
                             "max_results": _MAX_RESULTS, "include_answer": False}
                    _hdrs = {"Content-Type": "application/json",
                             "Authorization": f"Bearer {tavily}", "User-Agent": _ua()}
                req = urllib.request.Request(
                    _TAVILY_URL, data=json.dumps(_body).encode(),
                    headers=_hdrs, method="POST",
                )
                rb   = await loop.run_in_executor(None, lambda r=req: _fetch(r, opener))
                data = json.loads(rb.decode("utf-8", errors="replace"))
                results_raw = data.get("results", [])
                print(f"  Style '{_style}': keys={list(data.keys())} results={len(results_raw)}")
                for r in results_raw[:3]:
                    print(f"    [{r.get('title','')[:55]}]")
                    print(f"     {str(r.get('content',''))[:100]}")
                if results_raw:
                    print(f"  ✓ Auth style that worked: {_style}")
                    _tavily_worked = True
                    break
            except Exception as e:
                print(f"  ✗ Style '{_style}' FAILED: {e}")
        if not _tavily_worked:
            print("  ✗ Both auth styles failed")
        print()
        await _run("Tavily (parsed)",
                   lambda: _search_tavily(query, _MAX_RESULTS, loop, opener))
