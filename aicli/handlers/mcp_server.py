"""
handlers/mcp_server.py — MCP (Model Context Protocol) server for aicli.

Exposes aicli as a Claude Desktop / MCP-compatible tool via stdio or SSE transport.

Tools exposed:
  ask(prompt, session_id?, model?, web?, role?)
                             — single-shot query, returns text
                             — web=true enables 6-backend web search
                             — role overrides system prompt
  cmd(prompt, model?)        — shell command generation, returns command string
  code(prompt, language?, model?)
                             — code generation, returns code string
  tag(session_id, tags)      — tag a session in the graph
  do(prompt, dry_run?, auto_confirm?, role?)
                             — OS function calling: open browser, play music,
                               send email, notify, read/write files, run commands
                             — dispatches to the 12 built-in OS tools
                             — dry_run=true returns planned calls without executing

Resources exposed:
  sessions://list                — list all sessions (URI resource)
  sessions://{session_id}        — read session message history (URI template)

Usage:
  aicli mcp                      — stdio transport (Claude Desktop default)
  aicli mcp --transport sse      — SSE transport (web clients)
  aicli mcp --transport sse --port 8766

Claude Desktop config (~/.config/claude/claude_desktop_config.json):
  {
    "mcpServers": {
      "aicli": {
        "command": "aicli",
        "args": ["mcp"]
      }
    }
  }
"""

import asyncio
import json
import queue
import sys
from typing import Any

from ..config import load_config, CONFIG_DIR, CHROMA_DIR
from ..providers.pipeline import ProviderPipeline, ProviderExhaustedError

# Optional RAG dependency — bound at module level so tests can patch
# aicli.handlers.mcp_server.ContextRetriever cleanly.
# CHROMA_DIR lives in the single config import line above (Phase 5 check).
# ContextRetriever is None when chromadb is absent; _tool_ask guards on it.
try:
    from ..context.retriever import ContextRetriever
except ImportError:
    ContextRetriever = None  # type: ignore[assignment,misc]


# ── MCP protocol constants ────────────────────────────────────────────────────

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "aicli-maxmux"
SERVER_VERSION_IMPORT = None  # loaded lazily to avoid import at module level


def _server_version() -> str:
    global SERVER_VERSION_IMPORT
    if SERVER_VERSION_IMPORT is None:
        try:
            from aicli.__version__ import __version__
            SERVER_VERSION_IMPORT = __version__
        except Exception:
            SERVER_VERSION_IMPORT = "1.6.3"
    return SERVER_VERSION_IMPORT


# ── Tool definitions ──────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "ask",
        "description": (
            "Send a prompt to aicli and return the AI response as text. "
            "Uses the configured provider chain with automatic failover. "
            "Optionally provide a session_id to use a specific session context. "
            "Set web=true to search the web before answering (6-backend chain). "
            "Set role to override the system prompt (e.g. 'shell', 'code', 'default')."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "The prompt to send to the AI",
                },
                "session_id": {
                    "type": "string",
                    "description": "Optional session ID for context (leave empty for stateless query)",
                },
                "model": {
                    "type": "string",
                    "description": "Optional model override (e.g. 'llama-3.3-70b-versatile')",
                },
                "web": {
                    "type": "boolean",
                    "description": "Search the web before answering (default: false)",
                },
                "role": {
                    "type": "string",
                    "description": "Override system prompt role (e.g. 'shell', 'code', 'default')",
                },
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "cmd",
        "description": (
            "Generate a shell command for the given task description. "
            "Returns a raw shell command string ready to copy-paste or execute. "
            "Does NOT execute the command — returns text only."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Task description (e.g. 'find all files larger than 100MB')",
                },
                "model": {
                    "type": "string",
                    "description": "Optional model override",
                },
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "code",
        "description": (
            "Generate code for the given task description. "
            "Returns raw code only — no markdown fences, no explanations. "
            "Specify language to get code in a specific programming language."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Code generation task (e.g. 'write a merge sort in Python')",
                },
                "language": {
                    "type": "string",
                    "description": "Programming language (default: python)",
                    "enum": ["python", "bash", "javascript", "typescript", "node", "ruby", "go", "rust"],
                },
                "model": {
                    "type": "string",
                    "description": "Optional model override",
                },
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "tag",
        "description": (
            "Add tags to a session in the aicli graph viewer. "
            "Tags appear as chips in the graph browser for filtering. "
            "Returns the updated tag list for the session."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Session ID or name to tag",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of tags to add (merged with existing)",
                },
            },
            "required": ["session_id", "tags"],
        },
    },
    {
        "name": "do",
        "description": (
            "Execute tasks by dispatching OS tool calls via aicli's function-calling system. "
            "The LLM decides which of the 12 built-in tools to call based on the prompt. "
            "Tools: open_url_in_browser, play_music, send_email, send_notification, "
            "get_clipboard, copy_to_clipboard, open_file, read_file_content, "
            "write_file_content, search_web, get_system_info, run_shell_command. "
            "Set dry_run=true to see planned tool calls without executing. "
            "auto_confirm=true skips per-tool confirmation (use carefully). "
            "Always returns a human-readable summary of what was done."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Task to perform (e.g. 'play music and open hacker news')",
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "Show planned tool calls without executing (default: false)",
                },
                "auto_confirm": {
                    "type": "boolean",
                    "description": "Skip per-tool confirmation prompts (default: false)",
                },
                "role": {
                    "type": "string",
                    "description": "Optional custom role / system prompt for the function-calling LLM",
                },
                "model": {
                    "type": "string",
                    "description": "Optional model override",
                },
            },
            "required": ["prompt"],
        },
    },
]

