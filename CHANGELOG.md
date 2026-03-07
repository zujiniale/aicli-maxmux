# Changelog

All notable changes to `aicli-maxmux` are documented here.

---

## [1.1.0] — 2026-03-07

### Added

- **F2: Multimodal vision support** (`--image` / `-i` flag on `aicli ask`)
  - Accepts PNG, JPEG, GIF, WebP — up to 20MB per image
  - Multiple images supported: `aicli ask -i a.png -i b.png "compare these"`
  - Automatically routes to vision-capable providers (OpenRouter, Gemini)
  - Groq and Mistral transparently skipped for image requests
  - New module: `aicli/image_utils.py` — `load_image_b64`, `build_multimodal_content`, `is_multimodal`

- **Adaptive failover cooldowns** (`COOLDOWN_BY_STATUS` in `pipeline.py`)
  - HTTP 429 (rate limit): 300s cooldown (was flat 60s)
  - HTTP 401/403 (bad key / forbidden): 3600s cooldown
  - HTTP 500 (server error): 15s cooldown
  - HTTP 502/503 (gateway / unavailable): 10s cooldown

- **ChromaDB cold-layer RAG** (`aicli/context/`)
  - Auto-indexes every message turn via `_index_message_cold()`
  - Semantic retrieval via `--context` flag on `ask` and `chat`
  - Backfill on session resume
  - Graceful degradation if `chromadb` not installed (`_rag_enabled=False`)

- **Agent mode** (`aicli agent`) — F3
  - Multi-step plan/execute/feedback loop
  - Structured JSON observation protocol (replaces fragile string-match)
  - Fallback parser for non-compliant model responses
  - `--dry-run` flag to preview plan without executing
  - `--yes` flag to auto-confirm all steps

- **Session export** (`aicli export`) — F1
  - Markdown and JSON output formats
  - Pipe-friendly: `aicli export mysession > out.md`

- **env var reference** in `aicli config show`
  - Lists all required env vars with provider descriptions

### Fixed

- **Bug #1/#3**: Groq/OpenRouter/Gemini/Mistral 403 — `User-Agent` changed to `curl/8.5.0`
- **Bug #2**: 83 deprecation warnings from `utcnow()` — replaced with `now(timezone.utc)`
- **Bug #4**: OpenRouter model instability — fixed to `openrouter/auto`
- **Bug #5**: Deceptive "Ollama not running" error — `PROVIDER_MODELS` moved to `pipeline.py`
- **Bug #6**: REPL lost history between turns — `ContextManager` now persisted per session
- **Bug #7**: `providers_map` NameError in `app.py` — missing import added
- **Bug #8**: `_provider_test` used stale `PROVIDER_MODELS` — updated to use `pipeline.py`
- **Bug #9**: `get_api_key()` prompt edge case in `config.py`
- **Bug #10**: `session_name` stored as ID instead of slug in `chat_db.py`
- **chat_db.py**: `save_message` now accepts `str | list` — multimodal content serialized
  via `_pack_content` / `_unpack_content` (backward compatible with all existing rows)

### Changed

- `pipeline.py`: `stream()` and `complete()` accept `requires_vision: bool = False`
- `base.py`: `BaseProvider` ABC updated with `requires_vision` param
- `chat_db.py`: `content` column now stores JSON for multimodal messages
- `map_structure.sh`: dynamic line counts via `cloc` (was hardcoded)
- `stats_final.sh`: `--not-match-f='\.txt$'` exclusion prevents `PROJECT_MAP.txt` inflation
- Version string in `app.py` updated to `1.1.0`

### Tests

- 41 tests total (was 24 at v1.0.0)
- Added `TestImageUtils` — 6 tests covering `image_utils.py` and `chat_db` pack/unpack
- Added `TestAdaptiveCooldowns` — 5 tests verifying `COOLDOWN_BY_STATUS` values
- Added `TestChromaDB` — 6 tests covering cold-layer indexing, retrieval, idempotency

---

## [1.0.0] — 2026-03-06

### Added

- Initial PyPI release
- 5-provider failover pipeline: Groq → OpenRouter → Gemini → Mistral → Ollama
- CMA 3-layer memory: Hot (in-memory) / Warm (SQLite + Fernet) / Cold (ChromaDB)
- Fernet encryption with machine-fingerprint key derivation
- `aicli ask` — single-shot prompt with `--shell`, `--code`, `--describe` modes
- `aicli chat` — persistent named sessions
- `aicli repl` — interactive REPL loop
- `aicli config` — API key management (encrypted on disk)
- `aicli provider status` — live provider availability
- `aicli session` — list, show, delete sessions
- Shell tool: generate + confirm + execute with 12 HIGH_RISK_PATTERNS guard
- Token counting via tiktoken (`cl100k_base`) with char-blend heuristic fallback
- Auto-summarization at 80% token threshold (fire-and-forget async)
- `[AUTO-SUMMARY]` blocks protected from `trim_messages()` pruning
- `expand.sh` / `retract.sh` — venv lifecycle management
- `map_structure.sh` — dynamic `PROJECT_MAP.txt` generation
- `stats_final.sh` — accurate project statistics

---

*Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).*
*Versioning follows [Semantic Versioning](https://semver.org/).*
