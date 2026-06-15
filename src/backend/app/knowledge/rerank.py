"""Rerank retrieved chunks by query relevance."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Literal

from loguru import logger

RerankProvider = Literal["none", "lexical", "cohere", "bge", "cross-encoder"]


@dataclass
class RankedChunk:
    document_id: str
    knowledge_base_id: str
    chunk_index: int
    content: str
    title: str
    vector_score: float = 0.0
    keyword_score: float = 0.0
    fused_score: float = 0.0
    rerank_score: float = 0.0

    @property
    def final_score(self) -> float:
        return self.rerank_score if self.rerank_score else self.fused_score


def reciprocal_rank_fusion(
    ranked_lists: list[list[RankedChunk]],
    k: int = 60,
) -> list[RankedChunk]:
    """Merge multiple ranked lists with RRF."""
    scores: dict[str, RankedChunk] = {}
    rrf: dict[str, float] = {}

    for results in ranked_lists:
        for rank, item in enumerate(results, start=1):
            key = _chunk_key(item)
            rrf[key] = rrf.get(key, 0.0) + 1.0 / (k + rank)
            if key not in scores:
                scores[key] = item

    merged = []
    for key, score in sorted(rrf.items(), key=lambda x: x[1], reverse=True):
        item = scores[key]
        item.fused_score = score
        merged.append(item)
    return merged


def _chunk_key(item: RankedChunk) -> str:
    return f"{item.document_id}:{item.chunk_index}"


def _tokenize(text: str, config=None) -> set[str]:
    from app.knowledge.tokenize import TokenizeConfig, tokenize_for_search

    return tokenize_for_search(text, config or TokenizeConfig())


def _lexical_score(terms: set[str], content: str) -> float:
    if not terms or not content:
        return 0.0
    content_lower = content.lower()
    hits = sum(1 for t in terms if t in content_lower)
    idf_boost = sum(math.log(1 + content_lower.count(t)) for t in terms if t in content_lower)
    return min(1.0, (hits / len(terms)) * 0.7 + (idf_boost / (len(terms) * 3)) * 0.3)


def _lexical_rerank(query: str, chunks: list[RankedChunk], top_n: int) -> list[RankedChunk]:
    """Lightweight reranker: blend fused score with lexical overlap."""
    if not chunks:
        return []

    terms = _tokenize(query)
    if not terms:
        return chunks[:top_n]

    max_fused = max((c.fused_score for c in chunks), default=1.0) or 1.0

    for chunk in chunks:
        overlap = _lexical_score(terms, chunk.content)
        norm_fused = chunk.fused_score / max_fused if max_fused else 0.0
        chunk.rerank_score = 0.65 * norm_fused + 0.35 * overlap

    chunks.sort(key=lambda c: c.rerank_score, reverse=True)
    return chunks[:top_n]


async def _cohere_rerank(
    query: str, chunks: list[RankedChunk], top_n: int, model: str | None, api_key: str
) -> list[RankedChunk]:
    import httpx

    documents = [c.content for c in chunks]
    payload = {
        "query": query,
        "documents": documents,
        "top_n": top_n,
        "return_documents": False,
    }
    if model:
        payload["model"] = model

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            "https://api.cohere.com/v1/rerank",
            json=payload,
            headers={"Authorization": f"Bearer {api_key}"},
        )
        resp.raise_for_status()
        data = resp.json()

    scores: dict[int, float] = {}
    for item in data.get("results", []):
        scores[item["index"]] = item.get("relevance_score", 0.0)

    for i, chunk in enumerate(chunks):
        chunk.rerank_score = scores.get(i, 0.0)

    chunks.sort(key=lambda c: c.rerank_score, reverse=True)
    return chunks[:top_n]


_ce_models: dict[str, object] = {}


def _get_cross_encoder(model_name: str) -> object:
    if model_name not in _ce_models:
        from sentence_transformers import CrossEncoder
        _ce_models[model_name] = CrossEncoder(model_name)
    return _ce_models[model_name]


async def _cross_encoder_rerank(
    query: str, chunks: list[RankedChunk], top_n: int, model: str
) -> list[RankedChunk]:
    import asyncio

    ce = _get_cross_encoder(model)
    pairs = [(query, c.content) for c in chunks]
    scores = await asyncio.to_thread(ce.predict, pairs, show_progress_bar=False)

    for i, chunk in enumerate(chunks):
        chunk.rerank_score = float(scores[i]) if i < len(scores) else 0.0

    chunks.sort(key=lambda c: c.rerank_score, reverse=True)
    return chunks[:top_n]


async def rerank_chunks(
    query: str,
    chunks: list[RankedChunk],
    top_n: int,
    provider: RerankProvider = "lexical",
    model: str | None = None,
    api_key: str | None = None,
) -> list[RankedChunk]:
    """Rerank chunks. Provider: none, lexical, cohere, bge, cross-encoder."""
    if not chunks or provider == "none":
        return chunks[:top_n]

    if provider == "cohere":
        if not api_key:
            logger.warning("Cohere reranker requested but no API key configured, falling back to lexical")
            return _lexical_rerank(query, chunks, top_n)
        try:
            return await _cohere_rerank(query, chunks, top_n, model, api_key)
        except Exception as e:
            logger.warning(f"Cohere rerank failed, falling back to lexical: {e}")
            return _lexical_rerank(query, chunks, top_n)

    if provider in ("bge", "cross-encoder"):
        if not model:
            logger.warning(f"{provider} reranker requested but no model configured, falling back to lexical")
            return _lexical_rerank(query, chunks, top_n)
        try:
            return await _cross_encoder_rerank(query, chunks, top_n, model)
        except Exception as e:
            logger.warning(f"{provider} rerank failed, falling back to lexical: {e}")
            return _lexical_rerank(query, chunks, top_n)

    # lexical (default)
    return _lexical_rerank(query, chunks, top_n)