# ── Resource definitions ──────────────────────────────────────────────────────

RESOURCES = [
    {
        "uri": "sessions://list",
        "name": "All Sessions",
        "description": "List of all aicli chat sessions with metadata",
        "mimeType": "application/json",
    },
]

RESOURCE_TEMPLATES = [
    {
        "uriTemplate": "sessions://{session_id}",
        "name": "Session Messages",
        "description": "Full message history for a specific session",
        "mimeType": "application/json",
    },
]


# ── Tool implementations ──────────────────────────────────────────────────────

async def _tool_ask(
    prompt: str,
    session_id: str | None = None,
    model: str | None = None,
    web: bool = False,
    role: str | None = None,
) -> str:
    """Single-shot query, returns response text.

    If session_id is provided, loads session history AND performs semantic RAG
    search (if chromadb is available) for richer context than the last-10-message window.
    web=True triggers the 6-backend web search chain before calling the LLM.
    role overrides the default system prompt with a named role or literal string.
    """
    from ..role import get_role
    config = load_config()
    try:
        pipeline = ProviderPipeline(
            provider_chain=config["provider_chain"],
            cooldown_seconds=config["cooldown_seconds"],
            max_retries_per_provider=config["max_retries_per_provider"],
            show_provider=False,
        )
    except ProviderExhaustedError as e:
        return f"Error: {e}"

    # Role: use provided role name, or fallback to "default"
    if role:
        try:
            role_obj = get_role(role)
        except Exception:
            role_obj = get_role("default")
    else:
        role_obj = get_role("default")

    messages = []
    if role_obj.system_prompt:
        messages.append({"role": "system", "content": role_obj.system_prompt})

    # RAG semantic context — inject before session history if chromadb available.
    # Uses module-level ContextRetriever / CHROMA_DIR (bound at import time, or None
    # if chromadb is absent) so tests can patch aicli.handlers.mcp_server.ContextRetriever.
    rag_block = None
    try:
        if ContextRetriever is None or CHROMA_DIR is None:
            raise ImportError("chromadb not installed")
        retriever = ContextRetriever(CHROMA_DIR)
        status = retriever.status()
        if status["chat_chunks"] > 0:
            rag_block = retriever.retrieve(
                prompt,
                include_files=False,
                include_chat=True,
                n_chat=5,
                min_score=0.25,
            )
    except Exception:
        pass  # RAG optional — chromadb may not be installed

    if rag_block:
        messages.append({"role": "system", "content": rag_block})

    # If session_id provided, also load recent message history from that session
    if session_id:
        try:
            from ..db.chat_db import get_connection, load_messages, list_sessions
            conn = get_connection()
            sessions = list_sessions(conn)
            matching = [s for s in sessions if s["name"] == session_id or s["id"] == session_id]
            if matching:
                history = load_messages(conn, matching[0]["id"])
                # Include last 10 messages as recent context (after RAG block)
                for msg in history[-10:]:
                    messages.append({"role": msg["role"], "content": msg["content"]})
        except Exception:
            pass  # Session context optional — continue without it

    messages.append({"role": "user", "content": prompt})

    # Web search — inject results as system message before user turn when web=True
    if web:
        try:
            from ..web import web_search
            web_block = await web_search(prompt)
            if web_block:
                # Insert web results before the user turn (second-to-last position)
                messages.insert(-1, {"role": "system", "content": web_block})
        except Exception:
            pass  # Web search optional — continue without if it fails

    try:
        return await pipeline.complete(messages, model=model)
    except ProviderExhaustedError as e:
        return f"Error: All providers failed — {e}"


