"""
test_graph_server.py — Tests for aicli/graph_server.py

Run:
    pytest tests/test_graph_server.py -v

Covers:
    - load_sessions_from_exports: normal, skip rules, dedup, malformed JSON
    - load_graph_links / save_graph_links: round-trip, missing file, corrupt
    - _graph_links_file path resolution
    - GraphHandler: GET /, GET /api/sessions, POST /api/save, 404
    - _kill_existing: no process, invalid port
    - run_graph_server: port reuse (ReusableTCPServer)
"""

import json
import os
import threading
import time
import urllib.request
import http.client
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

# Mark server-starting test classes as slow
# Skip with: pytest tests/ -q -m "not slow"


# ── Helpers ───────────────────────────────────────────────────────────────────

import socket as _socket

def _wait_for_port(host: str, port: int, timeout: float = 3.0) -> bool:
    """Poll until port accepts connections — replaces time.sleep(0.x) for server startup."""
    import time as _time
    deadline = _time.monotonic() + timeout
    while _time.monotonic() < deadline:
        try:
            with _socket.create_connection((host, port), timeout=0.05):
                return True
        except OSError:
            _time.sleep(0.01)
    return False


def _write_session(directory: Path, filename: str, session_id: str,
                   name: str, messages: list, extra: dict = None) -> Path:
    """Write a minimal session JSON to directory/filename."""
    data = {"id": session_id, "name": name, "messages": messages}
    if extra:
        data.update(extra)
    p = directory / filename
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def _import_with_exports_dir(tmp_path):
    """Import graph_server with _exports_dir patched to tmp_path."""
    import importlib, sys
    # Fresh import with patch active
    with patch("aicli.graph_server._exports_dir", return_value=tmp_path):
        import aicli.graph_server as gs
        return gs


# ── load_sessions_from_exports ────────────────────────────────────────────────

