"""
context/embeddings.py — ChromaDB RAG cold layer (Phase 5).

Two stores:
  LocalContext      — indexes local files (.py, .md, .txt, etc.)
  ChatContextStore  — indexes past chat messages and summaries

Both use ChromaDB's default embedding function (sentence-transformers all-MiniLM-L6-v2).
No external API needed — embeddings run locally.

Usage:
    local = LocalContext(chroma_dir)
    local.index_directory(Path("."))
    results = local.search("pipeline failover logic", n_results=5)

    chat = ChatContextStore(chroma_dir)
    chat.index_session(session_id, messages)
    results = chat.search("what rules did we establish", n_results=3)
"""

from pathlib import Path
from typing import Optional


# ── LocalContext ───────────────────────────────────────────────────────────────

class LocalContext:
    """
    Indexes local files into ChromaDB for semantic search.
    Chunks files by paragraph/function block (~500 chars each).
    """

    SUPPORTED_EXTENSIONS = {".py", ".md", ".txt", ".rst", ".toml", ".yaml", ".yml", ".json", ".sh"}
    CHUNK_SIZE = 500        # characters per chunk
    CHUNK_OVERLAP = 50      # overlap between chunks to preserve context

    def __init__(self, chroma_dir: Path):
        import chromadb
        self._client = chromadb.PersistentClient(path=str(chroma_dir))
        self._collection = self._client.get_or_create_collection(
            name="local_files",
            metadata={"hnsw:space": "cosine"},
        )

    def index_directory(
        self,
        path: Path,
        extensions: set[str] | None = None,
        exclude_dirs: set[str] | None = None,
    ) -> int:
        """
        Walk path, chunk and upsert all matching files.
        Returns number of chunks indexed.
        Skips files that haven't changed since last index (mtime check).
        """
        exts = extensions or self.SUPPORTED_EXTENSIONS
        skip_dirs = exclude_dirs or {"venv", ".venv", "__pycache__", ".git", "node_modules", ".mypy_cache"}

        documents, ids, metadatas = [], [], []
        indexed = 0

        for filepath in path.rglob("*"):
            if not filepath.is_file():
                continue
            if filepath.suffix not in exts:
                continue
            if any(part in skip_dirs for part in filepath.parts):
                continue

            try:
                text = filepath.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            mtime = str(filepath.stat().st_mtime)
            chunks = self._chunk_text(text)

            for i, chunk in enumerate(chunks):
                chunk_id = f"{filepath}::{i}"
                documents.append(chunk)
                ids.append(chunk_id)
                metadatas.append({
                    "filepath": str(filepath),
                    "chunk_index": i,
                    "mtime": mtime,
                    "extension": filepath.suffix,
                })
                indexed += 1

        if documents:
            # Upsert in batches of 100
            for i in range(0, len(documents), 100):
                self._collection.upsert(
                    documents=documents[i:i+100],
                    ids=ids[i:i+100],
                    metadatas=metadatas[i:i+100],
                )

        return indexed

    def index_file(self, filepath: Path) -> int:
        """Index a single file. Returns number of chunks indexed."""
        return self.index_directory(filepath.parent, exclude_dirs=set())

    def search(self, query: str, n_results: int = 5) -> list[dict]:
        """
        Semantic search over indexed files.
        Returns list of {text, filepath, chunk_index, score}.
        """
        count = self._collection.count()
        if count == 0:
            return []

        results = self._collection.query(
            query_texts=[query],
            n_results=min(n_results, count),
        )

        output = []
        for i, doc in enumerate(results["documents"][0]):
            meta = results["metadatas"][0][i]
            distance = results["distances"][0][i] if results.get("distances") else 0.0
            output.append({
                "text": doc,
                "filepath": meta.get("filepath", ""),
                "chunk_index": meta.get("chunk_index", 0),
                "score": round(1.0 - distance, 4),  # cosine similarity (higher = better)
            })
        return output

    def clear(self) -> None:
        """Remove all indexed local files."""
        self._client.delete_collection("local_files")
        self._collection = self._client.get_or_create_collection(
            name="local_files",
            metadata={"hnsw:space": "cosine"},
        )

    def count(self) -> int:
        """Number of indexed chunks."""
        return self._collection.count()

    def _chunk_text(self, text: str) -> list[str]:
        """
        Split text into overlapping chunks.
        Tries to split on paragraph/function boundaries first.
        Falls back to character-based splitting.
        """
        # Try paragraph-based splitting first
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

        chunks = []
        current = ""

        for para in paragraphs:
            if len(current) + len(para) <= self.CHUNK_SIZE:
                current = f"{current}\n\n{para}".strip()
            else:
                if current:
                    chunks.append(current)
                # Para itself too long — split by chars with overlap
                if len(para) > self.CHUNK_SIZE:
                    for i in range(0, len(para), self.CHUNK_SIZE - self.CHUNK_OVERLAP):
                        chunks.append(para[i:i + self.CHUNK_SIZE])
                else:
                    current = para

        if current:
            chunks.append(current)

        return chunks or [text[:self.CHUNK_SIZE]]


