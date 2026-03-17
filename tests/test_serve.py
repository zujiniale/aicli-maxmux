"""
tests/test_serve.py — Tests for aicli serve (local HTTP API).

serve.py uses asyncio.run(pipeline.complete(...)) from a sync BaseHTTPRequestHandler,
so complete() must be AsyncMock. load_config() and get_role() are also patched
so tests have no dependency on real config files or keyring.
"""

import json
import socket
import threading
import time
import urllib.request
import urllib.error
import pytest
from unittest.mock import patch, MagicMock, AsyncMock


# ── Shared mock config ────────────────────────────────────────────────────────

MOCK_CONFIG = {
    "provider_chain": ["groq"],
    "cooldown_seconds": 60,
    "max_retries_per_provider": 1,
    "show_provider": False,
}


class MockRole:
    system_prompt = "You are a helpful assistant."


# ── Helpers ───────────────────────────────────────────────────────────────────

def _free_port() -> int:
    """Ask the OS for a free ephemeral port — avoids hardcoded ports that stay
    occupied between runs because daemon server threads never release them."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_port(host: str, port: int, timeout: float = 3.0) -> bool:
    """Poll until port accepts connections. Faster than fixed sleep."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.05):
                return True
        except OSError:
            time.sleep(0.01)
    return False


def _make_pipeline(response: str = "ok", provider: str = "groq"):
    """Mock pipeline. complete() is AsyncMock — serve.py calls asyncio.run(complete(...))."""
    mock = MagicMock()
    mock.last_provider = provider
    mock.complete = AsyncMock(return_value=response)
    mock.status.return_value = [
        {"name": "groq", "available": True, "cooldown_remaining": 0.0, "failures": 0}
    ]
    return mock


def _start_server(port: int, extra_patches: dict = None):
    """
    Start the serve server with required patches active.
    Returns a list of started patch contexts (call .stop() on each to clean up).
    extra_patches: {patch_target: return_value} for additional mocks.
    """
    from aicli.handlers.serve import run_serve

    patches = {}

    # Always patch load_config — it reads keyring and config files
    p_config = patch("aicli.handlers.serve.load_config", return_value=MOCK_CONFIG)
    patches["load_config"] = p_config.start()

    # Always patch get_role
    p_role = patch("aicli.handlers.serve.get_role", return_value=MockRole())
    patches["get_role"] = p_role.start()

    # Apply extra patches
    extra_ctxs = []
    if extra_patches:
        for target, value in extra_patches.items():
            ctx = patch(target, return_value=value)
            ctx.start()
            extra_ctxs.append(ctx)

    t = threading.Thread(
        target=run_serve,
        kwargs={"host": "127.0.0.1", "port": port, "quiet": True},
        daemon=True,
    )
    t.start()
    assert _wait_for_port("127.0.0.1", port), f"Server on port {port} failed to start"

    return p_config, p_role, extra_ctxs


def _stop_patches(p_config, p_role, extra_ctxs):
    patch.stopall()  # cleanest way since we're in class scope


def _get(url: str) -> tuple[int, dict]:
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _post(url: str, body: dict) -> tuple[int, dict]:
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


# ── Tests: /health ─────────────────────────────────────────────────────────────

class TestServeHealth:

    @pytest.fixture(autouse=True, scope="class")
    def server(self):
        port = _free_port()
        self.__class__._port = port
        mock = _make_pipeline()
        p_config, p_role, extras = _start_server(
            port, {"aicli.handlers.serve._build_pipeline": mock}
        )
        yield mock
        _stop_patches(p_config, p_role, extras)

    def test_health_returns_ok(self, server):
        status, body = _get(f"http://127.0.0.1:{self._port}/health")
        assert status == 200
        assert body["status"] == "ok"

    def test_health_includes_providers(self, server):
        _, body = _get(f"http://127.0.0.1:{self._port}/health")
        assert "providers" in body
        assert isinstance(body["providers"], list)

    def test_health_includes_version(self, server):
        _, body = _get(f"http://127.0.0.1:{self._port}/health")
        assert "version" in body

    def test_health_degraded_when_no_providers(self):
        from aicli.providers.pipeline import ProviderExhaustedError
        from aicli.handlers.serve import run_serve
        port = _free_port()
        with patch("aicli.handlers.serve.load_config", return_value=MOCK_CONFIG), \
             patch("aicli.handlers.serve.get_role", return_value=MockRole()), \
             patch("aicli.handlers.serve._build_pipeline",
                   side_effect=ProviderExhaustedError("none")):
            t = threading.Thread(
                target=run_serve,
                kwargs={"host": "127.0.0.1", "port": port, "quiet": True},
                daemon=True,
            )
            t.start()
            assert _wait_for_port("127.0.0.1", port)
            status, body = _get(f"http://127.0.0.1:{port}/health")
        assert status == 503
        assert body["status"] == "error"


# ── Tests: /providers ──────────────────────────────────────────────────────────