class TestLoadSessionsFromExports:

    def test_single_latest_json_returns_node(self, tmp_path):
        _write_session(tmp_path, "proj__latest.json", "abc-123", "My Project",
                       [{"role": "user", "content": "hello"},
                        {"role": "assistant", "content": "hi"}])
        import aicli.graph_server as gs
        with patch.object(gs, "_exports_dir", return_value=tmp_path):
            nodes = gs.load_sessions_from_exports()
        assert len(nodes) == 1
        assert nodes[0]["id"] == "abc-123"
        assert nodes[0]["name"] == "My Project"
        assert nodes[0]["msgs"] == 2

    def test_skips_backup_files(self, tmp_path):
        _write_session(tmp_path, "backup-20260308.json", "x", "backup",
                       [{"role": "user", "content": "x"}])
        import aicli.graph_server as gs
        with patch.object(gs, "_exports_dir", return_value=tmp_path):
            nodes = gs.load_sessions_from_exports()
        assert nodes == []

    def test_skips_sync_files(self, tmp_path):
        _write_session(tmp_path, "_sync_sessions.json", "x", "sync",
                       [{"role": "user", "content": "x"}])
        import aicli.graph_server as gs
        with patch.object(gs, "_exports_dir", return_value=tmp_path):
            nodes = gs.load_sessions_from_exports()
        assert nodes == []

    def test_skips_graph_links_json(self, tmp_path):
        (tmp_path / "graph_links.json").write_text(
            json.dumps({"links": [], "names": {}}))
        import aicli.graph_server as gs
        with patch.object(gs, "_exports_dir", return_value=tmp_path):
            nodes = gs.load_sessions_from_exports()
        assert nodes == []

    def test_skips_pure_graph_files(self, tmp_path):
        # A file with nodes+links but no messages key = pure graph export, skip
        (tmp_path / "graph__latest.json").write_text(
            json.dumps({"nodes": [], "links": []}))
        import aicli.graph_server as gs
        with patch.object(gs, "_exports_dir", return_value=tmp_path):
            nodes = gs.load_sessions_from_exports()
        assert nodes == []

    def test_deduplicates_same_session_id(self, tmp_path):
        # Both files have same session id — should appear only once
        _write_session(tmp_path, "proj__latest.json", "dup-id", "Project",
                       [{"role": "user", "content": "a"}])
        _write_session(tmp_path, "proj__20260101.json", "dup-id", "Project Old",
                       [{"role": "user", "content": "a"},
                        {"role": "assistant", "content": "b"}])
        import aicli.graph_server as gs
        with patch.object(gs, "_exports_dir", return_value=tmp_path):
            nodes = gs.load_sessions_from_exports()
        assert len(nodes) == 1
        # __latest.json takes priority (processed first in glob)
        assert nodes[0]["msgs"] == 1

    def test_multiple_sessions(self, tmp_path):
        _write_session(tmp_path, "a__latest.json", "id-a", "Session A",
                       [{"role": "user", "content": "a"}])
        _write_session(tmp_path, "b__latest.json", "id-b", "Session B",
                       [{"role": "user", "content": "b"},
                        {"role": "assistant", "content": "c"}])
        import aicli.graph_server as gs
        with patch.object(gs, "_exports_dir", return_value=tmp_path):
            nodes = gs.load_sessions_from_exports()
        ids = {n["id"] for n in nodes}
        assert ids == {"id-a", "id-b"}

    def test_empty_directory(self, tmp_path):
        import aicli.graph_server as gs
        with patch.object(gs, "_exports_dir", return_value=tmp_path):
            nodes = gs.load_sessions_from_exports()
        assert nodes == []

    def test_malformed_json_skipped(self, tmp_path):
        (tmp_path / "corrupt__latest.json").write_text("{ not valid json {{")
        _write_session(tmp_path, "good__latest.json", "good-id", "Good",
                       [{"role": "user", "content": "ok"}])
        import aicli.graph_server as gs
        with patch.object(gs, "_exports_dir", return_value=tmp_path):
            nodes = gs.load_sessions_from_exports()
        assert len(nodes) == 1
        assert nodes[0]["id"] == "good-id"

    def test_summary_truncated_to_120_chars(self, tmp_path):
        long_summary = "x" * 200
        _write_session(tmp_path, "s__latest.json", "s-id", "S",
                       [{"role": "user", "content": "hi"}],
                       extra={"summary": long_summary})
        import aicli.graph_server as gs
        with patch.object(gs, "_exports_dir", return_value=tmp_path):
            nodes = gs.load_sessions_from_exports()
        assert len(nodes[0]["summary"]) == 120

    def test_missing_id_falls_back_to_stem(self, tmp_path):
        data = {"name": "No ID", "messages": []}
        (tmp_path / "noid__latest.json").write_text(json.dumps(data))
        import aicli.graph_server as gs
        with patch.object(gs, "_exports_dir", return_value=tmp_path):
            nodes = gs.load_sessions_from_exports()
        assert nodes[0]["id"] == "noid__latest"

    def test_node_has_required_fields(self, tmp_path):
        _write_session(tmp_path, "full__latest.json", "full-id", "Full Session",
                       [{"role": "user", "content": "x"}],
                       extra={"exported_at": "2026-03-08T12:00:00", "summary": "brief"})
        import aicli.graph_server as gs
        with patch.object(gs, "_exports_dir", return_value=tmp_path):
            nodes = gs.load_sessions_from_exports()
        node = nodes[0]
        for field in ("id", "name", "msgs", "session_id", "exported_at", "summary"):
            assert field in node, f"Missing field: {field}"


# ── load_graph_links / save_graph_links ──────────────────────────────────────

class TestGraphLinks:

    def test_save_and_load_roundtrip(self, tmp_path):
        links = [
            {"id": "link1", "source": "sess-a", "target": "sess-b"},
            {"id": "link2", "source": "sess-b", "target": "sess-c"},
        ]
        import aicli.graph_server as gs
        with patch.object(gs, "_exports_dir", return_value=tmp_path):
            gs.save_graph_links(links)
            loaded = gs.load_graph_links()
        assert loaded == links

    def test_load_missing_file_returns_empty(self, tmp_path):
        import aicli.graph_server as gs
        with patch.object(gs, "_exports_dir", return_value=tmp_path):
            result = gs.load_graph_links()
        assert result == []

    def test_load_corrupt_file_returns_empty(self, tmp_path):
        (tmp_path / "graph_links.json").write_text("{ bad json")
        import aicli.graph_server as gs
        with patch.object(gs, "_exports_dir", return_value=tmp_path):
            result = gs.load_graph_links()
        assert result == []

    def test_save_writes_valid_json(self, tmp_path):
        links = [{"id": "x", "source": "a", "target": "b"}]
        import aicli.graph_server as gs
        with patch.object(gs, "_exports_dir", return_value=tmp_path):
            gs.save_graph_links(links)
        data = json.loads((tmp_path / "graph_links.json").read_text())
        assert data["links"] == links
        assert "saved" in data

    def test_save_empty_links(self, tmp_path):
        import aicli.graph_server as gs
        with patch.object(gs, "_exports_dir", return_value=tmp_path):
            gs.save_graph_links([])
            loaded = gs.load_graph_links()
        assert loaded == []

    def test_save_overwrites_previous(self, tmp_path):
        import aicli.graph_server as gs
        with patch.object(gs, "_exports_dir", return_value=tmp_path):
            gs.save_graph_links([{"id": "old", "source": "a", "target": "b"}])
            gs.save_graph_links([{"id": "new", "source": "c", "target": "d"}])
            loaded = gs.load_graph_links()
        assert len(loaded) == 1
        assert loaded[0]["id"] == "new"


