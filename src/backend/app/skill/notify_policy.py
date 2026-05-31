"""Restricted notification skills (SMS) — admin-only, separate from tenant tools."""

from __future__ import annotations

from app.models.skill import Skill
from app.skill.ops_policy import SCOPE_NOTIFICATION, is_notification_skill

__all__ = [
    "SCOPE_NOTIFICATION",
    "is_notification_skill",
    "filter_notification_skills",
]


def filter_notification_skills(
    skills: list[Skill],
    *,
    allow_notification: bool,
    allowlist: list[str] | None,
) -> list[Skill]:
    out: list[Skill] = []
    for skill in skills:
        if not is_notification_skill(skill):
            out.append(skill)
            continue
        if not allow_notification:
            continue
        if allowlist is not None and len(allowlist) > 0 and skill.name not in allowlist:
            continue
        out.append(skill)
    return out
