"""Knowledge service - business logic for knowledge management."""

import tempfile
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import inspect as sa_inspect, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.chunk_store import delete_document_chunks
from app.knowledge.embedding_fingerprint import needs_reindex
from app.knowledge.importer import DocumentImporter
from app.knowledge.milvus_client import milvus_client
from app.knowledge.embedding_align import align_kb_embedding_to_milvus
from app.knowledge.rag import RagService
from app.knowledge.rag_config import rag_settings_from_kb
from app.core.config import settings as app_settings
from app.models.group import GroupMember
from app.models.knowledge import Document, KnowledgeBase
from app.services.storage_service import storage_service
from app.schemas.knowledge import (
    DocumentCreate,
    DocumentListItem,
    DocumentResponse,
    KnowledgeBaseCreate,
    KnowledgeBaseResponse,
    KnowledgeBaseUpdate,
    ReindexRequest,
    ReindexResponse,
    SearchResponse,
    DocumentReindexResult,
)


def _kb_to_response(kb: KnowledgeBase) -> KnowledgeBaseResponse:
    return KnowledgeBaseResponse(
        id=kb.id,
        user_id=kb.user_id,
        group_id=kb.group_id,
        name=kb.name,
        description=kb.description,
        enabled=kb.enabled,
        document_count=len(kb.documents) if kb.documents is not None else 0,
        chunk_strategy=kb.chunk_strategy,
        chunk_size=kb.chunk_size,
        chunk_overlap=kb.chunk_overlap,
        chunk_min_size=kb.chunk_min_size,
        chunk_semantic_threshold=kb.chunk_semantic_threshold,
        chunk_parent_enabled=kb.chunk_parent_enabled,
        embedding_provider=kb.embedding_provider,
        embedding_model=kb.embedding_model,
        embedding_api_base=kb.embedding_api_base,
        embedding_dimension=kb.embedding_dimension,
        retrieval_mode=kb.retrieval_mode,
        retrieval_top_k=kb.retrieval_top_k,
        retrieval_candidate_k=kb.retrieval_candidate_k,
        rerank_enabled=kb.rerank_enabled,
        rerank_top_n=kb.rerank_top_n,
        retrieval_bm25_enabled=kb.retrieval_bm25_enabled,
        retrieval_bm25_k1=kb.retrieval_bm25_k1,
        retrieval_bm25_b=kb.retrieval_bm25_b,
        rerank_provider=kb.rerank_provider,
        rerank_model=kb.rerank_model,
        retrieval_query_rewrite_enabled=kb.retrieval_query_rewrite_enabled,
        retrieval_query_rewrite_count=kb.retrieval_query_rewrite_count,
        retrieval_stop_words=kb.retrieval_stop_words,
        retrieval_query_suffix_chars=kb.retrieval_query_suffix_chars,
        retrieval_user_dict=kb.retrieval_user_dict,
        retrieval_keyword_backend=kb.retrieval_keyword_backend,
        indexed_embedding_key=kb.indexed_embedding_key,
        needs_reindex=needs_reindex(kb),
        reindex_status=kb.reindex_status,
        created_at=kb.created_at,
        updated_at=kb.updated_at,
    )


def _apply_rag_fields(kb: KnowledgeBase, data: KnowledgeBaseCreate | KnowledgeBaseUpdate) -> None:
    fields = [
        "chunk_strategy",
        "chunk_size",
        "chunk_overlap",
        "chunk_min_size",
        "chunk_semantic_threshold",
        "chunk_parent_enabled",
        "embedding_provider",
        "embedding_model",
        "embedding_api_base",
        "embedding_dimension",
        "retrieval_mode",
        "retrieval_top_k",
        "retrieval_candidate_k",
        "rerank_enabled",
        "rerank_top_n",
        "retrieval_bm25_enabled",
        "retrieval_bm25_k1",
        "retrieval_bm25_b",
        "rerank_provider",
        "rerank_model",
        "retrieval_query_rewrite_enabled",
        "retrieval_query_rewrite_count",
        "retrieval_stop_words",
        "retrieval_query_suffix_chars",
        "retrieval_user_dict",
        "retrieval_keyword_backend",
    ]
    tokenizer_fields = {
        "retrieval_user_dict",
    }
    tokenizer_changed = False
    for field in fields:
        value = getattr(data, field, None)
        if value is not None:
            if field in tokenizer_fields:
                tokenizer_changed = True
            setattr(kb, field, value)
    if tokenizer_changed:
        from app.knowledge.bm25 import bm25_index

        bm25_index.invalidate(kb.id)