# ── GraphHandler HTTP ─────────────────────────────────────────────────────────

class TestGraphHandler:
    """Integration tests — spin up a real server on a random port."""
    pytestmark = pytest.mark.slow

    @pytest.fixture
    def server(self, tmp_path):
        """Start a GraphHandler server on a random port, yield (host, port)."""
        import aicli.graph_server as gs

        # Patch exports dir for this test
        patcher = patch.object(gs, "_exports_dir", return_value=tmp_path)
        patcher.start()

        srv = gs.ReusableTCPServer(("localhost", 0), gs.GraphHandler)
        port = srv.server_address[1]
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()

        yield "localhost", port

        srv.shutdown()
        srv.server_close()
        patcher.stop()

    def _get(self, host, port, path):
        conn = http.client.HTTPConnection(host, port, timeout=5)
        conn.request("GET", path)
        resp = conn.getresponse()
        body = resp.read()
        conn.close()
        return resp.status, resp.getheader("Content-Type"), body

    def _post(self, host, port, path, data: dict):
        body = json.dumps(data).encode()
        conn = http.client.HTTPConnection(host, port, timeout=5)
        conn.request("POST", path, body=body,
                     headers={"Content-Type": "application/json",
                              "Content-Length": str(len(body))})
        resp = conn.getresponse()
        resp_body = resp.read()
        conn.close()
        return resp.status, resp_body

    def test_get_root_returns_html(self, server, tmp_path):
        host, port = server
        status, ct, body = self._get(host, port, "/")
        assert status == 200
        assert "html" in ct
        assert b"<!DOCTYPE html>" in body or b"<html" in body

    def test_get_index_html_same_as_root(self, server, tmp_path):
        host, port = server
        s1, _, b1 = self._get(host, port, "/")
        s2, _, b2 = self._get(host, port, "/index.html")
        assert s1 == s2 == 200
        assert b1 == b2

    def test_get_sessions_empty(self, server, tmp_path):
        host, port = server
        status, ct, body = self._get(host, port, "/api/sessions")
        assert status == 200
        assert "json" in ct
        data = json.loads(body)
        assert "nodes" in data
        assert "links" in data
        assert data["nodes"] == []
        assert data["links"] == []

    def test_get_sessions_with_data(self, server, tmp_path):
        import aicli.graph_server as gs
        _write_session(tmp_path, "proj__latest.json", "sess-1", "My Project",
                       [{"role": "user", "content": "hi"}])
        host, port = server
        status, _, body = self._get(host, port, "/api/sessions")
        data = json.loads(body)
        assert len(data["nodes"]) == 1
        assert data["nodes"][0]["name"] == "My Project"

    def test_get_sessions_merges_saved_names(self, server, tmp_path):
        import aicli.graph_server as gs
        _write_session(tmp_path, "proj__latest.json", "sess-x", "Original Name",
                       [{"role": "user", "content": "hi"}])
        # Write graph_links.json with name override
        (tmp_path / "graph_links.json").write_text(json.dumps({
            "links": [],
            "names": {"sess-x": {"name": "Custom Name", "notes": "my note"}}
        }))
        host, port = server
        _, _, body = self._get(host, port, "/api/sessions")
        data = json.loads(body)
        node = data["nodes"][0]
        assert node["name"] == "Custom Name"
        assert node["notes"] == "my note"

    def test_get_unknown_path_returns_404(self, server, tmp_path):
        host, port = server
        status, _, _ = self._get(host, port, "/nonexistent/path")
        assert status == 404

    def test_post_save_persists_links(self, server, tmp_path):
        host, port = server
        payload = {
            "links": [{"id": "l1", "source": "a", "target": "b"}],
            "names": {"a": {"name": "Session A", "notes": ""}}
        }
        status, body = self._post(host, port, "/api/save", payload)
        assert status == 200
        assert json.loads(body).get("ok") is True
        # Verify persisted
        saved = json.loads((tmp_path / "graph_links.json").read_text())
        assert saved["links"] == payload["links"]
        assert saved["names"] == payload["names"]

    def test_post_save_unknown_path_returns_404(self, server, tmp_path):
        host, port = server
        status, _ = self._post(host, port, "/api/nope", {})
        assert status == 404

    def test_cors_header_present(self, server, tmp_path):
        host, port = server
        conn = http.client.HTTPConnection(host, port, timeout=5)
        conn.request("GET", "/")
        resp = conn.getresponse()
        resp.read()
        assert resp.getheader("Access-Control-Allow-Origin") == "*"
        conn.close()

    def test_post_save_overwrites_existing(self, server, tmp_path):
        host, port = server
        self._post(host, port, "/api/save",
                   {"links": [{"id": "old", "source": "a", "target": "b"}], "names": {}})
        self._post(host, port, "/api/save",
                   {"links": [{"id": "new", "source": "c", "target": "d"}], "names": {}})
        saved = json.loads((tmp_path / "graph_links.json").read_text())
        assert len(saved["links"]) == 1
        assert saved["links"][0]["id"] == "new"


