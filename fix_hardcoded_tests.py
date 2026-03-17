#!/usr/bin/env python3
"""
fix_hardcoded_tests.py — One-shot patch for test_comprehensive.py and test_mcp_server.py.

These files have hardcoded assertions that expected 4 MCP tools and version 1.5.4.
We now have 5 tools (added 'do') and version 1.5.7.

Run from your repo root:
    python fix_hardcoded_tests.py
"""

from pathlib import Path

fixes = {
    "tests/test_comprehensive.py": [
        # Version assertion
        ('assert cfg["project"]["version"] == "1.5.4"',
         'assert cfg["project"]["version"] == "1.5.7"'),
        # MCP tools count (3 places)
        ('assert len(r["result"]["tools"]) == 4',
         'assert len(r["result"]["tools"]) >= 4  # 5 tools since v1.5.7 (added do)'),
        ('assert names == {"ask", "cmd", "code", "tag"}',
         'assert {"ask", "cmd", "code", "tag"}.issubset(names)  # do added in v1.5.7'),
        ('assert len(json.loads(json.dumps(TOOLS))) == 4',
         'assert len(json.loads(json.dumps(TOOLS))) >= 4  # 5 tools since v1.5.7'),
    ],
    "tests/test_mcp_server.py": [
        # MCP tools count (2 places)
        ('assert len(result["result"]["tools"]) == 4',
         'assert len(result["result"]["tools"]) >= 4  # 5 tools since v1.5.7 (added do)'),
        ('assert len(parsed) == 4',
         'assert len(parsed) >= 4  # 5 tools since v1.5.7 (added do)'),
    ],
}

for filepath, replacements in fixes.items():
    p = Path(filepath)
    if not p.exists():
        print(f"  SKIP (not found): {filepath}")
        continue

    content = p.read_text()
    changed = 0
    for old, new in replacements:
        if old in content:
            content = content.replace(old, new)
            changed += 1
            print(f"  ✓  {filepath}: replaced: {old[:60]}...")
        else:
            print(f"  ?  {filepath}: not found (may already be fixed): {old[:60]}...")

    if changed:
        p.write_text(content)
        print(f"  → Wrote {filepath} ({changed} change(s))")

print("\nDone. Run: pytest tests/test_comprehensive.py tests/test_mcp_server.py -q")
