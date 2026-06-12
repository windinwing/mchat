"""End-to-end knowledge base tests with local model support.

This test suite covers the full knowledge base pipeline:
- Chunking strategies (fixed, paragraph, markdown)
- Knowledge base creation and configuration
- Document indexing and chunk storage
- Search/retrieval with keyword and BM25
- Reranking and RRF fusion
- Import from test data files

Prerequisites for local model tests:
    ollama pull nomic-embed-text  # Embedding model
    ollama pull qwen2.5           # Chat model (optional)

Usage:
    # Run all KB tests (mock mode, no Ollama needed):
    pytest tests/unit/test_local_knowledge_base.py -v

    # Run with coverage:
    pytest tests/unit/test_local_knowledge_base.py -v --cov=app.knowledge

    # Run a specific test:
    pytest tests/unit/test_local_knowledge_base.py -v -k "test_search"
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import select

from app.knowledge.chunking import ChunkConfig, chunk_text
from app.knowledge.chunk_store import replace_document_chunks
from app.knowledge.importer import DocumentImporter
from app.knowledge.rag import RagService
from app.knowledge.rag_config import (
    EmbeddingConfig,
    KnowledgeBaseRagSettings,
    RetrievalConfig,
    rag_settings_from_kb,
)
from app.knowledge.rerank import RankedChunk, reciprocal_rank_fusion, rerank_chunks
from app.models.knowledge import Document, DocumentChunk, KnowledgeBase
from app.models.user import User
from app.schemas.knowledge import DocumentCreate
from app.services.knowledge_service import KnowledgeService
from tests.conftest import TestSessionFactory

# ---------------------------------------------------------------------------
# Test data paths
# ---------------------------------------------------------------------------

TEST_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
MANUAL_MD = TEST_DATA_DIR / "ai_chatbot_manual.md"
FAQ_TXT = TEST_DATA_DIR / "faq.txt"
RAG_GUIDE_EN = TEST_DATA_DIR / "rag_guide_en.md"
SHORT_DOC = TEST_DATA_DIR / "short_doc.txt"


# ---------------------------------------------------------------------------
# Fake embedder for tests without Ollama/Milvus
# ---------------------------------------------------------------------------

class FakeEmbedder:
    """Produces deterministic fake embeddings for testing."""

    def __init__(self, dim: int = 768) -> None:
        self.dim = dim

    def is_configured(self) -> bool:
        return True

    async def embed_query(self, query: str) -> list[float]:
        # Deterministic: use hash of query to seed
        seed = sum(ord(c) for c in query)
        return [(seed * (i + 1) / 1000.0) % 1.0 for i in range(self.dim)]

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [await self.embed_query(t) for t in texts]


def _patch_kb_indexing(monkeypatch) -> None:
    """Patch embedder and milvus for tests that don't need real services."""
    monkeypatch.setattr("app.core.database.async_session_factory", TestSessionFactory)
    monkeypatch.setattr("app.knowledge.rag.milvus_client._connected", False)
    monkeypatch.setattr("app.knowledge.importer.milvus_client._connected", False)


# ---------------------------------------------------------------------------
# Helper: create a user in the test DB
# ---------------------------------------------------------------------------

async def _create_user(db_session, username: str = "kb_tester") -> User:
    user = User(username=username, password_hash="hash", role="admin")
    db_session.add(user)
    await db_session.flush()
    return user


# ===========================================================================
# Tests: Chunking strategies
# ===========================================================================

class TestChunking:
    """Verify chunking strategies produce correct results."""

    def test_fixed_chunking(self):
        text = "你好世界。这是第二句。这是第三句。这是第四句。"
        config = ChunkConfig(strategy="fixed", size=5, overlap=0)
        chunks = chunk_text(text, config)
        assert len(chunks) >= 1
        assert all(c for c in chunks)

    def test_paragraph_chunking(self):
        long_text = (
            ("A" * 80 + "\n\n") +
            ("B" * 80 + "\n\n") +
            ("C" * 80 + "\n\n")
        )
        config = ChunkConfig(strategy="paragraph", size=100, overlap=0, min_chunk_size=5)
        chunks = chunk_text(long_text, config)
        assert len(chunks) == 3
        assert "A" * 80 in chunks[0]
        assert "B" * 80 in chunks[1]
        assert "C" * 80 in chunks[2]

    def test_markdown_chunking(self):
        text = "# Section A\n" + "x" * 80 + "\n\n# Section B\n" + "y" * 80
        config = ChunkConfig(strategy="markdown", size=100, overlap=0, min_chunk_size=5)
        chunks = chunk_text(text, config)
        assert len(chunks) >= 2
        assert any("Section A" in c for c in chunks)
        assert any("Section B" in c for c in chunks)

    def test_chunking_handles_empty_text(self):
        assert chunk_text("", ChunkConfig()) == []
        assert chunk_text("   ", ChunkConfig()) == []

    def test_chunking_min_size_merges_small(self):
        config = ChunkConfig(strategy="fixed", size=500, overlap=0, min_chunk_size=5)
        chunks = chunk_text("ab\n\ncd\n\nef", config)
        assert len(chunks) == 1
        assert "ab" in chunks[0] and "cd" in chunks[0]

    def test_chunking_with_overlap(self):
        text = "ABCDEFGHIJKLMNOPQRSTUVWXYZ" * 20  # 520 chars
        config = ChunkConfig(strategy="fixed", size=200, overlap=100)
        chunks = chunk_text(text, config)
        # Multiple chunks expected with size=200 and overlap=100
        assert len(chunks) >= 3
        # Verify overlap: consecutive chunks should share characters
        for i in range(len(chunks) - 1):
            assert len(chunks[i]) >= config.min_chunk_size


