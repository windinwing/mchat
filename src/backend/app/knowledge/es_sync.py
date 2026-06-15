"""Sync knowledge chunks to optional Elasticsearch index."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import Document, DocumentChunk, KnowledgeBase


async def sync_document_chunks_to_es(
    db: AsyncSession,
    *,
    document_id: str,
    knowledge_base_id: str,
) -> None:
    from app.knowledge.es_client import es_knowledge_client

    if not es_knowledge_client.connected:
        return

    kb = await db.get(KnowledgeBase, knowledge_base_id)
    if kb is None or (kb.retrieval_keyword_backend or "local") != "elasticsearch":
        return

    doc = await db.get(Document, document_id)
    if doc is None:
        return

    result = await db.execute(
        select(DocumentChunk)
        .where(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.chunk_index.asc())
    )
    rows = result.scalars().all()
    await es_knowledge_client.sync_document(
        knowledge_base_id=knowledge_base_id,
        document_id=document_id,
        title=doc.title or "Untitled",
        chunks=[
            {
                "chunk_id": row.id,
                "chunk_index": row.chunk_index,
                "content": row.content or "",
            }
            for row in rows
        ],
    )


async def delete_document_from_es(
    db: AsyncSession,
    *,
    document_id: str,
    knowledge_base_id: str | None = None,
) -> None:
    from app.knowledge.es_client import es_knowledge_client

    if not es_knowledge_client.connected:
        return

    kb_id = knowledge_base_id
    if kb_id is None:
        result = await db.execute(
            select(DocumentChunk.knowledge_base_id)
            .where(DocumentChunk.document_id == document_id)
            .limit(1)
        )
        kb_id = result.scalar_one_or_none()

    if kb_id:
        kb = await db.get(KnowledgeBase, kb_id)
        if kb is None or (kb.retrieval_keyword_backend or "local") != "elasticsearch":
            return

    await es_knowledge_client.delete_document(document_id=document_id)
