"""Knowledge base and document models."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    group_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("groups.id"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    # Chunking
    chunk_strategy: Mapped[str] = mapped_column(
        String(20), nullable=False, default="fixed"
    )
    chunk_size: Mapped[int] = mapped_column(Integer, nullable=False, default=500)
    chunk_overlap: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    chunk_min_size: Mapped[int] = mapped_column(Integer, nullable=False, default=80)
    # Embedding (null = use global settings)
    embedding_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    embedding_api_base: Mapped[str | None] = mapped_column(String(500), nullable=True)
    embedding_dimension: Mapped[int] = mapped_column(Integer, nullable=False, default=768)
    # Retrieval
    retrieval_mode: Mapped[str] = mapped_column(
        String(20), nullable=False, default="hybrid"
    )
    retrieval_top_k: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    retrieval_candidate_k: Mapped[int] = mapped_column(
        Integer, nullable=False, default=20
    )
    rerank_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    rerank_top_n: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    # BM25
    retrieval_bm25_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    retrieval_bm25_k1: Mapped[float] = mapped_column(Float, nullable=False, default=1.5)
    retrieval_bm25_b: Mapped[float] = mapped_column(Float, nullable=False, default=0.75)
    # Reranker
    rerank_provider: Mapped[str] = mapped_column(
        String(20), nullable=False, default="lexical"
    )
    rerank_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Query rewriting
    retrieval_query_rewrite_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    retrieval_query_rewrite_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3
    )
    retrieval_stop_words: Mapped[str | None] = mapped_column(Text, nullable=True)
    retrieval_query_suffix_chars: Mapped[str | None] = mapped_column(
        String(200), nullable=True
    )
    retrieval_user_dict: Mapped[str | None] = mapped_column(Text, nullable=True)
    retrieval_keyword_backend: Mapped[str] = mapped_column(
        String(20), nullable=False, default="local"
    )  # local | elasticsearch
    # Semantic chunking
    chunk_semantic_threshold: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.7
    )
    chunk_parent_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    # Last successful full index embedding config (provider|model|dim|base)
    indexed_embedding_key: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    reindex_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="idle"
    )  # idle | running | completed | failed
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    user = relationship("User", back_populates="knowledge_bases")
    group = relationship("Group", back_populates="knowledge_bases")
    documents = relationship(
        "Document",
        back_populates="knowledge_base",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<KnowledgeBase(id={self.id}, name={self.name})>"


class DocumentFolder(Base):
    """A folder inside a knowledge base for organizing documents (tree)."""

    __tablename__ = "document_folders"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    knowledge_base_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    parent_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("document_folders.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )  # None = root of the knowledge base
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    parent = relationship(
        "DocumentFolder",
        back_populates="children",
        remote_side="DocumentFolder.id",
    )
    children = relationship(
        "DocumentFolder",
        back_populates="parent",
        lazy="selectin",
        cascade="all, delete-orphan",
    )
    documents = relationship(
        "Document",
        back_populates="folder",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<DocumentFolder(id={self.id}, name={self.name})>"


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    knowledge_base_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("knowledge_bases.id"),
        nullable=False,
        index=True,
    )
    folder_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("document_folders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )  # None = root of the knowledge base; storage is organizational only
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Storage key (local path under uploads/ or S3 key) of the uploaded source
    # file, kept so the background index runner can re-read it after restart.
    source_file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )  # pending, processing, indexed, failed
    chunk_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    knowledge_base = relationship("KnowledgeBase", back_populates="documents")
    folder = relationship("DocumentFolder", back_populates="documents")
    chunks = relationship(
        "DocumentChunk",
        back_populates="document",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Document(id={self.id}, title={self.title})>"


class DocumentChunk(Base):
    """Stored text chunks for keyword/hybrid retrieval."""

    __tablename__ = "document_chunks"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    document_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    knowledge_base_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    parent_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    chunk_type: Mapped[str] = mapped_column(
        String(10), nullable=False, default="child"
    )  # "child" | "parent"
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    document = relationship("Document", back_populates="chunks")
    knowledge_base = relationship("KnowledgeBase")

    def __repr__(self) -> str:
        return f"<DocumentChunk(doc={self.document_id}, idx={self.chunk_index})>"
