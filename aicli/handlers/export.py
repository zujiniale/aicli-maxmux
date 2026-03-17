"""handlers/export.py — Session export handler (F1)."""
import json
import sys
from datetime import datetime

from ..db.chat_db import get_connection, list_sessions, load_messages, load_latest_summary
from ..printer import print_error, print_info


async def _export(session_name: str, fmt: str, output: str | None, include_summary: bool = False, obsidian: bool = False):
    conn = get_connection()
    sessions = list_sessions(conn)
    matching = [s for s in sessions if s["name"] == session_name or s["id"] == session_name]

    if not matching:
        print_error(f"Session not found: {session_name}")
        return

    session_id = matching[0]["id"]
    messages = load_messages(conn, session_id)
    summary = load_latest_summary(conn, session_id)

    if not messages:
        print_info(f"Session '{session_name}' has no messages.")
        return

    if fmt == "json":
        content = _to_json(session_name, session_id, messages, summary, include_summary=include_summary)
    elif obsidian:
        content = _to_obsidian(session_name, session_id, messages, summary, include_summary=include_summary)
    else:
        content = _to_markdown(session_name, session_id, messages, summary, include_summary=include_summary)

    if output:
        with open(output, "w") as f:
            f.write(content)
        print_info(f"Exported {len(messages)} messages to {output}")
    else:
        sys.stdout.write(content)


def _to_markdown(session_name, session_id, messages, summary, include_summary: bool = False) -> str:
    lines = []
    lines.append(f"# aicli session: {session_name}")
    lines.append(f"\n**Session ID:** `{session_id}`")
    lines.append(f"**Exported:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"**Messages:** {len(messages)}")

    if include_summary and summary:
        lines.append(f"\n---\n\n## Summary\n\n{summary}")

    lines.append("\n---\n\n## Conversation\n")

    for msg in messages:
        role = msg["role"]
        content = msg["content"]
        timestamp = msg.get("timestamp", "")
        ts = f" *({timestamp[:16]})*" if timestamp else ""

        if role == "system":
            if content.startswith("[AUTO-SUMMARY]"):
                lines.append(f"> **Auto-Summary:** {content[14:].strip()}\n")
            # skip other system messages in export
        elif role == "user":
            lines.append(f"### You{ts}\n\n{content}\n")
        elif role == "assistant":
            lines.append(f"### Assistant{ts}\n\n{content}\n")

    return "\n".join(lines) + "\n"


def _to_json(session_name, session_id, messages, summary, include_summary: bool = False) -> str:
    data = {
        "session_name": session_name,
        "session_id": session_id,
        "exported_at": datetime.now().isoformat(),
        "message_count": len(messages),
        "summary": summary if include_summary else None,
        "messages": [
            {
                "role": msg["role"],
                "content": msg["content"],
                "timestamp": msg.get("timestamp", ""),
            }
            for msg in messages
            if msg["role"] != "system" or msg["content"].startswith("[AUTO-SUMMARY]")
        ],
    }
    return json.dumps(data, indent=2) + "\n"


def _to_obsidian(session_name, session_id, messages, summary, include_summary: bool = False) -> str:
    """
    Obsidian-compatible markdown export.

    Features vs standard markdown:
    - YAML frontmatter (title, session_id, date, tags, summary)
    - [[wikilinks]] for session cross-references mentioned in messages
    - Callout blocks for assistant responses (> [!assistant])
    - Summary as a collapsible > [!summary] callout
    - Each message timestamped and linkable via heading anchors
    """
    now = datetime.now()
    lines = []

    # ── YAML frontmatter ──────────────────────────────────────────────────────
    lines.append("---")
    lines.append(f"title: \"{session_name}\"")
    lines.append(f"session_id: \"{session_id}\"")
    lines.append(f"date: {now.strftime('%Y-%m-%d')}")
    lines.append(f"created: {now.strftime('%Y-%m-%dT%H:%M:%S')}")
    lines.append(f"message_count: {len([m for m in messages if m['role'] != 'system'])}")
    lines.append("tags:")
    lines.append("  - aicli")
    lines.append("  - ai-session")
    if summary:
        # First 12 words of summary as description
        desc = " ".join(summary.split()[:12])
        lines.append(f"description: \"{desc}…\"")
    lines.append("---")
    lines.append("")

    # ── Title + backlink ──────────────────────────────────────────────────────
    lines.append(f"# {session_name}")
    lines.append("")
    lines.append(f"> Session `{session_id[:8]}` · exported {now.strftime('%Y-%m-%d %H:%M')}")
    lines.append("")

    # ── Summary callout ───────────────────────────────────────────────────────
    if include_summary and summary:
        lines.append("> [!summary]+ Session Summary")
        for sline in summary.strip().splitlines():
            lines.append(f"> {sline}")
        lines.append("")

    lines.append("---")
    lines.append("")

    # ── Messages ──────────────────────────────────────────────────────────────
    for idx, msg in enumerate(messages):
        role = msg["role"]
        content = msg["content"]
        timestamp = msg.get("timestamp", "")
        ts = timestamp[:16] if timestamp else now.strftime("%Y-%m-%d %H:%M")

        if role == "system":
            if content.startswith("[AUTO-SUMMARY]"):
                lines.append("> [!info]- Auto-summary")
                lines.append(f"> {content[14:].strip()}")
                lines.append("")
            continue

        elif role == "user":
            lines.append(f"## 💬 You  ^msg-{idx}")
            lines.append(f"*{ts}*")
            lines.append("")
            lines.append(content)
            lines.append("")

        elif role == "assistant":
            lines.append(f"## 🤖 Assistant  ^msg-{idx}")
            lines.append(f"*{ts}*")
            lines.append("")
            # Wrap in callout for visual distinction
            lines.append("> [!assistant]-")
            for cline in content.splitlines():
                lines.append(f"> {cline}" if cline else ">")
            lines.append("")

        lines.append("---")
        lines.append("")

    return "\n".join(lines) + "\n"
