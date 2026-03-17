"""
handlers/serve.py — aicli serve: local HTTP API server.

Exposes aicli as a local HTTP API for scripting, MCP integration,
and third-party tool access.

Endpoints:
  POST /ask           — single-shot prompt (JSON body)
  POST /ask/shell     — shell command generation
  POST /ask/code      — code generation
  GET  /sessions      — list all sessions
  GET  /sessions/:id  — get session messages
  GET  /health        — health check + provider status
  GET  /providers     — provider status

Request body (POST /ask):
  {
    "prompt": "explain async/await",
    "model": null,          // optional override
    "web": false,           // enable web search
    "stream": false,        // streaming response (chunked transfer)
    "session": null,        // session name for persistent context
    "lite": false           // skip RAG init
  }

Response (non-streaming):
  {
    "response": "...",
    "provider": "groq",
    "session": null
  }

Usage:
  aicli serve                    # default port 8765
  aicli serve --port 9000
  aicli serve --host 0.0.0.0    # expose to network (caution)
  aicli serve --no-browser       # suppress startup message
"""

import json
import asyncio
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

from ..config import load_config
from ..providers.pipeline import ProviderPipeline, ProviderExhaustedError
from ..db.chat_db import get_connection, list_sessions, load_messages
from ..role import get_role


def _build_pipeline(config: dict) -> ProviderPipeline:
    return ProviderPipeline(
        provider_chain=config["provider_chain"],
        cooldown_seconds=config["cooldown_seconds"],
        max_retries_per_provider=config["max_retries_per_provider"],
        show_provider=False,
    )


def _json_response(handler, data: dict, status: int = 200) -> None:
    body = json.dumps(data, ensure_ascii=False).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "http://localhost")
    handler.end_headers()
    handler.wfile.write(body)


def _error_response(handler, message: str, status: int = 400) -> None:
    _json_response(handler, {"error": message}, status)


class AicliHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        # Suppress default access log — use our own
        pass

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "http://localhost")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path == "/health":
            self._handle_health()
        elif path == "/providers":
            self._handle_providers()
        elif path == "/sessions":
            self._handle_sessions_list()
        elif path.startswith("/sessions/"):
            session_id = path[len("/sessions/"):]
            self._handle_session_get(session_id)
        else:
            _error_response(self, f"Unknown endpoint: {self.path}", 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        length = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(length)) if length else {}
        except json.JSONDecodeError:
            _error_response(self, "Invalid JSON body")
            return

        if path == "/ask":
            self._handle_ask(body, shell=False, code=False)
        elif path == "/ask/shell":
            self._handle_ask(body, shell=True, code=False)
        elif path == "/ask/code":
            self._handle_ask(body, shell=False, code=True)
        else:
            _error_response(self, f"Unknown endpoint: {self.path}", 404)

    # ── Handlers ──────────────────────────────────────────────────────────────

    def _handle_health(self):
        config = load_config()
        try:
            pipeline = _build_pipeline(config)
            statuses = pipeline.status()
            available = [s for s in statuses if s["available"]]
            _json_response(self, {
                "status": "ok" if available else "degraded",
                "providers": statuses,
                "version": self._get_version(),
            })
        except ProviderExhaustedError as e:
            _json_response(self, {"status": "error", "error": str(e)}, 503)

    def _handle_providers(self):
        config = load_config()
        try:
            pipeline = _build_pipeline(config)
            _json_response(self, {"providers": pipeline.status()})
        except ProviderExhaustedError as e:
            _json_response(self, {"providers": [], "error": str(e)}, 503)

    def _handle_sessions_list(self):
        config = load_config()
        conn = get_connection()
        sessions = list_sessions(conn)
        _json_response(self, {"sessions": [
            {"id": s["id"], "name": s.get("name", s["id"]), "message_count": s.get("message_count", 0)}
            for s in sessions
        ]})

    def _handle_session_get(self, session_id: str):
        conn = get_connection()
        messages = load_messages(conn, session_id)
        if not messages:
            _error_response(self, f"Session not found: {session_id}", 404)
            return
        _json_response(self, {
            "session_id": session_id,
            "messages": [{"role": m["role"], "content": m["content"]} for m in messages],
        })

    def _handle_ask(self, body: dict, shell: bool, code: bool):
        prompt = body.get("prompt", "").strip()
        if not prompt:
            _error_response(self, "Missing required field: prompt")
            return

        model = body.get("model")
        web = body.get("web", False)
        lite = body.get("lite", False)
        session_name = body.get("session")

        config = load_config()

        # Determine role
        if shell:
            role_name = "shell"
        elif code:
            role_name = "code"
        else:
            role_name = "default"
        role = get_role(role_name)

        # Build messages
        messages = []
        if role.system_prompt:
            messages.append({"role": "system", "content": role.system_prompt})

        # Web search
        if web and not lite:
            try:
                from ..web import web_search
                web_block = asyncio.run(web_search(prompt))
                if web_block:
                    messages.append({"role": "system", "content": web_block})
            except Exception:
                pass

        messages.append({"role": "user", "content": prompt})

        # Run pipeline
        try:
            pipeline = _build_pipeline(config)
            response_text = asyncio.run(pipeline.complete(messages, model=model))
            if shell:
                # Strip fences for shell commands
                response_text = response_text.strip().strip("`").strip()

            result = {
                "response": response_text,
                "provider": pipeline.last_provider,
            }
            if session_name:
                result["session"] = session_name
            _json_response(self, result)

        except ProviderExhaustedError as e:
            _error_response(self, f"All providers failed: {e}", 503)
        except Exception as e:
            _error_response(self, str(e), 500)

    def _get_version(self) -> str:
        try:
            from ..__version__ import __version__
            return __version__
        except Exception:
            return "unknown"