class TestServeProviders:

    @pytest.fixture(autouse=True, scope="class")
    def server(self):
        port = _free_port()
        self.__class__._port = port
        mock = _make_pipeline()
        mock.status.return_value = [
            {"name": "groq",   "available": True, "cooldown_remaining": 0.0, "failures": 0},
            {"name": "ollama", "available": True, "cooldown_remaining": 0.0, "failures": 0},
        ]
        p_config, p_role, extras = _start_server(
            port, {"aicli.handlers.serve._build_pipeline": mock}
        )
        yield mock
        _stop_patches(p_config, p_role, extras)

    def test_providers_returns_list(self, server):
        _, body = _get(f"http://127.0.0.1:{self._port}/providers")
        assert "providers" in body
        # Pipeline mock returns 2 providers; real pipeline may return more — just check structure
        assert isinstance(body["providers"], list)
        assert len(body["providers"]) >= 1
        assert body["providers"][0]["name"] == "groq"


# ── Tests: POST /ask ──────────────────────────────────────────────────────────

class TestServeAsk:

    @pytest.fixture(autouse=True, scope="class")
    def server(self):
        port = _free_port()
        self.__class__._port = port
        mock = _make_pipeline(response="Hello from aicli!")
        p_config, p_role, extras = _start_server(
            port, {"aicli.handlers.serve._build_pipeline": mock}
        )
        yield mock
        _stop_patches(p_config, p_role, extras)

    def test_ask_returns_response(self, server):
        status, body = _post(f"http://127.0.0.1:{self._port}/ask", {"prompt": "hello"})
        assert status == 200
        assert body["response"] == "Hello from aicli!"

    def test_ask_includes_provider(self, server):
        _, body = _post(f"http://127.0.0.1:{self._port}/ask", {"prompt": "hello"})
        assert body["provider"] == "groq"

    def test_ask_missing_prompt_returns_400(self, server):
        status, body = _post(f"http://127.0.0.1:{self._port}/ask", {})
        assert status == 400
        assert "error" in body

    def test_ask_empty_prompt_returns_400(self, server):
        status, _ = _post(f"http://127.0.0.1:{self._port}/ask", {"prompt": "   "})
        assert status == 400

    def test_ask_invalid_json_returns_400(self, server):
        data = b"not json"
        req = urllib.request.Request(
            f"http://127.0.0.1:{self._port}/ask", data=data,
            headers={"Content-Type": "application/json", "Content-Length": str(len(data))},
        )
        try:
            urllib.request.urlopen(req, timeout=3)
            assert False, "Expected HTTPError 400"
        except urllib.error.HTTPError as e:
            assert e.code == 400


# ── Tests: POST /ask/shell ────────────────────────────────────────────────────

class TestServeAskShell:

    @pytest.fixture(autouse=True, scope="class")
    def server(self):
        port = _free_port()
        self.__class__._port = port
        mock = _make_pipeline(response="ls -la")
        p_config, p_role, extras = _start_server(
            port, {"aicli.handlers.serve._build_pipeline": mock}
        )
        yield mock
        _stop_patches(p_config, p_role, extras)

    def test_ask_shell_returns_single_command(self, server):
        status, body = _post(f"http://127.0.0.1:{self._port}/ask/shell", {"prompt": "list files"})
        assert status == 200
        assert body["response"] == "ls -la"

    def test_ask_shell_strips_backticks(self):
        port = _free_port()
        mock = _make_pipeline(response="`find . -name '*.log'`")
        p_config, p_role, extras = _start_server(port, {"aicli.handlers.serve._build_pipeline": mock})
        try:
            _, body = _post(f"http://127.0.0.1:{port}/ask/shell", {"prompt": "find log files"})
            assert body["response"] == "find . -name '*.log'"
        finally:
            _stop_patches(p_config, p_role, extras)


# ── Tests: /sessions ──────────────────────────────────────────────────────────

class TestServeSessions:

    @pytest.fixture(autouse=True, scope="class")
    def server(self):
        port = _free_port()
        self.__class__._port = port
        mock_sessions = [{"id": "abc123", "name": "myproject", "message_count": 10}]
        class _FakeConn:
            pass
        p_config, p_role, extras = _start_server(port, {
            "aicli.handlers.serve.list_sessions": mock_sessions,
            "aicli.handlers.serve.get_connection": _FakeConn(),
            "aicli.handlers.serve.load_messages": [],
        })
        yield
        _stop_patches(p_config, p_role, extras)

    def test_sessions_list_returns_array(self, server):
        status, body = _get(f"http://127.0.0.1:{self._port}/sessions")
        assert status == 200
        assert "sessions" in body
        assert isinstance(body["sessions"], list)

    def test_sessions_unknown_returns_404(self, server):
        status, _ = _get(f"http://127.0.0.1:{self._port}/sessions/nonexistent-session")
        assert status == 404

    def test_sessions_unknown_endpoint_404(self, server):
        status, _ = _get(f"http://127.0.0.1:{self._port}/notaroute")
        assert status == 404
