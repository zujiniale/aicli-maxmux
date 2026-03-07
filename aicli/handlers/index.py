"""handlers/index.py — RAG indexing handler."""
from pathlib import Path

from ..config import load_config, CHROMA_DIR
from ..printer import print_error, print_success, print_info
from ..db.chat_db import get_connection, list_sessions, load_messages, load_latest_summary


async def _index(path_str: str, include_chat: bool):
    from ..context.retriever import ContextRetriever

    config = load_config()

    try:
        retriever = ContextRetriever(CHROMA_DIR)
    except ImportError:
        print_error("chromadb not installed. Run: pip install chromadb")
        return

    # Index local files
    target = Path(path_str).resolve()
    print_info(f"Indexing {target} ...")
    count = retriever.index_directory(target)
    print_success(f"Indexed {count} chunks from {target}")

    # Optionally index chat sessions
    if include_chat:
        conn = get_connection()
        sessions = list_sessions(conn)
        total = 0
        for s in sessions:
            messages = load_messages(conn, s["id"])
            summary = load_latest_summary(conn, s["id"])
            n = retriever.index_session(s["id"], messages, summary=summary)
            total += n
        print_success(f"Indexed {total} chunks from {len(sessions)} chat sessions")

    status = retriever.status()
    print_info(f"Total indexed: {status['local_chunks']} file chunks, {status['chat_chunks']} chat chunks")
