"""handlers/export.py — Session export handler (F1)."""
import json
import sys
from datetime import datetime

from ..db.chat_db import get_connection, list_sessions, load_messages, load_latest_summary
from ..printer import print_error, print_info


async def _export(session_name: str, fmt: str, output: str | None):
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
        content = _to_json(session_name, session_id, messages, summary)
    else:
        content = _to_markdown(session_name, session_id, messages, summary)

    if output:
        with open(output, "w") as f:
            f.write(content)
        print_info(f"Exported {len(messages)} messages to {output}")
    else:
        sys.stdout.write(content)


def _to_markdown(session_name, session_id, messages, summary) -> str:
    lines = []
    lines.append(f"# aicli session: {session_name}")
    lines.append(f"\n**Session ID:** `{session_id}`")
    lines.append(f"**Exported:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"**Messages:** {len(messages)}")

    if summary:
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


def _to_json(session_name, session_id, messages, summary) -> str:
    data = {
        "session_name": session_name,
        "session_id": session_id,
        "exported_at": datetime.now().isoformat(),
        "message_count": len(messages),
        "summary": summary,
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