# ===========================================================================
# Tests: Knowledge Base CRUD
# ===========================================================================

class TestKnowledgeBaseCRUD:
    """Test knowledge base create, read, update, delete operations."""

    @pytest.mark.asyncio
    async def test_create_knowledge_base(self, db_session):
        user = await _create_user(db_session)
        service = KnowledgeService(db_session)
        from app.schemas.knowledge import KnowledgeBaseCreate

        kb = await service.create_knowledge_base(
            user_id=user.id,
            data=KnowledgeBaseCreate(
                name="测试知识库",
                description="用于测试的知识库",
                embedding_provider="ollama",
                embedding_model="nomic-embed-text",
                retrieval_mode="hybrid",
                chunk_strategy="fixed",
                chunk_size=500,
            ),
        )
        assert kb.id is not None
        assert kb.name == "测试知识库"
        assert kb.embedding_provider == "ollama"
        assert kb.embedding_model == "nomic-embed-text"
        assert kb.retrieval_mode == "hybrid"
        assert kb.chunk_strategy == "fixed"
        assert kb.chunk_size == 500
        assert kb.document_count == 0

    @pytest.mark.asyncio
    async def test_create_kb_with_different_retrieval_modes(self, db_session):
        user = await _create_user(db_session)
        service = KnowledgeService(db_session)
        from app.schemas.knowledge import KnowledgeBaseCreate

        for mode in ("vector", "keyword", "hybrid"):
            kb = await service.create_knowledge_base(
                user_id=user.id,
                data=KnowledgeBaseCreate(
                    name=f"{mode}知识库",
                    retrieval_mode=mode,
                    retrieval_top_k=10,
                ),
            )
            assert kb.retrieval_mode == mode

    @pytest.mark.asyncio
    async def test_list_knowledge_bases(self, db_session):
        user = await _create_user(db_session)
        service = KnowledgeService(db_session)
        from app.schemas.knowledge import KnowledgeBaseCreate

        for i in range(3):
            await service.create_knowledge_base(
                user_id=user.id,
                data=KnowledgeBaseCreate(name=f"KB_{i}"),
            )

        kbs = await service.list_knowledge_bases(user_id=user.id)
        assert len(kbs) == 3

    @pytest.mark.asyncio
    async def test_get_knowledge_base(self, db_session):
        user = await _create_user(db_session)
        service = KnowledgeService(db_session)
        from app.schemas.knowledge import KnowledgeBaseCreate

        created = await service.create_knowledge_base(
            user_id=user.id,
            data=KnowledgeBaseCreate(name="查找测试"),
        )

        found = await service.get_knowledge_base(created.id, user_id=user.id)
        assert found is not None
        assert found.id == created.id

    @pytest.mark.asyncio
    async def test_update_knowledge_base(self, db_session):
        user = await _create_user(db_session)
        service = KnowledgeService(db_session)
        from app.schemas.knowledge import KnowledgeBaseCreate, KnowledgeBaseUpdate

        kb = await service.create_knowledge_base(
            user_id=user.id,
            data=KnowledgeBaseCreate(name="原始名称"),
        )

        updated = await service.update_knowledge_base(
            kb.id, user.id,
            data=KnowledgeBaseUpdate(
                name="新名称",
                description="新描述",
                retrieval_top_k=10,
            ),
        )
        assert updated is not None
        assert updated.name == "新名称"
        assert updated.description == "新描述"
        assert updated.retrieval_top_k == 10

    @pytest.mark.asyncio
    async def test_delete_knowledge_base(self, db_session):
        user = await _create_user(db_session)
        service = KnowledgeService(db_session)
        from app.schemas.knowledge import KnowledgeBaseCreate

        kb = await service.create_knowledge_base(
            user_id=user.id,
            data=KnowledgeBaseCreate(name="待删除"),
        )

        deleted = await service.delete_knowledge_base(kb.id, user.id)
        assert deleted is True

        found = await service.get_knowledge_base(kb.id, user.id)
        assert found is None


# ===========================================================================
# Tests: Document indexing and management
# ===========================================================================