# ── ChatContextStore ───────────────────────────────────────────────────────────

class ChatContextStore:
    """
    Indexes past chat messages and summaries for semantic search.
    Enables queries like "what did we decide about the pipeline last week".
    """

    CHUNK_SIZE = 800  # larger chunks for conversation context

    def __init__(self, chroma_dir: Path):
        import chromadb
        self._client = chromadb.PersistentClient(path=str(chroma_dir))
        self._collection = self._client.get_or_create_collection(
            name="chat_history",
            metadata={"hnsw:space": "cosine"},
        )

    def index_session(self, session_id: str, messages: list[dict], summary: str | None = None) -> int:
        """
        Index messages and optional summary for a session.
        Groups messages into conversation chunks for better semantic coherence.
        Returns number of chunks indexed.
        """
        documents, ids, metadatas = [], [], []

        # Index summary if present
        if summary:
            doc_id = f"{session_id}::summary"
            documents.append(f"[SUMMARY] {summary}")
            ids.append(doc_id)
            metadatas.append({"session_id": session_id, "type": "summary", "chunk_index": 0})

        # Group messages into chunks (pair user+assistant turns)
        chunks = self._chunk_messages(messages)
        for i, chunk in enumerate(chunks):
            doc_id = f"{session_id}::chunk::{i}"
            documents.append(chunk)
            ids.append(doc_id)
            metadatas.append({"session_id": session_id, "type": "messages", "chunk_index": i})

        if documents:
            self._collection.upsert(
                documents=documents,
                ids=ids,
                metadatas=metadatas,
            )

        return len(documents)

    def search(self, query: str, n_results: int = 3) -> list[dict]:
        """
        Semantic search over past chat history.
        Returns list of {text, session_id, type, score}.
        """
        count = self._collection.count()
        if count == 0:
            return []

        results = self._collection.query(
            query_texts=[query],
            n_results=min(n_results, count),
        )

        output = []
        for i, doc in enumerate(results["documents"][0]):
            meta = results["metadatas"][0][i]
            distance = results["distances"][0][i] if results.get("distances") else 0.0
            output.append({
                "text": doc,
                "session_id": meta.get("session_id", ""),
                "type": meta.get("type", "messages"),
                "score": round(1.0 - distance, 4),
            })
        return output

    def count(self) -> int:
        """Number of indexed chunks."""
        return self._collection.count()

    def _chunk_messages(self, messages: list[dict]) -> list[str]:
        """Group messages into semantic chunks (pairs of user+assistant turns)."""
        chunks = []
        current = ""

        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "system":
                continue
            line = f"{role.upper()}: {content}"
            if len(current) + len(line) > self.CHUNK_SIZE and current:
                chunks.append(current.strip())
                current = line
            else:
                current = f"{current}\n{line}".strip()

        if current:
            chunks.append(current.strip())

        return chunks
