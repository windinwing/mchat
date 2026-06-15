"""Persist document chunks for keyword / hybrid retrieval."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import DocumentChunk


def _invalidate_bm25(knowledge_base_id: str) -> None:
    try:
        from app.knowledge.bm25 import bm25_index
        bm25_index.invalidate(knowledge_base_id)
    except Exception:
        pass


async def replace_document_chunks(
    db: AsyncSession,
    *,
    document_id: str,
    knowledge_base_id: str,
    chunks: list[str],
    parents: list[str | None] | None = None,
) -> int:
    """Replace all chunks for a document. Optional parent_content per chunk."""
    await db.execute(
        delete(DocumentChunk).where(DocumentChunk.document_id == document_id)
    )
    for index, content in enumerate(chunks):
        parent_content = parents[index] if parents and index < len(parents) else None
        db.add(
            DocumentChunk(
                id=str(uuid.uuid4()),
                document_id=document_id,
                knowledge_base_id=knowledge_base_id,
                chunk_index=index,
                content=content,
                parent_content=parent_content,
                chunk_type="child",
            )
        )
    await db.flush()
    _invalidate_bm25(knowledge_base_id)
    from app.knowledge.es_sync import sync_document_chunks_to_es

    await sync_document_chunks_to_es(
        db,
        document_id=document_id,
        knowledge_base_id=knowledge_base_id,
    )
    return len(chunks)


async def delete_document_chunks(db: AsyncSession, document_id: str) -> None:
    # Look up kb_id before deleting for BM25 invalidation
    result = await db.execute(
        select(DocumentChunk.knowledge_base_id).where(
            DocumentChunk.document_id == document_id
        ).limit(1)
    )
    kb_id = result.scalar_one_or_none()

    await db.execute(
        delete(DocumentChunk).where(DocumentChunk.document_id == document_id)
    )
    await db.flush()

    if kb_id:
        _invalidate_bm25(kb_id)

    from app.knowledge.es_sync import delete_document_from_es

    await delete_document_from_es(
        db,
        document_id=document_id,
        knowledge_base_id=kb_id,
    )


async def load_document_chunks(
    db: AsyncSession, document_id: str
) -> list[str]:
    """Load chunk texts ordered by index."""
    result = await db.execute(
        select(DocumentChunk)
        .where(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.chunk_index.asc())
    )
    rows = result.scalars().all()
    return [row.content for row in rows if row.content]
