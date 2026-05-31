"""SQLite FTS5 index for Cloud Portal studio Markdown memory."""

from __future__ import annotations

import asyncio
import hashlib
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

_CHUNK_CHARS = 1600
_CHUNK_OVERLAP = 320
_DEBOUNCE_SECONDS = 1.5

_pending_sync: dict[str, asyncio.Task] = {}


@dataclass
class MemorySearchHit:
    path: str
    content: str
    line_start: int
    line_end: int
    score: float


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _chunk_text(text: str, path: str) -> list[tuple[int, int, str]]:
    if not text.strip():
        return []
    lines = text.splitlines(keepends=True)
    chunks: list[tuple[int, int, str]] = []
    buf = ""
    line_start = 1
    line_end = 1
    for idx, line in enumerate(lines, start=1):
        if not buf:
            line_start = idx
        buf += line
        line_end = idx
        if len(buf) >= _CHUNK_CHARS:
            chunks.append((line_start, line_end, buf.strip()))
            tail = buf[-_CHUNK_OVERLAP:] if len(buf) > _CHUNK_OVERLAP else buf
            buf = tail
            line_start = max(1, line_end - tail.count("\n"))
    if buf.strip():
        chunks.append((line_start, line_end, buf.strip()))
    if not chunks and text.strip():
        chunks.append((1, max(1, len(lines)), text.strip()))
    return chunks


class StudioMemoryIndex:
    """Per-workspace FTS index stored as `.memory.sqlite`."""

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace
        self.db_path = workspace / ".memory.sqlite"

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS files (
                path TEXT PRIMARY KEY,
                mtime REAL NOT NULL,
                content_hash TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT NOT NULL,
                line_start INTEGER NOT NULL,
                line_end INTEGER NOT NULL,
                content TEXT NOT NULL
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                path,
                content,
                content='chunks',
                content_rowid='id',
                tokenize='unicode61'
            );
            """
        )

    def _memory_files(self) -> list[Path]:
        files: list[Path] = []
        memory_md = self.workspace / "MEMORY.md"
        if memory_md.is_file():
            files.append(memory_md)
        memory_dir = self.workspace / "memory"
        if memory_dir.is_dir():
            files.extend(sorted(memory_dir.glob("*.md")))
        return files

    def _relative_path(self, path: Path) -> str:
        return path.relative_to(self.workspace).as_posix()

    def sync(self) -> None:
        """Rebuild index for all Markdown memory files."""
        self.workspace.mkdir(parents=True, exist_ok=True)
        conn = self._connect()
        try:
            self._ensure_schema(conn)
            conn.execute("DELETE FROM chunks")
            conn.execute("DELETE FROM files")
            try:
                conn.execute("INSERT INTO chunks_fts(chunks_fts) VALUES('delete-all')")
            except sqlite3.OperationalError:
                pass
            for file_path in self._memory_files():
                rel = self._relative_path(file_path)
                text = file_path.read_text(encoding="utf-8")
                mtime = file_path.stat().st_mtime
                digest = _content_hash(text)
                conn.execute(
                    "INSERT INTO files(path, mtime, content_hash) VALUES (?, ?, ?)",
                    (rel, mtime, digest),
                )
                for line_start, line_end, chunk in _chunk_text(text, rel):
                    cur = conn.execute(
                        """
                        INSERT INTO chunks(path, line_start, line_end, content)
                        VALUES (?, ?, ?, ?)
                        """,
                        (rel, line_start, line_end, chunk),
                    )
                    row_id = cur.lastrowid
                    conn.execute(
                        """
                        INSERT INTO chunks_fts(rowid, path, content)
                        VALUES (?, ?, ?)
                        """,
                        (row_id, rel, chunk),
                    )
            conn.commit()
        finally:
            conn.close()

    def search(self, query: str, *, top_k: int = 5) -> list[MemorySearchHit]:
        self.sync()
        q = (query or "").strip()
        if not q or not self.db_path.is_file():
            return []
        conn = self._connect()
        try:
            self._ensure_schema(conn)
            fts_query = " OR ".join(
                f'"{token}"'
                for token in re.findall(r"\w+", q, flags=re.UNICODE)
                if len(token) >= 2
            )
            if not fts_query:
                fts_query = f'"{q[:200]}"'
            rows = conn.execute(
                """
                SELECT c.path, c.line_start, c.line_end, c.content,
                       bm25(chunks_fts) AS rank
                FROM chunks_fts
                JOIN chunks c ON c.id = chunks_fts.rowid
                WHERE chunks_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (fts_query, top_k),
            ).fetchall()
            hits: list[MemorySearchHit] = []
            for row in rows:
                content = str(row["content"] or "")
                if len(content) > 700:
                    content = content[:700] + "…"
                hits.append(
                    MemorySearchHit(
                        path=str(row["path"]),
                        content=content,
                        line_start=int(row["line_start"]),
                        line_end=int(row["line_end"]),
                        score=round(float(-row["rank"]), 4),
                    )
                )
            return hits
        except sqlite3.OperationalError as e:
            logger.warning(f"Studio memory FTS search failed: {e}")
            return []
        finally:
            conn.close()


def schedule_index_sync(workspace: Path) -> None:
    """Debounce index rebuild after file writes."""
    key = str(workspace.resolve())

    async def _run() -> None:
        await asyncio.sleep(_DEBOUNCE_SECONDS)
        try:
            StudioMemoryIndex(workspace).sync()
        except Exception as e:
            logger.warning(f"Studio memory index sync failed for {workspace}: {e}")
        finally:
            _pending_sync.pop(key, None)

    existing = _pending_sync.get(key)
    if existing and not existing.done():
        existing.cancel()
    try:
        loop = asyncio.get_running_loop()
        _pending_sync[key] = loop.create_task(_run())
    except RuntimeError:
        StudioMemoryIndex(workspace).sync()
