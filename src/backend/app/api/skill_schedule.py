"""Skill schedule API router."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.middleware.auth import Permission, require_permission
from app.models.user import User
from app.schemas.skill_schedule import (
    SkillScheduleCreate,
    SkillScheduleRunOnceRequest,
    SkillScheduleRunResponse,
    SkillScheduleRunResult,
    SkillScheduleResponse,
    SkillScheduleUpdate,
)
from app.services.skill_schedule_service import SkillScheduleService

router = APIRouter()


@router.get("", response_model=list[SkillScheduleResponse])
async def list_skill_schedules(
    admin: User = Depends(require_permission(Permission.SKILLS_READ)),
    db: AsyncSession = Depends(get_db),
):
    service = SkillScheduleService(db)
    return await service.list_schedules(user_id=admin.id)


@router.post("", response_model=SkillScheduleResponse, status_code=status.HTTP_201_CREATED)
async def create_skill_schedule(
    request: SkillScheduleCreate,
    admin: User = Depends(require_permission(Permission.SKILLS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    service = SkillScheduleService(db)
    return await service.create_schedule(user_id=admin.id, data=request)


@router.patch("/{schedule_id}", response_model=SkillScheduleResponse)
async def update_skill_schedule(
    schedule_id: str,
    request: SkillScheduleUpdate,
    admin: User = Depends(require_permission(Permission.SKILLS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    service = SkillScheduleService(db)
    return await service.update_schedule(
        schedule_id=schedule_id,
        user_id=admin.id,
        data=request,
    )


@router.delete("/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_skill_schedule(
    schedule_id: str,
    admin: User = Depends(require_permission(Permission.SKILLS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    service = SkillScheduleService(db)
    await service.delete_schedule(schedule_id=schedule_id, user_id=admin.id)
    return None


@router.post("/{schedule_id}/run-once", response_model=SkillScheduleRunResult)
async def run_skill_schedule_once(
    schedule_id: str,
    request: SkillScheduleRunOnceRequest,
    admin: User = Depends(require_permission(Permission.SKILLS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    service = SkillScheduleService(db)
    run = await service.run_once(
        schedule_id=schedule_id,
        user_id=admin.id,
        payload_override=request.payload,
    )
    return SkillScheduleRunResult(run=run)


@router.get("/runs", response_model=list[SkillScheduleRunResponse])
async def list_skill_schedule_runs(
    schedule_id: str | None = Query(default=None),
    limit: int = Query(default=30, ge=1, le=200),
    admin: User = Depends(require_permission(Permission.SKILLS_READ)),
    db: AsyncSession = Depends(get_db),
):
    service = SkillScheduleService(db)
    return await service.list_runs(
        user_id=admin.id,
        schedule_id=schedule_id,
        limit=limit,
    )