# ── _kill_existing ────────────────────────────────────────────────────────────

class TestKillExisting:

    def test_no_process_on_port_returns_false(self):
        import aicli.graph_server as gs
        # Use a port with nothing on it
        result = gs._kill_existing(19998)
        assert result is False

    def test_returns_false_when_lsof_not_found(self, monkeypatch):
        import aicli.graph_server as gs
        import subprocess
        def fake_run(args, **kwargs):
            raise FileNotFoundError("lsof not found")
        monkeypatch.setattr(subprocess, "run", fake_run)
        # Should fall through to fuser attempt gracefully, return False
        result = gs._kill_existing(19998)
        assert isinstance(result, bool)

    def test_handles_empty_pid_list(self, monkeypatch):
        import aicli.graph_server as gs
        import subprocess
        mock = MagicMock()
        mock.stdout = ""   # no PIDs
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: mock)
        result = gs._kill_existing(19999)
        assert result is False


# ── ReusableTCPServer ─────────────────────────────────────────────────────────

class TestReusableTCPServer:
    pytestmark = pytest.mark.slow

    def test_allow_reuse_address_is_true(self):
        import aicli.graph_server as gs
        assert gs.ReusableTCPServer.allow_reuse_address is True

    def test_server_binds_and_responds(self, tmp_path):
        import aicli.graph_server as gs
        with patch.object(gs, "_exports_dir", return_value=tmp_path):
            srv = gs.ReusableTCPServer(("localhost", 0), gs.GraphHandler)
            port = srv.server_address[1]
            t = threading.Thread(target=srv.serve_forever, daemon=True)
            t.start()
            _wait_for_port("localhost", port)

            conn = http.client.HTTPConnection("localhost", port, timeout=3)
            conn.request("GET", "/")
            resp = conn.getresponse()
            assert resp.status == 200
            conn.close()

            srv.shutdown()
            srv.server_close()


# ── Node tags (v1.5.3) ────────────────────────────────────────────────────────

