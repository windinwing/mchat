import pytest

from app.knowledge.rerank import RankedChunk, reciprocal_rank_fusion, rerank_chunks
from app.knowledge.rag import RagService
from app.models.knowledge import Document, DocumentChunk, KnowledgeBase
from app.models.user import User
from tests.conftest import TestSessionFactory


def test_rrf_merges_vector_and_keyword():
    vector = [
        RankedChunk("d1", "kb1", 0, "alpha beta", "Doc1", vector_score=0.9),
        RankedChunk("d2", "kb1", 1, "gamma", "Doc2", vector_score=0.8),
    ]
    keyword = [
        RankedChunk("d2", "kb1", 1, "gamma delta", "Doc2", keyword_score=0.7),
        RankedChunk("d3", "kb1", 0, "beta epsilon", "Doc3", keyword_score=0.6),
    ]
    merged = reciprocal_rank_fusion([vector, keyword])
    keys = {f"{c.document_id}:{c.chunk_index}" for c in merged}
    assert "d1:0" in keys
    assert "d2:1" in keys


@pytest.mark.asyncio
async def test_rerank_prefers_lexical_overlap():
    chunks = [
        RankedChunk("d1", "kb1", 0, "unrelated", "A", fused_score=0.2),
        RankedChunk(
            "d2",
            "kb1",
            0,
            "安装步骤说明",
            "B",
            fused_score=0.5,
        ),
    ]
    ranked = await rerank_chunks("怎么安装", chunks, top_n=1)
    assert ranked[0].document_id == "d2"


@pytest.mark.asyncio
async def test_bm25_matches_chinese_followup_with_suffix(db_session, monkeypatch):
    from app.knowledge.bm25 import bm25_index

    user = User(username="bm25_user", password_hash="hash", role="admin")
    db_session.add(user)
    await db_session.flush()

    kb = KnowledgeBase(
        user_id=user.id,
        name="Troops KB",
        retrieval_mode="keyword",
        retrieval_bm25_enabled=True,
    )
    db_session.add(kb)
    await db_session.flush()

    doc = Document(
        knowledge_base_id=kb.id,
        title="troops.txt",
        content="troops data",
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
            content=(
                "12\t镇守者\t镇守者是鹰之神界针对重装兵种防御而开发的得意之作。\n"
                "13\t统御者\t鹰之神界轻装兵种攻击力的翘楚。"
            ),
        )
    )
    await db_session.commit()

    bm25_index.invalidate(kb.id)
    monkeypatch.setattr("app.core.database.async_session_factory", TestSessionFactory)

    response = await RagService().search(
        query="镇守者呢",
        user_id=user.id,
        knowledge_base_id=kb.id,
        top_k=3,
    )

    assert response.total >= 1
    assert "镇守者" in response.results[0].content


@pytest.mark.asyncio
async def test_hybrid_search_uses_db_chunks(db_session, monkeypatch):
    user = User(username="hybrid_user", password_hash="hash", role="admin")
    db_session.add(user)
    await db_session.flush()

    kb = KnowledgeBase(
        user_id=user.id,
        name="Hybrid KB",
        retrieval_mode="hybrid",
        retrieval_bm25_enabled=False,
    )
    db_session.add(kb)
    await db_session.flush()

    doc = Document(
        knowledge_base_id=kb.id,
        title="手册",
        content="完整安装手册内容",
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
            content="请按照三步完成安装配置",
        )
    )
    await db_session.commit()

    monkeypatch.setattr("app.core.database.async_session_factory", TestSessionFactory)
    monkeypatch.setattr("app.knowledge.rag.milvus_client._connected", False)

    response = await RagService().search(
        query="安装配置",
        user_id=user.id,
        knowledge_base_id=kb.id,
        top_k=3,
    )

    assert response.total >= 1
    assert "安装" in response.results[0].content
