"""Server-side ops skills: global switch, allowlist, admin-only."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.skill import Skill
from app.models.user import User

SCOPE_SERVER_OPS = "server_ops"
SCOPE_NOTIFICATION = "notification"


def skill_scope(skill: Skill) -> str:
    """tenant (default) | server_ops."""
    cfg = skill.config or {}
    raw = str(cfg.get("scope") or "tenant").strip().lower()
    return raw or "tenant"


def is_server_ops_skill(skill: Skill) -> bool:
    return skill_scope(skill) == SCOPE_SERVER_OPS


def is_notification_skill(skill: Skill) -> bool:
    return skill_scope(skill) == SCOPE_NOTIFICATION


def _parse_allowlist(raw: Any) -> list[str] | None:
    """None = no allowlist (all server_ops names); [] = allow none."""
    if raw is None:
        return None
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [str(x).strip() for x in parsed if str(x).strip()]
        except json.JSONDecodeError:
            return [p.strip() for p in text.split(",") if p.strip()]
    return None


async def server_ops_enabled_for_user(
    db: AsyncSession,
    user_id: str,
) -> bool:
    """Global switch ON and user is admin."""
    if not getattr(settings, "server_ops_skills_enabled", False):
        return False
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        return False
    role = (user.role or "").strip().lower()
    return role == "admin"


def filter_skills_by_ops_policy(
    skills: list[Skill],
    *,
    allow_server_ops: bool,
    allowlist: list[str] | None,
    allow_notification: bool = False,
    notification_allowlist: list[str] | None = None,
) -> list[Skill]:
    """Drop server_ops / notification skills when disabled; optional name allowlists."""
    from app.skill.notify_policy import filter_notification_skills

    out = filter_notification_skills(
        skills,
        allow_notification=allow_notification,
        allowlist=notification_allowlist,
    )
    filtered: list[Skill] = []
    for skill in out:
        if not is_server_ops_skill(skill):
            filtered.append(skill)
            continue
        if not allow_server_ops:
            continue
        if allowlist is not None and len(allowlist) > 0:
            if skill.name not in allowlist:
                continue
        filtered.append(skill)
    return filtered


def sync_server_ops_settings_from_db(
    *,
    enabled: bool,
    allowlist: list[str] | None,
    shell_allowlist: list[dict] | None = None,
) -> None:
    settings.server_ops_skills_enabled = enabled
    settings.server_ops_skill_allowlist = allowlist
    settings.server_ops_shell_allowlist = shell_allowlist or []


def sync_notification_settings_from_db(
    *,
    enabled: bool,
    allowlist: list[str] | None,
    sms_default_provider: str,
    sms_phone_allowlist: list[str] | None,
    sms_alert_phones: list[str] | None,
    sms_workflow_alert_enabled: bool,
    sms_send_cooldown_seconds: int,
) -> None:
    settings.notification_skills_enabled = enabled
    settings.notification_skill_allowlist = allowlist
    settings.sms_default_provider = sms_default_provider or "dev"
    settings.sms_phone_allowlist = sms_phone_allowlist or []
    settings.sms_alert_phones = sms_alert_phones or []
    settings.sms_workflow_alert_enabled = sms_workflow_alert_enabled
    settings.sms_send_cooldown_seconds = max(30, int(sms_send_cooldown_seconds or 60))


async def notification_enabled_for_user(db: AsyncSession, user_id: str) -> bool:
    if not getattr(settings, "notification_skills_enabled", False):
        return False
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        return False
    return (user.role or "").strip().lower() == "admin"
