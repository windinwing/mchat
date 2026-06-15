"""RAG configuration helpers for knowledge bases."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.core.config import settings
from app.knowledge.chunking import ChunkConfig, ChunkStrategy
from app.knowledge.tokenize import TokenizeConfig

RetrievalMode = Literal["vector", "keyword", "hybrid"]
KeywordBackend = Literal["local", "elasticsearch"]


class EmbeddingConfig(BaseModel):
    provider: str | None = None
    model: str | None = None
    api_base: str | None = None
    dimension: int | None = None

    def resolved_provider(self) -> str:
        return (self.provider or settings.embedding_provider).strip().lower()

    def resolved_model(self) -> str:
        return self.model or settings.embedding_model

    def resolved_api_base(self) -> str | None:
        base = (self.api_base or settings.embedding_api_base or "").strip()
        if base:
            return base.rstrip("/")
        if self.resolved_provider() == "ollama":
            return "http://localhost:11434"
        return None

    def resolved_dimension(self) -> int:
        return int(self.dimension or settings.embedding_dimension)


class RetrievalConfig(BaseModel):
    mode: RetrievalMode = "hybrid"
    top_k: int = Field(5, ge=1, le=50)
    candidate_k: int = Field(20, ge=5, le=100)
    rerank_enabled: bool = True
    rerank_top_n: int = Field(5, ge=1, le=20)
    vector_weight: float = Field(0.6, ge=0.0, le=1.0)
    keyword_weight: float = Field(0.4, ge=0.0, le=1.0)
    # BM25
    bm25_enabled: bool = True
    bm25_k1: float = Field(1.5, ge=0.5, le=3.0)
    bm25_b: float = Field(0.75, ge=0.0, le=1.0)
    # Reranker
    rerank_provider: str = "lexical"
    rerank_model: str | None = None
    # Query rewriting
    query_rewrite_enabled: bool = False
    query_rewrite_count: int = Field(3, ge=1, le=5)
    # Parent-child retrieval
    parent_enabled: bool = True
    # Keyword tokenization (per-KB; empty fields use built-in defaults)
    tokenize: TokenizeConfig = Field(default_factory=TokenizeConfig)
    keyword_backend: KeywordBackend = "local"


class KnowledgeBaseRagSettings(BaseModel):
    chunk_strategy: ChunkStrategy = "fixed"
    chunk_size: int = Field(500, ge=100, le=4000)
    chunk_overlap: int = Field(50, ge=0, le=500)
    chunk_min_size: int = Field(80, ge=20, le=500)
    chunk_semantic_threshold: float = 0.7
    chunk_parent_enabled: bool = True
    embedding_provider: str | None = None
    embedding_model: str | None = None
    embedding_api_base: str | None = None
    embedding_dimension: int = Field(default_factory=lambda: int(settings.embedding_dimension), ge=128, le=4096)
    retrieval_mode: RetrievalMode = "hybrid"
    retrieval_top_k: int = Field(5, ge=1, le=50)
    retrieval_candidate_k: int = Field(20, ge=5, le=100)
    rerank_enabled: bool = True
    rerank_top_n: int = Field(5, ge=1, le=20)
    retrieval_bm25_enabled: bool = True
    retrieval_bm25_k1: float = 1.5
    retrieval_bm25_b: float = 0.75
    rerank_provider: str = "lexical"
    rerank_model: str | None = None
    retrieval_query_rewrite_enabled: bool = False
    retrieval_query_rewrite_count: int = 3
    retrieval_stop_words: str | None = None
    retrieval_query_suffix_chars: str | None = None
    retrieval_user_dict: str | None = None
    retrieval_keyword_backend: str = "local"
    knowledge_base_id: str | None = None

    def chunk_config(self) -> ChunkConfig:
        return ChunkConfig(
            strategy=self.chunk_strategy,
            size=self.chunk_size,
            overlap=self.chunk_overlap,
            min_chunk_size=self.chunk_min_size,
            semantic_threshold=self.chunk_semantic_threshold,
            parent_max_ratio=3,
        ).normalized()

    def embedding_config(self) -> EmbeddingConfig:
        return EmbeddingConfig(
            provider=self.embedding_provider,
            model=self.embedding_model,
            api_base=self.embedding_api_base,
            dimension=self.embedding_dimension,
        )

    def _resolved_tokenize_config(self) -> TokenizeConfig:
        from app.knowledge.tokenizer_files import resolve_tokenizer_texts

        class _KbShim:
            id = self.knowledge_base_id
            retrieval_stop_words = self.retrieval_stop_words
            retrieval_query_suffix_chars = self.retrieval_query_suffix_chars
            retrieval_user_dict = self.retrieval_user_dict

        stop_words, suffix_chars, user_dict = resolve_tokenizer_texts(_KbShim)
        return TokenizeConfig.from_kb_fields(
            stop_words_text=stop_words,
            query_suffix_chars_text=suffix_chars,
            user_dict_text=user_dict,
        )

    def retrieval_config(self) -> RetrievalConfig:
        return RetrievalConfig(
            mode=self.retrieval_mode,
            top_k=self.retrieval_top_k,
            candidate_k=self.retrieval_candidate_k,
            rerank_enabled=self.rerank_enabled,
            rerank_top_n=self.rerank_top_n,
            bm25_enabled=self.retrieval_bm25_enabled,
            bm25_k1=self.retrieval_bm25_k1,
            bm25_b=self.retrieval_bm25_b,
            rerank_provider=self.rerank_provider,
            rerank_model=self.rerank_model,
            query_rewrite_enabled=self.retrieval_query_rewrite_enabled,
            query_rewrite_count=self.retrieval_query_rewrite_count,
            parent_enabled=self.chunk_parent_enabled,
            tokenize=self._resolved_tokenize_config(),
            keyword_backend=(
                "elasticsearch"
                if (self.retrieval_keyword_backend or "local").strip().lower()
                == "elasticsearch"
                else "local"
            ),
        )


def rag_settings_from_kb(kb: Any | None) -> KnowledgeBaseRagSettings:
    """Build RAG settings from a KnowledgeBase ORM row or None (defaults)."""
    if kb is None:
        return KnowledgeBaseRagSettings()

    return KnowledgeBaseRagSettings(
        chunk_strategy=getattr(kb, "chunk_strategy", None) or "fixed",
        chunk_size=int(getattr(kb, "chunk_size", None) or 500),
        chunk_overlap=int(getattr(kb, "chunk_overlap", None) or 50),
        chunk_min_size=int(getattr(kb, "chunk_min_size", None) or 80),
        chunk_semantic_threshold=float(getattr(kb, "chunk_semantic_threshold", None) or 0.7),
        chunk_parent_enabled=bool(getattr(kb, "chunk_parent_enabled", True)),
        embedding_provider=getattr(kb, "embedding_provider", None),
        embedding_model=getattr(kb, "embedding_model", None),
        embedding_api_base=getattr(kb, "embedding_api_base", None),
        embedding_dimension=int(
            getattr(kb, "embedding_dimension", None) or settings.embedding_dimension
        ),
        # Note: importer aligns KB row to Milvus before indexing
        retrieval_mode=getattr(kb, "retrieval_mode", None) or "hybrid",
        retrieval_top_k=int(getattr(kb, "retrieval_top_k", None) or 5),
        retrieval_candidate_k=int(getattr(kb, "retrieval_candidate_k", None) or 20),
        rerank_enabled=bool(getattr(kb, "rerank_enabled", True)),
        rerank_top_n=int(getattr(kb, "rerank_top_n", None) or 5),
        retrieval_bm25_enabled=bool(getattr(kb, "retrieval_bm25_enabled", True)),
        retrieval_bm25_k1=float(getattr(kb, "retrieval_bm25_k1", None) or 1.5),
        retrieval_bm25_b=float(getattr(kb, "retrieval_bm25_b", None) or 0.75),
        rerank_provider=getattr(kb, "rerank_provider", None) or "lexical",
        rerank_model=getattr(kb, "rerank_model", None),
        retrieval_query_rewrite_enabled=bool(getattr(kb, "retrieval_query_rewrite_enabled", False)),
        retrieval_query_rewrite_count=int(getattr(kb, "retrieval_query_rewrite_count", None) or 3),
        retrieval_stop_words=getattr(kb, "retrieval_stop_words", None),
        retrieval_query_suffix_chars=getattr(kb, "retrieval_query_suffix_chars", None),
        retrieval_user_dict=getattr(kb, "retrieval_user_dict", None),
        retrieval_keyword_backend=getattr(kb, "retrieval_keyword_backend", None) or "local",
        knowledge_base_id=str(getattr(kb, "id", "") or "") or None,
    )