async def _tool_cmd(prompt: str, model: str | None = None) -> str:
    """Shell command generation, returns command string."""
    from ..role import get_role
    config = load_config()
    try:
        pipeline = ProviderPipeline(
            provider_chain=config["provider_chain"],
            cooldown_seconds=config["cooldown_seconds"],
            max_retries_per_provider=config["max_retries_per_provider"],
            show_provider=False,
        )
    except ProviderExhaustedError as e:
        return f"Error: {e}"

    role = get_role("shell")
    messages = []
    if role.system_prompt:
        messages.append({"role": "system", "content": role.system_prompt})
    messages.append({"role": "user", "content": prompt})

    try:
        result = await pipeline.complete(messages, model=model)
        # Strip markdown fences: ```bash\n...\n``` or ```\n...\n``` or lone backtick wrapping
        import re as _re
        result = result.strip()
        result = _re.sub(r'^```[a-zA-Z]*\n?', '', result)
        result = _re.sub(r'\n?```$', '', result)
        result = result.strip().strip('`').strip()  # remove lone backtick wrapping e.g. `ls -la`
        return result.strip()
    except ProviderExhaustedError as e:
        return f"Error: All providers failed — {e}"


async def _tool_code(prompt: str, language: str = "python", model: str | None = None) -> str:
    """Code generation, returns raw code."""
    from ..role import get_role

    # Proper display names — capitalize() gives wrong casing for js/ts/node
    _LANG_DISPLAY = {
        "python": "Python",
        "bash": "Bash",
        "javascript": "JavaScript",
        "typescript": "TypeScript",
        "node": "Node.js",
        "ruby": "Ruby",
        "go": "Go",
        "rust": "Rust",
    }

    config = load_config()
    try:
        pipeline = ProviderPipeline(
            provider_chain=config["provider_chain"],
            cooldown_seconds=config["cooldown_seconds"],
            max_retries_per_provider=config["max_retries_per_provider"],
            show_provider=False,
        )
    except ProviderExhaustedError as e:
        return f"Error: {e}"

    role = get_role("code")
    messages = []
    if language != "python":
        lang_display = _LANG_DISPLAY.get(language, language.capitalize())
        messages.append({
            "role": "system",
            "content": (
                f"You are a {lang_display} code generation assistant. "
                f"Output ONLY raw {lang_display} code with no explanation, "
                f"no markdown fences, no backticks. "
                f"The code must be complete and runnable as-is."
            )
        })
    elif role.system_prompt:
        messages.append({"role": "system", "content": role.system_prompt})

    messages.append({"role": "user", "content": prompt})

    try:
        return await pipeline.complete(messages, model=model)
    except ProviderExhaustedError as e:
        return f"Error: All providers failed — {e}"


