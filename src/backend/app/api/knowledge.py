"""Knowledge base API router."""

from fastapi import (
    APIRouter,
    Depends,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from pydantic import BaseModel

from app.core.database import get_db
from app.middleware.auth import require_permission, Permission
from app.models.user import User
from app.schemas.knowledge import (
    DocumentCreate,
    DocumentListItem,
    DocumentResponse,
    KnowledgeBaseCreate,
    KnowledgeBaseResponse,
    KnowledgeBaseUpdate,
    ReindexRequest,
    ReindexResponse,
    SearchRequest,
    SearchResponse,
)
from app.schemas.embedding_model import EmbeddingModelResponse, EmbeddingModelUploadResponse
from app.services.embedding_model_service import EmbeddingModelService
from app.services.knowledge_service import KnowledgeService

router = APIRouter()


@router.get("/embedding-models", response_model=list[EmbeddingModelResponse])
async def list_embedding_models(
    admin: User = Depends(require_permission(Permission.KNOWLEDGE_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    """List uploaded local embedding models."""
    service = EmbeddingModelService(db)
    return await service.list_models(user_id=admin.id)


@router.post(
    "/embedding-models/upload",
    response_model=EmbeddingModelUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_embedding_model(
    file: UploadFile,
    name: str | None = Form(None),
    admin: User = Depends(require_permission(Permission.KNOWLEDGE_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    """Upload a .zip HuggingFace / sentence-transformers model for local embedding."""
    service = EmbeddingModelService(db)
    model = await service.upload_model(user_id=admin.id, file=file, name=name)
    return EmbeddingModelUploadResponse(
        model=model,
        message="模型已上传并校验通过" if model.status == "ready" else "模型处理失败",
    )


@router.delete("/embedding-models/{model_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_embedding_model(
    model_id: str,
    admin: User = Depends(require_permission(Permission.KNOWLEDGE_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    service = EmbeddingModelService(db)
    deleted = await service.delete_model(model_id=model_id, user_id=admin.id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Embedding model not found",
        )
    return None


@router.post("/bases", response_model=KnowledgeBaseResponse, status_code=status.HTTP_201_CREATED)
async def create_knowledge_base(
    request: KnowledgeBaseCreate,
    admin: User = Depends(require_permission(Permission.KNOWLEDGE_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    """Create a new knowledge base."""
    service = KnowledgeService(db)
    return await service.create_knowledge_base(
        user_id=admin.id, data=request
    )


@router.get("/bases", response_model=list[KnowledgeBaseResponse])
async def list_knowledge_bases(
    group_id: str | None = None,
    admin: User = Depends(require_permission(Permission.KNOWLEDGE_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    """List all knowledge bases for current user."""
    service = KnowledgeService(db)
    return await service.list_knowledge_bases(user_id=admin.id, group_id=group_id)


@router.get("/bases/{kb_id}", response_model=KnowledgeBaseResponse)
async def get_knowledge_base(
    kb_id: str,
    admin: User = Depends(require_permission(Permission.KNOWLEDGE_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific knowledge base."""
    service = KnowledgeService(db)
    kb = await service.get_knowledge_base(
        kb_id=kb_id, user_id=admin.id
    )
    if kb is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found",
        )
    return kb


@router.patch("/bases/{kb_id}", response_model=KnowledgeBaseResponse)
async def update_knowledge_base(
    kb_id: str,
    request: KnowledgeBaseUpdate,
    admin: User = Depends(require_permission(Permission.KNOWLEDGE_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    """Update knowledge base settings including RAG configuration."""
    service = KnowledgeService(db)
    kb = await service.update_knowledge_base(
        kb_id=kb_id, user_id=admin.id, data=request
    )
    if kb is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found",
        )
    return kb


class KbTokenizerFileContent(BaseModel):
    content: str = ""


@router.get("/bases/{kb_id}/tokenizer/user_dict")
async def read_kb_user_dict(
    kb_id: str,
    admin: User = Depends(require_permission(Permission.KNOWLEDGE_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    """Read per-knowledge-base user dictionary file."""
    service = KnowledgeService(db)
    kb = await service.get_knowledge_base(kb_id=kb_id, user_id=admin.id)
    if kb is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found")
    from app.knowledge.tokenizer_files import read_kb_tokenizer_file

    return read_kb_tokenizer_file(kb_id)


@router.put("/bases/{kb_id}/tokenizer/user_dict")
async def write_kb_user_dict(
    kb_id: str,
    request: KbTokenizerFileContent,
    admin: User = Depends(require_permission(Permission.KNOWLEDGE_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    """Write per-knowledge-base user dictionary file."""
    service = KnowledgeService(db)
    kb = await service.get_knowledge_base(kb_id=kb_id, user_id=admin.id)
    if kb is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found")
    from app.knowledge.bm25 import bm25_index
    from app.knowledge.tokenizer_files import write_kb_tokenizer_file

    result = write_kb_tokenizer_file(kb_id, request.content)
    bm25_index.invalidate(kb_id)
    return result


@router.post("/bases/{kb_id}/reindex", response_model=ReindexResponse)
async def reindex_knowledge_base(
    kb_id: str,
    request: ReindexRequest | None = None,
    admin: User = Depends(require_permission(Permission.KNOWLEDGE_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    """Re-embed all documents after embedding or chunk settings change."""
    service = KnowledgeService(db)
    try:
        return await service.reindex_knowledge_base(
            kb_id=kb_id,
            user_id=admin.id,
            options=request or ReindexRequest(),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Reindex failed: {e}",
        )


@router.delete("/bases/{kb_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_knowledge_base(
    kb_id: str,
    admin: User = Depends(require_permission(Permission.KNOWLEDGE_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    """Delete a knowledge base."""
    service = KnowledgeService(db)
    success = await service.delete_knowledge_base(
        kb_id=kb_id, user_id=admin.id
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found",
        )
    return None


@router.get("/bases/{kb_id}/documents", response_model=list[DocumentListItem])
async def list_documents(
    kb_id: str,
    admin: User = Depends(require_permission(Permission.KNOWLEDGE_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    """List all documents in a knowledge base."""
    service = KnowledgeService(db)
    return await service.list_documents(
        kb_id=kb_id, user_id=admin.id
    )


@router.post("/bases/{kb_id}/documents", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def create_document(
    kb_id: str,
    request: DocumentCreate,
    admin: User = Depends(require_permission(Permission.KNOWLEDGE_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    """Add a document to a knowledge base and index it."""
    service = KnowledgeService(db)
    return await service.create_document(
        kb_id=kb_id, user_id=admin.id, data=request
    )


@router.delete("/documents/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    doc_id: str,
    admin: User = Depends(require_permission(Permission.KNOWLEDGE_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    """Delete a document."""
    service = KnowledgeService(db)
    success = await service.delete_document(
        doc_id=doc_id, user_id=admin.id
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    return None


@router.post("/search", response_model=SearchResponse)
async def search_documents(
    request: SearchRequest,
    admin: User = Depends(require_permission(Permission.KNOWLEDGE_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    """Search documents using semantic search."""
    service = KnowledgeService(db)
    return await service.search(
        query=request.query,
        user_id=admin.id,
        knowledge_base_id=request.knowledge_base_id,
        top_k=request.top_k,
    )


@router.post("/bases/{kb_id}/import-file", response_model=DocumentListItem)
async def import_file(
    kb_id: str,
    file: UploadFile,
    admin: User = Depends(require_permission(Permission.KNOWLEDGE_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    """Import a file into a knowledge base."""
    service = KnowledgeService(db)
    try:
        doc = await service.import_file(
            kb_id=kb_id,
            user_id=admin.id,
            file=file,
        )
        return doc
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Import failed: {e}",
        )


@router.post("/bases/{kb_id}/import-url")
async def import_url(
    kb_id: str,
    url: str,
    admin: User = Depends(require_permission(Permission.KNOWLEDGE_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    """Import content from a URL into a knowledge base."""
    service = KnowledgeService(db)
    try:
        doc = await service.import_url(
            kb_id=kb_id,
            user_id=admin.id,
            url=url,
        )
        return doc
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"URL import failed: {e}",
        )
