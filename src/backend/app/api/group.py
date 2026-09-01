"""Group collaboration API."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.middleware.auth import Permission, get_current_user, require_permission
from app.models.user import User
from app.schemas.chat import ConversationResponse
from app.schemas.group import (
    GroupChatResumeRequest,
    GroupCreateRequest,
    GroupMemoryCreateRequest,
    GroupMemoryRevisionResponse,
    GroupMemoryResponse,
    GroupMemoryUpdateRequest,
    GroupMemberResponse,
    GroupMemberUpsertRequest,
    GroupResponse,
    GroupUpdateRequest,
)
from app.services.chat_service import ChatService
from app.services.group_service import GroupService

router = APIRouter()


@router.get("/mine", response_model=list[GroupResponse])
async def list_my_groups(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await GroupService(db).list_groups_for_user(current_user.id)


@router.get("", response_model=list[GroupResponse])
async def list_groups(
    _admin: User = Depends(require_permission(Permission.USERS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    return await GroupService(db).list_groups()


@router.post("", response_model=GroupResponse, status_code=status.HTTP_201_CREATED)
async def create_group(
    request: GroupCreateRequest,
    admin: User = Depends(require_permission(Permission.USERS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    return await GroupService(db).create_group(admin.id, request)


@router.patch("/{group_id}", response_model=GroupResponse)
async def update_group(
    group_id: str,
    request: GroupUpdateRequest,
    admin: User = Depends(require_permission(Permission.USERS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    return await GroupService(db).update_group(group_id, admin.id, request)


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(
    group_id: str,
    _admin: User = Depends(require_permission(Permission.USERS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    await GroupService(db).delete_group(group_id)
    return None


@router.get("/{group_id}/members", response_model=list[GroupMemberResponse])
async def list_group_members(
    group_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await GroupService(db).list_members(group_id, current_user.id)


@router.post("/{group_id}/members", response_model=GroupMemberResponse)
async def upsert_group_member(
    group_id: str,
    request: GroupMemberUpsertRequest,
    _admin: User = Depends(require_permission(Permission.USERS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    return await GroupService(db).upsert_member(group_id, request)


@router.delete("/{group_id}/members/{member_user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group_member(
    group_id: str,
    member_user_id: str,
    _admin: User = Depends(require_permission(Permission.USERS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    await GroupService(db).remove_member(group_id, member_user_id)
    return None


@router.post("/{group_id}/chat/resume", response_model=ConversationResponse)
async def resume_group_chat(
    group_id: str,
    request: GroupChatResumeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationResponse:
    """Open or resume group chat for the current member (no personal assistant needed)."""
    return await ChatService(db).get_or_resume_group_conversation(
        user_id=current_user.id,
        group_id=group_id,
        title=request.title,
        force_new=request.force_new,
    )


@router.get("/{group_id}/memories", response_model=list[GroupMemoryResponse])
async def list_group_memories(
    group_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await GroupService(db).list_memories(group_id, current_user.id)


@router.post("/{group_id}/memories", response_model=GroupMemoryResponse, status_code=status.HTTP_201_CREATED)
async def create_group_memory(
    group_id: str,
    request: GroupMemoryCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await GroupService(db).create_memory(group_id, current_user.id, request)


@router.patch("/{group_id}/memories/{memory_id}", response_model=GroupMemoryResponse)
async def update_group_memory(
    group_id: str,
    memory_id: str,
    request: GroupMemoryUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await GroupService(db).update_memory(group_id, memory_id, current_user.id, request)


@router.delete("/{group_id}/memories/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group_memory(
    group_id: str,
    memory_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await GroupService(db).delete_memory(group_id, memory_id, current_user.id)
    return None


@router.get("/{group_id}/memories/{memory_id}/revisions", response_model=list[GroupMemoryRevisionResponse])
async def list_group_memory_revisions(
    group_id: str,
    memory_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await GroupService(db).list_memory_revisions(group_id, memory_id, current_user.id)