def _tool_tag(session_id: str, tags: list[str]) -> str:
    """Add tags to a session in graph_links.json.
    Resolves session name or partial UUID to full UUID via DB lookup.
    """
    import json as _json
    try:
        # Resolve session name / short-id → full UUID via DB
        resolved_id = session_id
        display_name = session_id
        try:
            from ..db.chat_db import get_connection, list_sessions
            conn = get_connection()
            sessions = list_sessions(conn)
            matching = [
                s for s in sessions
                if s["name"] == session_id
                or s["id"] == session_id
                or s["id"].startswith(session_id)
            ]
            if matching:
                resolved_id = matching[0]["id"]
                display_name = matching[0]["name"]
        except Exception:
            pass  # Fall back to using literal string as graph key

        graph_file = CONFIG_DIR / "graph_links.json"
        data: dict = {}
        if graph_file.exists():
            try:
                data = _json.loads(graph_file.read_text())
            except Exception:
                data = {}

        names = data.get("names", {})
        if resolved_id not in names:
            names[resolved_id] = {"name": display_name, "notes": "", "tags": []}

        existing = set(names[resolved_id].get("tags", []))
        new_tags = sorted(existing | set(tags))
        names[resolved_id]["tags"] = new_tags
        data["names"] = names

        graph_file.parent.mkdir(parents=True, exist_ok=True)
        graph_file.write_text(_json.dumps(data, indent=2))
        added = sorted(set(tags) - existing)
        return (
            f"Tagged '{display_name}' with: {', '.join(sorted(set(tags)))}. "
            f"All tags: {', '.join(new_tags)}"
            + (f" (added: {', '.join(added)})" if added else "")
        )
    except Exception as e:
        return f"Error tagging session: {e}"


# ── do tool — OS function calling via MCP ─────────────────────────────────────

async def _tool_do(
    prompt: str,
    dry_run: bool = False,
    auto_confirm: bool = True,  # MCP callers are non-interactive — default to auto_confirm
    role: str | None = None,
    model: str | None = None,
) -> str:
    """Execute OS tool calls via aicli's function-calling system.

    MCP clients are non-interactive, so auto_confirm defaults to True (unlike
    the CLI 'aicli do' which defaults to requiring confirmation). The caller can
    set auto_confirm=False to get a dry-run-style description instead.

    Returns a human-readable summary of what was done (or would be done).
    """
    # Capture stdout since run_do_command prints directly
    import io
    import contextlib

    output_buf = io.StringIO()
    try:
        from ..tools.executor import run_do_command
        with contextlib.redirect_stdout(output_buf):
            await run_do_command(
                prompt_parts=(prompt,),
                auto_confirm=auto_confirm,
                dry_run=dry_run,
                quiet=False,
                model=model,
                lite=False,
                role=role,
            )
        output = output_buf.getvalue().strip()
        return output if output else f"{'[dry-run] ' if dry_run else ''}Completed: {prompt}"
    except ImportError:
        # tools.executor not available (lite install) — fall back to plain ask
        return f"OS tools not available in this install. Use: aicli do \"{prompt}\""
    except Exception as e:
        return f"do tool error: {e}"


# ── Resource implementations ──────────────────────────────────────────────────

def _resource_sessions_list() -> str:
    """Return JSON list of all sessions."""
    try:
        from ..db.chat_db import get_connection, list_sessions
        conn = get_connection()
        sessions = list_sessions(conn)
        result = [
            {
                "id": s["id"],
                "name": s["name"],
                "message_count": s["message_count"],
                "updated_at": s.get("updated_at", ""),
            }
            for s in sessions
        ]
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


