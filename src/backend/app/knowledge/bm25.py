"""BM25 keyword search index per knowledge base."""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass, field
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.tokenize import TokenizeConfig, tokenize_for_search


@dataclass
class _ChunkEntry:
    chunk_id: str
    content: str
    term_freqs: dict[str, int] = field(default_factory=dict)
    doc_len: int = 0


@dataclass
class _CorpusStats:
    chunks: list[_ChunkEntry]
    avgdl: float = 0.0
    idf: dict[str, float] = field(default_factory=dict)


class Bm25Index:
    """Pure-Python BM25 scorer with per-knowledge-base caching."""

    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self._cache: dict[str, _CorpusStats] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def _get_lock(self, kb_id: str) -> asyncio.Lock:
        if kb_id not in self._locks:
            self._locks[kb_id] = asyncio.Lock()
        return self._locks[kb_id]

    def invalidate(self, kb_id: str) -> None:
        self._cache.pop(kb_id, None)

    def invalidate_all(self) -> None:
        self._cache.clear()

    async def _load_chunks(
        self, db: AsyncSession, kb_id: str, tokenize_config: TokenizeConfig | None = None
    ) -> list[_ChunkEntry]:
        from app.models.knowledge import DocumentChunk, Document

        stmt = (
            select(DocumentChunk.id, DocumentChunk.content)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(
                DocumentChunk.knowledge_base_id == kb_id,
                Document.status == "indexed",
            )
        )
        result = await db.execute(stmt)
        entries: list[_ChunkEntry] = []
        for chunk_id, content in result.all():
            text = (content or "").lower()
            tokens = tokenize_for_search(
                text,
                tokenize_config,
                apply_stop_words=False,
            )
            tf: dict[str, int] = {}
            for t in tokens:
                tf[t] = tf.get(t, 0) + 1
            entries.append(
                _ChunkEntry(
                    chunk_id=chunk_id,
                    content=content or "",
                    term_freqs=tf,
                    doc_len=len(tokens),
                )
            )
        return entries

    async def build_index(
        self,
        db: AsyncSession,
        kb_id: str,
        tokenize_config: TokenizeConfig | None = None,
    ) -> None:
        entries = await self._load_chunks(db, kb_id, tokenize_config)
        if not entries:
            self._cache[kb_id] = _CorpusStats(chunks=[], avgdl=0.0, idf={})
            return

        num_docs = len(entries)
        total_len = sum(e.doc_len for e in entries)
        avgdl = total_len / num_docs if num_docs > 0 else 0.0

        df: dict[str, int] = defaultdict(int)
        for entry in entries:
            for term in entry.term_freqs:
                df[term] += 1

        idf: dict[str, float] = {}
        for term, freq in df.items():
            idf[term] = math.log(
                (num_docs - freq + 0.5) / (freq + 0.5) + 1.0
            )

        self._cache[kb_id] = _CorpusStats(
            chunks=entries, avgdl=avgdl, idf=idf
        )

    async def ensure_index(
        self,
        db: AsyncSession,
        kb_id: str,
        tokenize_config: TokenizeConfig | None = None,
    ) -> None:
        if kb_id in self._cache:
            return
        lock = self._get_lock(kb_id)
        async with lock:
            if kb_id not in self._cache:
                await self.build_index(db, kb_id, tokenize_config)

    async def search(
        self,
        db: AsyncSession,
        query: str,
        kb_id: str,
        top_k: int,
        k1: float | None = None,
        b: float | None = None,
        tokenize_config: TokenizeConfig | None = None,
    ) -> list[tuple[float, str]]:
        """Return scored (score, chunk_id) pairs."""
        await self.ensure_index(db, kb_id, tokenize_config)
        stats = self._cache.get(kb_id)
        if not stats or not stats.chunks:
            return []

        _k1 = k1 if k1 is not None else self.k1
        _b = b if b is not None else self.b

        query_terms = tokenize_for_search(query, tokenize_config)
        if not query_terms:
            return []

        scored: list[tuple[float, str]] = []
        for entry in stats.chunks:
            score = 0.0
            for term in query_terms:
                tf = entry.term_freqs.get(term, 0)
                if tf == 0:
                    continue
                idf_val = stats.idf.get(term, 0.0)
                numerator = tf * (_k1 + 1)
                denominator = tf + _k1 * (
                    1 - _b + _b * (entry.doc_len / stats.avgdl if stats.avgdl > 0 else 1)
                )
                score += idf_val * (numerator / denominator)
            if score > 0:
                scored.append((score, entry.chunk_id))

        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[:top_k]


# Module-level singleton
bm25_index = Bm25Index()