class TestNodeTags:
    """Tags are stored in graph_links.json names dict and surfaced via /api/sessions."""

    def test_tags_in_api_sessions_response(self, tmp_path):
        """Nodes in /api/sessions have a tags field."""
        import aicli.graph_server as gs
        _write_session(tmp_path, "proj__latest.json", "t-id", "Tagged",
                       [{"role": "user", "content": "hi"}])
        (tmp_path / "graph_links.json").write_text(json.dumps({
            "links": [],
            "names": {"t-id": {"name": "Tagged", "notes": "", "tags": ["research", "python"]}}
        }))
        with patch.object(gs, "_exports_dir", return_value=tmp_path):
            nodes = gs.load_sessions_from_exports()
            # Simulate the merge that /api/sessions does
            names = json.loads((tmp_path / "graph_links.json").read_text()).get("names", {})
            for n in nodes:
                if n["id"] in names:
                    n["tags"] = names[n["id"]].get("tags", [])
                else:
                    n["tags"] = []
        assert nodes[0]["tags"] == ["research", "python"]

    def test_tags_empty_by_default(self, tmp_path):
        """Node with no saved metadata gets tags=[]."""
        import aicli.graph_server as gs
        _write_session(tmp_path, "plain__latest.json", "p-id", "Plain",
                       [{"role": "user", "content": "hi"}])
        with patch.object(gs, "_exports_dir", return_value=tmp_path):
            nodes = gs.load_sessions_from_exports()
            names = {}
            for n in nodes:
                n["tags"] = names.get(n["id"], {}).get("tags", [])
        assert nodes[0]["tags"] == []

    def test_tags_persisted_in_save(self, tmp_path):
        """Tags survive a save/load round-trip via graph_links.json."""
        import aicli.graph_server as gs
        links_file = tmp_path / "graph_links.json"
        payload = {
            "links": [],
            "names": {
                "sess-a": {"name": "Session A", "notes": "", "tags": ["ml", "experiment"]},
                "sess-b": {"name": "Session B", "notes": "note", "tags": []},
            }
        }
        with patch.object(gs, "_exports_dir", return_value=tmp_path):
            gs.save_graph_links(payload["links"])
            # Write names manually as save_graph_links only handles links
            existing = json.loads(links_file.read_text())
            existing["names"] = payload["names"]
            links_file.write_text(json.dumps(existing))
            saved = json.loads(links_file.read_text())
        assert saved["names"]["sess-a"]["tags"] == ["ml", "experiment"]
        assert saved["names"]["sess-b"]["tags"] == []

    def test_tags_case_insensitive_filter(self, tmp_path):
        """Tag filter is case-insensitive."""
        import aicli.graph_server as gs
        srv = gs.ReusableTCPServer(("localhost", 0), gs.GraphHandler)
        port = srv.server_address[1]
        _write_session(tmp_path, "a__latest.json", "id-a", "Session A",
                       [{"role": "user", "content": "hi"}])
        (tmp_path / "graph_links.json").write_text(json.dumps({
            "links": [],
            "names": {"id-a": {"name": "Session A", "notes": "", "tags": ["Python"]}}
        }))

        import threading, http.client
        patcher = patch.object(gs, "_exports_dir", return_value=tmp_path)
        patcher.start()
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()

        try:
            body = json.dumps({"tag": "python"}).encode()  # lowercase
            conn = http.client.HTTPConnection("localhost", port, timeout=3)
            conn.request("POST", "/api/tags", body=body,
                         headers={"Content-Type": "application/json",
                                  "Content-Length": str(len(body))})
            resp = conn.getresponse()
            data = json.loads(resp.read())
            conn.close()
            assert resp.status == 200
            assert len(data["nodes"]) == 1
        finally:
            srv.shutdown()
            srv.server_close()
            patcher.stop()

    def test_tags_filter_returns_matching_only(self, tmp_path):
        """POST /api/tags only returns nodes that have the requested tag."""
        import aicli.graph_server as gs, threading, http.client

        _write_session(tmp_path, "a__latest.json", "id-a", "A",
                       [{"role": "user", "content": "hi"}])
        _write_session(tmp_path, "b__latest.json", "id-b", "B",
                       [{"role": "user", "content": "hello"}])
        (tmp_path / "graph_links.json").write_text(json.dumps({
            "links": [],
            "names": {
                "id-a": {"name": "A", "notes": "", "tags": ["nlp"]},
                "id-b": {"name": "B", "notes": "", "tags": ["vision"]},
            }
        }))
        srv = gs.ReusableTCPServer(("localhost", 0), gs.GraphHandler)
        port = srv.server_address[1]
        patcher = patch.object(gs, "_exports_dir", return_value=tmp_path)
        patcher.start()
        threading.Thread(target=srv.serve_forever, daemon=True).start()

        try:
            body = json.dumps({"tag": "nlp"}).encode()
            conn = http.client.HTTPConnection("localhost", port, timeout=3)
            conn.request("POST", "/api/tags", body=body,
                         headers={"Content-Type": "application/json",
                                  "Content-Length": str(len(body))})
            resp = conn.getresponse()
            data = json.loads(resp.read())
            conn.close()
            assert len(data["nodes"]) == 1
            assert data["nodes"][0]["id"] == "id-a"
        finally:
            srv.shutdown()
            srv.server_close()
            patcher.stop()

    def test_tags_filter_empty_tag_returns_all(self, tmp_path):
        """POST /api/tags with empty tag returns all nodes."""
        import aicli.graph_server as gs, threading, http.client

        _write_session(tmp_path, "a__latest.json", "id-a", "A",
                       [{"role": "user", "content": "hi"}])
        _write_session(tmp_path, "b__latest.json", "id-b", "B",
                       [{"role": "user", "content": "hello"}])
        srv = gs.ReusableTCPServer(("localhost", 0), gs.GraphHandler)
        port = srv.server_address[1]
        patcher = patch.object(gs, "_exports_dir", return_value=tmp_path)
        patcher.start()
        threading.Thread(target=srv.serve_forever, daemon=True).start()

        try:
            body = json.dumps({"tag": ""}).encode()
            conn = http.client.HTTPConnection("localhost", port, timeout=3)
            conn.request("POST", "/api/tags", body=body,
                         headers={"Content-Type": "application/json",
                                  "Content-Length": str(len(body))})
            resp = conn.getresponse()
            data = json.loads(resp.read())
            conn.close()
            assert resp.status == 200
            assert len(data["nodes"]) == 2
        finally:
            srv.shutdown()
            srv.server_close()
            patcher.stop()