def _resource_session_messages(session_id: str) -> str:
    """Return JSON message history for a session."""
    try:
        from ..db.chat_db import get_connection, list_sessions, load_messages
        conn = get_connection()
        sessions = list_sessions(conn)
        matching = [s for s in sessions if s["name"] == session_id or s["id"] == session_id]
        if not matching:
            return json.dumps({"error": f"Session not found: {session_id}"})
        messages = load_messages(conn, matching[0]["id"])
        result = [{"role": m["role"], "content": m["content"]} for m in messages]
        return json.dumps({"session": matching[0]["name"], "messages": result}, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


# ── JSON-RPC message handling ─────────────────────────────────────────────────

def _make_response(request_id: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _make_error(request_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


async def _handle_message(message: dict) -> dict | None:
    """Dispatch a JSON-RPC message and return the response (or None for notifications)."""
    method = message.get("method", "")
    params = message.get("params", {})
    req_id = message.get("id")

    # Notifications have no id — handle and return None
    if req_id is None:
        return None  # notifications/initialized and others — no response

    # id=0 is valid JSON-RPC (falsy but not None) — proceed normally

    # ── initialize ───────────────────────────────────────────────────────────
    if method == "initialize":
        return _make_response(req_id, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {
                "tools": {"listChanged": False},
                "resources": {"subscribe": False, "listChanged": False},
            },
            "serverInfo": {
                "name": SERVER_NAME,
                "version": _server_version(),
            },
        })

    # ── tools/list ───────────────────────────────────────────────────────────
    if method == "tools/list":
        return _make_response(req_id, {"tools": TOOLS})

    # ── tools/call ───────────────────────────────────────────────────────────
    if method == "tools/call":
        tool_name = params.get("name", "")
        args = params.get("arguments", {})

        if not tool_name:
            return _make_error(req_id, -32602, "Missing required parameter: name")

        try:
            if tool_name == "ask":
                result = await _tool_ask(
                    prompt=args["prompt"],
                    session_id=args.get("session_id"),
                    model=args.get("model"),
                    web=bool(args.get("web", False)),
                    role=args.get("role"),
                )
            elif tool_name == "cmd":
                result = await _tool_cmd(
                    prompt=args["prompt"],
                    model=args.get("model"),
                )
            elif tool_name == "code":
                result = await _tool_code(
                    prompt=args["prompt"],
                    language=args.get("language", "python"),
                    model=args.get("model"),
                )
            elif tool_name == "tag":
                result = _tool_tag(
                    session_id=args["session_id"],
                    tags=args.get("tags", []),
                )
            elif tool_name == "do":
                result = await _tool_do(
                    prompt=args["prompt"],
                    dry_run=bool(args.get("dry_run", False)),
                    auto_confirm=bool(args.get("auto_confirm", True)),
                    role=args.get("role"),
                    model=args.get("model"),
                )
            else:
                return _make_error(req_id, -32601, f"Unknown tool: {tool_name}")

            return _make_response(req_id, {
                "content": [{"type": "text", "text": result}],
                "isError": result.startswith("Error:"),
            })

        except KeyError as e:
            return _make_error(req_id, -32602, f"Missing required argument: {e}")
        except Exception as e:
            return _make_error(req_id, -32603, f"Tool execution error: {e}")

    # ── resources/list ───────────────────────────────────────────────────────
    if method == "resources/list":
        return _make_response(req_id, {
            "resources": RESOURCES,
            "resourceTemplates": RESOURCE_TEMPLATES,
        })

    # ── resources/read ───────────────────────────────────────────────────────
    if method == "resources/read":
        uri = params.get("uri", "")

        if uri == "sessions://list":
            content = _resource_sessions_list()
            return _make_response(req_id, {
                "contents": [{"uri": uri, "mimeType": "application/json", "text": content}]
            })

        if uri.startswith("sessions://") and uri != "sessions://list":
            session_id = uri.removeprefix("sessions://")
            content = _resource_session_messages(session_id)
            return _make_response(req_id, {
                "contents": [{"uri": uri, "mimeType": "application/json", "text": content}]
            })

        return _make_error(req_id, -32002, f"Resource not found: {uri}")

    # ── ping ─────────────────────────────────────────────────────────────────
    if method == "ping":
        return _make_response(req_id, {})

    return _make_error(req_id, -32601, f"Method not found: {method}")


# ── stdio transport ───────────────────────────────────────────────────────────

async def _run_stdio():
    """Run MCP server over stdio — the default transport for Claude Desktop.

    Reads newline-delimited JSON-RPC messages from stdin, writes responses to stdout.
    Status/debug messages go to stderr so they don't corrupt the JSON-RPC channel.
    """
    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader(limit=2 ** 20)
    protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)

    # Write directly to stdout buffer — no pipe transport needed (avoids the class-as-factory bug)
    out = sys.stdout.buffer

    while True:
        try:
            line_bytes = await reader.readline()
            if not line_bytes:
                break
            line = line_bytes.decode("utf-8", errors="replace").strip()
            if not line:
                continue

            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue

            response = await _handle_message(message)
            if response is not None:
                out.write((json.dumps(response) + "\n").encode("utf-8"))
                out.flush()

        except (EOFError, ConnectionResetError, BrokenPipeError):
            break
        except Exception as exc:
            print(f"[aicli mcp] stdio error: {exc}", file=sys.stderr, flush=True)
            break


# ── SSE transport ─────────────────────────────────────────────────────────────

async def _run_sse(host: str = "127.0.0.1", port: int = 8766, quiet: bool = False):
    """Run MCP server over HTTP+SSE — for web-based MCP clients.

    Uses stdlib queue.SimpleQueue (thread-safe) rather than asyncio.Queue so that
    the synchronous BaseHTTPRequestHandler threads can put/get without needing the
    asyncio event loop. The loop reference is captured once and passed in via closure.
    """
    from http.server import BaseHTTPRequestHandler, HTTPServer
    import threading
    import time

    # Capture the running loop once — passed into the POST handler via closure
    loop = asyncio.get_running_loop()
    # session_id -> thread-safe SimpleQueue of response dicts
    sessions: dict[int, queue.SimpleQueue] = {}
    sessions_lock = threading.Lock()

    class SSEHandler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            if not quiet:
                super().log_message(fmt, *args)

        def do_OPTIONS(self):
            self.send_response(200)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()

        def do_GET(self):
            if self.path == "/health":
                body = json.dumps({
                    "status": "ok",
                    "server": SERVER_NAME,
                    "version": _server_version(),
                    "protocol": PROTOCOL_VERSION,
                    "transport": "sse",
                }).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if self.path.startswith("/sse"):
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()

                session_id = id(threading.current_thread())
                q: queue.SimpleQueue = queue.SimpleQueue()
                with sessions_lock:
                    sessions[session_id] = q

                try:
                    while True:
                        try:
                            # Block for up to 25s, then send keepalive
                            msg = q.get(timeout=25)
                            data = json.dumps(msg)
                            self.wfile.write(f"data: {data}\n\n".encode())
                            self.wfile.flush()
                        except queue.Empty:
                            # Send SSE keepalive comment to prevent client timeout
                            self.wfile.write(b": keepalive\n\n")
                            self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, OSError):
                    pass
                finally:
                    with sessions_lock:
                        sessions.pop(session_id, None)
                return

            self.send_response(404)
            self.end_headers()

        def do_POST(self):
            if self.path == "/message":
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length)
                self.send_response(202)
                self.send_header("Content-Length", "0")
                self.end_headers()

                async def _process():
                    try:
                        message = json.loads(body)
                        response = await _handle_message(message)
                        if response is not None:
                            with sessions_lock:
                                active = list(sessions.values())
                            for q in active:
                                q.put(response)
                    except Exception as exc:
                        print(f"[aicli mcp] SSE process error: {exc}",
                              file=sys.stderr, flush=True)

                # Schedule coroutine on the captured event loop from the HTTP thread
                asyncio.run_coroutine_threadsafe(_process(), loop)
                return

            self.send_response(404)
            self.end_headers()

    server = HTTPServer((host, port), SSEHandler)
    if not quiet:
        print(f"aicli MCP server (SSE) listening on http://{host}:{port}", flush=True)
        print(f"  SSE endpoint:     http://{host}:{port}/sse", flush=True)
        print(f"  Message endpoint: http://{host}:{port}/message", flush=True)
        print(f"  Health check:     http://{host}:{port}/health", flush=True)

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        while True:
            await asyncio.sleep(1)
    except (KeyboardInterrupt, asyncio.CancelledError):
        server.shutdown()


# ── Entry point ───────────────────────────────────────────────────────────────

def run_mcp(transport: str = "stdio", host: str = "127.0.0.1", port: int = 8766, quiet: bool = False):
    """Start the MCP server. Called from app.py aicli mcp command."""
    if transport == "stdio":
        if not quiet:
            print(f"aicli MCP server starting (stdio transport, protocol {PROTOCOL_VERSION})",
                  file=sys.stderr, flush=True)
            print(f"Server: {SERVER_NAME} v{_server_version()}", file=sys.stderr, flush=True)
        asyncio.run(_run_stdio())
    elif transport == "sse":
        asyncio.run(_run_sse(host=host, port=port, quiet=quiet))
    else:
        print(f"Unknown transport: {transport!r}. Use 'stdio' or 'sse'.", file=sys.stderr)
        sys.exit(1)
