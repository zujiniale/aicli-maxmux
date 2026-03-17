# aicli-maxmux Testing Guidelines
## Canonical Patterns — Established Across Sessions S1–S15

This document records the 5 canonical testing patterns that have caused failures
when violated and should be followed for all new tests. Each pattern is backed by
a real bug that was found and fixed in production test runs.

---

## Pattern 1 — Never Mock Generator Consumers

**Rule:** Mock the *producer* (`pipeline.stream`), not the *consumer*
(`stream_to_terminal`). Mocking the consumer prevents iteration — the mock
returns a non-iterable and captured values stay empty.

**Bad:**
```python
with patch("aicli.printer.stream_to_terminal") as mock_stream:
    result = runner.invoke(cli, ["ask", "hello"])
    # mock_stream called but nothing was captured — always empty
```

**Good:**
```python
async def _fake_stream(*a, **kw):
    yield "Hello, world!"

mock_pipeline.stream = _fake_stream
```

**Real bug:** `TestWatchMode` — patching the terminal consumer meant the watch
loop never saw any output, silently passing when it should have failed.

---

## Pattern 2 — Module-Level Imports for Patchability (Lazy Import Shadow Bug)

**Rule:** Any name imported *inside* a function body is not patchable via
`unittest.mock.patch` using the calling module as the target. Always use
`try/except ImportError` at module level for any name that tests need to mock.

**Bad:**
```python
# In production code (default.py):
async def _watch_evaluate(...):
    from ..tools.executor import run_do_command  # lazy — inside function
    await run_do_command(...)

# In test:
with patch("aicli.handlers.default.run_do_command", mock):  # AttributeError!
```

**Good (patch at source module):**
```python
with patch("aicli.tools.executor.run_do_command", mock):  # ✓ works
```

**Rule of thumb:** Always patch at the module where the name is *defined*, not
where it is used when the import is lazy.

**Real bug:** `TestWatchDoIntegration` — `AttributeError: module
'aicli.handlers.default' does not have the attribute 'run_do_command'` because
the import lives inside `_watch_evaluate`'s body.

---

## Pattern 3 — Registry Reference Capture

**Rule:** `TOOL_REGISTRY` captures `fn` at decoration time. Patching the
decorated function's module attribute after decoration does not affect the
registry entry. Patch via the registry dict directly, with `try/finally` restore.

**Bad:**
```python
with patch("aicli.tools.os_functions.run_shell_command", mock):
    # TOOL_REGISTRY["run_shell_command"]["fn"] still points to the original
```

**Good:**
```python
from aicli.tools.registry import TOOL_REGISTRY
original = TOOL_REGISTRY["run_shell_command"]["fn"]
TOOL_REGISTRY["run_shell_command"]["fn"] = mock
try:
    ...
finally:
    TOOL_REGISTRY["run_shell_command"]["fn"] = original
```

For plugin registration tests, save/restore the entire registry:
```python
original = dict(TOOL_REGISTRY)
try:
    _load_plugin_file(path)
    assert "my_tool" in TOOL_REGISTRY
finally:
    TOOL_REGISTRY.clear()
    TOOL_REGISTRY.update(original)
```

---

## Pattern 4 — CliRunner `sys.argv` Incompatibility + `_FallbackGroup`

**Rule:** `sys.argv` under `CliRunner` contains pytest's own args, not the
invoked args. Do not read `sys.argv` in CLI code under test.

After S14: `_FallbackGroup` in `app.py` handles direct invocation correctly.
Use `ctx.args` directly — never `ctx.protected_args + ctx.args` (deprecated in
Click 9.0, raises `DeprecationWarning`).

**What `_FallbackGroup` does:** If the first positional token is not a known
subcommand name, all args are stored in `ctx.args` and subcommand resolution is
skipped — `invoke_without_command=True` then fires `cli()`. Known subcommands
still route normally.

**Tests must use CliRunner kwargs:**
```python
runner = CliRunner(mix_stderr=False)
result = runner.invoke(cli, ["explain", "async", "await"])
assert result.exit_code == 0   # not 2 ("No such command")
```

---

## Pattern 5 — `asyncio.run` Patch Anti-Pattern

**Rule:** Never `patch("module.asyncio.run")` — the coroutine is created but
handed to a `MagicMock` which never awaits or closes it. Python's GC then emits
`RuntimeWarning: coroutine '...' was never awaited`.

**Bad:**
```python
with patch("aicli.app.asyncio.run") as mock_run:
    runner.invoke(cli, ["do", "open hacker news"])
    # asyncio.run received a live coroutine — GC warning at teardown
```

**Good:**
```python
with patch("aicli.tools.executor.run_do_command", new=AsyncMock(return_value=None)):
    runner.invoke(cli, ["do", "open hacker news"])
    # no coroutine created — AsyncMock replaces the function before it's called
```

**Also applies to `_cmd_chain`:**
```python
with patch("aicli.app._cmd_chain", new=AsyncMock(return_value=None)):
    runner.invoke(cli, ["cmd", "--chain", "init project"])
```

---

## Pattern 6 — `asyncio.run()` vs `get_event_loop()` in Tests (Python 3.12)

**Rule:** Python 3.12 removed the implicit creation of an event loop by
`get_event_loop()`. Calling `asyncio.get_event_loop().run_until_complete(coro)`
outside an async context raises `RuntimeError: There is no current event loop`.

**Bad:**
```python
count = asyncio.get_event_loop().run_until_complete(_run())
```

**Good:**
```python
count = asyncio.run(_run())
```

`asyncio.run()` creates a fresh event loop, runs the coroutine, and tears down
cleanly. This is the correct pattern for all Python 3.10+ test code.

---

## Quick Reference

| Pattern | Key rule | Common mistake |
|---|---|---|
| 1 | Mock producer, not consumer | `patch("printer.stream_to_terminal")` |
| 2 | Patch at source module for lazy imports | `patch("default.run_do_command")` |
| 3 | Patch `TOOL_REGISTRY["name"]["fn"]` directly | `patch("os_functions.run_shell_command")` |
| 4 | Use `_FallbackGroup` + `ctx.args`; no `sys.argv` | `ctx.protected_args + ctx.args` |
| 5 | Patch the coroutine function with `AsyncMock` | `patch("module.asyncio.run")` |
| 6 | Use `asyncio.run(coro)` in tests | `get_event_loop().run_until_complete(coro)` |

---

*aicli-maxmux v1.5.7 · Patterns established S1–S15 · 2026-03-16*