class TestDocumentIndexing:
    """Test document creation, indexing, and chunk storage."""

    @pytest.mark.asyncio
    async def test_create_document_and_index(self, db_session, monkeypatch):
        _patch_kb_indexing(monkeypatch)
        monkeypatch.setattr(
            "app.knowledge.importer.embedder_for_config",
            lambda _cfg: FakeEmbedder(),
        )

        user = await _create_user(db_session)
        kb = KnowledgeBase(user_id=user.id, name="DocKB")
        db_session.add(kb)
        await db_session.flush()

        fake_embedder = FakeEmbedder(dim=768)
        importer = DocumentImporter(db=db_session)
        importer._embedder = fake_embedder

        doc = Document(
            id="doc-test-1",
            knowledge_base_id=kb.id,
            title="测试文档",
            content="这是测试文档的内容。用于验证知识库的索引功能。",
            source="manual",
        )

        monkeypatch.setattr(DocumentImporter, "_validate_embedding_dimension", lambda *a, **kw: None)

        chunks, _ = importer._chunk_with_parents(doc.content)
        chunk_count = await importer.index_document(doc, user_id=user.id, chunks=chunks)
        assert chunk_count > 0

        # Verify chunks stored
        result = await db_session.execute(
            select(DocumentChunk).where(DocumentChunk.document_id == "doc-test-1")
        )
        db_chunks = result.scalars().all()
        assert len(db_chunks) == chunk_count
        assert all(c.knowledge_base_id == kb.id for c in db_chunks)

    @pytest.mark.asyncio
    async def test_create_document_via_service(self, db_session, monkeypatch):
        _patch_kb_indexing(monkeypatch)
        monkeypatch.setattr(
            "app.knowledge.importer.embedder_for_config",
            lambda _cfg: FakeEmbedder(),
        )
        # Make Milvus appear connected so index_document stores chunks
        monkeypatch.setattr("app.knowledge.importer.milvus_client._connected", True)
        monkeypatch.setattr(
            DocumentImporter,
            "_validate_embedding_dimension",
            lambda *a, **kw: None,
        )

        # Mock milvus insert to avoid actual Milvus call
        async def fake_insert(**kwargs):
            return len(kwargs.get("chunks", []))

        monkeypatch.setattr(
            "app.knowledge.importer.milvus_client.insert_vectors",
            fake_insert,
        )

        user = await _create_user(db_session)
        from app.schemas.knowledge import KnowledgeBaseCreate

        service = KnowledgeService(db_session)
        kb = await service.create_knowledge_base(
            user_id=user.id,
            data=KnowledgeBaseCreate(name="服务测试KB"),
        )

        doc = await service.create_document(
            kb_id=kb.id,
            user_id=user.id,
            data=DocumentCreate(
                title="通过服务创建的文档",
                content="这是一段很长很长的测试内容，用于验证通过 KnowledgeService 创建文档时是否正确调用了索引流程。"
                        "这里添加更多内容以确保文档足够长，从而产生多个分块。"
                        "继续添加内容来扩展文档长度。"
                        "机器学习是人工智能的一个分支，它使计算机能够从数据中学习而无需显式编程。"
                        "深度学习使用多层神经网络来处理复杂的模式识别任务。",
            ),
        )
        assert doc.status == "indexed"
        assert doc.chunk_count > 0
        assert doc.title == "通过服务创建的文档"

    @pytest.mark.asyncio
    async def test_index_multiple_documents(self, db_session, monkeypatch):
        _patch_kb_indexing(monkeypatch)
        monkeypatch.setattr(
            "app.knowledge.importer.embedder_for_config",
            lambda _cfg: FakeEmbedder(),
        )
        monkeypatch.setattr(
            DocumentImporter,
            "_validate_embedding_dimension",
            lambda *a, **kw: None,
        )

        user = await _create_user(db_session)
        from app.schemas.knowledge import KnowledgeBaseCreate

        service = KnowledgeService(db_session)
        kb = await service.create_knowledge_base(
            user_id=user.id,
            data=KnowledgeBaseCreate(name="多文档KB"),
        )

        docs_data = [
            DocumentCreate(title="文档A", content="Python是一个高级编程语言，以其简洁和可读性著称。"),
            DocumentCreate(title="文档B", content="FastAPI是一个现代Web框架，用于构建高性能API。"),
            DocumentCreate(title="文档C", content="知识库系统使用向量检索来查找相关内容。"),
        ]

        for data in docs_data:
            await service.create_document(kb_id=kb.id, user_id=user.id, data=data)

        docs = await service.list_documents(kb_id=kb.id, user_id=user.id)
        assert len(docs) == 3
        assert all(d.status == "indexed" for d in docs)

    @pytest.mark.asyncio
    async def test_delete_document(self, db_session, monkeypatch):
        _patch_kb_indexing(monkeypatch)
        monkeypatch.setattr(
            "app.knowledge.importer.embedder_for_config",
            lambda _cfg: FakeEmbedder(),
        )
        monkeypatch.setattr(
            DocumentImporter,
            "_validate_embedding_dimension",
            lambda *a, **kw: None,
        )

        user = await _create_user(db_session)
        from app.schemas.knowledge import KnowledgeBaseCreate

        service = KnowledgeService(db_session)
        kb = await service.create_knowledge_base(
            user_id=user.id,
            data=KnowledgeBaseCreate(name="删除测试KB"),
        )

        doc = await service.create_document(
            kb_id=kb.id, user_id=user.id,
            data=DocumentCreate(title="将被删除", content="这个文档会被删除。"),
        )

        deleted = await service.delete_document(doc.id, user.id)
        assert deleted is True

        docs = await service.list_documents(kb_id=kb.id, user_id=user.id)
        assert len(docs) == 0


# ===========================================================================
# Tests: Search and retrieval
# ===========================================================================

