"""Workspace summaries for admin UI (no sidecar auto-start)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.customer import CustomerConfig
from app.models.user import User
from app.schemas.workspace import ChannelWorkspaceSummary, SidecarListItem, SidecarStatusResponse, UserWorkspaceSummary
from app.services.subscription_gate import channel_subscription_active
from app.workspace.disk_usage import tenant_execution_usage_bytes
from app.workspace.policy import container_block_reason
from app.workspace.resolver import build_workspace_context, resolve_workspace_mode
from app.workspace.sidecar import sidecar_inspect
from app.workspace.sidecar_lifecycle import (
    idle_minutes_since,
    list_sidecars,
    read_sidecar_meta,
    remove_sidecar,
)
from app.workspace.sidecar_limits import (
    effective_sidecar_limits,
    sidecar_limits_path,
    write_user_sidecar_limits,
)
from app.workspace.skill_policy import user_container_entitled
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


def summarize_channel(
    customer: CustomerConfig,
    *,
    user_container_allowed: bool | None = None,
) -> ChannelWorkspaceSummary:
    subscription_active = channel_subscription_active(customer)
    requested = resolve_workspace_mode(
        plan=customer.plan or "free",
        workspace_mode_override=customer.workspace_mode,
        subscription_active=subscription_active,
        user_container_allowed=True,
    )
    ctx = build_workspace_context(
        customer.user_id,
        customer_config=customer,
        channel_id=customer.id,
        user_container_allowed=user_container_allowed,
    )
    sidecar_raw = (
        sidecar_inspect(ctx.container_name)
        if ctx.mode == WorkspaceMode.CONTAINER and ctx.container_name
        else {"exists": False, "running": False}
    )
    meta = read_sidecar_meta(customer.user_id)
    disk = tenant_execution_usage_bytes(ctx.tenant_root)
    fallback = None
    if requested == WorkspaceMode.CONTAINER and ctx.mode == WorkspaceMode.LOCAL:
        fallback = container_block_reason(
            plan=customer.plan or "free",
            subscription_active=subscription_active,
            workspace_mode_override=customer.workspace_mode,
            user_container_allowed=user_container_allowed,
            requested_mode=WorkspaceMode.CONTAINER,
        )
    return ChannelWorkspaceSummary(
        customer_id=customer.id,
        customer_name=customer.name,
        user_id=customer.user_id,
        plan=customer.plan or "free",
        workspace_mode=customer.workspace_mode,
        user_container_allowed=user_container_allowed,
        requested_mode=requested.value,
        effective_mode=_effective_mode_for_peek(ctx.mode, sidecar_raw),
        fallback_reason=fallback,
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


async def _user_container_policies(
    db: AsyncSession,
    user_ids: set[str],
) -> dict[str, bool | None]:
    if not user_ids:
        return {}
    result = await db.execute(select(User).where(User.id.in_(user_ids)))
    return {
        user.id: user.workspace_container_allowed
        for user in result.scalars().all()
    }


async def list_channel_summaries(
    db: AsyncSession,
    *,
    user_id: str | None = None,
) -> list[ChannelWorkspaceSummary]:
    query = select(CustomerConfig).order_by(CustomerConfig.created_at.desc())
    if user_id:
        query = query.where(CustomerConfig.user_id == user_id)
    result = await db.execute(query)
    customers = list(result.scalars().all())
    policies = await _user_container_policies(
        db, {c.user_id for c in customers if c.user_id}
    )
    return [
        summarize_channel(c, user_container_allowed=policies.get(c.user_id))
        for c in customers
    ]


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
        if mode == "container":
            owner = await db.get(User, customer.user_id)
            subscription_active = channel_subscription_active(customer)
            block = container_block_reason(
                plan=customer.plan or "free",
                subscription_active=subscription_active,
                workspace_mode_override="container",
                user_container_allowed=(
                    owner.workspace_container_allowed if owner else None
                ),
                requested_mode=WorkspaceMode.CONTAINER,
            )
            if block:
                raise ValueError(block)
        customer.workspace_mode = mode
    else:
        customer.workspace_mode = None

    await db.flush()
    await db.refresh(customer)
    owner = await db.get(User, customer.user_id)
    return summarize_channel(
        customer,
        user_container_allowed=(
            owner.workspace_container_allowed if owner else None
        ),
    )


def recycle_user_sidecar(user_id: str) -> bool:
    from app.workspace.resolver import build_workspace_context

    ctx = build_workspace_context(user_id)
    if not ctx.container_name:
        return False
    return remove_sidecar(ctx.container_name)


async def list_user_workspace_summaries(
    db: AsyncSession,
) -> list[UserWorkspaceSummary]:
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    users = list(result.scalars().all())
    sidecars_by_user = {
        item.get("user_id"): item for item in list_sidecars() if item.get("user_id")
    }

    summaries: list[UserWorkspaceSummary] = []
    for user in users:
        entitled = await user_container_entitled(db, user.id)
        sidecar = sidecars_by_user.get(user.id, {})
        ctx = build_workspace_context(
            user.id,
            user_container_allowed=user.workspace_container_allowed,
        )
        disk = tenant_execution_usage_bytes(ctx.tenant_root)
        limits = effective_sidecar_limits(user.id)
        if (
            user.workspace_sidecar_memory or user.workspace_sidecar_cpus
        ) and not sidecar_limits_path(user.id).is_file():
            write_user_sidecar_limits(
                user.id,
                memory=user.workspace_sidecar_memory,
                cpus=user.workspace_sidecar_cpus,
            )
        summaries.append(
            UserWorkspaceSummary(
                user_id=user.id,
                username=user.username,
                display_name=user.display_name,
                workspace_container_allowed=user.workspace_container_allowed,
                container_entitled=entitled,
                tenant_skill_authoring=entitled,
                workspace_sidecar_memory=user.workspace_sidecar_memory,
                workspace_sidecar_cpus=user.workspace_sidecar_cpus,
                effective_memory=limits.get("memory"),
                effective_cpus=limits.get("cpus"),
                container_name=ctx.container_name,
                sidecar=SidecarStatusResponse(
                    exists=bool(sidecar.get("container_name")),
                    running=bool(sidecar.get("running")),
                    status=sidecar.get("status"),
                    image=sidecar.get("image"),
                ),
                memory_limit_bytes=sidecar.get("memory_limit_bytes"),
                running_cpus=sidecar.get("cpus"),
                disk_usage_bytes=disk,
                idle_minutes=sidecar.get("idle_minutes"),
                last_active_at=sidecar.get("last_active_at"),
                image_matches=sidecar.get("image_matches", True),
            )
        )
    return summaries


async def update_user_workspace_settings(
    db: AsyncSession,
    *,
    user_id: str,
    workspace_container_allowed: bool | None = None,
    set_container_allowed: bool = False,
    workspace_sidecar_memory: str | None = None,
    workspace_sidecar_cpus: str | None = None,
    set_sidecar_memory: bool = False,
    set_sidecar_cpus: bool = False,
) -> User | None:
    user = await db.get(User, user_id)
    if user is None:
        return None
    if set_container_allowed:
        user.workspace_container_allowed = workspace_container_allowed
    if set_sidecar_memory:
        user.workspace_sidecar_memory = (
            workspace_sidecar_memory.strip() if workspace_sidecar_memory else None
        )
    if set_sidecar_cpus:
        user.workspace_sidecar_cpus = (
            workspace_sidecar_cpus.strip() if workspace_sidecar_cpus else None
        )
    write_user_sidecar_limits(
        user.id,
        memory=user.workspace_sidecar_memory,
        cpus=user.workspace_sidecar_cpus,
        clear=not user.workspace_sidecar_memory and not user.workspace_sidecar_cpus,
    )
    await db.flush()
    await db.refresh(user)
    return user
