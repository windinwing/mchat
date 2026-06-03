"""Workspace status API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.middleware.auth import get_current_user, has_global_scope
from app.models.customer import CustomerConfig
from app.models.user import User
from app.schemas.workspace import WorkspaceStatusResponse
from app.workspace.context import workspace_execution_scope
from app.workspace.factory import get_workspace_provider
from app.workspace.resolver import build_workspace_context

router = APIRouter()


@router.get("/status", response_model=WorkspaceStatusResponse)
async def get_workspace_status(
    customer_id: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceStatusResponse:
    """Return resolved workspace mode and limits for the current user."""
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
        return WorkspaceStatusResponse(
            user_id=ready.user_id,
            customer_id=ready.customer_id,
            channel_id=ready.channel_id,
            mode=ready.mode.value,
            effective_mode=ready.effective_mode.value,
            fallback_reason=ready.fallback_reason,
            tenant_root=str(ready.tenant_root),
            uploads_dir=str(ready.uploads_dir()),
            container_name=ready.container_name,
            limits={
                "shell_enabled": ready.limits.shell_enabled,
                "studio_enabled": ready.limits.studio_enabled,
                "max_disk_bytes": ready.limits.max_disk_bytes,
            },
            execution_env=provider.execution_env(),
        )
