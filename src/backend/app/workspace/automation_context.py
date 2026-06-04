"""Workspace context for workflow/schedule automation (best plan, channel overrides)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.subscription_gate import active_customer_configs_for_user
from app.workspace.channel_plan import channel_container_entitled
from app.workspace.resolver import build_workspace_context
from app.workspace.skill_policy import best_plan_for_user
from app.workspace.types import WorkspaceContext


async def _automation_workspace_mode_override(
    db: AsyncSession,
    user_id: str,
) -> str | None:
    """Explicit container path for automation when plan auto alone would stay local."""
    for ch in await active_customer_configs_for_user(db, user_id):
        mode = (ch.workspace_mode or "").strip().lower()
        if mode != "container":
            continue
        if channel_container_entitled(ch):
            return "container"
    return None


async def build_automation_workspace_context(
    db: AsyncSession,
    user_id: str,
) -> WorkspaceContext:
    """Resolve workspace using active channel plans and explicit container overrides."""
    plan = await best_plan_for_user(db, user_id)
    workspace_mode_override = await _automation_workspace_mode_override(db, user_id)
    return build_workspace_context(
        user_id,
        plan_override=plan,
        workspace_mode_override=workspace_mode_override,
    )
