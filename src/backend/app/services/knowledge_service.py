"""Knowledge service - business logic for knowledge management."""

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
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
from app.models.knowledge import Document, DocumentFolder, KnowledgeBase
from app.services.storage_service import storage_service
from app.schemas.knowledge import (
    DocumentCreate,
    DocumentListItem,
    DocumentMoveRequest,
    DocumentResponse,
    FolderCreate,
    FolderResponse,
    FolderUpdate,
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
        folder_id=doc.folder_id,
        title=doc.title,
        source=doc.source,
        status=doc.status,
        chunk_count=doc.chunk_count,
        file_size=len(doc.content or ""),
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


def _folder_to_response(folder: DocumentFolder) -> FolderResponse:
    return FolderResponse(
        id=folder.id,
        knowledge_base_id=folder.knowledge_base_id,
        parent_id=folder.parent_id,
        name=folder.name,
        sort_order=folder.sort_order,
        document_count=len(folder.documents) if folder.documents is not None else 0,
        created_at=folder.created_at,
        updated_at=folder.updated_at,
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
        self, kb_id: str, user_id: str, folder_id: str | None = None
    ) -> list[DocumentListItem]:
        if await self._get_kb_row(kb_id, user_id) is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Knowledge base not found",
            )

        query = select(Document).where(Document.knowledge_base_id == kb_id)
        if folder_id is not None:
            query = query.where(Document.folder_id == folder_id)
        result = await self.db.execute(query.order_by(Document.created_at.desc()))
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

        if data.folder_id:
            await self._ensure_folder_in_kb(data.folder_id, kb_id, user_id, write=True)

        doc = Document(
            knowledge_base_id=kb_id,
            folder_id=data.folder_id,
            title=data.title,
            content=data.content,
            source=data.source or "manual",
            source_url=data.source_url,
            status="processing",
        )
        self.db.add(doc)
        await self.db.flush()

        # Indexing is deferred to the background runner so this request returns
        # promptly instead of blocking on parse → chunk → embed.
        from app.knowledge.index_runner import enqueue_index_document

        enqueue_index_document(doc.id)
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

    async def move_document(
        self, doc_id: str, user_id: str, data: DocumentMoveRequest
    ) -> DocumentListItem | None:
        """Move a document into a folder (or to the kb root when folder_id is null)."""
        result = await self.db.execute(select(Document).where(Document.id == doc_id))
        doc = result.scalar_one_or_none()
        if doc is None:
            return None
        kb = await self._get_kb_row(doc.knowledge_base_id, user_id, write=True)
        if kb is None:
            return None
        if data.folder_id:
            await self._ensure_folder_in_kb(data.folder_id, doc.knowledge_base_id, user_id, write=True)
        doc.folder_id = data.folder_id
        await self.db.flush()
        await self.db.refresh(doc)
        return _doc_to_list_item(doc)

    # ---- Folders -----------------------------------------------------------

    async def _ensure_folder_in_kb(
        self,
        folder_id: str,
        kb_id: str,
        user_id: str,
        *,
        write: bool = False,
    ) -> DocumentFolder:
        """Validate the kb owns the folder (and the caller can access it)."""
        if await self._get_kb_row(kb_id, user_id, write=write) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found")
        result = await self.db.execute(
            select(DocumentFolder).where(
                DocumentFolder.id == folder_id,
                DocumentFolder.knowledge_base_id == kb_id,
            )
        )
        folder = result.scalar_one_or_none()
        if folder is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found")
        return folder

    async def _collect_subtree_ids(self, folder_id: str) -> list[str]:
        """Return folder_id and all descendant folder ids (BFS)."""
        ids: list[str] = [folder_id]
        queue = [folder_id]
        while queue:
            result = await self.db.execute(
                select(DocumentFolder.id).where(DocumentFolder.parent_id.in_(queue))
            )
            child_ids = [row[0] for row in result.all()]
            ids.extend(child_ids)
            queue = child_ids
        return ids

    async def list_folders(
        self, kb_id: str, user_id: str
    ) -> list[FolderResponse]:
        if await self._get_kb_row(kb_id, user_id) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found")
        result = await self.db.execute(
            select(DocumentFolder)
            .where(DocumentFolder.knowledge_base_id == kb_id)
            .order_by(DocumentFolder.sort_order, DocumentFolder.name)
        )
        folders = result.scalars().all()
        return [_folder_to_response(f) for f in folders]

    async def create_folder(
        self, kb_id: str, user_id: str, data: FolderCreate
    ) -> FolderResponse:
        kb = await self._get_kb_row(kb_id, user_id, write=True)
        if kb is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found")
        if data.parent_id:
            await self._ensure_folder_in_kb(data.parent_id, kb_id, user_id, write=True)
        folder = DocumentFolder(
            knowledge_base_id=kb_id,
            parent_id=data.parent_id,
            name=data.name,
        )
        self.db.add(folder)
        await self.db.flush()
        await self.db.refresh(folder)
        return _folder_to_response(folder)

    async def update_folder(
        self, folder_id: str, user_id: str, data: FolderUpdate
    ) -> FolderResponse | None:
        result = await self.db.execute(
            select(DocumentFolder).where(DocumentFolder.id == folder_id)
        )
        folder = result.scalar_one_or_none()
        if folder is None:
            return None
        if await self._get_kb_row(folder.knowledge_base_id, user_id, write=True) is None:
            return None

        if data.parent_id is not None:
            # Moving the folder; "" -> root (parent_id None).
            new_parent = data.parent_id or None
            if new_parent == folder.id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A folder cannot be its own parent")
            if new_parent:
                await self._ensure_folder_in_kb(new_parent, folder.knowledge_base_id, user_id, write=True)
                # Prevent moving a folder into itself or any of its descendants.
                descendant_ids = await self._collect_subtree_ids(folder.id)
                if new_parent in descendant_ids:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Cannot move a folder into its own descendant",
                    )
            folder.parent_id = new_parent
        if data.name is not None:
            folder.name = data.name
        await self.db.flush()
        await self.db.refresh(folder)
        return _folder_to_response(folder)

    async def delete_folder(
        self, folder_id: str, user_id: str
    ) -> bool:
        """Delete a folder, its subfolders, and all documents inside.

        Vectors and chunks are cleaned up manually because ORM cascade does
        not touch Milvus.
        """
        result = await self.db.execute(
            select(DocumentFolder).where(DocumentFolder.id == folder_id)
        )
        folder = result.scalar_one_or_none()
        if folder is None:
            return False
        if await self._get_kb_row(folder.knowledge_base_id, user_id, write=True) is None:
            return False

        subtree_ids = await self._collect_subtree_ids(folder.id)
        doc_result = await self.db.execute(
            select(Document).where(Document.folder_id.in_(subtree_ids))
        )
        docs = list(doc_result.scalars().all())
        for doc in docs:
            if milvus_client._connected:
                await milvus_client.delete_vectors(doc.id)
            await delete_document_chunks(self.db, doc.id)
            await self.db.delete(doc)

        await self.db.delete(folder)
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
        self, kb_id: str, user_id: str, file: UploadFile, folder_id: str | None = None
    ) -> DocumentListItem:
        kb = await self._get_kb_row(kb_id, user_id, write=True)
        if kb is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Knowledge base not found",
            )

        if folder_id:
            await self._ensure_folder_in_kb(folder_id, kb_id, user_id, write=True)

        if milvus_client._connected and align_kb_embedding_to_milvus(kb):
            await self.db.flush()

        content = await file.read()
        stored = storage_service.save_bytes(
            content,
            filename=file.filename or "upload.dat",
            content_type=file.content_type,
            prefix="knowledge",
        )

        # The background runner needs a durable local file to parse from. In
        # local-storage mode the saved object already lives under uploads/; for
        # S3 backends we mirror a copy to disk so parsing works offline.
        file_path = stored.local_path
        if file_path is None:
            from app.utils.upload_paths import safe_upload_file_path

            mirrored = safe_upload_file_path(stored.key)
            if mirrored is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid upload path for knowledge file",
                )
            mirrored.parent.mkdir(parents=True, exist_ok=True)
            mirrored.write_bytes(content)
            file_path = mirrored

        suffix = (file.filename or "upload.dat").rsplit(".", 1)[-1].lower()
        doc = Document(
            knowledge_base_id=kb_id,
            folder_id=folder_id,
            title=file.filename or "unknown",
            content="",
            source=suffix,
            status="processing",
            source_file_path=str(file_path),
        )
        self.db.add(doc)
        await self.db.flush()
        await self.db.refresh(doc)

        # Defer parse → chunk → embed to the background runner so this request
        # returns immediately and does not block the event loop.
        from app.knowledge.index_runner import enqueue_index_document

        enqueue_index_document(doc.id)
        return _doc_to_list_item(doc)

    async def import_url(
        self, kb_id: str, user_id: str, url: str
    ) -> DocumentResponse:
        kb = await self._get_kb_row(kb_id, user_id, write=True)
        if kb is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Knowledge base not found",
            )

        # Fetch URL content here (fast IO + immediate error feedback to caller),
        # then defer the CPU-heavy chunk/embed work to the background runner.
        import httpx

        try:
            async with httpx.AsyncClient(
                timeout=30.0, follow_redirects=True
            ) as client:
                response = await client.get(url)
                response.raise_for_status()
                content = response.text
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to fetch URL: {e}",
            )

        doc = Document(
            knowledge_base_id=kb_id,
            title=url,
            content=content,
            source="url",
            source_url=url,
            status="processing",
        )
        self.db.add(doc)
        await self.db.flush()
        await self.db.refresh(doc)

        from app.knowledge.index_runner import enqueue_index_document

        enqueue_index_document(doc.id)
        return DocumentResponse.model_validate(doc)