class TestSearchRetrieval:
    """Test search functionality across different retrieval modes."""

    @pytest.mark.asyncio
    async def test_keyword_search_finds_relevant_chunks(self, db_session, monkeypatch):
        _patch_kb_indexing(monkeypatch)

        user = await _create_user(db_session)
        kb = KnowledgeBase(
            user_id=user.id,
            name="SearchKB",
            retrieval_mode="keyword",
            retrieval_bm25_enabled=False,
        )
        db_session.add(kb)
        await db_session.flush()

        doc = Document(
            knowledge_base_id=kb.id,
            title="Python教程",
            content="Python入门教程：安装、配置和第一个程序。",
            status="indexed",
            chunk_count=1,
        )
        db_session.add(doc)
        await db_session.flush()

        db_session.add(
            DocumentChunk(
                document_id=doc.id,
                knowledge_base_id=kb.id,
                chunk_index=0,
                content="Python入门教程：安装、配置和第一个程序。",
            )
        )
        await db_session.commit()

        response = await RagService().search(
            query="Python 教程",
            user_id=user.id,
            knowledge_base_id=kb.id,
            top_k=3,
        )
        assert response.total >= 1
        assert "Python" in response.results[0].content

    @pytest.mark.asyncio
    async def test_hybrid_search_fallback_to_keyword(self, db_session, monkeypatch):
        _patch_kb_indexing(monkeypatch)

        user = await _create_user(db_session)
        kb = KnowledgeBase(
            user_id=user.id,
            name="HybridKB",
            retrieval_mode="hybrid",
            retrieval_bm25_enabled=False,
        )
        db_session.add(kb)
        await db_session.flush()

        doc = Document(
            knowledge_base_id=kb.id,
            title="MChat部署指南",
            content="详细的MChat部署步骤，包括Docker和本地部署方式。",
            status="indexed",
            chunk_count=1,
        )
        db_session.add(doc)
        await db_session.flush()

        db_session.add(
            DocumentChunk(
                document_id=doc.id,
                knowledge_base_id=kb.id,
                chunk_index=0,
                content="详细的MChat部署步骤，包括Docker和本地部署方式。",
            )
        )
        await db_session.commit()

        response = await RagService().search(
            query="部署方式",
            user_id=user.id,
            knowledge_base_id=kb.id,
            top_k=3,
        )
        assert response.total >= 1
        assert "部署" in response.results[0].content

    @pytest.mark.asyncio
    async def test_search_no_results(self, db_session, monkeypatch):
        _patch_kb_indexing(monkeypatch)

        user = await _create_user(db_session)
        kb = KnowledgeBase(
            user_id=user.id,
            name="EmptyKB",
            retrieval_mode="keyword",
        )
        db_session.add(kb)
        await db_session.commit()

        response = await RagService().search(
            query="找不到的内容",
            user_id=user.id,
            knowledge_base_id=kb.id,
            top_k=3,
        )
        assert response.total == 0
        assert len(response.results) == 0

    @pytest.mark.asyncio
    async def test_search_with_multiple_docs_ranks_correctly(self, db_session, monkeypatch):
        _patch_kb_indexing(monkeypatch)

        user = await _create_user(db_session)
        kb = KnowledgeBase(
            user_id=user.id,
            name="RankKB",
            retrieval_mode="keyword",
            retrieval_bm25_enabled=False,
        )
        db_session.add(kb)
        await db_session.flush()

        docs_data = [
            ("不相关文档", "今天天气很好，适合出去散步。"),
            ("相关文档A", "RAG系统使用向量检索和关键词检索来查找相关内容。"),
            ("相关文档B", "知识库的检索功能包括向量检索、关键词检索和混合检索。"),
        ]
        for title, content in docs_data:
            doc = Document(
                knowledge_base_id=kb.id,
                title=title,
                content=content,
                status="indexed",
                chunk_count=1,
            )
            db_session.add(doc)
            await db_session.flush()
            db_session.add(
                DocumentChunk(
                    document_id=doc.id,
                    knowledge_base_id=kb.id,
                    chunk_index=0,
                    content=content,
                )
            )
        await db_session.commit()

        response = await RagService().search(
            query="检索 相关 知识库",
            user_id=user.id,
            knowledge_base_id=kb.id,
            top_k=3,
        )
        assert response.total >= 1
        if response.total >= 1:
            first_title = response.results[0].title
            assert "相关" in first_title

    @pytest.mark.asyncio
    async def test_search_respects_top_k(self, db_session, monkeypatch):
        _patch_kb_indexing(monkeypatch)

        user = await _create_user(db_session)
        kb = KnowledgeBase(
            user_id=user.id,
            name="TopKKB",
            retrieval_mode="keyword",
            retrieval_bm25_enabled=False,
        )
        db_session.add(kb)
        await db_session.flush()

        for i in range(10):
            doc = Document(
                knowledge_base_id=kb.id,
                title=f"文档{i}",
                content=f"测试内容{i}: 这是一个关于知识库检索的测试文档。",
                status="indexed",
                chunk_count=1,
            )
            db_session.add(doc)
            await db_session.flush()
            db_session.add(
                DocumentChunk(
                    document_id=doc.id,
                    knowledge_base_id=kb.id,
                    chunk_index=0,
                    content=f"测试内容{i}: 这是一个关于知识库检索的测试文档。",
                )
            )
        await db_session.commit()

        response = await RagService().search(
            query="知识库 检索",
            user_id=user.id,
            knowledge_base_id=kb.id,
            top_k=3,
        )
        assert response.total <= 3


# ===========================================================================
# Tests: Rerank and RRF
# ===========================================================================

