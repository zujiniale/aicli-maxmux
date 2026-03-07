"""
context/retriever.py — Unified semantic search over files + chat history.

ContextRetriever combines LocalContext and ChatContextStore into a single
interface. Given a query, it retrieves the most relevant chunks from both
stores and formats them as a context block for injection into the AI prompt.
"""

from pathlib import Path


class ContextRetriever:
    """
    Unified semantic search over local files and chat history.
    Returns a formatted context block ready for injection into messages.
    """

    def __init__(self, chroma_dir: Path):
        from .embeddings import LocalContext, ChatContextStore
        self._local = LocalContext(chroma_dir)
        self._chat = ChatContextStore(chroma_dir)
        self._chroma_dir = chroma_dir

    def retrieve(
        self,
        query: str,
        include_files: bool = True,
        include_chat: bool = True,
        n_files: int = 3,
        n_chat: int = 3,
        min_score: float = 0.25,
        depth: int = 1,
    ) -> str | None:
        """
        Search both stores and return a formatted context block.
        depth multiplier scales n_files and n_chat (1=default, 2=2x, 3=3x).

        Chat strategy: fetch ALL summaries first (they are always preferred
        over raw message chunks), then fill remaining slots with top-scoring
        raw message chunks from sessions not already covered by a summary.
        """
        n_files = n_files * depth
        n_chat = n_chat * depth

        sections = []

        if include_chat:
            total = self._chat.count()
            if total > 0:
                # Fetch ALL documents and separate summaries from messages
                all_results = self._chat.search(query, n_results=min(total, 50))
                summaries = [r for r in all_results if r["type"] == "summary"]
                messages  = [r for r in all_results if r["type"] != "summary"]

                # Always include all summaries (they are the most complete context)
                covered_sessions = set()
                for r in summaries:
                    sections.append(f"[chat summary: {r['session_id']}]\n{r['text']}")
                    covered_sessions.add(r["session_id"])

                # Fill remaining slots with top message chunks from uncovered sessions
                added = 0
                for r in messages:
                    if added >= n_chat:
                        break
                    if r["session_id"] not in covered_sessions and r["score"] >= min_score:
                        sections.append(f"[chat: {r['session_id']}]\n{r['text']}")
                        added += 1

        if include_files:
            file_results = self._local.search(query, n_results=n_files)
            for r in file_results:
                if r["score"] >= min_score:
                    sections.append(f"[file: {r['filepath']}]\n{r['text']}")

        if not sections:
            return None

        return "RELEVANT CONTEXT:\n\n" + "\n\n".join(sections)

    def index_directory(self, path: Path, **kwargs) -> int:
        """Index a local directory. Returns number of chunks indexed."""
        return self._local.index_directory(path, **kwargs)

    def index_session(self, session_id: str, messages: list[dict], summary: str | None = None) -> int:
        """Index a chat session into the chat store."""
        return self._chat.index_session(session_id, messages, summary=summary)

    def status(self) -> dict:
        """Return counts from both stores."""
        return {
            "local_chunks": self._local.count(),
            "chat_chunks": self._chat.count(),
        }
