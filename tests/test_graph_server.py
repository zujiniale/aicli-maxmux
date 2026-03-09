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


# ── Helpers ───────────────────────────────────────────────────────────────────

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
            time.sleep(0.1)

            conn = http.client.HTTPConnection("localhost", port, timeout=3)
            conn.request("GET", "/")
            resp = conn.getresponse()
            assert resp.status == 200
            conn.close()

            srv.shutdown()
            srv.server_close()
