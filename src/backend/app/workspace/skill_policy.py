"""Tenant skill authoring vs platform-only rules (local vs container)."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.skills_paths import resolve_skill_directory
from app.models.skill import Skill
from app.models.user import User
from app.services.subscription_gate import active_customer_configs_for_user
from app.skill.ops_policy import is_server_ops_skill
from app.workspace.channel_plan import channel_container_entitled
from app.workspace.paths import tenant_skills_dir
from app.workspace.resolver import resolve_workspace_mode
from app.workspace.types import WorkspaceMode

SKILL_ORIGIN_PLATFORM = "platform"
SKILL_ORIGIN_TENANT = "tenant"

TENANT_SKILL_AUTHORING_REQUIRES_CONTAINER = "tenant_skill_authoring_requires_container"
TENANT_SKILL_EXECUTION_REQUIRES_CONTAINER = "tenant_skill_execution_requires_container"

_PLAN_RANK = {"free": 0, "free_trial": 1, "pro": 2, "enterprise": 3}


async def best_plan_for_user(db: AsyncSession, user_id: str) -> str:
    """Highest plan among enabled channels with active subscription/trial."""
    configs = await active_customer_configs_for_user(db, user_id)
    plans = [c.plan for c in configs if c.plan]
    if not plans:
        return "free"
    return max(plans, key=lambda p: _PLAN_RANK.get((p or "free").lower(), 0))


async def _best_plan_for_user(db: AsyncSession, user_id: str) -> str:
    return await best_plan_for_user(db, user_id)


async def user_may_author_tenant_skills(db: AsyncSession, user_id: str) -> bool:
    """Platform admins may always manage skills; tenants need container entitlement."""
    from app.middleware.auth import has_global_scope

    user = await db.get(User, user_id)
    if user is not None and await has_global_scope(user, db):
        return True
    return await user_container_entitled(db, user_id)


async def user_may_edit_skill_files(db: AsyncSession, user_id: str, skill: Skill) -> bool:
    """Whether user may write files in this skill directory."""
    if skill.skill_type == "builtin" or is_server_ops_skill(skill):
        return False
    if is_tenant_authored_skill(skill, user_id):
        return await user_may_author_tenant_skills(db, user_id)
    from app.middleware.auth import has_global_scope

    user = await db.get(User, user_id)
    return user is not None and await has_global_scope(user, db)


async def user_container_entitled(db: AsyncSession, user_id: str) -> bool:
    """User may author/run tenant skills in container workspace."""
    if not settings.workspace_container_enabled:
        return False
    user = await db.get(User, user_id)
    if user is not None and user.workspace_container_allowed is False:
        return False
    if user is not None and user.workspace_container_allowed is True:
        return True

    for ch in await active_customer_configs_for_user(db, user_id):
        if channel_container_entitled(ch):
            return True

    plan = await _best_plan_for_user(db, user_id)
    allowed = user.workspace_container_allowed if user else None
    return (
        resolve_workspace_mode(
            plan=plan,
            subscription_active=True,
            user_container_allowed=allowed,
        )
        == WorkspaceMode.CONTAINER
    )


def skill_origin_for_disk_path(path: str, *, user_id: str, skill_name: str) -> str:
    """Classify skill on disk as platform-distributed or tenant-authored."""
    resolved = Path(path).resolve()
    try:
        resolved.relative_to(tenant_skills_dir(user_id).resolve())
    except ValueError:
        return SKILL_ORIGIN_PLATFORM
    if resolve_skill_directory(skill_name):
        return SKILL_ORIGIN_PLATFORM
    return SKILL_ORIGIN_TENANT


def is_tenant_authored_skill(skill: Skill, user_id: str) -> bool:
    """True for user-created tenant skills (not platform catalog / server_ops)."""
    if skill.skill_type == "builtin" or is_server_ops_skill(skill):
        return False
    cfg = skill.config or {}
    origin = str(cfg.get("origin") or "").strip().lower()
    if origin == SKILL_ORIGIN_PLATFORM:
        return False
    if origin == SKILL_ORIGIN_TENANT:
        return True
    if not skill.path:
        return False
    return skill_origin_for_disk_path(skill.path, user_id=user_id, skill_name=skill.name) == (
        SKILL_ORIGIN_TENANT
    )


def tenant_skill_execution_blocked(skill: Skill, user_id: str, effective_mode: str | None) -> str | None:
    if not is_tenant_authored_skill(skill, user_id):
        return None
    if effective_mode != WorkspaceMode.CONTAINER.value:
        return TENANT_SKILL_EXECUTION_REQUIRES_CONTAINER
    return None
