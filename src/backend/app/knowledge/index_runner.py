"""Background index runner for knowledge documents.

The HTTP upload path used to run parse → chunk → embed → Milvus insert inline,
which blocked the event loop for large files and starved every other request.
This module moves that work to a bounded set of ``asyncio`` background tasks so
the upload endpoint can return immediately with a ``processing`` document and
the frontend polls until indexing finishes.

Design notes
------------
* Tasks run in the API process (single-instance deployment, no separate worker
  process exists). CPU-heavy steps (file parsing, chunking, Milvus insert) are
  dispatched via ``asyncio.to_thread`` so they never block the event loop.
* Each task owns its own ``AsyncSession`` (opened from
  ``async_session_factory``); it must not touch the request-scoped session.
* ``recover_stale_indexing`` re-queues documents stuck in ``processing`` after a
  restart, since ``asyncio.create_task`` is not durable across restarts.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from loguru import logger
from sqlalchemy import select, update

from app.core.database import async_session_factory
from app.knowledge.chunk_store import replace_document_chunks
from app.knowledge.chunking import chunk_text_with_parents
from app.knowledge.embedder import embedder_for_config
from app.knowledge.embedding_align import align_kb_embedding_to_milvus
from app.knowledge.importer import DocumentImporter
from app.knowledge.milvus_client import milvus_client
from app.knowledge.rag_config import rag_settings_from_kb
from app.models.knowledge import Document, KnowledgeBase

#: Max concurrent index tasks. Keeps memory/CPU bounded under bulk uploads.
_DEFAULT_CONCURRENCY = 4

_runner: "_IndexRunner | None" = None


class _IndexRunner:
    """Manages background document indexing with a concurrency semaphore."""

    def __init__(self, concurrency: int = _DEFAULT_CONCURRENCY) -> None:
        self._semaphore = asyncio.Semaphore(concurrency)
        self._tasks: set[asyncio.Task[Any]] = set()
        self._started = True

    def started(self) -> bool:
        return self._started

    def enqueue(self, doc_id: str) -> None:
        """Schedule indexing for a document. Safe to call repeatedly."""
        if not self._started:
            logger.warning("Index runner not started; skipping {}", doc_id)
            return

        task = asyncio.create_task(self._guarded_run(doc_id))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _guarded_run(self, doc_id: str) -> None:
        async with self._semaphore:
            try:
                await self._run_index(doc_id)
            except asyncio.CancelledError:
                raise
            except Exception:
                # _run_index already marks the doc failed on its own errors;
                # this is a last-resort guard so one bad task can't kill others.
                logger.exception("Unexpected error indexing document {}", doc_id)
                await self._mark_status(doc_id, "failed")

    async def _run_index(self, doc_id: str) -> None:
        """Index one document end-to-end in a dedicated session."""
        async with async_session_factory() as db:
            result = await db.execute(
                select(Document).where(Document.id == doc_id)
            )
            doc = result.scalar_one_or_none()
            if doc is None:
                logger.warning("Index task: document {} vanished", doc_id)
                return
            if doc.status == "indexed":
                return

            kb_result = await db.execute(
                select(KnowledgeBase).where(KnowledgeBase.id == doc.knowledge_base_id)
            )
            kb = kb_result.scalar_one_or_none()
            if kb is None:
                logger.warning(
                    "Index task: knowledge base {} missing for doc {}",
                    doc.knowledge_base_id,
                    doc_id,
                )
                doc.status = "failed"
                await db.commit()
                return

            rag_settings = rag_settings_from_kb(kb)
            doc.status = "processing"
            await db.commit()

            try:
                content = await self._resolve_content(doc)
            except Exception as exc:
                logger.error("Failed to read content for {}: {}", doc_id, exc)
                doc.status = "failed"
                await db.commit()
                return

            if not content.strip():
                doc.content = content
                doc.status = "failed"
                doc.chunk_count = 0
                await db.commit()
                return

            doc.content = content
            await db.commit()

            importer = DocumentImporter(rag_settings=rag_settings, db=db)
            try:
                chunk_count = await self._index_with_importer(
                    importer, doc, kb, content
                )
            except Exception as exc:
                logger.error("Background indexing failed for {}: {}", doc_id, exc)
                doc.status = "failed"
                await db.commit()
                return

            if chunk_count > 0:
                doc.chunk_count = chunk_count
                doc.status = "indexed"
                if milvus_client._connected:
                    importer.mark_kb_indexed(kb)
            else:
                doc.status = "failed"
            await db.commit()
            logger.info("Document {} indexed ({} chunks)", doc_id, chunk_count)

    async def _resolve_content(self, doc: Document) -> str:
        """Return text content for a document.

        URL imports already have ``content`` populated by the caller (fetched
        inline before enqueue). File imports resolve from the stored source
        file path via the importer's parser.
        """
        if (doc.content or "").strip():
            return doc.content

        file_path = self._resolve_source_path(doc)
        if file_path is not None:
            importer = DocumentImporter()
            # Parsing is synchronous CPU work — run off the event loop.
            return await asyncio.to_thread(importer._read_file, file_path)

        return doc.content or ""

    @staticmethod
    def _resolve_source_path(doc: Document) -> Path | None:
        raw = (doc.source_file_path or "").strip()
        if not raw:
            return None
        return Path(raw)

    async def _index_with_importer(
        self,
        importer: DocumentImporter,
        doc: Document,
        kb: KnowledgeBase,
        content: str,
    ) -> int:
        """Chunk → store chunks → embed → Milvus insert.

        Mirrors ``DocumentImporter.import_file`` but lets us reuse the
        caller's session and wrap CPU-bound steps in ``to_thread``.
        """
        align_kb_embedding_to_milvus(kb)
        importer.rag_settings = rag_settings_from_kb(kb)
        importer._embedder = embedder_for_config(importer.rag_settings.embedding_config())

        chunk_cfg = importer.rag_settings.chunk_config()
        # Chunking (esp. pdfplumber-driven parsing above) is CPU-bound.
        children, parents = await asyncio.to_thread(
            chunk_text_with_parents, content, chunk_cfg, importer._embedder
        )
        if not children:
            return 0

        await replace_document_chunks(
            importer.db,
            document_id=doc.id,
            knowledge_base_id=doc.knowledge_base_id,
            chunks=children,
            parents=parents if any(parents) else None,
        )

        if not milvus_client._connected:
            # No vector store — keyword/hybrid retrieval still works via DB chunks.
            return len(children)

        embeddings = await importer._embedder.embed_documents(children)

        # pymilvus delete+insert+flush is synchronous blocking I/O; run off the
        # event loop so other requests stay responsive during indexing.
        milvus_client.delete_blocking(doc.id)
        chunk_count = await asyncio.to_thread(
            milvus_client.insert_blocking,
            doc.id,
            doc.knowledge_base_id,
            kb.user_id,
            children,
            embeddings,
        )
        return chunk_count

    async def _mark_status(self, doc_id: str, status: str) -> None:
        try:
            async with async_session_factory() as db:
                await db.execute(
                    update(Document).where(Document.id == doc_id).values(status=status)
                )
                await db.commit()
        except Exception:
            logger.exception("Failed to mark document {} as {}", doc_id, status)

    async def shutdown(self) -> None:
        """Cancel in-flight tasks. Pending documents are recovered on restart."""
        self._started = False
        for task in list(self._tasks):
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()


def start_index_runner(concurrency: int = _DEFAULT_CONCURRENCY) -> _IndexRunner:
    """Start the global index runner. Idempotent; called from app lifespan."""
    global _runner
    if _runner is None or not _runner.started():
        _runner = _IndexRunner(concurrency=concurrency)
        logger.info("Knowledge index runner started (concurrency={})", concurrency)
    return _runner


def get_index_runner() -> _IndexRunner:
    """Return the global runner, lazily creating one if needed."""
    global _runner
    if _runner is None:
        _runner = _IndexRunner()
    return _runner


async def stop_index_runner() -> None:
    """Cancel in-flight tasks and mark the runner stopped (app shutdown)."""
    global _runner
    if _runner is not None:
        await _runner.shutdown()
        _runner = None
        logger.info("Knowledge index runner stopped")


def enqueue_index_document(doc_id: str) -> None:
    """Public entry point: schedule background indexing for a document."""
    get_index_runner().enqueue(doc_id)


async def recover_stale_indexing() -> int:
    """Re-queue documents left in ``processing`` after a restart.

    ``asyncio.create_task`` tasks are lost on restart, so any document that was
    mid-index will be stuck in ``processing`` forever. Reset and re-enqueue.
    """
    async with async_session_factory() as db:
        result = await db.execute(
            select(Document.id).where(Document.status == "processing")
        )
        doc_ids = [row[0] for row in result.all()]
        if doc_ids:
            await db.execute(
                update(Document)
                .where(Document.id.in_(doc_ids))
                .values(status="pending")
            )
            await db.commit()

    for doc_id in doc_ids:
        enqueue_index_document(doc_id)
    if doc_ids:
        logger.info("Recovered {} stale indexing document(s)", len(doc_ids))
    return len(doc_ids)


__all__ = [
    "enqueue_index_document",
    "get_index_runner",
    "recover_stale_indexing",
    "start_index_runner",
    "stop_index_runner",
]