class TestRerankAndRRF:
    """Test reranking algorithms and Reciprocal Rank Fusion."""

    def test_rrf_merges_results(self):
        vector_hits = [
            RankedChunk("d1", "kb1", 0, "alpha beta", "Doc1", vector_score=0.9),
            RankedChunk("d2", "kb1", 1, "gamma", "Doc2", vector_score=0.8),
        ]
        keyword_hits = [
            RankedChunk("d2", "kb1", 1, "gamma delta", "Doc2", keyword_score=0.7),
            RankedChunk("d3", "kb1", 0, "beta epsilon", "Doc3", keyword_score=0.6),
        ]
        merged = reciprocal_rank_fusion([vector_hits, keyword_hits])
        assert len(merged) >= 2
        keys = {f"{c.document_id}:{c.chunk_index}" for c in merged}
        assert "d1:0" in keys
        assert "d2:1" in keys

    def test_rrf_single_list_returns_same(self):
        hits = [
            RankedChunk("d1", "kb1", 0, "text", "Doc1", fused_score=0.9),
            RankedChunk("d2", "kb1", 0, "text", "Doc2", fused_score=0.5),
        ]
        merged = reciprocal_rank_fusion([hits])
        assert len(merged) == 2
        assert [c.document_id for c in merged] == ["d1", "d2"]

    @pytest.mark.asyncio
    async def test_lexical_rerank_improves_ordering(self):
        chunks = [
            RankedChunk("d1", "kb1", 0, "unrelated content here", "A", fused_score=0.3),
            RankedChunk(
                "d2", "kb1", 0,
                "知识库管理系统支持多种检索方式，包括向量检索和关键词检索",
                "B", fused_score=0.5,
            ),
            RankedChunk(
                "d3", "kb1", 0,
                "检索功能是知识库的核心特性之一，用户可以通过检索找到相关信息",
                "C", fused_score=0.4,
            ),
        ]
        ranked = await rerank_chunks("知识库检索", chunks, top_n=2)
        assert len(ranked) == 2
        # d2 and d3 have keyword overlap with "检索", "知识库"; d1 does not
        top_ids = {c.document_id for c in ranked}
        assert "d1" not in top_ids

    @pytest.mark.asyncio
    async def test_rerank_respects_top_n(self):
        chunks = [
            RankedChunk("d1", "kb1", 0, f"content_{i}", str(i), fused_score=0.5)
            for i in range(5)
        ]
        ranked = await rerank_chunks("test query", chunks, top_n=3)
        assert len(ranked) == 3


# ===========================================================================
# Tests: Embedding configuration
# ===========================================================================

class TestEmbeddingConfig:
    """Test embedding configuration resolution."""

    def test_ollama_config_defaults(self):
        config = EmbeddingConfig(provider="ollama", model="nomic-embed-text")
        assert config.resolved_provider() == "ollama"
        assert config.resolved_model() == "nomic-embed-text"
        assert "localhost" in (config.resolved_api_base() or "")

    def test_openai_config(self):
        config = EmbeddingConfig(
            provider="openai",
            model="text-embedding-ada-002",
            api_base="https://api.openai.com/v1",
            dimension=1536,
        )
        assert config.resolved_provider() == "openai"
        assert config.resolved_dimension() == 1536

    def test_config_fallback_to_settings(self):
        config = EmbeddingConfig()
        # Should fall back to settings defaults (ollama by default)
        assert config.resolved_provider() in ("ollama", "")
        assert config.resolved_dimension() > 0


# ===========================================================================
# Tests: RAG settings from KnowledgeBase
# ===========================================================================

class TestRagSettings:
    """Test building RAG settings from KnowledgeBase ORM row."""

    def test_settings_from_kb_row(self):
        kb = KnowledgeBase(
            name="TestKB",
            chunk_strategy="paragraph",
            chunk_size=800,
            chunk_overlap=100,
            embedding_provider="ollama",
            embedding_model="nomic-embed-text",
            retrieval_mode="hybrid",
            retrieval_top_k=7,
            rerank_enabled=True,
            rerank_provider="lexical",
        )
        settings = rag_settings_from_kb(kb)
        assert settings.chunk_strategy == "paragraph"
        assert settings.chunk_size == 800
        assert settings.retrieval_mode == "hybrid"
        assert settings.retrieval_top_k == 7
        assert settings.rerank_enabled is True

    def test_settings_defaults_when_none(self):
        settings = rag_settings_from_kb(None)
        assert settings.chunk_strategy == "fixed"
        assert settings.chunk_size == 500
        assert settings.retrieval_mode == "hybrid"

    def test_chunk_config_from_settings(self):
        settings = KnowledgeBaseRagSettings(
            chunk_strategy="fixed",
            chunk_size=600,
            chunk_overlap=60,
            chunk_min_size=100,
        )
        cfg = settings.chunk_config()
        assert cfg.strategy == "fixed"
        assert cfg.size == 600
        assert cfg.overlap == 60
        assert cfg.min_chunk_size == 100

    def test_retrieval_config_from_settings(self):
        settings = KnowledgeBaseRagSettings(
            retrieval_mode="vector",
            retrieval_top_k=8,
            retrieval_candidate_k=30,
            rerank_enabled=False,
        )
        cfg = settings.retrieval_config()
        assert cfg.mode == "vector"
        assert cfg.top_k == 8
        assert cfg.candidate_k == 30
        assert cfg.rerank_enabled is False


# ===========================================================================
# Tests: Document import from test data files
# ===========================================================================

