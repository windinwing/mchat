from __future__ import annotations

import io
from pathlib import Path

import pytest
from fastapi import HTTPException, UploadFile

from app.knowledge.chunking import ChunkConfig, chunk_text
from app.knowledge.importer import DocumentImporter
from app.models.knowledge import Document, KnowledgeBase
from app.schemas.knowledge import (
    DocumentCreate,
    DocumentMoveRequest,
    FolderCreate,
    FolderUpdate,
)
from app.services.knowledge_service import KnowledgeService


class _FakeEmbedder:
    def is_configured(self) -> bool:
        return True

    async def embed_documents(self, chunks: list[str]) -> list[list[float]]:
        return [[0.1] * 768 for _ in chunks]


def _noop_validate_dimension(self, dim: int) -> None:
    return None


def _patch_importer_embedder(monkeypatch) -> None:
    monkeypatch.setattr("app.knowledge.importer.milvus_client._connected", True)
    monkeypatch.setattr(
        DocumentImporter,
        "_validate_embedding_dimension",
        _noop_validate_dimension,
    )
    monkeypatch.setattr(
        "app.knowledge.importer.embedder_for_config",
        lambda _cfg: _FakeEmbedder(),
    )


@pytest.mark.asyncio
async def test_index_document_passes_user_id_to_milvus(monkeypatch):
    _patch_importer_embedder(monkeypatch)
    importer = DocumentImporter()
    importer._embedder = _FakeEmbedder()
    doc = Document(
        id="doc-1",
        knowledge_base_id="kb-1",
        title="Manual",
        content="Alpha paragraph.\n\nBeta paragraph.",
        source="manual",
    )
    captured: dict[str, object] = {}

    _patch_importer_embedder(monkeypatch)

    async def fake_insert_vectors(**kwargs):
        captured.update(kwargs)
        return len(kwargs["chunks"])

    monkeypatch.setattr(
        "app.knowledge.importer.milvus_client.insert_vectors", fake_insert_vectors
    )

    chunk_count = await importer.index_document(doc, user_id="user-123")

    assert chunk_count > 0
    assert captured["user_id"] == "user-123"
    assert captured["kb_id"] == "kb-1"
    assert captured["document_id"] == "doc-1"


@pytest.mark.asyncio
async def test_import_file_assigns_document_id_before_indexing(monkeypatch, tmp_path: Path):
    _patch_importer_embedder(monkeypatch)
    importer = DocumentImporter()
    importer._embedder = _FakeEmbedder()
    file_path = tmp_path / "notes.txt"
    file_path.write_text("Hello knowledge base", encoding="utf-8")

    captured: dict[str, object] = {}

    _patch_importer_embedder(monkeypatch)

    async def fake_insert_vectors(**kwargs):
        captured.update(kwargs)
        return len(kwargs["chunks"])

    monkeypatch.setattr(
        "app.knowledge.importer.milvus_client.insert_vectors", fake_insert_vectors
    )

    doc = await importer.import_file(
        kb_id="kb-42",
        user_id="user-42",
        file_path=file_path,
        original_filename="notes.txt",
    )

    assert doc.id
    assert captured["document_id"] == doc.id
    assert captured["kb_id"] == "kb-42"
    assert captured["user_id"] == "user-42"
    assert doc.status == "indexed"
    assert doc.chunk_count == 1


def test_chunk_text_short_document_returns_single_chunk():
    chunks = chunk_text("short note", ChunkConfig(strategy="fixed", size=500, overlap=0))
    assert len(chunks) == 1
    assert chunks[0] == "short note"


@pytest.mark.asyncio
async def test_create_document_passes_kb_user_id_to_indexer(db_session, monkeypatch):
    kb = KnowledgeBase(user_id="owner-1", name="KB")
    db_session.add(kb)
    await db_session.flush()

    enqueued: list[str] = []

    def fake_enqueue(doc_id: str) -> None:
        enqueued.append(doc_id)

    monkeypatch.setattr(
        "app.knowledge.index_runner.enqueue_index_document", fake_enqueue
    )

    service = KnowledgeService(db_session)
    response = await service.create_document(
        kb_id=kb.id,
        user_id=kb.user_id,
        data=DocumentCreate(title="Guide", content="Hello world"),
    )

    # Indexing is now deferred: the document is created in "processing" state
    # and handed to the background runner.
    assert response.status == "processing"
    assert enqueued == [response.id]


@pytest.mark.asyncio
async def test_import_file_and_url_pass_kb_user_id(db_session, monkeypatch, tmp_path: Path):
    kb = KnowledgeBase(user_id="owner-2", name="KB")
    db_session.add(kb)
    await db_session.flush()

    enqueued: list[str] = []

    def fake_enqueue(doc_id: str) -> None:
        enqueued.append(doc_id)

    monkeypatch.setattr(
        "app.knowledge.index_runner.enqueue_index_document", fake_enqueue
    )
    # import_url fetches the URL inline; stub httpx so no network is used.
    class _FakeResponse:
        text = "url body"

        def raise_for_status(self) -> None:
            return None

    class _FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url):
            return _FakeResponse()

    monkeypatch.setattr("httpx.AsyncClient", _FakeClient)

    service = KnowledgeService(db_session)
    upload = UploadFile(filename="notes.txt", file=io.BytesIO(b"hello"))

    file_item = await service.import_file(kb_id=kb.id, user_id=kb.user_id, file=upload)
    url_resp = await service.import_url(
        kb_id=kb.id,
        user_id=kb.user_id,
        url="https://example.com/help",
    )

    # Both return immediately in "processing" and are enqueued for background indexing.
    assert file_item.status == "processing"
    assert file_item.title == "notes.txt"
    assert url_resp.status == "processing"
    assert url_resp.source_url == "https://example.com/help"
    assert len(enqueued) == 2


