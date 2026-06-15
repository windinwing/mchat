"""Knowledge management Pydantic schemas."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.core.config import settings

ChunkStrategy = Literal["fixed", "paragraph", "markdown"]
RetrievalMode = Literal["vector", "keyword", "hybrid"]


class KnowledgeBaseRagFields(BaseModel):
    """RAG configuration fields for a knowledge base."""

    chunk_strategy: ChunkStrategy = "fixed"
    chunk_size: int = Field(500, ge=100, le=4000)
    chunk_overlap: int = Field(50, ge=0, le=500)
    chunk_min_size: int = Field(80, ge=20, le=500)
    chunk_semantic_threshold: float = 0.7
    chunk_parent_enabled: bool = True
    embedding_provider: str | None = None
    embedding_model: str | None = None
    embedding_api_base: str | None = None
    embedding_dimension: int | None = Field(None, ge=128, le=4096)
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


class KnowledgeBaseCreate(KnowledgeBaseRagFields):
    """Request body for creating a knowledge base."""
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    enabled: bool = True
    group_id: str | None = None

    @model_validator(mode="after")
    def _default_embedding_from_settings(self) -> "KnowledgeBaseCreate":
        if self.embedding_dimension is None:
            object.__setattr__(
                self, "embedding_dimension", int(settings.embedding_dimension)
            )
        if self.embedding_provider is None:
            object.__setattr__(self, "embedding_provider", settings.embedding_provider)
        if self.embedding_model is None:
            object.__setattr__(self, "embedding_model", settings.embedding_model)
        if self.embedding_api_base is None and settings.embedding_api_base:
            object.__setattr__(self, "embedding_api_base", settings.embedding_api_base)
        return self


class KnowledgeBaseUpdate(BaseModel):
    """Partial update for knowledge base settings."""

    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    enabled: bool | None = None
    group_id: str | None = None
    chunk_strategy: ChunkStrategy | None = None
    chunk_size: int | None = Field(None, ge=100, le=4000)
    chunk_overlap: int | None = Field(None, ge=0, le=500)
    chunk_min_size: int | None = Field(None, ge=20, le=500)
    chunk_semantic_threshold: float | None = None
    chunk_parent_enabled: bool | None = None
    embedding_provider: str | None = None
    embedding_model: str | None = None
    embedding_api_base: str | None = None
    embedding_dimension: int | None = Field(None, ge=128, le=4096)
    retrieval_mode: RetrievalMode | None = None
    retrieval_top_k: int | None = Field(None, ge=1, le=50)
    retrieval_candidate_k: int | None = Field(None, ge=5, le=100)
    rerank_enabled: bool | None = None
    rerank_top_n: int | None = Field(None, ge=1, le=20)
    retrieval_bm25_enabled: bool | None = None
    retrieval_bm25_k1: float | None = None
    retrieval_bm25_b: float | None = None
    rerank_provider: str | None = None
    rerank_model: str | None = None
    retrieval_query_rewrite_enabled: bool | None = None
    retrieval_query_rewrite_count: int | None = None
    retrieval_stop_words: str | None = None
    retrieval_query_suffix_chars: str | None = Field(None, max_length=200)
    retrieval_user_dict: str | None = None
    retrieval_keyword_backend: str | None = None


class KnowledgeBaseResponse(KnowledgeBaseRagFields):
    """Knowledge base response schema."""
    id: str
    user_id: str
    group_id: str | None = None
    name: str
    description: str | None = None
    enabled: bool
    document_count: int = 0
    indexed_embedding_key: str | None = None
    needs_reindex: bool = False
    reindex_status: str = "idle"
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ReindexRequest(BaseModel):
    """Options for full knowledge base re-embedding."""

    rechunk: bool = Field(
        True,
        description="Re-split documents with current chunk settings; if false, reuse stored chunks",
    )


class DocumentReindexResult(BaseModel):
    document_id: str
    title: str
    status: str
    chunk_count: int = 0
    error: str | None = None


class ReindexResponse(BaseModel):
    knowledge_base_id: str
    total: int
    succeeded: int
    failed: int
    rechunk: bool
    milvus_enabled: bool
    indexed_embedding_key: str | None = None
    documents: list[DocumentReindexResult] = Field(default_factory=list)


class DocumentListItem(BaseModel):
    """Document summary for list/upload responses (no full content)."""
    id: str
    knowledge_base_id: str
    title: str
    source: str | None = None
    status: str
    chunk_count: int
    file_size: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentCreate(BaseModel):
    """Request body for creating a document."""
    title: str = Field(..., min_length=1, max_length=500)
    content: str = Field(..., min_length=1)
    source: str | None = None
    source_url: str | None = None


class DocumentResponse(BaseModel):
    """Document response schema."""
    id: str
    knowledge_base_id: str
    title: str
    content: str
    source: str | None = None
    source_url: str | None = None
    status: str
    chunk_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SearchRequest(BaseModel):
    """Search query request."""
    query: str = Field(..., min_length=1, max_length=1000)
    knowledge_base_id: str | None = None
    top_k: int = Field(5, ge=1, le=50)


class SearchResult(BaseModel):
    """Single search result."""
    document_id: str
    title: str
    content: str
    score: float
    knowledge_base_id: str
    chunk_index: int = 0
    retrieval_mode: str | None = None


class SearchResponse(BaseModel):
    """Search results response."""
    results: list[SearchResult]
    total: int