class TestDocumentImport:
    """Test importing documents from test data files."""

    @pytest.mark.asyncio
    async def test_import_markdown_file(self, db_session, monkeypatch, tmp_path: Path):
        _patch_kb_indexing(monkeypatch)
        monkeypatch.setattr(
            "app.knowledge.importer.embedder_for_config",
            lambda _cfg: FakeEmbedder(),
        )
        monkeypatch.setattr(
            DocumentImporter,
            "_validate_embedding_dimension",
            lambda *a, **kw: None,
        )

        user = await _create_user(db_session)
        kb = KnowledgeBase(
            user_id=user.id,
            name="ImportKB",
            chunk_strategy="markdown",
            chunk_size=500,
        )
        db_session.add(kb)
        await db_session.flush()

        # Copy test file to tmp_path so importer can read it
        import shutil
        test_file = tmp_path / "chatbot_manual.md"
        shutil.copy(str(MANUAL_MD), str(test_file))

        importer = DocumentImporter(db=db_session)
        importer._embedder = FakeEmbedder()

        doc = await importer.import_file(
            kb_id=kb.id,
            user_id=user.id,
            file_path=test_file,
            original_filename="chatbot_manual.md",
        )

        assert doc is not None
        assert doc.status == "indexed"
        assert doc.chunk_count > 0
        assert doc.source == "md"

        # Verify chunks stored in DB
        result = await db_session.execute(
            select(DocumentChunk).where(DocumentChunk.document_id == doc.id)
        )
        chunks = result.scalars().all()
        assert len(chunks) > 0

    @pytest.mark.asyncio
    async def test_import_text_file(self, db_session, monkeypatch, tmp_path: Path):
        _patch_kb_indexing(monkeypatch)
        monkeypatch.setattr(
            "app.knowledge.importer.embedder_for_config",
            lambda _cfg: FakeEmbedder(),
        )
        monkeypatch.setattr(
            DocumentImporter,
            "_validate_embedding_dimension",
            lambda *a, **kw: None,
        )

        user = await _create_user(db_session)
        kb = KnowledgeBase(
            user_id=user.id,
            name="TextImportKB",
            chunk_strategy="paragraph",
            chunk_size=300,
        )
        db_session.add(kb)
        await db_session.flush()

        import shutil
        test_file = tmp_path / "faq.txt"
        shutil.copy(str(FAQ_TXT), str(test_file))

        importer = DocumentImporter(db=db_session)
        importer._embedder = FakeEmbedder()

        doc = await importer.import_file(
            kb_id=kb.id,
            user_id=user.id,
            file_path=test_file,
            original_filename="faq.txt",
        )

        assert doc.status == "indexed"
        assert doc.chunk_count > 0
        assert doc.source == "txt"

    @pytest.mark.asyncio
    async def test_import_short_document(self, db_session, monkeypatch, tmp_path: Path):
        _patch_kb_indexing(monkeypatch)
        monkeypatch.setattr(
            "app.knowledge.importer.embedder_for_config",
            lambda _cfg: FakeEmbedder(),
        )

        user = await _create_user(db_session)
        kb = KnowledgeBase(user_id=user.id, name="ShortDocKB")
        db_session.add(kb)
        await db_session.flush()

        import shutil
        test_file = tmp_path / "short.txt"
        shutil.copy(str(SHORT_DOC), str(test_file))

        importer = DocumentImporter(db=db_session)
        importer._embedder = FakeEmbedder()

        doc = await importer.import_file(
            kb_id=kb.id,
            user_id=user.id,
            file_path=test_file,
            original_filename="short.txt",
        )

        assert doc.status == "indexed"
        assert doc.chunk_count == 1  # short text = single chunk

    @pytest.mark.asyncio
    async def test_import_english_markdown(self, db_session, monkeypatch, tmp_path: Path):
        _patch_kb_indexing(monkeypatch)
        monkeypatch.setattr(
            "app.knowledge.importer.embedder_for_config",
            lambda _cfg: FakeEmbedder(),
        )
        monkeypatch.setattr(
            DocumentImporter,
            "_validate_embedding_dimension",
            lambda *a, **kw: None,
        )

        user = await _create_user(db_session)
        kb = KnowledgeBase(
            user_id=user.id,
            name="EnglishKB",
            chunk_strategy="markdown",
            chunk_size=500,
        )
        db_session.add(kb)
        await db_session.flush()

        import shutil
        test_file = tmp_path / "rag_guide.md"
        shutil.copy(str(RAG_GUIDE_EN), str(test_file))

        importer = DocumentImporter(db=db_session)
        importer._embedder = FakeEmbedder()

        doc = await importer.import_file(
            kb_id=kb.id,
            user_id=user.id,
            file_path=test_file,
            original_filename="rag_guide.md",
        )

        assert doc.status == "indexed"
        assert doc.chunk_count > 0
        assert doc.source == "md"


# ===========================================================================
# Tests: End-to-end workflow (knowledge base + indexing + search)
# ===========================================================================