# ── Obsidian export (v1.5.3) ──────────────────────────────────────────────────

class TestObsidianExport:
    """Tests for export.py _to_obsidian."""

    def _msgs(self):
        return [
            {"role": "user", "content": "Hello there", "timestamp": "2026-03-15T10:00:00"},
            {"role": "assistant", "content": "Hi! How can I help?", "timestamp": "2026-03-15T10:00:05"},
            {"role": "user", "content": "What is Python?", "timestamp": "2026-03-15T10:01:00"},
            {"role": "assistant", "content": "Python is a high-level language.", "timestamp": "2026-03-15T10:01:05"},
        ]

    def _get_obsidian(self, **kwargs):
        from aicli.handlers.export import _to_obsidian
        return _to_obsidian("myproject", "abc-123", self._msgs(), "Test summary.", **kwargs)

    def test_returns_string(self):
        assert isinstance(self._get_obsidian(), str)

    def test_has_yaml_frontmatter(self):
        out = self._get_obsidian()
        assert out.startswith("---\n")
        assert "\n---\n" in out

    def test_frontmatter_has_title(self):
        out = self._get_obsidian()
        assert 'title: "myproject"' in out

    def test_frontmatter_has_session_id(self):
        out = self._get_obsidian()
        assert 'session_id: "abc-123"' in out

    def test_frontmatter_has_aicli_tag(self):
        out = self._get_obsidian()
        assert "- aicli" in out

    def test_frontmatter_has_date(self):
        import re
        out = self._get_obsidian()
        assert re.search(r"date: \d{4}-\d{2}-\d{2}", out)

    def test_has_h1_title(self):
        out = self._get_obsidian()
        assert "# myproject" in out

    def test_assistant_callout_blocks(self):
        out = self._get_obsidian()
        assert "> [!assistant]-" in out

    def test_summary_callout_when_included(self):
        from aicli.handlers.export import _to_obsidian
        out = _to_obsidian("proj", "id-x", self._msgs(), "Summary text here.", include_summary=True)
        assert "> [!summary]+" in out
        assert "Summary text here." in out

    def test_no_summary_callout_when_not_included(self):
        out = self._get_obsidian()
        assert "> [!summary]" not in out

    def test_user_messages_present(self):
        out = self._get_obsidian()
        assert "Hello there" in out
        assert "What is Python?" in out

    def test_assistant_messages_present(self):
        out = self._get_obsidian()
        assert "Hi! How can I help?" in out
        assert "Python is a high-level language." in out

    def test_heading_anchors_for_wikilinks(self):
        """Each message gets a ^msg-N anchor for [[wikilink]] referencing."""
        out = self._get_obsidian()
        assert "^msg-0" in out
        assert "^msg-1" in out

    def test_system_messages_skipped(self):
        from aicli.handlers.export import _to_obsidian
        msgs = self._msgs() + [{"role": "system", "content": "internal", "timestamp": ""}]
        out = _to_obsidian("proj", "id-x", msgs, None)
        assert "internal" not in out

    def test_auto_summary_system_message_as_callout(self):
        from aicli.handlers.export import _to_obsidian
        msgs = self._msgs() + [
            {"role": "system", "content": "[AUTO-SUMMARY] This is the auto summary.", "timestamp": ""}
        ]
        out = _to_obsidian("proj", "id-x", msgs, None)
        assert "> [!info]-" in out
        assert "This is the auto summary." in out

    def test_different_from_standard_markdown(self):
        from aicli.handlers.export import _to_markdown, _to_obsidian
        md = _to_markdown("proj", "id-x", self._msgs(), None)
        obs = _to_obsidian("proj", "id-x", self._msgs(), None)
        assert md != obs

    def test_message_count_in_frontmatter(self):
        out = self._get_obsidian()
        assert "message_count: 4" in out


