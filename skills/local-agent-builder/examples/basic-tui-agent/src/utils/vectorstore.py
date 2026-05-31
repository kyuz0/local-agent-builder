# -------------------------------------------------------------
# [!CAUTION] RULES FOR LLM CODING ASSISTANTS EDITING THIS:
# 1. This is a UTILITY module, NOT an agent tool. Do NOT decorate
#    any function with @tool or pass the VectorStore class to AgentBuilder.
# 2. The VectorStore is instantiated programmatically at startup in app.py.
#    The agent NEVER triggers embedding or ingestion.
# 3. Agent-facing tools that query this store live in src/tools/rag.py.
# 4. If your project does not use RAG, delete this file and remove
#    sqlite-vec + semchunk from pyproject.toml.
# -------------------------------------------------------------

import os
import hashlib
import sqlite3
import struct
import shutil
import logging
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

# --- Optional dependency imports (graceful degradation) ---
try:
    import sqlite_vec
    _sqlite_vec_available = True
except ImportError:
    _sqlite_vec_available = False
    logger.warning("sqlite-vec not installed. RAG vector search will be unavailable.")

try:
    import semchunk
    _semchunk_available = True
except ImportError:
    _semchunk_available = False
    logger.warning("semchunk not installed. Using basic character-level chunking fallback.")


def _serialize_f32(vec: list[float]) -> bytes:
    """Serialize a list of floats into a compact binary format for sqlite-vec."""
    return struct.pack(f"{len(vec)}f", *vec)


def _basic_chunk(text: str, chunk_size: int = 1000, overlap: int = 150) -> list[str]:
    """Fallback chunker when semchunk is unavailable."""
    chunks = []
    step = max(1, chunk_size - overlap)
    for i in range(0, len(text), step):
        chunk = text[i:i + chunk_size]
        if chunk.strip():
            chunks.append(chunk)
        if i + chunk_size >= len(text):
            break
    return chunks