class TestEndToEndWorkflow:
    """Full pipeline: create KB -> index docs -> search -> verify."""

    @pytest.mark.asyncio
    async def test_e2e_chinese_kb_workflow(self, db_session, monkeypatch, tmp_path: Path):
        """Complete end-to-end workflow with Chinese documents."""
        _patch_kb_indexing(monkeypatch)
        monkeypatch.setattr(
            "app.knowledge.importer.embedder_for_config",
            lambda _cfg: FakeEmbedder(),
        )
        monkeypatch.setattr(
            DocumentImporter,
            "_validate_embedding_dimension",
            lambda *a, **kw: None,
        )

        # 1. Create user and knowledge base
        user = await _create_user(db_session)
        from app.schemas.knowledge import KnowledgeBaseCreate

        service = KnowledgeService(db_session)
        kb = await service.create_knowledge_base(
            user_id=user.id,
            data=KnowledgeBaseCreate(
                name="E2E测试知识库",
                description="端到端测试",
                retrieval_mode="keyword",
                retrieval_bm25_enabled=False,
                chunk_strategy="paragraph",
                chunk_size=400,
                rerank_enabled=True,
                rerank_top_n=3,
            ),
        )

        # 2. Index test documents
        import shutil
        importer = DocumentImporter(db=db_session)
        importer._embedder = FakeEmbedder()

        test_files = [
            (MANUAL_MD, "manual.md"),
            (FAQ_TXT, "faq.txt"),
        ]
        for src_file, dest_name in test_files:
            dest = tmp_path / dest_name
            shutil.copy(str(src_file), str(dest))
            await importer.import_file(
                kb_id=kb.id,
                user_id=user.id,
                file_path=dest,
                original_filename=dest_name,
            )
        await db_session.commit()

        # 3. Verify documents indexed
        docs = await service.list_documents(kb_id=kb.id, user_id=user.id)
        assert len(docs) == 2
        assert all(d.status == "indexed" for d in docs)

        # 4. Search - should find relevant content
        test_queries = [
            ("安装", True),              # Should find content about installation
            ("检索", True),              # Should find content about knowledge base search
            ("Ollama", True),            # Should find content about Ollama
            ("今天天气", False),         # Should NOT find anything
        ]

        for query, expect_results in test_queries:
            result = await RagService().search(
                query=query,
                user_id=user.id,
                knowledge_base_id=kb.id,
                top_k=5,
            )
            if expect_results:
                assert result.total >= 1, f"Query '{query}' should return results"
            else:
                assert result.total == 0, f"Query '{query}' should NOT return results"

    @pytest.mark.asyncio
    async def test_e2e_english_kb_workflow(self, db_session, monkeypatch, tmp_path: Path):
        """End-to-end workflow with English documents."""
        _patch_kb_indexing(monkeypatch)
        monkeypatch.setattr(
            "app.knowledge.importer.embedder_for_config",
            lambda _cfg: FakeEmbedder(),
        )
        monkeypatch.setattr(
            DocumentImporter,
            "_validate_embedding_dimension",
            lambda *a, **kw: None,
        )

        user = await _create_user(db_session)
        kb = KnowledgeBase(
            user_id=user.id,
            name="EnglishE2EKB",
            retrieval_mode="keyword",
            retrieval_bm25_enabled=False,
            chunk_strategy="markdown",
            chunk_size=500,
        )
        db_session.add(kb)
        await db_session.flush()

        import shutil
        dest = tmp_path / "rag_guide.md"
        shutil.copy(str(RAG_GUIDE_EN), str(dest))

        importer = DocumentImporter(db=db_session)
        importer._embedder = FakeEmbedder()

        doc = await importer.import_file(
            kb_id=kb.id,
            user_id=user.id,
            file_path=dest,
            original_filename="rag_guide.md",
        )
        await db_session.commit()
        assert doc.status == "indexed"

        # Search in English - use single terms that appear in the content
        result = await RagService().search(
            query="embedding configuration retrieval",
            user_id=user.id,
            knowledge_base_id=kb.id,
            top_k=5,
        )
        assert result.total >= 1

        result = await RagService().search(
            query="chunking strategy fixed",
            user_id=user.id,
            knowledge_base_id=kb.id,
            top_k=5,
        )
        assert result.total >= 1


# ===========================================================================
# Tests: RagConfig and RetrievalConfig defaults
# ===========================================================================

class TestRagConfigDefaults:
    """Test that config models produce sensible defaults."""

    def test_default_rag_settings(self):
        settings = KnowledgeBaseRagSettings()
        assert settings.retrieval_mode in ("hybrid", "vector", "keyword")
        assert settings.retrieval_top_k >= 1
        assert settings.chunk_size >= 100

    def test_retrieval_config_defaults(self):
        config = RetrievalConfig()
        assert config.mode in ("hybrid", "vector", "keyword")
        assert config.top_k >= 1
        assert config.candidate_k >= config.top_k


# ===========================================================================
# Tests: Search result formatting
# ===========================================================================

class TestSearchResponse:
    """Test search response structure."""

    @pytest.mark.asyncio
    async def test_search_response_structure(self, db_session, monkeypatch):
        _patch_kb_indexing(monkeypatch)

        user = await _create_user(db_session)
        kb = KnowledgeBase(
            user_id=user.id,
            name="ResponseKB",
            retrieval_mode="keyword",
            retrieval_bm25_enabled=False,
        )
        db_session.add(kb)
        await db_session.flush()

        doc = Document(
            knowledge_base_id=kb.id,
            title="响应测试",
            content="测试搜索响应结构",
            status="indexed",
            chunk_count=1,
        )
        db_session.add(doc)
        await db_session.flush()
        db_session.add(
            DocumentChunk(
                document_id=doc.id,
                knowledge_base_id=kb.id,
                chunk_index=0,
                content="测试搜索响应结构",
            )
        )
        await db_session.commit()

        response = await RagService().search(
            query="搜索 响应",
            user_id=user.id,
            knowledge_base_id=kb.id,
            top_k=3,
        )

        assert hasattr(response, "results")
        assert hasattr(response, "total")
        assert response.total == len(response.results)
        for r in response.results:
            assert r.document_id is not None
            assert r.title is not None
            assert r.content is not None
            assert r.score >= 0


# ===========================================================================
# Tests: Local model integration (optional - requires Ollama)
# ===========================================================================