def _pid_file():
    """Return path to the PID file for the daemon serve process."""
    from ..config import CONFIG_DIR
    return CONFIG_DIR / "serve.pid"


def run_serve(host: str = "127.0.0.1", port: int = 8765, quiet: bool = False,
              daemon: bool = False) -> None:
    """Start the aicli HTTP API server. Blocks until Ctrl+C.

    If daemon=True, forks into the background, writes PID to CONFIG_DIR/serve.pid,
    and returns immediately. Use `aicli serve stop` to terminate.
    """
    if daemon:
        _start_daemon(host, port, quiet)
        return

    server = HTTPServer((host, port), AicliHandler)
    base_url = f"http://{host}:{port}"

    if not quiet:
        print(f"\n\033[1maicli serve\033[0m — local HTTP API")
        print(f"  Listening: \033[36m{base_url}\033[0m")
        print(f"")
        print(f"  Endpoints:")
        print(f"    POST {base_url}/ask          — single-shot prompt")
        print(f"    POST {base_url}/ask/shell    — shell command generation")
        print(f"    POST {base_url}/ask/code     — code generation")
        print(f"    GET  {base_url}/sessions     — list sessions")
        print(f"    GET  {base_url}/sessions/:id — session messages")
        print(f"    GET  {base_url}/health       — health + provider status")
        print(f"    GET  {base_url}/providers    — provider status")
        print(f"")
        print(f"  Example:")
        print(f'    curl -s {base_url}/ask -d \'{{"prompt":"hello"}}\' -H "Content-Type: application/json"')
        print(f"")
        print(f"  \033[90mCtrl+C to stop\033[0m\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        if not quiet:
            print("\n\033[90maicli serve stopped.\033[0m")
        server.shutdown()


def _start_daemon(host: str, port: int, quiet: bool) -> None:
    """Fork serve into the background and write PID to serve.pid."""
    import os
    import sys

    pid_file = _pid_file()
    pid_file.parent.mkdir(parents=True, exist_ok=True)

    # Check if already running
    if pid_file.exists():
        existing_pid = pid_file.read_text().strip()
        try:
            os.kill(int(existing_pid), 0)  # 0 = check existence only
            print(f"\033[33maicli serve already running (PID {existing_pid})\033[0m")
            print(f"  Stop with: \033[36maicli serve stop\033[0m")
            return
        except (ProcessLookupError, ValueError):
            pid_file.unlink(missing_ok=True)  # stale PID file

    pid = os.fork()
    if pid > 0:
        # Parent — print status and exit
        if not quiet:
            base_url = f"http://{host}:{port}"
            print(f"\033[32m✓ aicli serve started in background\033[0m (PID {pid})")
            print(f"  Listening: \033[36m{base_url}\033[0m")
            print(f"  Stop with: \033[36maicli serve stop\033[0m")
        return

    # Child — detach from terminal and start server
    os.setsid()
    # Redirect stdin/stdout/stderr to /dev/null in daemon
    devnull = open(os.devnull, "r+")
    os.dup2(devnull.fileno(), sys.stdin.fileno())
    os.dup2(devnull.fileno(), sys.stdout.fileno())
    os.dup2(devnull.fileno(), sys.stderr.fileno())

    # Write PID file
    pid_file.write_text(str(os.getpid()))

    try:
        server = HTTPServer((host, port), AicliHandler)
        server.serve_forever()
    finally:
        pid_file.unlink(missing_ok=True)
    os._exit(0)


def stop_serve() -> None:
    """Stop a background aicli serve daemon by sending SIGTERM to saved PID."""
    import os
    import signal

    pid_file = _pid_file()
    if not pid_file.exists():
        print("\033[33mNo aicli serve daemon is running (no PID file found).\033[0m")
        return

    try:
        pid = int(pid_file.read_text().strip())
    except ValueError:
        print("\033[31mCorrupt PID file — removing.\033[0m")
        pid_file.unlink(missing_ok=True)
        return

    try:
        os.kill(pid, signal.SIGTERM)
        pid_file.unlink(missing_ok=True)
        print(f"\033[32m✓ aicli serve stopped\033[0m (PID {pid})")
    except ProcessLookupError:
        print(f"\033[33mProcess {pid} not found — removing stale PID file.\033[0m")
        pid_file.unlink(missing_ok=True)
    except PermissionError:
        print(f"\033[31mPermission denied killing PID {pid}.\033[0m")