def _parse_file(filepath: str) -> str | None:
    """Parse a file to text, preferring liteparse then falling back to markitdown.
    
    Returns the parsed text content, or None if parsing fails.
    """
    # Try liteparse first (better spatial accuracy for PDFs, tables)
    if shutil.which("liteparse"):
        try:
            import subprocess
            result = subprocess.run(
                ["liteparse", filepath],
                capture_output=True, text=True, timeout=60
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout
        except Exception as e:
            logger.debug(f"liteparse failed for {filepath}: {e}")

    # Fallback to markitdown
    try:
        from utils.parsers import convert_to_markdown
        content = convert_to_markdown(filepath)
        if content:
            return content
    except ImportError:
        pass
    except Exception as e:
        logger.debug(f"markitdown failed for {filepath}: {e}")

    # Last resort: try reading as plain text
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception:
        return None


class VectorStore:
    """SQLite-vec backed vector store for local RAG pipelines.
    
    Handles document scanning, parsing, chunking (via semchunk), embedding
    (via OpenAI-compatible /v1/embeddings), and KNN search — all deterministic
    and programmatic. This class is NEVER exposed as an agent tool.
    
    Usage in app.py:
        from utils.vectorstore import VectorStore
        
        vs = VectorStore(
            library_dir=cfg["settings"]["rag"]["library_dir"],
            embedding_url=cfg["api"].get("embedding_base_url", cfg["api"]["openai_base_url"]),
            embedding_model=cfg["api"].get("embedding_model", cfg["api"]["openai_model"]),
            chunk_size=cfg["settings"]["rag"].get("chunk_size", 1000),
            chunk_overlap=cfg["settings"]["rag"].get("chunk_overlap", 150),
        )
        stats = vs.sync()  # Scan, parse, chunk, embed new/changed files
    """

    def __init__(
        self,
        library_dir: str,
        embedding_url: str = "http://localhost:8080/v1",
        embedding_model: str = "local-model",
        chunk_size: int = 1000,
        chunk_overlap: int = 150,
        search_results: int = 5,
    ):
        if not _sqlite_vec_available:
            raise RuntimeError(
                "sqlite-vec is required for RAG. Install it: pip install sqlite-vec"
            )

        self.library_dir = os.path.abspath(os.path.expanduser(library_dir))
        self.embedding_url = embedding_url.rstrip("/")
        self.embedding_model = embedding_model
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.search_results = search_results
        self._embedding_dim: int | None = None

        os.makedirs(self.library_dir, exist_ok=True)
        db_path = os.path.join(self.library_dir, ".rag.db")
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.enable_load_extension(True)
        sqlite_vec.load(self.conn)
        self.conn.enable_load_extension(False)

        self._init_schema()

    def _init_schema(self):
        """Create metadata and document tables. vec_chunks is deferred until dim is known."""
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS rag_meta (
                key TEXT PRIMARY KEY,
                value TEXT
            );
            CREATE TABLE IF NOT EXISTS raw_docs (
                filename TEXT PRIMARY KEY,
                md5 TEXT,
                content TEXT
            );
            CREATE TABLE IF NOT EXISTS chunk_map (
                rowid INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT,
                chunk_text TEXT,
                start_char INTEGER,
                end_char INTEGER
            );
        """)
        self.conn.commit()

        # Load cached embedding dimension if available
        row = self.conn.execute(
            "SELECT value FROM rag_meta WHERE key = 'embedding_dim'"
        ).fetchone()
        if row:
            self._embedding_dim = int(row["value"])
            self._ensure_vec_table()

    def _ensure_vec_table(self):
        """Create the vec0 virtual table if it doesn't exist yet."""
        if self._embedding_dim is None:
            return
        # Check if table exists
        exists = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='vec_chunks'"
        ).fetchone()
        if not exists:
            self.conn.execute(
                f"CREATE VIRTUAL TABLE vec_chunks USING vec0(embedding float[{self._embedding_dim}])"
            )
            self.conn.commit()

    def _detect_dimension(self) -> int:
        """Auto-detect embedding dimension by sending a probe to /v1/embeddings."""
        vec = self._embed_single("dimension probe")
        dim = len(vec)
        self.conn.execute(
            "INSERT OR REPLACE INTO rag_meta (key, value) VALUES ('embedding_dim', ?)",
            (str(dim),)
        )
        self.conn.commit()
        self._embedding_dim = dim
        self._ensure_vec_table()
        logger.info(f"Auto-detected embedding dimension: {dim}")
        return dim

    def _embed_single(self, text: str) -> list[float]:
        """Embed a single text via /v1/embeddings endpoint."""
        resp = httpx.post(
            f"{self.embedding_url}/embeddings",
            json={"model": self.embedding_model, "input": text},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["data"][0]["embedding"]

    def _embed_batch(self, texts: list[str], batch_size: int = 8) -> list[list[float]]:
        """Embed texts in batches. Falls back to one-at-a-time if batch fails."""
        all_embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            try:
                resp = httpx.post(
                    f"{self.embedding_url}/embeddings",
                    json={"model": self.embedding_model, "input": batch},
                    timeout=120,
                )
                resp.raise_for_status()
                data = resp.json()["data"]
                # Sort by index to ensure order
                data.sort(key=lambda x: x["index"])
                all_embeddings.extend([d["embedding"] for d in data])
            except Exception:
                # Fallback: embed one at a time (some servers reject batches)
                for text in batch:
                    all_embeddings.append(self._embed_single(text))
        return all_embeddings

    def _chunk_text(self, text: str) -> list[str]:
        """Chunk text using semchunk (preferred) or basic fallback."""
        if _semchunk_available:
            return semchunk.chunk(text, chunk_size=self.chunk_size)
        return _basic_chunk(text, self.chunk_size, self.chunk_overlap)

    def sync(self) -> dict:
        """Scan library_dir for new/changed files, parse, chunk, embed, and store.
        
        Returns:
            Stats dict: {"new": int, "unchanged": int, "errors": int, "total_chunks": int}
        """
        stats = {"new": 0, "unchanged": 0, "errors": 0, "total_chunks": 0}
        files_to_embed: list[tuple[str, str]] = []  # [(filename, content)]

        for file_path in sorted(Path(self.library_dir).iterdir()):
            if not file_path.is_file() or file_path.name.startswith("."):
                continue

            filename = file_path.name
            try:
                current_md5 = hashlib.md5(file_path.read_bytes()).hexdigest()
            except Exception:
                stats["errors"] += 1
                continue

            row = self.conn.execute(
                "SELECT md5 FROM raw_docs WHERE filename = ?", (filename,)
            ).fetchone()

            if row and row["md5"] == current_md5:
                stats["unchanged"] += 1
                continue

            # Parse the file
            content = _parse_file(str(file_path))
            if not content or not content.strip():
                logger.warning(f"Skipping {filename}: could not parse content")
                stats["errors"] += 1
                continue

            # Store raw content
            self.conn.execute(
                "INSERT OR REPLACE INTO raw_docs (filename, md5, content) VALUES (?, ?, ?)",
                (filename, current_md5, content),
            )
            self.conn.commit()
            files_to_embed.append((filename, content))
            stats["new"] += 1

        if not files_to_embed:
            # Count existing chunks
            row = self.conn.execute("SELECT COUNT(*) as cnt FROM chunk_map").fetchone()
            stats["total_chunks"] = row["cnt"] if row else 0
            return stats

        # Auto-detect embedding dimension if not yet known
        if self._embedding_dim is None:
            self._detect_dimension()

        # Process each new/changed file
        for filename, content in files_to_embed:
            logger.info(f"Processing {filename}...")

            # Remove old chunks and vectors for this file
            old_rowids = [
                r["rowid"] for r in
                self.conn.execute("SELECT rowid FROM chunk_map WHERE filename = ?", (filename,)).fetchall()
            ]
            if old_rowids:
                placeholders = ",".join("?" * len(old_rowids))
                self.conn.execute(f"DELETE FROM vec_chunks WHERE rowid IN ({placeholders})", old_rowids)
                self.conn.execute("DELETE FROM chunk_map WHERE filename = ?", (filename,))
                self.conn.commit()

            # Chunk
            chunks = self._chunk_text(content)
            if not chunks:
                continue

            # Track character offsets
            chunk_data = []
            search_start = 0
            for chunk_text in chunks:
                start_char = content.find(chunk_text, search_start)
                if start_char == -1:
                    start_char = search_start
                end_char = start_char + len(chunk_text)
                chunk_data.append((filename, chunk_text, start_char, end_char))
                search_start = start_char + 1

            # Insert chunk metadata first to get rowids
            rowids = []
            for cd in chunk_data:
                cursor = self.conn.execute(
                    "INSERT INTO chunk_map (filename, chunk_text, start_char, end_char) VALUES (?, ?, ?, ?)",
                    cd,
                )
                rowids.append(cursor.lastrowid)
            self.conn.commit()

            # Embed all chunks
            embeddings = self._embed_batch([cd[1] for cd in chunk_data])

            # Insert vectors
            for rowid, embedding in zip(rowids, embeddings):
                self.conn.execute(
                    "INSERT INTO vec_chunks (rowid, embedding) VALUES (?, ?)",
                    (rowid, _serialize_f32(embedding)),
                )
            self.conn.commit()

            logger.info(f"  Indexed {len(chunks)} chunks from {filename}")

        row = self.conn.execute("SELECT COUNT(*) as cnt FROM chunk_map").fetchone()
        stats["total_chunks"] = row["cnt"] if row else 0
        return stats

    def semantic_search(self, query: str, k: int | None = None) -> list[dict]:
        """Embed the query and perform KNN search over the vector index.
        
        Returns:
            List of dicts: [{"filename": str, "chunk_text": str, "distance": float}]
        """
        if self._embedding_dim is None:
            return []

        k = k or self.search_results
        query_vec = self._embed_single(query)

        rows = self.conn.execute(
            """
            SELECT v.rowid, v.distance, c.filename, c.chunk_text
            FROM vec_chunks v
            JOIN chunk_map c ON c.rowid = v.rowid
            WHERE v.embedding MATCH ?
            ORDER BY v.distance
            LIMIT ?
            """,
            (_serialize_f32(query_vec), k),
        ).fetchall()

        return [
            {"filename": r["filename"], "chunk_text": r["chunk_text"], "distance": r["distance"]}
            for r in rows
        ]

    def keyword_search(self, query: str, max_results: int = 10) -> list[dict]:
        """Case-insensitive exact keyword match over all chunks.
        
        Returns:
            List of dicts: [{"filename": str, "chunk_text": str}]
        """
        rows = self.conn.execute(
            """
            SELECT filename, chunk_text
            FROM chunk_map
            WHERE chunk_text LIKE ?
            LIMIT ?
            """,
            (f"%{query}%", max_results),
        ).fetchall()

        return [{"filename": r["filename"], "chunk_text": r["chunk_text"]} for r in rows]

    def list_files(self) -> list[dict]:
        """List all indexed documents with line and character counts.
        
        Returns:
            List of dicts: [{"filename": str, "lines": int, "chars": int, "chunks": int}]
        """
        rows = self.conn.execute(
            """
            SELECT d.filename, d.content,
                   (SELECT COUNT(*) FROM chunk_map c WHERE c.filename = d.filename) as chunk_count
            FROM raw_docs d
            ORDER BY d.filename
            """
        ).fetchall()

        return [
            {
                "filename": r["filename"],
                "lines": len(r["content"].splitlines()),
                "chars": len(r["content"]),
                "chunks": r["chunk_count"],
            }
            for r in rows
        ]

    def read_file(self, filename: str, start_line: int = 1, end_line: int = -1) -> str | None:
        """Read a range of lines from a raw document. Lines are 1-indexed.
        
        Returns:
            Formatted string with line numbers, or None if file not found.
        """
        row = self.conn.execute(
            "SELECT content FROM raw_docs WHERE filename = ?", (filename,)
        ).fetchone()
        if not row:
            return None

        lines = row["content"].splitlines()
        total = len(lines)
        if end_line == -1:
            end_line = total

        start = max(1, start_line)
        end = min(total, end_line)
        selected = lines[start - 1:end]

        header = f"--- {filename} [Lines {start}-{end} of {total}] ---"
        body = "\n".join(f"{i + start}: {line}" for i, line in enumerate(selected))
        return f"{header}\n{body}"
