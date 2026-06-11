"""Chat API router."""

import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.middleware.auth import get_current_user, has_global_scope
from app.models.user import User
from app.schemas.chat import (
    ConversationList,
    ConversationResponse,
    ConversationStatsResponse,
    CreateConversationRequest,
    InitConversationRequest,
    MessageCreate,
    MessageResponse,
    ResumeConversationRequest,
)
from app.services.chat_service import ChatService
from app.utils.chat_upload import save_chat_attachment
from app.utils.request import extract_client_ip

router = APIRouter()


@router.post("/upload", response_model=MessageResponse)
async def upload_chat_attachment(
    conversation_id: str = Form(...),
    file: UploadFile = File(...),
    content: str | None = Form(None),
    role: str = Form("user"),
    extra_data_raw: str | None = Form(None, alias="extraData"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload an image or file and send it as a user message."""
    if role not in {"user", "assistant", "system"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid role",
        )

    parsed_extra_data: dict | None = None
    if extra_data_raw and extra_data_raw.strip():
        try:
            parsed_extra_data = json.loads(extra_data_raw)
        except json.JSONDecodeError as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid extraData JSON: {e.msg}",
            ) from e
        if not isinstance(parsed_extra_data, dict):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="extraData must be a JSON object",
            )

    attachment = await save_chat_attachment(
        file,
        user_id=current_user.id,
        conversation_id=conversation_id,
    )
    display = (content or "").strip() or attachment["name"]
    chat_service = ChatService(db)
    extra_data = dict(parsed_extra_data or {})
    attachments = list(extra_data.get("attachments") or [])
    attachments.append(attachment)
    extra_data["attachments"] = attachments

    try:
        return await chat_service.send_message(
            conversation_id=conversation_id,
            content=display,
            role=role,
            user=current_user,
            extra_data=extra_data,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send attachment: {e}",
        ) from e


@router.post("/send", response_model=MessageResponse)
async def send_message(
    request: MessageCreate,
    current_user: User | None = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send a message and get AI response."""
    chat_service = ChatService(db)
    try:
        result = await chat_service.send_message(
            conversation_id=request.conversation_id,
            content=request.content,
            role=request.role,
            user=current_user,
            extra_data=request.extra_data,
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send message: {e}",
        )


@router.get("/conversations", response_model=ConversationList)
async def list_conversations(
    skip: int = 0,
    limit: int = 50,
    status_filter: str | None = None,
    search: str | None = None,
    customer_id: str | None = None,
    scope_type: str | None = None,
    scope_id: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List conversations (admin sees all, agent sees own)."""
    chat_service = ChatService(db)
    user_id = None if await has_global_scope(current_user, db) else current_user.id
    conversations, total = await chat_service.list_conversations(
        user_id=user_id,
        skip=skip,
        limit=limit,
        status=status_filter,
        search=search,
        customer_id=customer_id,
        scope_type=scope_type,
        scope_id=scope_id,
    )
    return ConversationList(items=conversations, total=total)


@router.get("/conversations/stats", response_model=ConversationStatsResponse)
async def get_conversation_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get aggregate conversation stats for admin/agent scope."""
    chat_service = ChatService(db)
    user_id = None if await has_global_scope(current_user, db) else current_user.id
    stats = await chat_service.get_conversation_stats(user_id=user_id)
    return ConversationStatsResponse(**stats)


@router.post("/conversations", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    request: CreateConversationRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new conversation."""
    chat_service = ChatService(db)
    conversation = await chat_service.create_conversation(
        user_id=current_user.id,
        title=request.title,
        ai_config_id=request.ai_config_id,
        visitor_id=request.visitor_id,
        customer_id=request.customer_id,
        scope_type=request.scope_type,
        scope_id=request.scope_id,
    )
    return conversation


@router.post("/conversations/resume", response_model=ConversationResponse)
async def resume_channel_conversation(
    request: ResumeConversationRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Resume persistent channel chat (history + memory when Cloud studio is enabled)."""
    chat_service = ChatService(db)
    is_admin = await has_global_scope(current_user, db)
    return await chat_service.get_or_resume_channel_conversation(
        user_id=current_user.id,
        customer_id=request.customer_id,
        title=request.title,
        force_new=request.force_new,
        is_admin=is_admin,
        scope_type=request.scope_type,
        scope_id=request.scope_id,
    )


@router.get("/conversations/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get conversation with messages."""
    chat_service = ChatService(db)
    user_id = None if await has_global_scope(current_user, db) else current_user.id
    conversation = await chat_service.get_conversation(
        conversation_id=conversation_id,
        user_id=user_id,
    )
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )
    return conversation


@router.post("/conversations/{conversation_id}/close")
async def close_conversation(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Close a conversation."""
    chat_service = ChatService(db)
    user_id = None if await has_global_scope(current_user, db) else current_user.id
    success = await chat_service.close_conversation(
        conversation_id=conversation_id,
        user_id=user_id,
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )
    return {"status": "closed"}


@router.post("/conversations/init", response_model=ConversationResponse)
async def init_conversation(
    request: InitConversationRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Initialize a visitor conversation (no auth required)."""
    chat_service = ChatService(db)
    conversation = await chat_service.init_visitor_conversation(
        visitor_id=request.visitor_id,
        title=request.title,
        ai_config_id=request.ai_config_id,
        contact_info=request.contact_info,
        client_ip=extract_client_ip(http_request),
    )
    return conversation