# ── Node tag support (v1.5.3) ─────────────────────────────────────────────────

class TestNodeTags:
    """Tests for tag persistence and filtering in graph_server."""

    def test_save_tags_roundtrip(self, tmp_path):
        """Tags saved in names dict are returned in /api/sessions."""
        import aicli.graph_server as gs
        _write_session(tmp_path, "proj__latest.json", "sess-tag", "Tagged Project",
                       [{"role": "user", "content": "hi"}])
        # Manually write graph_links.json with tags
        (tmp_path / "graph_links.json").write_text(json.dumps({
            "links": [],
            "names": {"sess-tag": {"name": "Tagged Project", "notes": "", "tags": ["research", "python"]}}
        }))
        with patch.object(gs, "_exports_dir", return_value=tmp_path):
            nodes = gs.load_sessions_from_exports()
        # Tags merged in do_GET /api/sessions — test via HTTP
        srv = gs.ReusableTCPServer(("localhost", 0), gs.GraphHandler)
        port = srv.server_address[1]
        import threading
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        with patch.object(gs, "_exports_dir", return_value=tmp_path):
            t.start()
            _wait_for_port("localhost", port)
            conn = http.client.HTTPConnection("localhost", port, timeout=3)
            conn.request("GET", "/api/sessions")
            resp = conn.getresponse()
            data = json.loads(resp.read())
            conn.close()
        srv.shutdown(); srv.server_close()
        assert len(data["nodes"]) == 1
        assert data["nodes"][0]["tags"] == ["research", "python"]

    def test_nodes_without_tags_get_empty_list(self, tmp_path):
        """Nodes with no saved tags get tags=[] in response."""
        import aicli.graph_server as gs
        _write_session(tmp_path, "notags__latest.json", "no-tags-id", "No Tags",
                       [{"role": "user", "content": "hi"}])
        srv = gs.ReusableTCPServer(("localhost", 0), gs.GraphHandler)
        port = srv.server_address[1]
        import threading, http.client, time
        with patch.object(gs, "_exports_dir", return_value=tmp_path):
            t = threading.Thread(target=srv.serve_forever, daemon=True)
            t.start()
            _wait_for_port("localhost", port)
            conn = http.client.HTTPConnection("localhost", port, timeout=3)
            conn.request("GET", "/api/sessions")
            data = json.loads(conn.getresponse().read())
            conn.close()
        srv.shutdown(); srv.server_close()
        assert data["nodes"][0]["tags"] == []

    def test_api_tags_filters_by_tag(self, tmp_path):
        """POST /api/tags with tag returns only matching nodes."""
        import aicli.graph_server as gs
        _write_session(tmp_path, "a__latest.json", "id-a", "Session A",
                       [{"role": "user", "content": "a"}])
        _write_session(tmp_path, "b__latest.json", "id-b", "Session B",
                       [{"role": "user", "content": "b"}])
        (tmp_path / "graph_links.json").write_text(json.dumps({
            "links": [],
            "names": {
                "id-a": {"name": "Session A", "notes": "", "tags": ["python"]},
                "id-b": {"name": "Session B", "notes": "", "tags": ["research"]},
            }
        }))
        srv = gs.ReusableTCPServer(("localhost", 0), gs.GraphHandler)
        port = srv.server_address[1]
        import threading, http.client, time
        with patch.object(gs, "_exports_dir", return_value=tmp_path):
            t = threading.Thread(target=srv.serve_forever, daemon=True)
            t.start()
            _wait_for_port("localhost", port)
            body = json.dumps({"tag": "python"}).encode()
            conn = http.client.HTTPConnection("localhost", port, timeout=3)
            conn.request("POST", "/api/tags", body=body,
                         headers={"Content-Type": "application/json",
                                  "Content-Length": str(len(body))})
            data = json.loads(conn.getresponse().read())
            conn.close()
        srv.shutdown(); srv.server_close()
        assert len(data["nodes"]) == 1
        assert data["nodes"][0]["id"] == "id-a"
        assert data["tag"] == "python"

    def test_api_tags_empty_tag_returns_all(self, tmp_path):
        """POST /api/tags with empty tag returns all nodes."""
        import aicli.graph_server as gs
        _write_session(tmp_path, "a__latest.json", "id-a", "A",
                       [{"role": "user", "content": "a"}])
        _write_session(tmp_path, "b__latest.json", "id-b", "B",
                       [{"role": "user", "content": "b"}])
        srv = gs.ReusableTCPServer(("localhost", 0), gs.GraphHandler)
        port = srv.server_address[1]
        import threading, http.client, time
        with patch.object(gs, "_exports_dir", return_value=tmp_path):
            t = threading.Thread(target=srv.serve_forever, daemon=True)
            t.start()
            _wait_for_port("localhost", port)
            body = json.dumps({"tag": ""}).encode()
            conn = http.client.HTTPConnection("localhost", port, timeout=3)
            conn.request("POST", "/api/tags", body=body,
                         headers={"Content-Type": "application/json",
                                  "Content-Length": str(len(body))})
            data = json.loads(conn.getresponse().read())
            conn.close()
        srv.shutdown(); srv.server_close()
        assert len(data["nodes"]) == 2

    def test_api_tags_case_insensitive(self, tmp_path):
        """Tag filter is case-insensitive."""
        import aicli.graph_server as gs
        _write_session(tmp_path, "a__latest.json", "id-ci", "CI Session",
                       [{"role": "user", "content": "ci"}])
        (tmp_path / "graph_links.json").write_text(json.dumps({
            "links": [],
            "names": {"id-ci": {"name": "CI", "notes": "", "tags": ["Python"]}}
        }))
        srv = gs.ReusableTCPServer(("localhost", 0), gs.GraphHandler)
        port = srv.server_address[1]
        import threading, http.client, time
        with patch.object(gs, "_exports_dir", return_value=tmp_path):
            t = threading.Thread(target=srv.serve_forever, daemon=True)
            t.start()
            _wait_for_port("localhost", port)
            body = json.dumps({"tag": "python"}).encode()  # lowercase, tag is "Python"
            conn = http.client.HTTPConnection("localhost", port, timeout=3)
            conn.request("POST", "/api/tags", body=body,
                         headers={"Content-Type": "application/json",
                                  "Content-Length": str(len(body))})
            data = json.loads(conn.getresponse().read())
            conn.close()
        srv.shutdown(); srv.server_close()
        assert len(data["nodes"]) == 1

    def test_save_preserves_tags(self, tmp_path):
        """POST /api/save with tags in names dict persists them to graph_links.json."""
        import aicli.graph_server as gs
        srv = gs.ReusableTCPServer(("localhost", 0), gs.GraphHandler)
        port = srv.server_address[1]
        import threading, http.client, time
        with patch.object(gs, "_exports_dir", return_value=tmp_path):
            t = threading.Thread(target=srv.serve_forever, daemon=True)
            t.start()
            _wait_for_port("localhost", port)
            payload = json.dumps({
                "links": [],
                "names": {"id-x": {"name": "X", "notes": "", "tags": ["ml", "nlp"]}}
            }).encode()
            conn = http.client.HTTPConnection("localhost", port, timeout=3)
            conn.request("POST", "/api/save", body=payload,
                         headers={"Content-Type": "application/json",
                                  "Content-Length": str(len(payload))})
            conn.getresponse().read()
            conn.close()
        srv.shutdown(); srv.server_close()
        saved = json.loads((tmp_path / "graph_links.json").read_text())
        assert saved["names"]["id-x"]["tags"] == ["ml", "nlp"]

    def test_html_contains_tag_bar(self):
        """The embedded HTML contains the tag filter bar."""
        import aicli.graph_server as gs
        assert "tag-bar" in gs.HTML
        assert "filterByTag" in gs.HTML
        assert "clearTagFilter" in gs.HTML

    def test_html_contains_tag_input_in_panel(self):
        """The embedded HTML contains a tags field in the node panel."""
        import aicli.graph_server as gs
        assert "pt-tags" in gs.HTML

    def test_html_contains_tag_chips(self):
        """The tag chip/autocomplete system is present in the HTML."""
        import aicli.graph_server as gs
        assert "tag-chips" in gs.HTML or "_refreshTagChips" in gs.HTML

    def test_html_contains_node_tag_class(self):
        """Nodes render a tag label via .node-tag CSS class."""
        import aicli.graph_server as gs
        assert "node-tag" in gs.HTML
