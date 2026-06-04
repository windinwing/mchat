"""Filter skill id lists for tenant-facing configs (no server_ops)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.skill import Skill
from app.skill.ops_policy import is_server_ops_skill


async def filter_tenant_skill_ids(
    db: AsyncSession,
    user_id: str,
    skill_ids: list[str] | None,
) -> list[str]:
    """Remove server_ops skills from channel/template skill id lists (owner-scoped)."""
    if not skill_ids:
        return []
    ids = [str(x).strip() for x in skill_ids if str(x).strip()]
    if not ids:
        return []
    result = await db.execute(
        select(Skill).where(Skill.user_id == user_id, Skill.id.in_(ids))
    )
    return _strip_server_ops(result.scalars().all())


async def filter_skill_ids_global(
    db: AsyncSession,
    skill_ids: list[str] | None,
) -> list[str]:
    """Remove server_ops skills by id (for templates referencing platform admin skills)."""
    if not skill_ids:
        return []
    ids = [str(x).strip() for x in skill_ids if str(x).strip()]
    if not ids:
        return []
    result = await db.execute(select(Skill).where(Skill.id.in_(ids)))
    return _strip_server_ops(result.scalars().all())


def _strip_server_ops(skills) -> list[str]:
    allowed: list[str] = []
    for skill in skills:
        if is_server_ops_skill(skill):
            continue
        allowed.append(skill.id)
    return allowed


def tenant_facing_skill_error(skill: Skill) -> str | None:
    """Block server_ops on widget/portal/channel paths (matches skill_context policy)."""
    from app.skill.ops_policy import is_notification_skill

    if is_server_ops_skill(skill):
        return "server_ops skills are not allowed on tenant-facing channels"
    if is_notification_skill(skill):
        return "notification skills are not allowed on tenant-facing channels"
    return None
