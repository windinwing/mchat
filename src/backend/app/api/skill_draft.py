"""Skill draft API routes."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.middleware.auth import has_global_scope, require_permission, Permission
from app.models.user import User
from app.schemas.skill import SkillResponse
from app.schemas.skill_draft import (
    SkillDraftCommitRequest,
    SkillDraftFromChatRequest,
    SkillDraftListResponse,
    SkillDraftResponse,
    SkillDraftUpdateRequest,
)
from app.services.skill_draft_service import SkillDraftService

router = APIRouter()


@router.get("/drafts", response_model=SkillDraftListResponse)
async def list_skill_drafts(
    group_id: str | None = None,
    admin: User = Depends(require_permission(Permission.SKILLS_READ)),
    db: AsyncSession = Depends(get_db),
):
    service = SkillDraftService(db)
    items = await service.list_drafts(admin.id, group_id=group_id)
    return SkillDraftListResponse(items=items, total=len(items))


@router.post("/drafts/from-chat", response_model=SkillDraftResponse)
async def create_skill_draft_from_chat(
    request: SkillDraftFromChatRequest,
    admin: User = Depends(require_permission(Permission.SKILLS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    service = SkillDraftService(db)
    is_admin = await has_global_scope(admin, db)
    return await service.create_from_chat(
        user_id=admin.id,
        conversation_id=request.conversation_id,
        hint=request.hint,
        is_admin=is_admin,
    )


@router.get("/drafts/{draft_id}", response_model=SkillDraftResponse)
async def get_skill_draft(
    draft_id: str,
    group_id: str | None = None,
    admin: User = Depends(require_permission(Permission.SKILLS_READ)),
    db: AsyncSession = Depends(get_db),
):
    service = SkillDraftService(db)
    return await service.get_draft(admin.id, draft_id, group_id=group_id)


@router.patch("/drafts/{draft_id}", response_model=SkillDraftResponse)
async def update_skill_draft(
    draft_id: str,
    request: SkillDraftUpdateRequest,
    group_id: str | None = None,
    admin: User = Depends(require_permission(Permission.SKILLS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    service = SkillDraftService(db)
    return await service.update_draft(
        admin.id,
        draft_id,
        name=request.name,
        description=request.description,
        skill_type=request.skill_type,
        files=request.files,
        group_id=group_id,
    )


@router.post("/drafts/{draft_id}/commit", response_model=SkillResponse)
async def commit_skill_draft(
    draft_id: str,
    request: SkillDraftCommitRequest,
    admin: User = Depends(require_permission(Permission.SKILLS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    service = SkillDraftService(db)
    return await service.commit_draft(
        admin.id,
        draft_id,
        customer_id=request.customer_id,
        bind_channel=request.bind_channel,
        group_id=request.group_id,
    )


@router.delete("/drafts/{draft_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_skill_draft(
    draft_id: str,
    group_id: str | None = None,
    admin: User = Depends(require_permission(Permission.SKILLS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    service = SkillDraftService(db)
    await service.delete_draft(admin.id, draft_id, group_id=group_id)
    return None