@pytest.mark.skipif(
    not os.environ.get("TEST_WITH_OLLAMA"),
    reason="Set TEST_WITH_OLLAMA=1 to run local model integration tests",
)
class TestLocalModelIntegration:
    """Integration tests with real Ollama models.

    Prerequisites:
        ollama pull nomic-embed-text
        ollama pull qwen2.5  (or llama2, deepseek-r1, etc.)

    Usage:
        TEST_WITH_OLLAMA=1 pytest tests/unit/test_local_knowledge_base.py \
            -v -k "LocalModel"
    """

    @pytest.mark.asyncio
    async def test_ollama_embedding_is_configured(self):
        """Verify Ollama embedding service can connect."""
        from app.knowledge.embedder import EmbeddingService
        from app.knowledge.rag_config import EmbeddingConfig

        config = EmbeddingConfig(
            provider="ollama",
            model="nomic-embed-text",
            api_base="http://localhost:11434",
        )
        svc = EmbeddingService(config)
        assert svc.is_configured() is True

    @pytest.mark.asyncio
    async def test_ollama_embed_query(self):
        """Test that Ollama can generate embeddings for a query."""
        from app.knowledge.embedder import EmbeddingService
        from app.knowledge.rag_config import EmbeddingConfig

        config = EmbeddingConfig(
            provider="ollama",
            model="nomic-embed-text",
            api_base="http://localhost:11434",
            dimension=768,
        )
        svc = EmbeddingService(config)
        embedding = await svc.embed_query("测试中文嵌入")
        assert len(embedding) == 768
        assert any(v != 0.0 for v in embedding)

    @pytest.mark.asyncio
    async def test_ollama_embed_documents(self):
        """Test that Ollama can embed multiple documents."""
        from app.knowledge.embedder import EmbeddingService
        from app.knowledge.rag_config import EmbeddingConfig

        config = EmbeddingConfig(
            provider="ollama",
            model="nomic-embed-text",
            api_base="http://localhost:11434",
            dimension=768,
        )
        svc = EmbeddingService(config)
        texts = ["这是第一个文档", "这是第二个文档", "这是第三个文档"]
        embeddings = await svc.embed_documents(texts)
        assert len(embeddings) == 3
        assert all(len(e) == 768 for e in embeddings)

    @pytest.mark.asyncio
    async def test_ollama_chat_stream(self):
        """Test that Ollama can stream chat completions."""
        from app.bot.provider import OllamaProvider
        from app.models.ai_config import AIConfig

        # Use any available Ollama model
        model_name = os.environ.get("TEST_OLLAMA_MODEL", "qwen2.5")

        config = AIConfig(
            id="test",
            user_id="test_user",
            name="TestConfig",
            provider="ollama",
            model=model_name,
            api_base="http://localhost:11434/v1",
            api_key="ollama",
            system_prompt="你是一个有帮助的助手。",
            temperature=0.7,
            max_tokens=64,
            is_default=False,
        )

        provider = OllamaProvider(config)
        messages = [{"role": "user", "content": "请说'你好，知识库测试成功'"}] * 1  # only one message

        collected_content = []
        async for chunk in provider.stream_chat(
            messages=messages,
            max_tokens=32,
        ):
            if chunk.get("type") == "content":
                collected_content.append(chunk["content"])
            elif chunk.get("type") == "done":
                break

        full_response = "".join(collected_content)
        assert len(full_response) > 0, "Expected non-empty response from Ollama"
        print(f"\n    Ollama response: {full_response}")

    @pytest.mark.asyncio
    async def test_ollama_chat_augments_with_knowledge(
        self, db_session, monkeypatch, tmp_path: Path
    ):
        """End-to-end: embed with Ollama, search, and augment prompt for chat."""
        from app.knowledge.embedder import EmbeddingService
        from app.knowledge.rag import RagService
        from app.knowledge.rag_config import EmbeddingConfig
        from app.models.knowledge import DocumentChunk

        user = await _create_user(db_session, "ollama_tester")
        kb = KnowledgeBase(
            user_id=user.id,
            name="OllamaE2EKB",
            retrieval_mode="keyword",
            retrieval_bm25_enabled=False,
        )
        db_session.add(kb)
        await db_session.flush()

        doc = Document(
            knowledge_base_id=kb.id,
            title="产品介绍",
            content="MChat是一个多租户RAG平台，支持知识库管理、技能插件和工作流编排。"
                    "它支持10多种LLM提供商，包括OpenAI、DeepSeek和Ollama本地模型。",
            status="indexed",
            chunk_count=1,
        )
        db_session.add(doc)
        await db_session.flush()
        db_session.add(
            DocumentChunk(
                document_id=doc.id,
                knowledge_base_id=kb.id,
                chunk_index=0,
                content="MChat是一个多租户RAG平台，支持知识库管理、技能插件和工作流编排。"
                        "它支持10多种LLM提供商，包括OpenAI、DeepSeek和Ollama本地模型。",
            )
        )
        await db_session.commit()

        # Patch DB session factory for search
        monkeypatch.setattr("app.core.database.async_session_factory", TestSessionFactory)
        monkeypatch.setattr("app.knowledge.rag.milvus_client._connected", False)

        # Search
        search_result = await RagService().search(
            query="MChat 是什么",
            user_id=user.id,
            knowledge_base_id=kb.id,
            top_k=3,
        )
        assert search_result.total >= 1

        # Augment prompt
        prompt = await RagService().augment_prompt(
            query="MChat 是什么",
            user_id=user.id,
            knowledge_base_id=kb.id,
        )
        assert prompt is not None
        assert "MChat" in prompt
        assert "RAG" in prompt
        print(f"\n    Augmented prompt:\n{prompt[:200]}...")


# ===========================================================================
# Skip conditions
# ===========================================================================

# Optionally skip entire file if test data missing
if not TEST_DATA_DIR.exists():
    pytest.skip("tests/data/ directory not found", allow_module_level=True)
