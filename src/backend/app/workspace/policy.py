"""Workspace container eligibility (global, plan, per-user, per-channel)."""

from __future__ import annotations

from app.core.config import settings
from app.workspace.types import WorkspaceMode


def plan_allows_container_auto(plan: str | None, *, subscription_active: bool) -> bool:
    return (
        (plan or "free").lower() in ("pro", "enterprise")
        and subscription_active
    )


def container_block_reason(
    *,
    plan: str | None = None,
    subscription_active: bool = True,
    workspace_mode_override: str | None = None,
    user_container_allowed: bool | None = None,
    requested_mode: WorkspaceMode | None = None,
    ignore_user_denial: bool = False,
) -> str | None:
    """Why container mode cannot be used; None when allowed."""
    if requested_mode is not None and requested_mode != WorkspaceMode.CONTAINER:
        return None
    if not settings.workspace_container_enabled:
        return "container_disabled_globally"
    if not ignore_user_denial and user_container_allowed is False:
        return "user_container_denied"

    override = (workspace_mode_override or "").strip().lower()
    if override == "container":
        if not plan_allows_container_auto(plan, subscription_active=subscription_active):
            if user_container_allowed is not True:
                return "container_not_allowed_for_plan"
        return None

    if not plan_allows_container_auto(plan, subscription_active=subscription_active):
        return "plan_not_eligible"
    return None
