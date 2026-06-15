"""RAG service - retrieve and augment prompts with knowledge."""

from __future__ import annotations

from loguru import logger
from sqlalchemy import select

from app.knowledge.embedder import embedder_for_config
from app.knowledge.milvus_client import milvus_client
from app.knowledge.rag_config import (
    KnowledgeBaseRagSettings,
    rag_settings_from_kb,
)
from app.knowledge.rerank import RankedChunk, reciprocal_rank_fusion, rerank_chunks
from app.schemas.knowledge import SearchResponse, SearchResult


class RagService:
    """Retrieval-Augmented Generation service."""

    def __init__(self, rag_settings: KnowledgeBaseRagSettings | None = None) -> None:
        self.rag_settings = rag_settings or KnowledgeBaseRagSettings()

    async def _load_kb(self, knowledge_base_id: str | None):
        if not knowledge_base_id:
            return None
        try:
            from app.core.database import async_session_factory
            from app.models.knowledge import KnowledgeBase

            async with async_session_factory() as db:
                result = await db.execute(
                    select(KnowledgeBase).where(KnowledgeBase.id == knowledge_base_id)
                )
                return result.scalar_one_or_none()
        except Exception as e:
            logger.warning(f"Failed to load knowledge base {knowledge_base_id}: {e}")
            return None

    async def _resolve_settings(
        self, knowledge_base_id: str | None
    ) -> KnowledgeBaseRagSettings:
        if knowledge_base_id:
            kb = await self._load_kb(knowledge_base_id)
            if kb is not None:
                return rag_settings_from_kb(kb)
        if self.rag_settings:
            return self.rag_settings
        return KnowledgeBaseRagSettings()

    async def _load_document_titles(self, document_ids: list[str]) -> dict[str, str]:
        unique_ids = [
            document_id
            for document_id in {doc_id for doc_id in document_ids if doc_id}
        ]
        if not unique_ids:
            return {}

        try:
            from app.core.database import async_session_factory
            from app.models.knowledge import Document

            async with async_session_factory() as db:
                rows = await db.execute(
                    select(Document.id, Document.title).where(
                        Document.id.in_(unique_ids)
                    )
                )
                return {
                    document_id: title
                    for document_id, title in rows.all()
                    if document_id and title
                }
        except Exception as e:
            logger.warning(f"Failed to load document titles for RAG hits: {e}")
            return {}

    async def search(
        self,
        query: str,
        user_id: str | None = None,
        knowledge_base_id: str | None = None,
        top_k: int | None = None,
        chat_fn=None,
        *,
        conversation_id: str | None = None,
        log_source: str = "admin",
    ) -> SearchResponse:
        from app.services.retrieval_log_service import RetrievalTimer

        settings = await self._resolve_settings(knowledge_base_id)
        retrieval = settings.retrieval_config()
        final_k = top_k or retrieval.top_k
        candidate_k = max(retrieval.candidate_k, final_k)
        timer = RetrievalTimer()
        logged_hits: list[RankedChunk] = []
        query_variants = 1

        try:
            # Generate query variants if rewriting enabled
            queries = [query]
            if retrieval.query_rewrite_enabled and chat_fn is not None:
                from app.knowledge.query_rewriter import QueryRewriter
                rewriter = QueryRewriter(chat_fn=chat_fn)
                queries = await rewriter.rewrite(query, retrieval.query_rewrite_count)
            query_variants = len(queries)

            # Multi-recall: search for each query variant
            all_results: list[list[RankedChunk]] = []
            for q in queries:
                q_results = await self._search_single(
                    q, user_id, knowledge_base_id, settings,
                    candidate_k=candidate_k, final_k=final_k,
                )
                if q_results:
                    all_results.append(q_results)

            if not all_results:
                await self._maybe_log_retrieval(
                    query=query,
                    knowledge_base_id=knowledge_base_id,
                    user_id=user_id,
                    conversation_id=conversation_id,
                    source=log_source,
                    retrieval_mode=settings.retrieval_mode,
                    hits=[],
                    query_variant_count=query_variants,
                    duration_ms=timer.elapsed_ms,
                )
                return SearchResponse(results=[], total=0)

            # Merge multi-query results via RRF
            if len(all_results) > 1:
                results = reciprocal_rank_fusion(all_results)
            else:
                results = all_results[0]

            # Enrich with parent context if enabled
            if retrieval.parent_enabled and results:
                results = await self._enrich_with_parent_context(results)

            if retrieval.rerank_enabled and results:
                from app.core.config import settings as global_settings
                provider = retrieval.rerank_provider or global_settings.rerank_provider or "lexical"
                model = retrieval.rerank_model or global_settings.rerank_model or None
                api_key = global_settings.cohere_api_key or None
                # Rerank against original query for relevance
                results = await rerank_chunks(
                    query, results, retrieval.rerank_top_n,
                    provider=provider,
                    model=model,
                    api_key=api_key,
                )

            logged_hits = results[:final_k]
            response = self._to_response(logged_hits, settings)
            await self._maybe_log_retrieval(
                query=query,
                knowledge_base_id=knowledge_base_id,
                user_id=user_id,
                conversation_id=conversation_id,
                source=log_source,
                retrieval_mode=settings.retrieval_mode,
                hits=logged_hits,
                query_variant_count=query_variants,
                duration_ms=timer.elapsed_ms,
            )
            return response
        except Exception as e:
            logger.error(f"RAG search failed: {e}")
            await self._maybe_log_retrieval(
                query=query,
                knowledge_base_id=knowledge_base_id,
                user_id=user_id,
                conversation_id=conversation_id,
                source=log_source,
                retrieval_mode=settings.retrieval_mode,
                hits=logged_hits,
                query_variant_count=query_variants,
                duration_ms=timer.elapsed_ms,
            )
            return SearchResponse(results=[], total=0)

    async def _maybe_log_retrieval(
        self,
        *,
        query: str,
        knowledge_base_id: str | None,
        user_id: str | None,
        conversation_id: str | None,
        source: str,
        retrieval_mode: str,
        hits: list[RankedChunk],
        query_variant_count: int,
        duration_ms: int,
    ) -> None:
        try:
            from app.core.database import async_session_factory
            from app.services.retrieval_log_service import RetrievalLogService

            async with async_session_factory() as db:
                await RetrievalLogService(db).record(
                    query=query,
                    knowledge_base_id=knowledge_base_id,
                    user_id=user_id,
                    conversation_id=conversation_id,
                    source=source,
                    retrieval_mode=retrieval_mode,
                    hit_count=len(hits),
                    duration_ms=duration_ms,
                    hits=hits,
                    query_variant_count=query_variant_count,
                )
                await db.commit()
        except Exception as exc:
            logger.debug("Retrieval log skipped: {}", exc)

    async def _search_single(
        self,
        query: str,
        user_id: str | None,
        knowledge_base_id: str | None,
        settings: KnowledgeBaseRagSettings,
        *,
        candidate_k: int,
        final_k: int,
    ) -> list[RankedChunk]:
        """Run a single query through the retrieval pipeline (no rerank)."""
        retrieval = settings.retrieval_config()
        mode = retrieval.mode
        top_k = candidate_k if retrieval.rerank_enabled else final_k

        if mode == "keyword" or not milvus_client._connected:
            return await self._keyword_chunk_search(
                query=query,
                user_id=user_id,
                knowledge_base_id=knowledge_base_id,
                top_k=top_k,
                settings=settings,
            )
        elif mode == "vector":
            if not milvus_client._connected:
                return []
            return await self._vector_search(
                query=query,
                user_id=user_id,
                knowledge_base_id=knowledge_base_id,
                settings=settings,
                top_k=top_k,
            )
        else:
            if not milvus_client._connected:
                return await self._keyword_chunk_search(
                    query=query,
                    user_id=user_id,
                    knowledge_base_id=knowledge_base_id,
                    top_k=top_k,
                    settings=settings,
                )
            vector_hits = await self._vector_search(
                query=query,
                user_id=user_id,
                knowledge_base_id=knowledge_base_id,
                settings=settings,
                top_k=candidate_k,
            )
            keyword_hits = await self._keyword_chunk_search(
                query=query,
                user_id=user_id,
                knowledge_base_id=knowledge_base_id,
                top_k=candidate_k,
                settings=settings,
            )
            if keyword_hits and vector_hits:
                return reciprocal_rank_fusion([vector_hits, keyword_hits])
            if keyword_hits:
                return keyword_hits
            if vector_hits:
                return self._prioritize_vector_lexical_overlap(
                    query,
                    vector_hits,
                    retrieval.tokenize,
                    top_k,
                )
            return []

    async def _vector_search(
        self,
        query: str,
        user_id: str | None,
        knowledge_base_id: str | None,
        settings: KnowledgeBaseRagSettings,
        top_k: int,
    ) -> list[RankedChunk]:
        if not milvus_client._connected:
            return []

        embedder = embedder_for_config(settings.embedding_config())
        if not embedder.is_configured():
            return []
        query_embedding = await embedder.embed_query(query)
        hits = await milvus_client.search(
            query_embedding=query_embedding,
            top_k=top_k,
            user_id=user_id,
            kb_id=knowledge_base_id,
        )
        titles = await self._load_document_titles(
            [str(hit.get("document_id") or "") for hit in hits]
        )

        ranked: list[RankedChunk] = []
        for hit in hits:
            document_id = str(hit.get("document_id") or "")
            ranked.append(
                RankedChunk(
                    document_id=document_id,
                    knowledge_base_id=str(hit.get("kb_id") or knowledge_base_id or ""),
                    chunk_index=int(hit.get("chunk_index") or 0),
                    content=str(hit.get("content") or ""),
                    title=titles.get(document_id) or f"Chunk {hit.get('chunk_index', 0)}",
                    vector_score=float(hit.get("distance") or 0),
                    fused_score=float(hit.get("distance") or 0),
                )
            )
        return ranked

    @staticmethod
    def _prioritize_vector_lexical_overlap(
        query: str,
        vector_hits: list[RankedChunk],
        tokenize_config,
        top_k: int,
    ) -> list[RankedChunk]:
        """When keyword leg misses, prefer vector hits that still contain query terms."""
        from app.knowledge.tokenize import TokenizeConfig, tokenize_for_search

        terms = tokenize_for_search(query, tokenize_config or TokenizeConfig())
        if not terms:
            return vector_hits[:top_k]

        def overlap_score(chunk: RankedChunk) -> tuple[int, float]:
            content_lower = (chunk.content or "").lower()
            hits = sum(1 for term in terms if term in content_lower)
            return (hits, chunk.vector_score)

        ranked = sorted(vector_hits, key=overlap_score, reverse=True)
        return ranked[:top_k]

    async def _keyword_chunk_search(
        self,
        query: str,
        user_id: str | None,
        knowledge_base_id: str | None,
        top_k: int,
        settings: KnowledgeBaseRagSettings | None = None,
    ) -> list[RankedChunk]:
        if not knowledge_base_id:
            return await self._keyword_chunk_search_naive(
                query, user_id, knowledge_base_id, top_k, settings=settings
            )

        retrieval = (settings or self.rag_settings).retrieval_config()

        if retrieval.keyword_backend == "elasticsearch":
            from app.knowledge.es_client import es_knowledge_client

            if es_knowledge_client.connected:
                ranked = await self._es_search(
                    query, knowledge_base_id, top_k, retrieval
                )
                if ranked:
                    return ranked
                logger.warning(
                    "Elasticsearch keyword search empty for kb=%s, falling back to local",
                    knowledge_base_id,
                )

        if retrieval.bm25_enabled:
            return await self._bm25_search(
                query, user_id, knowledge_base_id, top_k, retrieval
            )

        return await self._keyword_chunk_search_naive(
            query, user_id, knowledge_base_id, top_k, tokenize_config=retrieval.tokenize
        )

    async def _es_search(
        self,
        query: str,
        knowledge_base_id: str,
        top_k: int,
        retrieval,
    ) -> list[RankedChunk]:
        from app.core.database import async_session_factory
        from app.knowledge.es_client import es_knowledge_client
        from app.models.knowledge import Document, DocumentChunk

        try:
            scored = await es_knowledge_client.search(
                query=query,
                knowledge_base_id=knowledge_base_id,
                top_k=top_k,
                tokenize_config=retrieval.tokenize,
            )
            if not scored:
                return []

            async with async_session_factory() as db:
                return await self._ranked_chunks_from_scored_ids(db, scored)
        except Exception as exc:
            logger.warning(f"Elasticsearch search failed, falling back to local: {exc}")
            return []

    async def _ranked_chunks_from_scored_ids(
        self,
        db,
        scored: list[tuple[float, str]],
    ) -> list[RankedChunk]:
        from app.models.knowledge import Document, DocumentChunk

        chunk_ids = [cid for _, cid in scored]
        score_map = {cid: s for s, cid in scored}
        stmt = (
            select(DocumentChunk, Document.title)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(DocumentChunk.id.in_(chunk_ids))
        )
        rows = await db.execute(stmt)
        chunk_map: dict[str, DocumentChunk] = {}
        titles: dict[str, str] = {}
        for chunk_row, title in rows.all():
            chunk_map[chunk_row.id] = chunk_row
            titles[chunk_row.id] = title

        ranked: list[RankedChunk] = []
        for _, chunk_id in scored:
            chunk_row = chunk_map.get(chunk_id)
            if chunk_row is None:
                continue
            score = score_map.get(chunk_id, 0.0)
            ranked.append(
                RankedChunk(
                    document_id=chunk_row.document_id,
                    knowledge_base_id=chunk_row.knowledge_base_id,
                    chunk_index=chunk_row.chunk_index,
                    content=chunk_row.content,
                    title=titles.get(chunk_id) or "Untitled",
                    keyword_score=score,
                    fused_score=score,
                )
            )
        return ranked

    async def _bm25_search(
        self,
        query: str,
        user_id: str | None,
        knowledge_base_id: str,
        top_k: int,
        retrieval,
    ) -> list[RankedChunk]:
        from app.core.database import async_session_factory
        from app.knowledge.bm25 import bm25_index as _bm25

        try:
            async with async_session_factory() as db:
                scored = await _bm25.search(
                    db,
                    query=query,
                    kb_id=knowledge_base_id,
                    top_k=top_k,
                    k1=retrieval.bm25_k1,
                    b=retrieval.bm25_b,
                    tokenize_config=retrieval.tokenize,
                )
                if not scored:
                    return []

                return await self._ranked_chunks_from_scored_ids(db, scored)
        except Exception as e:
            logger.warning(f"BM25 search failed, falling back to naive: {e}")
            return await self._keyword_chunk_search_naive(
                query, user_id, knowledge_base_id, top_k
            )

    async def _keyword_chunk_search_naive(
        self,
        query: str,
        user_id: str | None,
        knowledge_base_id: str | None,
        top_k: int,
        *,
        tokenize_config=None,
    ) -> list[RankedChunk]:
        from app.core.database import async_session_factory
        from app.models.knowledge import Document, DocumentChunk, KnowledgeBase
        from app.knowledge.tokenize import TokenizeConfig, tokenize_for_search

        query_terms = tokenize_for_search(query, tokenize_config or TokenizeConfig())

        try:
            async with async_session_factory() as db:
                stmt = (
                    select(
                        DocumentChunk,
                        Document.title,
                    )
                    .join(Document, Document.id == DocumentChunk.document_id)
                    .join(KnowledgeBase, KnowledgeBase.id == Document.knowledge_base_id)
                    .where(Document.status == "indexed")
                )
                if knowledge_base_id:
                    stmt = stmt.where(
                        DocumentChunk.knowledge_base_id == knowledge_base_id
                    )
                if user_id:
                    stmt = stmt.where(KnowledgeBase.user_id == user_id)

                rows = await db.execute(stmt.limit(2500))
                scored: list[tuple[float, RankedChunk]] = []

                for chunk_row, title in rows.all():
                    content_lower = (chunk_row.content or "").lower()
                    hits = sum(1 for t in query_terms if t in content_lower)
                    if hits == 0:
                        continue
                    score = hits / max(len(query_terms), 1)
                    scored.append(
                        (
                            score,
                            RankedChunk(
                                document_id=chunk_row.document_id,
                                knowledge_base_id=chunk_row.knowledge_base_id,
                                chunk_index=chunk_row.chunk_index,
                                content=chunk_row.content,
                                title=title or "Untitled",
                                keyword_score=score,
                                fused_score=score,
                            ),
                        )
                    )

                scored.sort(key=lambda x: x[0], reverse=True)
                return [item for _, item in scored[:top_k]]
        except Exception as e:
            logger.error(f"Keyword chunk search failed: {e}")
            return await self._legacy_document_keyword_search(
                query, user_id, knowledge_base_id, top_k
            )

    async def _legacy_document_keyword_search(
        self,
        query: str,
        user_id: str | None,
        knowledge_base_id: str | None,
        top_k: int,
    ) -> list[RankedChunk]:
        """Fallback when document_chunks table is empty."""
        from app.core.database import async_session_factory
        from app.models.knowledge import Document, KnowledgeBase

        from app.knowledge.tokenize import TokenizeConfig, tokenize_for_search

        query_terms = tokenize_for_search(query, TokenizeConfig())
        if not query_terms:
            return []
        try:
            async with async_session_factory() as db:
                stmt = select(Document).where(Document.status == "indexed")
                if knowledge_base_id:
                    stmt = stmt.where(
                        Document.knowledge_base_id == knowledge_base_id
                    )
                if user_id:
                    stmt = (
                        select(Document)
                        .join(KnowledgeBase)
                        .where(
                            Document.status == "indexed",
                            KnowledgeBase.user_id == user_id,
                        )
                    )
                    if knowledge_base_id:
                        stmt = stmt.where(
                            Document.knowledge_base_id == knowledge_base_id
                        )

                result = await db.execute(stmt)
                docs = result.scalars().all()
                ranked: list[RankedChunk] = []
                for doc in docs:
                    content_lower = (doc.content or "").lower()
                    hits = sum(
                        1
                        for t in query_terms
                        if t in content_lower
                        or t in (doc.title or "").lower()
                    )
                    if hits > 0:
                        score = hits / max(len(query_terms), 1)
                        ranked.append(
                            RankedChunk(
                                document_id=doc.id,
                                knowledge_base_id=doc.knowledge_base_id,
                                chunk_index=0,
                                content=doc.content or "",
                                title=doc.title or "Untitled",
                                keyword_score=score,
                                fused_score=score,
                            )
                        )
                ranked.sort(key=lambda c: c.keyword_score, reverse=True)
                return ranked[:top_k]
        except Exception as e:
            logger.error(f"Legacy keyword search failed: {e}")
            return []

    async def _enrich_with_parent_context(
        self, chunks: list[RankedChunk]
    ) -> list[RankedChunk]:
        """Replace child chunk content with parent context where available."""
        if not chunks:
            return chunks

        try:
            from app.core.database import async_session_factory
            from app.models.knowledge import DocumentChunk
            from sqlalchemy import and_, or_

            async with async_session_factory() as db:
                conditions = [
                    and_(
                        DocumentChunk.document_id == c.document_id,
                        DocumentChunk.chunk_index == c.chunk_index,
                    )
                    for c in chunks
                ]
                if not conditions:
                    return chunks

                result = await db.execute(
                    select(
                        DocumentChunk.document_id,
                        DocumentChunk.chunk_index,
                        DocumentChunk.parent_content,
                    ).where(or_(*conditions))
                )
                parent_map: dict[tuple[str, int], str] = {}
                for doc_id, idx, parent in result.all():
                    if parent:
                        parent_map[(doc_id, idx)] = parent

                enriched = []
                for c in chunks:
                    key = (c.document_id, c.chunk_index)
                    if key in parent_map:
                        enriched.append(
                            RankedChunk(
                                document_id=c.document_id,
                                knowledge_base_id=c.knowledge_base_id,
                                chunk_index=c.chunk_index,
                                content=parent_map[key],
                                title=c.title,
                                vector_score=c.vector_score,
                                keyword_score=c.keyword_score,
                                fused_score=c.fused_score,
                                rerank_score=c.rerank_score,
                            )
                        )
                    else:
                        enriched.append(c)
                return enriched
        except Exception as e:
            logger.warning(f"Parent context enrichment failed: {e}")
            return chunks

    def _to_response(
        self, chunks: list[RankedChunk], settings: KnowledgeBaseRagSettings
    ) -> SearchResponse:
        results = [
            SearchResult(
                document_id=c.document_id,
                title=c.title,
                content=c.content,
                score=round(c.final_score, 4),
                knowledge_base_id=c.knowledge_base_id,
                chunk_index=c.chunk_index,
                retrieval_mode=settings.retrieval_mode,
            )
            for c in chunks
        ]
        return SearchResponse(results=results, total=len(results))

    async def augment_prompt(
        self,
        query: str,
        user_id: str | None = None,
        knowledge_base_id: str | None = None,
    ) -> str | None:
        search_results = await self.search(
            query=query,
            user_id=user_id,
            knowledge_base_id=knowledge_base_id,
            top_k=3,
        )

        if not search_results.results:
            return None

        context_parts = []
        for r in search_results.results:
            context_parts.append(
                f"[Source: {r.title}] (relevance: {r.score:.2f})\n{r.content}"
            )

        return "\n\n".join(context_parts)
