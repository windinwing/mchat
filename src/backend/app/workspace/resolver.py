"""Resolve workspace mode and context from user, plan, and settings."""

from __future__ import annotations

from app.core.config import settings
from app.models.customer import CustomerConfig
from app.services.subscription_gate import channel_subscription_active
from app.workspace.limits import limits_for_plan
from app.workspace.paths import ensure_tenant_layout, tenant_root
from app.workspace.types import WorkspaceContext, WorkspaceMode


def _normalize_mode(value: str | None) -> WorkspaceMode | None:
    if not value:
        return None
    key = value.strip().lower()
    if key in ("local", "a"):
        return WorkspaceMode.LOCAL
    if key in ("container", "b", "openclaw"):
        return WorkspaceMode.CONTAINER
    return None


def resolve_workspace_mode(
    *,
    plan: str | None = None,
    workspace_mode_override: str | None = None,
    subscription_active: bool = True,
) -> WorkspaceMode:
    """Choose local (A) or container (B) backend."""
    override = _normalize_mode(workspace_mode_override)
    if override is not None:
        mode = override
    elif (
        (plan or "free").lower() in ("pro", "enterprise")
        and subscription_active
        and settings.workspace_container_enabled
    ):
        mode = WorkspaceMode.CONTAINER
    else:
        mode = WorkspaceMode(settings.workspace_default_mode or "local")

    if mode == WorkspaceMode.CONTAINER and not settings.workspace_container_enabled:
        return WorkspaceMode.LOCAL
    return mode


def build_workspace_context(
    user_id: str,
    *,
    customer_config: CustomerConfig | None = None,
    channel_id: str | None = None,
    workspace_mode_override: str | None = None,
) -> WorkspaceContext:
    plan = (customer_config.plan if customer_config else None) or "free"
    override = workspace_mode_override
    if customer_config is not None:
        override = override or getattr(customer_config, "workspace_mode", None)
    subscription_active = (
        channel_subscription_active(customer_config)
        if customer_config is not None
        else True
    )
    mode = resolve_workspace_mode(
        plan=plan,
        workspace_mode_override=override,
        subscription_active=subscription_active,
    )
    limits = limits_for_plan(plan)
    if mode == WorkspaceMode.LOCAL:
        limits = limits_for_plan("free") if plan in ("free", "free_trial") else limits

    cid = channel_id
    if cid is None and customer_config is not None:
        cid = customer_config.id

    root = tenant_root(user_id)
    container_name = None
    if mode == WorkspaceMode.CONTAINER:
        safe_uid = user_id.replace("-", "")[:12]
        container_name = f"{settings.workspace_container_name_prefix}-{safe_uid}"

    ctx = WorkspaceContext(
        user_id=user_id,
        mode=mode,
        effective_mode=mode,
        tenant_root=root,
        limits=limits,
        customer_id=customer_config.id if customer_config else None,
        channel_id=cid,
        container_name=container_name,
    )
    ensure_tenant_layout(
        root,
        include_studio=limits.studio_enabled,
        channel_id=cid,
    )
    return ctx


def workspace_user_id_for_execution(
    *,
    customer_config: CustomerConfig | None,
    fallback_user_id: str,
) -> str:
    """Platform account that owns the tenant workspace (not portal visitors)."""
    if customer_config is not None and customer_config.user_id:
        return customer_config.user_id
    return fallback_user_id


# Backward-compatible alias
workspace_user_id_for_chat = workspace_user_id_for_execution
