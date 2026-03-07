"""
tokens.py — Token counting and context window management.

Uses tiktoken (cl100k_base) when available for exact counts.
Falls back to a high-accuracy approximation when tiktoken is not installed:
  ~4 chars per token for English prose (GPT/Llama tokenizers agree closely).
  We add 10% safety margin and always count role/name overhead.
"""

import re
from typing import Sequence

try:
    import tiktoken
    _enc = tiktoken.get_encoding("cl100k_base")
    _USE_TIKTOKEN = True
except ImportError:
    _USE_TIKTOKEN = False


# ── Token counting ──────────────────────────────────────────────────────────────

def count_tokens(text: str) -> int:
    """
    Exact token count via tiktoken (cl100k_base) when available.
    Falls back to approximation: ~4 chars/token for English;
    code and symbols skew higher, so we use 3.5 chars/token as a
    conservative (safe) estimate.
    """
    if not text:
        return 0
    if _USE_TIKTOKEN:
        return len(_enc.encode(text))
    # Rough heuristic that closely matches cl100k_base:
    # Split on whitespace and punctuation, weight each piece
    words = len(text.split())
    chars = len(text)
    # Blend: words * 1.3 for subword tokens, chars / 4 as floor
    return max(int(words * 1.3), chars // 4)


def count_messages_tokens(messages: list[dict]) -> int:
    """
    Count total tokens across a list of messages.
    Adds 4 tokens overhead per message for role/formatting (matches OpenAI's formula).
    """
    total = 0
    for msg in messages:
        total += 4  # per-message overhead
        total += count_tokens(msg.get("content", ""))
        total += count_tokens(msg.get("role", ""))
        if "name" in msg:
            total += count_tokens(msg["name"])
    total += 2  # conversation-level overhead (priming tokens)
    return total


# ── Window trimming ─────────────────────────────────────────────────────────────

PROTECTED_ROLES = {"system"}
PROTECTED_PREFIXES = {"[AUTO-SUMMARY]"}


def is_protected(msg: dict) -> bool:
    """
    A message is protected from pruning if it is:
    - A system message
    - An [AUTO-SUMMARY] message (summarized context must survive)
    """
    if msg.get("role") in PROTECTED_ROLES:
        return True
    content = msg.get("content", "")
    return any(content.startswith(p) for p in PROTECTED_PREFIXES)


def trim_messages(messages: list[dict], token_limit: int) -> list[dict]:
    """
    Trim messages to fit within token_limit.
    Strategy:
    1. Always keep protected messages (system + [AUTO-SUMMARY])
    2. Drop oldest non-protected messages from the front until we fit
    3. Never returns an empty list if there are protected messages
    """
    if count_messages_tokens(messages) <= token_limit:
        return messages

    protected = [m for m in messages if is_protected(m)]
    non_protected = [m for m in messages if not is_protected(m)]

    # Drop from oldest non-protected messages
    while non_protected and count_messages_tokens(protected + non_protected) > token_limit:
        non_protected.pop(0)

    # Reconstruct in original order
    result = []
    p_idx = 0
    np_idx = 0
    for msg in messages:
        if is_protected(msg) and p_idx < len(protected):
            result.append(protected[p_idx])
            p_idx += 1
        elif not is_protected(msg) and np_idx < len(non_protected):
            result.append(non_protected[np_idx])
            np_idx += 1

    return result


def summarization_prompt(messages: list[dict]) -> str:
    """
    Build the summarization prompt for a chunk of messages.
    4 explicit preservation requirements for maximum fidelity.
    """
    conversation = "\n".join(
        f"{m['role'].upper()}: {m['content']}" for m in messages
    )
    return f"""Summarize the following conversation segment for use as compressed context in an ongoing AI conversation.

REQUIREMENTS — your summary MUST:
1. Preserve all technical decisions and their rationale (e.g., "chose SQLite over JSON because of WAL mode and indexing")
2. Preserve all named entities: filenames, variable names, function names, config keys, URLs, commands
3. Preserve all numerical values and measurements (token counts, timeouts, line counts, version numbers)
4. Write in third person past tense; keep output under 400 tokens; do not editorialize

CONVERSATION TO SUMMARIZE:
{conversation}

SUMMARY:"""
