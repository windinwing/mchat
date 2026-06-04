"""Channel plan ↔ workspace_mode validation and entitlement summaries."""

from __future__ import annotations

from app.models.customer import CustomerConfig
from app.services.subscription_gate import channel_subscription_active
from app.workspace.policy import container_block_reason, plan_allows_container_auto
from app.workspace.resolver import build_workspace_context, resolve_workspace_mode
from app.workspace.types import WorkspaceMode


def validate_channel_workspace_mode(
    customer: CustomerConfig,
    workspace_mode: str | None,
) -> None:
    """Raise ValueError(block_reason) when container mode is not allowed for this channel."""
    if workspace_mode is None:
        return
    mode = workspace_mode.strip().lower()
    if mode not in ("local", "container"):
        raise ValueError("workspace_mode must be local or container")
    if mode != "container":
        return
    subscription_active = channel_subscription_active(customer)
    block = container_block_reason(
        plan=customer.plan or "free",
        subscription_active=subscription_active,
        workspace_mode_override="container",
        requested_mode=WorkspaceMode.CONTAINER,
    )
    if block:
        raise ValueError(block)


def channel_container_entitled(customer: CustomerConfig) -> bool:
    """Whether this channel may use container workspace (plan + subscription + overrides)."""
    subscription_active = channel_subscription_active(customer)
    override = (customer.workspace_mode or "").strip().lower()
    if override == "container":
        return (
            container_block_reason(
                plan=customer.plan or "free",
                subscription_active=subscription_active,
                workspace_mode_override="container",
                requested_mode=WorkspaceMode.CONTAINER,
            )
            is None
        )
    return plan_allows_container_auto(
        customer.plan or "free",
        subscription_active=subscription_active,
    )


def channel_workspace_snapshot(customer: CustomerConfig) -> dict[str, str | bool | None]:
    """Workspace fields for admin channel responses."""
    subscription_active = channel_subscription_active(customer)
    requested = resolve_workspace_mode(
        plan=customer.plan or "free",
        workspace_mode_override=customer.workspace_mode,
        subscription_active=subscription_active,
    )
    ctx = build_workspace_context(
        customer.user_id,
        customer_config=customer,
    )
    return {
        "workspace_mode": customer.workspace_mode,
        "workspace_requested_mode": requested.value,
        "workspace_effective_mode": ctx.mode.value,
        "container_entitled": channel_container_entitled(customer),
        "subscription_active": subscription_active,
    }
