"""Workspace summaries for admin UI (no sidecar auto-start)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.customer import CustomerConfig
from app.schemas.workspace import ChannelWorkspaceSummary, SidecarListItem, SidecarStatusResponse
from app.workspace.disk_usage import tenant_execution_usage_bytes
from app.workspace.resolver import build_workspace_context, resolve_workspace_mode
from app.workspace.sidecar import sidecar_inspect
from app.workspace.sidecar_lifecycle import (
    idle_minutes_since,
    list_sidecars,
    read_sidecar_meta,
    remove_sidecar,
)
from app.workspace.types import WorkspaceMode


def _effective_mode_for_peek(
    requested: WorkspaceMode,
    sidecar: dict,
) -> str:
    if requested != WorkspaceMode.CONTAINER:
        return WorkspaceMode.LOCAL.value
    if not settings.workspace_container_enabled:
        return WorkspaceMode.LOCAL.value
    if sidecar.get("running"):
        return WorkspaceMode.CONTAINER.value
    if sidecar.get("exists"):
        return WorkspaceMode.LOCAL.value
    return requested.value


def summarize_channel(customer: CustomerConfig) -> ChannelWorkspaceSummary:
    ctx = build_workspace_context(
        customer.user_id,
        customer_config=customer,
        channel_id=customer.id,
    )
    sidecar_raw = (
        sidecar_inspect(ctx.container_name)
        if ctx.mode == WorkspaceMode.CONTAINER and ctx.container_name
        else {"exists": False, "running": False}
    )
    meta = read_sidecar_meta(customer.user_id)
    disk = tenant_execution_usage_bytes(ctx.tenant_root)
    return ChannelWorkspaceSummary(
        customer_id=customer.id,
        customer_name=customer.name,
        user_id=customer.user_id,
        plan=customer.plan or "free",
        workspace_mode=customer.workspace_mode,
        requested_mode=ctx.mode.value,
        effective_mode=_effective_mode_for_peek(ctx.mode, sidecar_raw),
        fallback_reason=None,
        container_name=ctx.container_name,
        sidecar=SidecarStatusResponse(**sidecar_raw),
        disk_usage_bytes=disk,
        usage_storage_bytes=customer.usage_storage_bytes,
        last_active_at=meta.get("last_active_at"),
        idle_minutes=idle_minutes_since(
            customer.user_id,
            started_at=sidecar_raw.get("started_at"),
        ),
        limits={
            "shell_enabled": ctx.limits.shell_enabled,
            "studio_enabled": ctx.limits.studio_enabled,
            "max_disk_bytes": ctx.limits.max_disk_bytes,
        },
    )


async def list_channel_summaries(
    db: AsyncSession,
    *,
    user_id: str | None = None,
) -> list[ChannelWorkspaceSummary]:
    query = select(CustomerConfig).order_by(CustomerConfig.created_at.desc())
    if user_id:
        query = query.where(CustomerConfig.user_id == user_id)
    result = await db.execute(query)
    return [summarize_channel(c) for c in result.scalars().all()]


def list_sidecar_items() -> list[SidecarListItem]:
    return [SidecarListItem.model_validate(item) for item in list_sidecars()]


async def update_channel_workspace_mode(
    db: AsyncSession,
    *,
    customer_id: str,
    user_id: str,
    workspace_mode: str | None,
    is_admin: bool = False,
) -> ChannelWorkspaceSummary | None:
    result = await db.execute(
        select(CustomerConfig).where(CustomerConfig.id == customer_id)
    )
    customer = result.scalar_one_or_none()
    if customer is None:
        return None
    if customer.user_id != user_id and not is_admin:
        return None

    if workspace_mode is not None:
        mode = workspace_mode.strip().lower()
        if mode not in ("local", "container"):
            raise ValueError("workspace_mode must be local or container")
        customer.workspace_mode = mode
    else:
        customer.workspace_mode = None

    await db.flush()
    await db.refresh(customer)
    return summarize_channel(customer)


def recycle_user_sidecar(user_id: str) -> bool:
    from app.workspace.resolver import build_workspace_context

    ctx = build_workspace_context(user_id)
    if not ctx.container_name:
        return False
    return remove_sidecar(ctx.container_name)
