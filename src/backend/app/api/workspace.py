"""Workspace status and admin APIs."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.middleware.auth import get_current_user, has_global_scope
from app.models.customer import CustomerConfig
from app.models.user import User
from app.schemas.workspace import (
    ChannelWorkspaceSummary,
    SidecarListItem,
    SidecarRecycleResponse,
    SidecarStatusResponse,
    UserWorkspaceSummary,
    UserWorkspaceUpdate,
    WorkspaceModeUpdate,
    WorkspaceStatusResponse,
)
from app.workspace.admin_service import (
    list_channel_summaries,
    list_sidecar_items,
    list_user_workspace_summaries,
    recycle_user_sidecar,
    summarize_channel,
    update_channel_workspace_mode,
    update_user_workspace_settings,
)
from app.workspace.context import workspace_execution_scope
from app.workspace.disk_usage import tenant_execution_usage_bytes
from app.workspace.factory import get_workspace_provider
from app.workspace.resolver import build_workspace_context
from app.workspace.sidecar import sidecar_inspect
from app.workspace.sidecar_lifecycle import recycle_idle_sidecars
from app.workspace.usage_service import refresh_customer_storage_usage

router = APIRouter()


@router.get("/status", response_model=WorkspaceStatusResponse)
async def get_workspace_status(
    customer_id: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceStatusResponse:
    """Return resolved workspace mode, sidecar state, disk usage, and execution env."""
    customer_config: CustomerConfig | None = None
    channel_id: str | None = None
    if customer_id:
        result = await db.execute(
            select(CustomerConfig).where(CustomerConfig.id == customer_id)
        )
        customer_config = result.scalar_one_or_none()
        if customer_config is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Channel not found",
            )
        if customer_config.user_id != current_user.id and not await has_global_scope(
            current_user, db
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not allowed to inspect this channel workspace",
            )
        channel_id = customer_config.id

    ctx = build_workspace_context(
        current_user.id,
        customer_config=customer_config,
        channel_id=channel_id,
    )
    async with workspace_execution_scope(ctx) as ready:
        assert ready is not None
        provider = get_workspace_provider(ready)
        sidecar_raw = sidecar_inspect(ready.container_name)
        usage_synced = await refresh_customer_storage_usage(db, ready.user_id)
        await db.commit()
        return WorkspaceStatusResponse(
            user_id=ready.user_id,
            customer_id=ready.customer_id,
            channel_id=ready.channel_id,
            mode=ready.mode.value,
            effective_mode=ready.effective_mode.value,
            fallback_reason=ready.fallback_reason,
            tenant_root=str(ready.tenant_root),
            uploads_dir=str(ready.uploads_dir()),
            skills_dir=str(ready.skills_dir()),
            data_dir=str(ready.data_dir()),
            container_name=ready.container_name,
            sidecar=SidecarStatusResponse(**sidecar_raw),
            disk_usage_bytes=tenant_execution_usage_bytes(ready.tenant_root),
            usage_storage_bytes=usage_synced,
            limits={
                "shell_enabled": ready.limits.shell_enabled,
                "studio_enabled": ready.limits.studio_enabled,
                "max_disk_bytes": ready.limits.max_disk_bytes,
            },
            execution_env=provider.execution_env(),
        )


@router.get("/channels", response_model=list[ChannelWorkspaceSummary])
async def list_workspace_channels(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ChannelWorkspaceSummary]:
    """List workspace execution summary per customer agent (no sidecar auto-start)."""
    is_admin = await has_global_scope(current_user, db)
    user_filter = None if is_admin else current_user.id
    return await list_channel_summaries(db, user_id=user_filter)


@router.patch("/channels/{customer_id}", response_model=ChannelWorkspaceSummary)
async def patch_channel_workspace_mode(
    customer_id: str,
    body: WorkspaceModeUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChannelWorkspaceSummary:
    """Assign local or container execution for a customer agent."""
    is_admin = await has_global_scope(current_user, db)
    try:
        summary = await update_channel_workspace_mode(
            db,
            customer_id=customer_id,
            user_id=current_user.id,
            workspace_mode=body.workspace_mode,
            is_admin=is_admin,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    if summary is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found")
    await db.commit()
    return summary


@router.get("/sidecars", response_model=list[SidecarListItem])
async def list_workspace_sidecars(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SidecarListItem]:
    """List Docker execution sidecars (admin: all; tenant: own user_id only)."""
    items = list_sidecar_items()
    if await has_global_scope(current_user, db):
        return items
    return [item for item in items if item.user_id == current_user.id]


@router.post("/sidecars/{user_id}/recycle", response_model=SidecarRecycleResponse)
async def recycle_sidecar_for_user(
    user_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SidecarRecycleResponse:
    """Remove a user's sidecar container (next execution recreates if needed)."""
    is_admin = await has_global_scope(current_user, db)
    if user_id != current_user.id and not is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    ok = recycle_user_sidecar(user_id)
    return SidecarRecycleResponse(
        ok=ok,
        removed=1 if ok else 0,
        message="Sidecar removed" if ok else "No sidecar to remove",
    )


@router.post("/sidecars/recycle-idle", response_model=SidecarRecycleResponse)
async def recycle_idle_sidecars_now(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SidecarRecycleResponse:
    """Manually run idle sidecar recycle (admin only)."""
    if not await has_global_scope(current_user, db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
    removed = recycle_idle_sidecars()
    return SidecarRecycleResponse(
        ok=True,
        removed=removed,
        message=f"Recycled {removed} idle sidecar(s)",
    )


@router.get("/users", response_model=list[UserWorkspaceSummary])
async def list_workspace_users(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[UserWorkspaceSummary]:
    """Admin: per-user container entitlement, sidecar status, and resource limits."""
    if not await has_global_scope(current_user, db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
    return await list_user_workspace_summaries(db)


@router.patch("/users/{user_id}", response_model=UserWorkspaceSummary)
async def patch_workspace_user(
    user_id: str,
    body: UserWorkspaceUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserWorkspaceSummary:
    """Admin: update container policy and sidecar memory/CPU for a user."""
    if not await has_global_scope(current_user, db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
    fields = body.model_dump(exclude_unset=True)
    user = await update_user_workspace_settings(
        db,
        user_id=user_id,
        workspace_container_allowed=body.workspace_container_allowed,
        set_container_allowed="workspace_container_allowed" in fields,
        workspace_sidecar_memory=body.workspace_sidecar_memory,
        workspace_sidecar_cpus=body.workspace_sidecar_cpus,
        set_sidecar_memory="workspace_sidecar_memory" in fields,
        set_sidecar_cpus="workspace_sidecar_cpus" in fields,
    )
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    await db.commit()
    items = await list_user_workspace_summaries(db)
    for item in items:
        if item.user_id == user_id:
            return item
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")


@router.get("/settings/runtime")
async def workspace_runtime_settings(
    current_user: User = Depends(get_current_user),
) -> dict:
    """Expose non-secret workspace container settings for admin UI."""
    return {
        "workspace_container_enabled": settings.workspace_container_enabled,
        "workspace_container_image": settings.workspace_container_image,
        "workspace_container_memory": settings.workspace_container_memory,
        "workspace_container_cpus": settings.workspace_container_cpus,
        "workspace_sidecar_idle_minutes": settings.workspace_sidecar_idle_minutes,
        "workspace_sidecar_recycle_enabled": settings.workspace_sidecar_recycle_enabled,
    }