def _doc_to_list_item(doc: Document) -> DocumentListItem:
    return DocumentListItem(
        id=doc.id,
        knowledge_base_id=doc.knowledge_base_id,
        title=doc.title,
        source=doc.source,
        status=doc.status,
        chunk_count=doc.chunk_count,
        file_size=len(doc.content or ""),
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


class KnowledgeService:
    """Handles knowledge base business logic."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _group_role(self, group_id: str, user_id: str) -> str | None:
        result = await self.db.execute(
            select(GroupMember.role).where(
                GroupMember.group_id == group_id,
                GroupMember.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def _ensure_group_role(
        self,
        group_id: str,
        user_id: str,
        *,
        write: bool = False,
    ) -> str:
        role = await self._group_role(group_id, user_id)
        if role is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Group access denied",
            )
        if write and role not in {"owner", "editor"}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Group write access denied",
            )
        return role

    async def _get_kb_row(self, kb_id: str, user_id: str, *, write: bool = False) -> KnowledgeBase | None:
        result = await self.db.execute(
            select(KnowledgeBase).where(KnowledgeBase.id == kb_id)
        )
        kb = result.scalar_one_or_none()
        if kb is None:
            return None
        if kb.group_id:
            await self._ensure_group_role(kb.group_id, user_id, write=write)
            return kb
        if kb.user_id != user_id:
            return None
        return kb

    async def create_knowledge_base(
        self, user_id: str, data: KnowledgeBaseCreate
    ) -> KnowledgeBaseResponse:
        if data.group_id:
            await self._ensure_group_role(data.group_id, user_id, write=True)
        kb = KnowledgeBase(
            user_id=user_id,
            group_id=data.group_id,
            name=data.name,
            description=data.description,
            enabled=data.enabled,
        )
        _apply_rag_fields(kb, data)
        if getattr(data, "embedding_dimension", None) is None:
            kb.embedding_dimension = int(app_settings.embedding_dimension)
        if kb.embedding_provider is None:
            kb.embedding_provider = app_settings.embedding_provider
        if kb.embedding_model is None:
            kb.embedding_model = app_settings.embedding_model
        self.db.add(kb)
        await self.db.flush()
        await self.db.refresh(kb)
        return _kb_to_response(kb)

    async def update_knowledge_base(
        self, kb_id: str, user_id: str, data: KnowledgeBaseUpdate
    ) -> KnowledgeBaseResponse | None:
        kb = await self._get_kb_row(kb_id, user_id, write=True)
        if kb is None:
            return None
        if data.name is not None:
            kb.name = data.name
        if data.description is not None:
            kb.description = data.description
        if data.enabled is not None:
            kb.enabled = data.enabled
        if data.group_id is not None:
            if data.group_id:
                await self._ensure_group_role(data.group_id, user_id, write=True)
            kb.group_id = data.group_id
        _apply_rag_fields(kb, data)
        await self.db.flush()
        await self.db.refresh(kb)
        return _kb_to_response(kb)

    async def list_knowledge_bases(
        self, user_id: str, *, group_id: str | None = None
    ) -> list[KnowledgeBaseResponse]:
        query = select(KnowledgeBase)
        if group_id:
            await self._ensure_group_role(group_id, user_id)
            query = query.where(KnowledgeBase.group_id == group_id)
        else:
            query = query.where(KnowledgeBase.user_id == user_id, KnowledgeBase.group_id.is_(None))
        result = await self.db.execute(query.order_by(KnowledgeBase.created_at.desc()))
        kbs = result.scalars().all()
        return [_kb_to_response(kb) for kb in kbs]

    async def get_knowledge_base(
        self, kb_id: str, user_id: str
    ) -> KnowledgeBaseResponse | None:
        kb = await self._get_kb_row(kb_id, user_id)
        if kb is None:
            return None
        return _kb_to_response(kb)

    async def delete_knowledge_base(
        self, kb_id: str, user_id: str
    ) -> bool:
        kb = await self._get_kb_row(kb_id, user_id, write=True)
        if kb is None:
            return False
        await self.db.delete(kb)
        await self.db.flush()
        return True

    async def list_documents(
        self, kb_id: str, user_id: str
    ) -> list[DocumentListItem]:
        if await self._get_kb_row(kb_id, user_id) is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Knowledge base not found",
            )

        result = await self.db.execute(
            select(Document)
            .where(Document.knowledge_base_id == kb_id)
            .order_by(Document.created_at.desc())
        )
        docs = result.scalars().all()
        return [_doc_to_list_item(d) for d in docs]

    async def create_document(
        self, kb_id: str, user_id: str, data: DocumentCreate
    ) -> DocumentResponse:
        kb = await self._get_kb_row(kb_id, user_id, write=True)
        if kb is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Knowledge base not found",
            )

        doc = Document(
            knowledge_base_id=kb_id,
            title=data.title,
            content=data.content,
            source=data.source or "manual",
            source_url=data.source_url,
            status="pending",
        )
        self.db.add(doc)
        await self.db.flush()

        try:
            importer = DocumentImporter(
                rag_settings=rag_settings_from_kb(kb), db=self.db
            )
            chunk_count = await importer.index_document(doc, user_id=kb.user_id)
            doc.status = "indexed"
            doc.chunk_count = chunk_count
            if chunk_count > 0:
                await importer.mark_kb_indexed(kb)
        except Exception:
            doc.status = "failed"

        await self.db.flush()
        await self.db.refresh(doc)
        return DocumentResponse.model_validate(doc)

    async def reindex_knowledge_base(
        self,
        kb_id: str,
        user_id: str,
        options: ReindexRequest | None = None,
    ) -> ReindexResponse:
        """Re-embed all documents in a knowledge base."""
        opts = options or ReindexRequest()
        kb = await self._get_kb_row(kb_id, user_id)
        if kb is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Knowledge base not found",
            )
        if kb.reindex_status == "running":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Reindex already in progress for this knowledge base",
            )

        result = await self.db.execute(
            select(Document)
            .where(Document.knowledge_base_id == kb_id)
            .order_by(Document.created_at.asc())
        )
        documents = list(result.scalars().all())

        kb.reindex_status = "running"
        await self.db.flush()

        importer = DocumentImporter(rag_settings=rag_settings_from_kb(kb), db=self.db)
        outcomes: list[DocumentReindexResult] = []
        succeeded = 0
        failed = 0

        try:
            outcomes, succeeded, failed = await self._run_reindex_documents(
                kb=kb,
                documents=documents,
                importer=importer,
                rechunk=opts.rechunk,
            )
        except Exception:
            kb.reindex_status = "failed"
            await self.db.flush()
            raise
        finally:
            if kb.reindex_status == "running":
                kb.reindex_status = (
                    "completed" if succeeded > 0 else "failed"
                )
                await self.db.flush()

        if succeeded > 0:
            await importer.mark_kb_indexed(kb)

        return ReindexResponse(
            knowledge_base_id=kb_id,
            total=len(documents),
            succeeded=succeeded,
            failed=failed,
            rechunk=opts.rechunk,
            milvus_enabled=milvus_client._connected,
            indexed_embedding_key=kb.indexed_embedding_key,
            documents=outcomes,
        )

    async def _run_reindex_documents(
        self,
        *,
        kb: KnowledgeBase,
        documents: list[Document],
        importer: DocumentImporter,
        rechunk: bool,
    ) -> tuple[list[DocumentReindexResult], int, int]:
        outcomes: list[DocumentReindexResult] = []
        succeeded = 0
        failed = 0

        for doc in documents:
            if not (doc.content or "").strip():
                doc.status = "failed"
                doc.chunk_count = 0
                outcomes.append(
                    DocumentReindexResult(
                        document_id=doc.id,
                        title=doc.title,
                        status="failed",
                        error="Empty document content",
                    )
                )
                failed += 1
                continue

            try:
                count = await importer.reindex_document(
                    doc,
                    user_id=kb.user_id,
                    rechunk=rechunk,
                )
                if count > 0:
                    succeeded += 1
                    outcomes.append(
                        DocumentReindexResult(
                            document_id=doc.id,
                            title=doc.title,
                            status=doc.status,
                            chunk_count=count,
                        )
                    )
                else:
                    failed += 1
                    outcomes.append(
                        DocumentReindexResult(
                            document_id=doc.id,
                            title=doc.title,
                            status=doc.status,
                            error="No chunks produced",
                        )
                    )
            except Exception as exc:
                doc.status = "failed"
                failed += 1
                outcomes.append(
                    DocumentReindexResult(
                        document_id=doc.id,
                        title=doc.title,
                        status="failed",
                        error=str(exc),
                    )
                )

        kb.reindex_status = "completed" if succeeded > 0 else "failed"
        await self.db.flush()
        return outcomes, succeeded, failed

    async def delete_document(
        self, doc_id: str, user_id: str
    ) -> bool:
        result = await self.db.execute(
            select(Document).join(KnowledgeBase).where(
                Document.id == doc_id,
            )
        )
        doc = result.scalar_one_or_none()
        if doc is None:
            return False
        kb = await self._get_kb_row(doc.knowledge_base_id, user_id, write=True)
        if kb is None:
            return False
        if milvus_client._connected:
            await milvus_client.delete_vectors(doc.id)
        await delete_document_chunks(self.db, doc.id)
        await self.db.delete(doc)
        await self.db.flush()
        return True

    async def search(
        self,
        query: str,
        user_id: str,
        knowledge_base_id: str | None = None,
        top_k: int = 5,
    ) -> SearchResponse:
        rag_settings = None
        if knowledge_base_id:
            kb = await self._get_kb_row(knowledge_base_id, user_id)
            if kb:
                rag_settings = rag_settings_from_kb(kb)
        rag = RagService(rag_settings=rag_settings)
        return await rag.search(
            query=query,
            user_id=user_id,
            knowledge_base_id=knowledge_base_id,
            top_k=top_k,
        )

    async def import_file(
        self, kb_id: str, user_id: str, file: UploadFile
    ) -> DocumentListItem:
        kb = await self._get_kb_row(kb_id, user_id, write=True)
        if kb is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Knowledge base not found",
            )

        if milvus_client._connected and align_kb_embedding_to_milvus(kb):
            await self.db.flush()

        content = await file.read()
        stored = storage_service.save_bytes(
            content,
            filename=file.filename or "upload.dat",
            content_type=file.content_type,
            prefix="knowledge",
        )

        temp_path: Path | None = None
        file_path = stored.local_path
        if file_path is None:
            suffix = Path(file.filename or "upload.dat").suffix
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
                f.write(content)
                temp_path = Path(f.name)
            file_path = temp_path

        importer = DocumentImporter(rag_settings=rag_settings_from_kb(kb), db=self.db)
        try:
            doc = await importer.import_file(
                kb_id=kb_id,
                user_id=kb.user_id,
                file_path=file_path,
                original_filename=file.filename or "unknown",
                kb=kb,
            )
            if sa_inspect(doc).session is None:
                doc.knowledge_base_id = kb_id
                self.db.add(doc)
            if doc.status == "indexed" and doc.chunk_count > 0:
                await importer.mark_kb_indexed(kb)
            await self.db.flush()
            await self.db.refresh(doc)
            return _doc_to_list_item(doc)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to import file: {e}",
            )
        finally:
            if temp_path and temp_path.exists():
                temp_path.unlink(missing_ok=True)

    async def import_url(
        self, kb_id: str, user_id: str, url: str
    ) -> DocumentResponse:
        kb = await self._get_kb_row(kb_id, user_id, write=True)
        if kb is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Knowledge base not found",
            )

        importer = DocumentImporter(rag_settings=rag_settings_from_kb(kb), db=self.db)
        try:
            doc = await importer.import_url(
                kb_id=kb_id,
                user_id=kb.user_id,
                url=url,
                kb=kb,
            )
            if sa_inspect(doc).session is None:
                doc.knowledge_base_id = kb_id
                self.db.add(doc)
            if doc.status == "indexed" and doc.chunk_count > 0:
                await importer.mark_kb_indexed(kb)
            await self.db.flush()
            await self.db.refresh(doc)
            return DocumentResponse.model_validate(doc)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to import URL: {e}",
            )