@pytest.mark.asyncio
async def test_folder_crud_and_nesting(db_session):
    kb = KnowledgeBase(user_id="owner-fold", name="KB")
    db_session.add(kb)
    await db_session.flush()

    service = KnowledgeService(db_session)
    parent = await service.create_folder(
        kb_id=kb.id, user_id=kb.user_id, data=FolderCreate(name="产品文档")
    )
    child = await service.create_folder(
        kb_id=kb.id,
        user_id=kb.user_id,
        data=FolderCreate(name="需求", parent_id=parent.id),
    )

    assert parent.parent_id is None
    assert child.parent_id == parent.id

    folders = await service.list_folders(kb_id=kb.id, user_id=kb.user_id)
    names = {f.name for f in folders}
    assert {"产品文档", "需求"} <= names

    # Rename
    renamed = await service.update_folder(
        folder_id=child.id,
        user_id=kb.user_id,
        data=FolderUpdate(name="需求文档"),
    )
    assert renamed.name == "需求文档"


@pytest.mark.asyncio
async def test_folder_cycle_prevention(db_session):
    kb = KnowledgeBase(user_id="owner-cycle", name="KB")
    db_session.add(kb)
    await db_session.flush()

    service = KnowledgeService(db_session)
    a = await service.create_folder(kb_id=kb.id, user_id=kb.user_id, data=FolderCreate(name="A"))
    b = await service.create_folder(
        kb_id=kb.id, user_id=kb.user_id, data=FolderCreate(name="B", parent_id=a.id)
    )
    # Moving A into its own descendant B must be rejected.
    with pytest.raises(HTTPException) as exc:
        await service.update_folder(
            folder_id=a.id, user_id=kb.user_id, data=FolderUpdate(parent_id=b.id)
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_import_file_into_folder_and_move(db_session, monkeypatch, tmp_path):
    kb = KnowledgeBase(user_id="owner-imp", name="KB")
    db_session.add(kb)
    await db_session.flush()

    def fake_enqueue(doc_id: str) -> None:
        return None

    monkeypatch.setattr(
        "app.knowledge.index_runner.enqueue_index_document", fake_enqueue
    )

    service = KnowledgeService(db_session)
    folder = await service.create_folder(
        kb_id=kb.id, user_id=kb.user_id, data=FolderCreate(name="Docs")
    )
    upload = UploadFile(filename="notes.txt", file=io.BytesIO(b"hello"))
    item = await service.import_file(
        kb_id=kb.id, user_id=kb.user_id, file=upload, folder_id=folder.id
    )
    assert item.folder_id == folder.id

    # Move it back to the root.
    moved = await service.move_document(
        doc_id=item.id,
        user_id=kb.user_id,
        data=DocumentMoveRequest(folder_id=None),
    )
    assert moved.folder_id is None


@pytest.mark.asyncio
async def test_delete_folder_cleans_vectors_and_documents(db_session, monkeypatch):
    kb = KnowledgeBase(user_id="owner-del", name="KB")
    db_session.add(kb)
    await db_session.flush()

    deleted_vectors: list[str] = []
    deleted_chunks: list[str] = []

    monkeypatch.setattr(
        "app.services.knowledge_service.milvus_client._connected", True
    )

    async def fake_delete_vectors(doc_id: str):
        deleted_vectors.append(doc_id)

    monkeypatch.setattr(
        "app.services.knowledge_service.milvus_client.delete_vectors",
        fake_delete_vectors,
    )

    async def fake_delete_chunks(session, doc_id: str):
        deleted_chunks.append(doc_id)

    monkeypatch.setattr(
        "app.services.knowledge_service.delete_document_chunks", fake_delete_chunks
    )

    service = KnowledgeService(db_session)
    parent = await service.create_folder(
        kb_id=kb.id, user_id=kb.user_id, data=FolderCreate(name="P")
    )
    child = await service.create_folder(
        kb_id=kb.id, user_id=kb.user_id, data=FolderCreate(name="C", parent_id=parent.id)
    )
    # A document in the child folder (nested).
    doc_child = Document(
        knowledge_base_id=kb.id,
        folder_id=child.id,
        title="nested",
        content="nested content",
        status="indexed",
    )
    # A document directly under parent.
    doc_parent = Document(
        knowledge_base_id=kb.id,
        folder_id=parent.id,
        title="parent doc",
        content="parent content",
        status="indexed",
    )
    db_session.add_all([doc_child, doc_parent])
    await db_session.flush()

    ok = await service.delete_folder(folder_id=parent.id, user_id=kb.user_id)
    assert ok is True
    # Both documents' vectors and chunks must be cleaned (recursively).
    assert sorted(deleted_vectors) == sorted([doc_child.id, doc_parent.id])
    assert sorted(deleted_chunks) == sorted([doc_child.id, doc_parent.id])

    # Folder and its subtree are gone.
    remaining = await service.list_folders(kb_id=kb.id, user_id=kb.user_id)
    assert remaining == []
