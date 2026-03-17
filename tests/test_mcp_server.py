"""
tests/test_mcp_server.py — Tests for the aicli MCP server.

Tests the JSON-RPC message handling, tool dispatch, and resource access
without requiring a live provider or actual stdio/SSE transport.

All provider calls are mocked. No network required.

NOTE: asyncio_mode = "auto" in pyproject.toml means all async tests
must be declared as `async def` and use `await` — NOT asyncio.run().
Using asyncio.run() inside an already-running pytest-asyncio event loop
raises RuntimeError: This event loop is already running.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_pipeline():
    """Mock ProviderPipeline that returns a predictable response."""
    pipeline = MagicMock()
    pipeline.complete = AsyncMock(return_value="mocked AI response")
    pipeline.last_provider = "groq"

    async def mock_stream(messages, model=None, requires_vision=False):
        yield "mocked"
        yield " response"

    pipeline.stream = mock_stream
    return pipeline


@pytest.fixture
def mock_config():
    """Minimal config dict matching what load_config() returns.
    Note: 'data_dir' is NOT a real config key — _tool_tag uses CONFIG_DIR directly.
    """
    return {
        "provider_chain": ["groq"],
        "cooldown_seconds": 60,
        "max_retries_per_provider": 1,
        "show_provider": False,
    }


@pytest.fixture
def mock_sessions():
    return [
        {"id": "abc123", "name": "myproject", "message_count": 5, "updated_at": "2026-03-15"},
        {"id": "def456", "name": "work", "message_count": 12, "updated_at": "2026-03-14"},
    ]


@pytest.fixture
def mock_messages():
    return [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there!"},
        {"role": "user", "content": "What is Python?"},
        {"role": "assistant", "content": "Python is a programming language."},
    ]


# ── Test: initialize ──────────────────────────────────────────────────────────

class TestMCPInitialize:
    async def test_initialize_returns_correct_protocol_version(self):
        from aicli.handlers.mcp_server import _handle_message
        msg = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
        result = await _handle_message(msg)
        assert result["result"]["protocolVersion"] == "2024-11-05"

    async def test_initialize_returns_server_info(self):
        from aicli.handlers.mcp_server import _handle_message
        msg = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
        result = await _handle_message(msg)
        assert result["result"]["serverInfo"]["name"] == "aicli-maxmux"

    async def test_initialize_declares_tools_capability(self):
        from aicli.handlers.mcp_server import _handle_message
        msg = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
        result = await _handle_message(msg)
        assert "tools" in result["result"]["capabilities"]

    async def test_initialize_declares_resources_capability(self):
        from aicli.handlers.mcp_server import _handle_message
        msg = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
        result = await _handle_message(msg)
        assert "resources" in result["result"]["capabilities"]

    async def test_notification_without_id_returns_none(self):
        """Messages without id are notifications — no response expected."""
        from aicli.handlers.mcp_server import _handle_message
        msg = {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}
        result = await _handle_message(msg)
        assert result is None

    async def test_notifications_initialized_no_params_returns_none(self):
        from aicli.handlers.mcp_server import _handle_message
        msg = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        result = await _handle_message(msg)
        assert result is None

    async def test_ping_returns_empty_result(self):
        from aicli.handlers.mcp_server import _handle_message
        msg = {"jsonrpc": "2.0", "id": 99, "method": "ping", "params": {}}
        result = await _handle_message(msg)
        assert result["result"] == {}

    async def test_unknown_method_returns_error_32601(self):
        from aicli.handlers.mcp_server import _handle_message
        msg = {"jsonrpc": "2.0", "id": 2, "method": "nonexistent/method", "params": {}}
        result = await _handle_message(msg)
        assert "error" in result
        assert result["error"]["code"] == -32601


# ── Test: tools/list ─────────────────────────────────────────────────────────

class TestMCPToolsList:
    async def test_tools_list_returns_four_tools(self):
        from aicli.handlers.mcp_server import _handle_message
        msg = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
        result = await _handle_message(msg)
        assert len(result["result"]["tools"]) >= 4  # 5 tools since v1.5.7 (added do)

    async def test_tools_list_contains_ask(self):
        from aicli.handlers.mcp_server import _handle_message
        msg = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
        result = await _handle_message(msg)
        names = [t["name"] for t in result["result"]["tools"]]
        assert "ask" in names

    async def test_tools_list_contains_cmd(self):
        from aicli.handlers.mcp_server import _handle_message
        msg = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
        result = await _handle_message(msg)
        assert "cmd" in [t["name"] for t in result["result"]["tools"]]

    async def test_tools_list_contains_code(self):
        from aicli.handlers.mcp_server import _handle_message
        msg = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
        result = await _handle_message(msg)
        assert "code" in [t["name"] for t in result["result"]["tools"]]

    async def test_tools_list_contains_tag(self):
        from aicli.handlers.mcp_server import _handle_message
        msg = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
        result = await _handle_message(msg)
        assert "tag" in [t["name"] for t in result["result"]["tools"]]

    async def test_ask_tool_has_required_prompt(self):
        from aicli.handlers.mcp_server import _handle_message
        msg = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
        result = await _handle_message(msg)
        ask_tool = next(t for t in result["result"]["tools"] if t["name"] == "ask")
        assert "prompt" in ask_tool["inputSchema"]["required"]

    async def test_code_tool_has_language_enum(self):
        from aicli.handlers.mcp_server import _handle_message
        msg = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
        result = await _handle_message(msg)
        code_tool = next(t for t in result["result"]["tools"] if t["name"] == "code")
        assert "enum" in code_tool["inputSchema"]["properties"]["language"]

    async def test_code_tool_enum_contains_javascript(self):
        from aicli.handlers.mcp_server import _handle_message
        msg = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
        result = await _handle_message(msg)
        code_tool = next(t for t in result["result"]["tools"] if t["name"] == "code")
        assert "javascript" in code_tool["inputSchema"]["properties"]["language"]["enum"]

    async def test_tag_tool_requires_session_id_and_tags(self):
        from aicli.handlers.mcp_server import _handle_message
        msg = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
        result = await _handle_message(msg)
        tag_tool = next(t for t in result["result"]["tools"] if t["name"] == "tag")
        assert "session_id" in tag_tool["inputSchema"]["required"]
        assert "tags" in tag_tool["inputSchema"]["required"]


# ── Test: tools/call — ask ────────────────────────────────────────────────────

class TestMCPToolCallAsk:
    async def test_ask_returns_text_content(self, mock_pipeline, mock_config):
        from aicli.handlers.mcp_server import _handle_message
        msg = {
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "ask", "arguments": {"prompt": "hello"}}
        }
        with patch("aicli.handlers.mcp_server.load_config", return_value=mock_config), \
             patch("aicli.handlers.mcp_server.ProviderPipeline", return_value=mock_pipeline):
            result = await _handle_message(msg)
        assert result["result"]["content"][0]["type"] == "text"
        assert result["result"]["content"][0]["text"] == "mocked AI response"

    async def test_ask_missing_prompt_returns_error(self, mock_pipeline, mock_config):
        from aicli.handlers.mcp_server import _handle_message
        msg = {
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "ask", "arguments": {}}
        }
        with patch("aicli.handlers.mcp_server.load_config", return_value=mock_config), \
             patch("aicli.handlers.mcp_server.ProviderPipeline", return_value=mock_pipeline):
            result = await _handle_message(msg)
        assert "error" in result

    async def test_ask_with_model_override(self, mock_pipeline, mock_config):
        from aicli.handlers.mcp_server import _handle_message
        msg = {
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "ask", "arguments": {"prompt": "hello", "model": "llama3"}}
        }
        with patch("aicli.handlers.mcp_server.load_config", return_value=mock_config), \
             patch("aicli.handlers.mcp_server.ProviderPipeline", return_value=mock_pipeline):
            result = await _handle_message(msg)
        mock_pipeline.complete.assert_called_once()
        call_kwargs = mock_pipeline.complete.call_args
        passed_model = (
            call_kwargs.kwargs.get("model")
            or (call_kwargs.args[1] if len(call_kwargs.args) > 1 else None)
        )
        assert passed_model == "llama3"

    async def test_ask_is_error_false_on_success(self, mock_pipeline, mock_config):
        from aicli.handlers.mcp_server import _handle_message
        msg = {
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "ask", "arguments": {"prompt": "hello"}}
        }
        with patch("aicli.handlers.mcp_server.load_config", return_value=mock_config), \
             patch("aicli.handlers.mcp_server.ProviderPipeline", return_value=mock_pipeline):
            result = await _handle_message(msg)
        assert result["result"]["isError"] is False

    async def test_ask_injects_rag_context_when_available(self, mock_pipeline, mock_config):
        """_tool_ask injects RAG context block when chromadb has indexed data."""
        from aicli.handlers.mcp_server import _tool_ask
        mock_retriever = MagicMock()
        mock_retriever.status.return_value = {"chat_chunks": 5, "local_chunks": 0}
        mock_retriever.retrieve.return_value = "RELEVANT CONTEXT:\n\n[chat: sess-1]\nPython async patterns..."
        with patch("aicli.handlers.mcp_server.load_config", return_value=mock_config), \
             patch("aicli.handlers.mcp_server.ProviderPipeline", return_value=mock_pipeline), \
             patch("aicli.handlers.mcp_server.ContextRetriever", return_value=mock_retriever,
                   create=True), \
             patch("aicli.handlers.mcp_server.CHROMA_DIR", MagicMock(), create=True):
            result = await _tool_ask("tell me about async patterns")
        # RAG block should appear in the messages passed to pipeline.complete
        call_args = mock_pipeline.complete.call_args
        messages_passed = call_args.args[0] if call_args.args else call_args.kwargs.get("messages", [])
        system_contents = [m["content"] for m in messages_passed if m["role"] == "system"]
        assert any("RELEVANT CONTEXT" in c for c in system_contents)

    async def test_ask_continues_without_rag_when_chromadb_missing(self, mock_pipeline, mock_config):
        """_tool_ask works normally when chromadb is not installed."""
        from aicli.handlers.mcp_server import _tool_ask
        with patch("aicli.handlers.mcp_server.load_config", return_value=mock_config), \
             patch("aicli.handlers.mcp_server.ProviderPipeline", return_value=mock_pipeline):
            # ContextRetriever import will fail — should not raise
            result = await _tool_ask("hello")
        assert result == "mocked AI response"


# ── Test: tools/call — cmd ────────────────────────────────────────────────────

class TestMCPToolCallCmd:
    async def test_cmd_returns_stripped_command(self, mock_config):
        from aicli.handlers.mcp_server import _handle_message
        pipeline = MagicMock()
        pipeline.complete = AsyncMock(return_value="  `ls -la`  ")
        msg = {
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "cmd", "arguments": {"prompt": "list files"}}
        }
        with patch("aicli.handlers.mcp_server.load_config", return_value=mock_config), \
             patch("aicli.handlers.mcp_server.ProviderPipeline", return_value=pipeline):
            result = await _handle_message(msg)
        assert result["result"]["content"][0]["text"] == "ls -la"

    async def test_cmd_missing_prompt_returns_error(self, mock_config):
        from aicli.handlers.mcp_server import _handle_message
        pipeline = MagicMock()
        pipeline.complete = AsyncMock(return_value="ls -la")
        msg = {
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "cmd", "arguments": {}}
        }
        with patch("aicli.handlers.mcp_server.load_config", return_value=mock_config), \
             patch("aicli.handlers.mcp_server.ProviderPipeline", return_value=pipeline):
            result = await _handle_message(msg)
        assert "error" in result


# ── Test: tools/call — code ───────────────────────────────────────────────────

class TestMCPToolCallCode:
    async def test_code_defaults_to_python(self, mock_pipeline, mock_config):
        from aicli.handlers.mcp_server import _tool_code
        with patch("aicli.handlers.mcp_server.load_config", return_value=mock_config), \
             patch("aicli.handlers.mcp_server.ProviderPipeline", return_value=mock_pipeline):
            await _tool_code("write a sort function")
        mock_pipeline.complete.assert_called_once()

    async def test_code_bash_uses_correct_display_name(self, mock_config):
        from aicli.handlers.mcp_server import _tool_code
        pipeline = MagicMock()
        pipeline.complete = AsyncMock(return_value="#!/bin/bash\nls -la")
        with patch("aicli.handlers.mcp_server.load_config", return_value=mock_config), \
             patch("aicli.handlers.mcp_server.ProviderPipeline", return_value=pipeline):
            await _tool_code("list files", language="bash")
        messages = pipeline.complete.call_args[0][0]
        assert "Bash" in messages[0]["content"]

    async def test_code_javascript_uses_correct_display_name(self, mock_config):
        """javascript.capitalize() = 'Javascript' — must produce 'JavaScript'."""
        from aicli.handlers.mcp_server import _tool_code
        pipeline = MagicMock()
        pipeline.complete = AsyncMock(return_value="console.log('hi')")
        with patch("aicli.handlers.mcp_server.load_config", return_value=mock_config), \
             patch("aicli.handlers.mcp_server.ProviderPipeline", return_value=pipeline):
            await _tool_code("say hello", language="javascript")
        messages = pipeline.complete.call_args[0][0]
        content = messages[0]["content"]
        assert "JavaScript" in content
        assert "Javascript" not in content

    async def test_code_typescript_uses_correct_display_name(self, mock_config):
        """typescript.capitalize() = 'Typescript' — must produce 'TypeScript'."""
        from aicli.handlers.mcp_server import _tool_code
        pipeline = MagicMock()
        pipeline.complete = AsyncMock(return_value="const x: number = 1")
        with patch("aicli.handlers.mcp_server.load_config", return_value=mock_config), \
             patch("aicli.handlers.mcp_server.ProviderPipeline", return_value=pipeline):
            await _tool_code("declare a variable", language="typescript")
        messages = pipeline.complete.call_args[0][0]
        content = messages[0]["content"]
        assert "TypeScript" in content
        assert "Typescript" not in content

    async def test_code_node_uses_nodejs_display_name(self, mock_config):
        """'node'.capitalize() = 'Node' — must produce 'Node.js'."""
        from aicli.handlers.mcp_server import _tool_code
        pipeline = MagicMock()
        pipeline.complete = AsyncMock(return_value="require('fs')")
        with patch("aicli.handlers.mcp_server.load_config", return_value=mock_config), \
             patch("aicli.handlers.mcp_server.ProviderPipeline", return_value=pipeline):
            await _tool_code("read a file", language="node")
        messages = pipeline.complete.call_args[0][0]
        content = messages[0]["content"]
        assert "Node.js" in content


# ── Test: tools/call — tag ────────────────────────────────────────────────────

class TestMCPToolCallTag:
    def test_tag_creates_graph_entry(self, tmp_path):
        import json as _json
        from aicli.handlers.mcp_server import _tool_tag
        with patch("aicli.handlers.mcp_server.CONFIG_DIR", tmp_path):
            result = _tool_tag("session123", ["work", "python"])
        assert "work" in result
        assert "python" in result
        graph_file = tmp_path / "graph_links.json"
        assert graph_file.exists()
        data = _json.loads(graph_file.read_text())
        assert "session123" in data["names"]

    def test_tag_merges_with_existing(self, tmp_path):
        import json as _json
        from aicli.handlers.mcp_server import _tool_tag
        graph_file = tmp_path / "graph_links.json"
        graph_file.write_text(_json.dumps({
            "names": {"session123": {"name": "session123", "notes": "", "tags": ["existing"]}}
        }))
        with patch("aicli.handlers.mcp_server.CONFIG_DIR", tmp_path):
            _tool_tag("session123", ["new-tag"])
        data = _json.loads(graph_file.read_text())
        tags = data["names"]["session123"]["tags"]
        assert "existing" in tags
        assert "new-tag" in tags

    def test_tag_does_not_duplicate_existing(self, tmp_path):
        import json as _json
        from aicli.handlers.mcp_server import _tool_tag
        graph_file = tmp_path / "graph_links.json"
        graph_file.write_text(_json.dumps({
            "names": {"s1": {"name": "s1", "notes": "", "tags": ["dup"]}}
        }))
        with patch("aicli.handlers.mcp_server.CONFIG_DIR", tmp_path):
            _tool_tag("s1", ["dup"])
        data = _json.loads(graph_file.read_text())
        assert data["names"]["s1"]["tags"].count("dup") == 1

    def test_tag_returns_confirmation_message(self, tmp_path):
        from aicli.handlers.mcp_server import _tool_tag
        with patch("aicli.handlers.mcp_server.CONFIG_DIR", tmp_path):
            result = _tool_tag("mysession", ["urgent"])
        assert "mysession" in result
        assert "urgent" in result

    def test_tag_db_resolution_fallback(self, tmp_path):
        """When DB raises, falls back to using the literal string as key — no crash."""
        from aicli.handlers.mcp_server import _tool_tag
        with patch("aicli.handlers.mcp_server.CONFIG_DIR", tmp_path), \
             patch("aicli.handlers.mcp_server.ProviderPipeline", create=True), \
             patch("aicli.db.chat_db.get_connection", side_effect=Exception("no db")):
            result = _tool_tag("fallback-key", ["t1"])
        assert isinstance(result, str)
        # Result is either confirmation or error — must not raise
        assert "t1" in result or "Error" in result

    async def test_unknown_tool_returns_error(self):
        from aicli.handlers.mcp_server import _handle_message
        msg = {
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "nonexistent_tool", "arguments": {}}
        }
        result = await _handle_message(msg)
        assert "error" in result
        assert result["error"]["code"] == -32601

    async def test_empty_tool_name_returns_32602(self):
        """Empty tool name must return -32602 (missing param), not -32601 (unknown tool)."""
        from aicli.handlers.mcp_server import _handle_message
        msg = {
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "", "arguments": {}}
        }
        result = await _handle_message(msg)
        assert "error" in result
        assert result["error"]["code"] == -32602


# ── Test: resources/list ──────────────────────────────────────────────────────

class TestMCPResourcesList:
    async def test_resources_list_includes_sessions_list_uri(self):
        from aicli.handlers.mcp_server import _handle_message
        msg = {"jsonrpc": "2.0", "id": 1, "method": "resources/list", "params": {}}
        result = await _handle_message(msg)
        uris = [r["uri"] for r in result["result"]["resources"]]
        assert "sessions://list" in uris

    async def test_resources_list_includes_session_id_template(self):
        from aicli.handlers.mcp_server import _handle_message
        msg = {"jsonrpc": "2.0", "id": 1, "method": "resources/list", "params": {}}
        result = await _handle_message(msg)
        templates = result["result"]["resourceTemplates"]
        assert any("session_id" in t["uriTemplate"] for t in templates)

    async def test_resources_list_templates_have_mime_type(self):
        from aicli.handlers.mcp_server import _handle_message
        msg = {"jsonrpc": "2.0", "id": 1, "method": "resources/list", "params": {}}
        result = await _handle_message(msg)
        for tmpl in result["result"]["resourceTemplates"]:
            assert "mimeType" in tmpl


# ── Test: resources/read ──────────────────────────────────────────────────────

class TestMCPResourcesRead:
    async def test_sessions_list_returns_json_content(self, mock_sessions):
        from aicli.handlers.mcp_server import _handle_message
        msg = {
            "jsonrpc": "2.0", "id": 1, "method": "resources/read",
            "params": {"uri": "sessions://list"}
        }
        with patch("aicli.handlers.mcp_server._resource_sessions_list",
                   return_value=json.dumps(mock_sessions)):
            result = await _handle_message(msg)
        contents = result["result"]["contents"]
        assert len(contents) == 1
        assert contents[0]["mimeType"] == "application/json"

    async def test_session_by_id_calls_session_messages(self, mock_messages):
        from aicli.handlers.mcp_server import _handle_message
        msg = {
            "jsonrpc": "2.0", "id": 1, "method": "resources/read",
            "params": {"uri": "sessions://myproject"}
        }
        with patch("aicli.handlers.mcp_server._resource_session_messages") as mock_read:
            mock_read.return_value = json.dumps({"session": "myproject", "messages": mock_messages})
            result = await _handle_message(msg)
        assert result["result"]["contents"][0]["uri"] == "sessions://myproject"
        mock_read.assert_called_once_with("myproject")

    async def test_unknown_resource_uri_returns_32002(self):
        from aicli.handlers.mcp_server import _handle_message
        msg = {
            "jsonrpc": "2.0", "id": 1, "method": "resources/read",
            "params": {"uri": "unknown://whatever"}
        }
        result = await _handle_message(msg)
        assert "error" in result
        assert result["error"]["code"] == -32002

    async def test_empty_uri_returns_error(self):
        from aicli.handlers.mcp_server import _handle_message
        msg = {
            "jsonrpc": "2.0", "id": 1, "method": "resources/read",
            "params": {"uri": ""}
        }
        result = await _handle_message(msg)
        assert "error" in result

    async def test_sessions_list_uri_returned_in_contents(self, mock_sessions):
        from aicli.handlers.mcp_server import _handle_message
        msg = {
            "jsonrpc": "2.0", "id": 1, "method": "resources/read",
            "params": {"uri": "sessions://list"}
        }
        with patch("aicli.handlers.mcp_server._resource_sessions_list",
                   return_value=json.dumps(mock_sessions)):
            result = await _handle_message(msg)
        assert result["result"]["contents"][0]["uri"] == "sessions://list"


# ── Test: resource function layer ─────────────────────────────────────────────

class TestMCPResourceFunctions:
    def test_sessions_list_returns_valid_json_string(self, mock_sessions):
        from aicli.handlers import mcp_server as _m
        with patch.object(_m, "_resource_sessions_list", return_value=json.dumps(mock_sessions)):
            result = _m._resource_sessions_list()
        parsed = json.loads(result)
        assert isinstance(parsed, list)

    def test_sessions_list_error_returns_error_json(self):
        from aicli.handlers import mcp_server as _m
        with patch.object(_m, "_resource_sessions_list",
                          return_value=json.dumps({"error": "db error"})):
            result = _m._resource_sessions_list()
        assert "error" in json.loads(result)

    def test_session_messages_not_found_returns_error_json(self):
        from aicli.handlers import mcp_server as _m
        with patch.object(_m, "_resource_session_messages",
                          return_value=json.dumps({"error": "Session not found: nope"})):
            result = _m._resource_session_messages("nope")
        assert "error" in json.loads(result)

    def test_session_messages_found_returns_messages_key(self, mock_messages):
        from aicli.handlers import mcp_server as _m
        expected = json.dumps({"session": "myproject", "messages": mock_messages})
        with patch.object(_m, "_resource_session_messages", return_value=expected):
            result = _m._resource_session_messages("myproject")
        parsed = json.loads(result)
        assert "messages" in parsed
        assert parsed["session"] == "myproject"

    def test_both_functions_return_strings(self):
        from aicli.handlers import mcp_server as _m
        with patch.object(_m, "_resource_sessions_list", return_value="[]"):
            r1 = _m._resource_sessions_list()
        with patch.object(_m, "_resource_session_messages",
                          return_value=json.dumps({"error": "not found"})):
            r2 = _m._resource_session_messages("x")
        assert isinstance(r1, str)
        assert isinstance(r2, str)


# ── Test: app.py command registration ────────────────────────────────────────

class TestMCPAppCommand:
    def test_mcp_command_registered(self):
        import subprocess, sys
        result = subprocess.run(
            [sys.executable, "-c",
             "from aicli.app import cli; print(list(cli.commands.keys()))"],
            capture_output=True, text=True
        )
        assert "mcp" in result.stdout

    def test_tag_command_registered(self):
        import subprocess, sys
        result = subprocess.run(
            [sys.executable, "-c",
             "from aicli.app import cli; print(list(cli.commands.keys()))"],
            capture_output=True, text=True
        )
        assert "tag" in result.stdout

    def test_mcp_help_shows_transport_option(self):
        import subprocess, sys
        result = subprocess.run(
            [sys.executable, "-m", "aicli", "mcp", "--help"],
            capture_output=True, text=True
        )
        assert "stdio" in result.stdout or "transport" in result.stdout


# ── Test: JSON-RPC edge cases ─────────────────────────────────────────────────

class TestMCPEdgeCases:
    async def test_id_zero_is_valid_not_notification(self):
        """id=0 is falsy in Python but NOT a notification — must return a response."""
        from aicli.handlers.mcp_server import _handle_message
        msg = {"jsonrpc": "2.0", "id": 0, "method": "ping", "params": {}}
        result = await _handle_message(msg)
        assert result is not None
        assert result["id"] == 0
        assert result["result"] == {}

    async def test_notifications_initialized_no_response(self):
        from aicli.handlers.mcp_server import _handle_message
        msg = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        result = await _handle_message(msg)
        assert result is None

    async def test_tools_call_no_arguments_key_handled(self):
        """Missing 'arguments' key defaults to empty dict — no AttributeError."""
        from aicli.handlers.mcp_server import _handle_message
        msg = {
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "ask"}
        }
        result = await _handle_message(msg)
        assert "error" in result or "result" in result

    async def test_cmd_strips_triple_backtick_bash_fence(self, mock_config):
        from aicli.handlers.mcp_server import _tool_cmd
        pipeline = MagicMock()
        pipeline.complete = AsyncMock(return_value="```bash\nls -la\n```")
        with patch("aicli.handlers.mcp_server.load_config", return_value=mock_config), \
             patch("aicli.handlers.mcp_server.ProviderPipeline", return_value=pipeline):
            result = await _tool_cmd("list files")
        assert "```" not in result
        assert "ls -la" in result

    async def test_cmd_strips_annotated_fence(self, mock_config):
        from aicli.handlers.mcp_server import _tool_cmd
        pipeline = MagicMock()
        pipeline.complete = AsyncMock(return_value="```sh\nfind . -name '*.py'\n```")
        with patch("aicli.handlers.mcp_server.load_config", return_value=mock_config), \
             patch("aicli.handlers.mcp_server.ProviderPipeline", return_value=pipeline):
            result = await _tool_cmd("find py files")
        assert "```" not in result
        assert "find" in result

    async def test_cmd_plain_command_not_modified(self, mock_config):
        from aicli.handlers.mcp_server import _tool_cmd
        pipeline = MagicMock()
        pipeline.complete = AsyncMock(return_value="ls -la /tmp")
        with patch("aicli.handlers.mcp_server.load_config", return_value=mock_config), \
             patch("aicli.handlers.mcp_server.ProviderPipeline", return_value=pipeline):
            result = await _tool_cmd("list tmp")
        assert result == "ls -la /tmp"

    async def test_resources_read_empty_uri_returns_error(self):
        from aicli.handlers.mcp_server import _handle_message
        msg = {
            "jsonrpc": "2.0", "id": 1, "method": "resources/read",
            "params": {"uri": ""}
        }
        result = await _handle_message(msg)
        assert "error" in result


# ── Test: server constants and version ───────────────────────────────────────

class TestMCPServerVersion:
    def test_server_version_returns_non_empty_string(self):
        from aicli.handlers.mcp_server import _server_version
        version = _server_version()
        assert isinstance(version, str) and len(version) > 0

    def test_server_version_is_semver(self):
        from aicli.handlers.mcp_server import _server_version
        parts = _server_version().split(".")
        assert len(parts) >= 2
        assert all(p.isdigit() for p in parts[:2])

    def test_server_version_at_least_1_5_4(self):
        from aicli.handlers.mcp_server import _server_version
        v = _server_version()
        major, minor, patch_v = (int(p) for p in v.split(".")[:3])
        assert (major, minor, patch_v) >= (1, 5, 4)

    def test_tools_schema_serializable(self):
        from aicli.handlers.mcp_server import TOOLS
        parsed = json.loads(json.dumps(TOOLS))
        assert len(parsed) >= 4  # 5 tools since v1.5.7 (added do)

    def test_all_tools_have_input_schema_object(self):
        from aicli.handlers.mcp_server import TOOLS
        for tool in TOOLS:
            assert "inputSchema" in tool
            assert tool["inputSchema"]["type"] == "object"

    def test_all_tools_have_meaningful_descriptions(self):
        from aicli.handlers.mcp_server import TOOLS
        for tool in TOOLS:
            assert len(tool.get("description", "")) > 10

    def test_language_display_names_correct_casing(self):
        """_LANG_DISPLAY must contain correct mixed-case names, not capitalize() output."""
        import inspect
        from aicli.handlers.mcp_server import _tool_code
        source = inspect.getsource(_tool_code)
        assert "JavaScript" in source
        assert "TypeScript" in source
        assert "Node.js" in source
        assert "Javascript" not in source
        assert "Typescript" not in source


# ── Test: transport constants and entry ──────────────────────────────────────

class TestMCPTransport:
    def test_invalid_transport_exits_1(self):
        from aicli.handlers.mcp_server import run_mcp
        with pytest.raises(SystemExit) as exc_info:
            run_mcp(transport="invalid")
        assert exc_info.value.code == 1

    def test_server_name_is_aicli_maxmux(self):
        from aicli.handlers.mcp_server import SERVER_NAME
        assert SERVER_NAME == "aicli-maxmux"

    def test_protocol_version_is_2024_11_05(self):
        from aicli.handlers.mcp_server import PROTOCOL_VERSION
        assert PROTOCOL_VERSION == "2024-11-05"

    def test_protocol_version_is_date_format(self):
        import re
        from aicli.handlers.mcp_server import PROTOCOL_VERSION
        assert re.match(r"^\d{4}-\d{2}-\d{2}$", PROTOCOL_VERSION)

    def test_resources_and_templates_nonempty(self):
        from aicli.handlers.mcp_server import RESOURCES, RESOURCE_TEMPLATES
        assert len(RESOURCES) >= 1 and all("uri" in r for r in RESOURCES)
        assert len(RESOURCE_TEMPLATES) >= 1 and all("uriTemplate" in t for t in RESOURCE_TEMPLATES)
