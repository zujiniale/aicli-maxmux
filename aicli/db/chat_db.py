"""
db.py — SQLite persistent storage for aicli.
Schema: sessions + messages + summaries tables.
WAL mode for concurrent read performance.
Optional Fernet encryption per message content.

CRITICAL: db.save() is always called FIRST — before token counting,
before threshold checks, before any pruning. This is non-negotiable.
"""

import json
import sqlite3
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ..config import DB_FILE


# ---------------------------------------------------------------------------
# Content serialization helpers (F2: multimodal list[dict] support)
# ---------------------------------------------------------------------------

def _pack_content(content) -> str:
    """Serialize content for SQLite storage. Handles str or list[dict] (multimodal)."""
    if isinstance(content, list):
        return json.dumps(content)
    return content  # already a string


def _unpack_content(raw: str):
    """Deserialize content from SQLite. Returns list[dict] if JSON array, else str.
    Backward compatible: plain strings pass through unchanged."""
    if raw is None:
        return raw
    if raw.startswith("[") or raw.startswith("{"):
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            pass
    return raw  # plain string — backward compatible


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """Open a SQLite connection with WAL mode and foreign keys enabled."""
    path = db_path or DB_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    _create_schema(conn)
    return conn


def _create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            id          TEXT PRIMARY KEY,
            name        TEXT,
            role        TEXT DEFAULT 'default',
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS messages (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  TEXT NOT NULL REFERENCES sessions(id),
            role        TEXT NOT NULL,
            content     TEXT NOT NULL,
            token_count INTEGER DEFAULT 0,
            created_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS summaries (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  TEXT NOT NULL REFERENCES sessions(id),
            summary     TEXT NOT NULL,
            covers_from INTEGER NOT NULL,
            covers_to   INTEGER NOT NULL,
            created_at  TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
        CREATE INDEX IF NOT EXISTS idx_summaries_session ON summaries(session_id);
    """)
    conn.commit()


def ensure_session(conn: sqlite3.Connection, session_id: str, name: str = "", role: str = "default") -> None:
    """Create session if it doesn't exist."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute("""
        INSERT OR IGNORE INTO sessions (id, name, role, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
    """, (session_id, name or session_id, role, now, now))
    conn.commit()


def save_message(
    conn: sqlite3.Connection,
    session_id: str,
    role: str,
    content: str | list,
    token_count: int = 0,
    fernet=None,
) -> int:
    """
    Save a message to SQLite. ALWAYS call this first before any other logic.
    Returns the message ID.
    """
    ensure_session(conn, session_id)
    packed = _pack_content(content)
    stored_content = packed
    if fernet:
        stored_content = fernet.encrypt(packed.encode()).decode()

    now = datetime.now(timezone.utc).isoformat()
    cursor = conn.execute("""
        INSERT INTO messages (session_id, role, content, token_count, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (session_id, role, stored_content, token_count, now))
    conn.commit()
    return cursor.lastrowid


def save_summary(
    conn: sqlite3.Connection,
    session_id: str,
    summary: str,
    covers_from: int,
    covers_to: int,
) -> None:
    """Save a summarization result covering message IDs covers_from to covers_to."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute("""
        INSERT INTO summaries (session_id, summary, covers_from, covers_to, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (session_id, summary, covers_from, covers_to, now))
    conn.commit()


def load_messages(
    conn: sqlite3.Connection,
    session_id: str,
    fernet=None,
) -> list[dict]:
    """Load all messages for a session in chronological order."""
    rows = conn.execute("""
        SELECT id, role, content, created_at FROM messages
        WHERE session_id = ?
        ORDER BY id ASC
    """, (session_id,)).fetchall()

    result = []
    for row in rows:
        content = row["content"]
        if fernet:
            try:
                content = fernet.decrypt(content.encode()).decode()
            except Exception:
                pass  # Unencrypted row (e.g., from migration)
        content = _unpack_content(content)  # deserialize JSON list if multimodal
        result.append({"id": row["id"], "role": row["role"], "content": content, "timestamp": row["created_at"]})
    return result


def load_latest_summary(
    conn: sqlite3.Connection,
    session_id: str,
) -> Optional[str]:
    """Load the most recent summary for a session."""
    row = conn.execute("""
        SELECT summary FROM summaries
        WHERE session_id = ?
        ORDER BY id DESC
        LIMIT 1
    """, (session_id,)).fetchone()
    return row["summary"] if row else None


def list_sessions(conn: sqlite3.Connection) -> list[dict]:
    """List all sessions ordered by most recently updated."""
    rows = conn.execute("""
        SELECT s.id, s.name, s.role, s.updated_at,
               COUNT(m.id) as message_count
        FROM sessions s
        LEFT JOIN messages m ON m.session_id = s.id
        GROUP BY s.id
        ORDER BY s.updated_at DESC
    """).fetchall()
    return [dict(row) for row in rows]


def delete_session(conn: sqlite3.Connection, session_id: str) -> None:
    """Delete a session and all its messages and summaries."""
    conn.execute("DELETE FROM summaries WHERE session_id = ?", (session_id,))
    conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
    conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    conn.commit()


def fork_session(
    conn: sqlite3.Connection,
    source_session_id: str,
    new_name: str,
    up_to_message_id: Optional[int] = None,
) -> str:
    """
    Fork a session by copying its messages into a new session.

    `up_to_message_id` is 1-indexed position within the session (NOT the global DB id).
    E.g. up_to_message_id=5 copies the first 5 messages of the session.
    If None, copies ALL messages.

    Returns the new session's UUID.
    """
    import uuid as _uuid

    source = conn.execute(
        "SELECT name, role FROM sessions WHERE id = ?", (source_session_id,)
    ).fetchone()
    if not source:
        raise ValueError(f"Source session not found: {source_session_id}")

    # Use LIMIT N for positional slicing — message IDs are global autoincrement,
    # so id <= N would match nothing for sessions with high-numbered message IDs.
    if up_to_message_id is not None:
        rows = conn.execute("""
            SELECT role, content, token_count, created_at FROM messages
            WHERE session_id = ?
            ORDER BY id ASC
            LIMIT ?
        """, (source_session_id, up_to_message_id)).fetchall()
    else:
        rows = conn.execute("""
            SELECT role, content, token_count, created_at FROM messages
            WHERE session_id = ?
            ORDER BY id ASC
        """, (source_session_id,)).fetchall()

    new_id = str(_uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    conn.execute("""
        INSERT INTO sessions (id, name, role, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
    """, (new_id, new_name, source["role"], now, now))

    for row in rows:
        conn.execute("""
            INSERT INTO messages (session_id, role, content, token_count, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (new_id, row["role"], row["content"], row["token_count"], row["created_at"]))

    # Copy the latest summary so the fork starts with full historical context.
    # Only copy the most recent summary — it covers the full history up to that point.
    latest_summary = conn.execute("""
        SELECT summary, covers_from, covers_to FROM summaries
        WHERE session_id = ?
        ORDER BY id DESC
        LIMIT 1
    """, (source_session_id,)).fetchone()
    if latest_summary:
        conn.execute("""
            INSERT INTO summaries (session_id, summary, covers_from, covers_to, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (new_id, latest_summary["summary"], latest_summary["covers_from"], latest_summary["covers_to"], now))

    conn.commit()
    return new_id
