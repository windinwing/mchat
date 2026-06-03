"""Map subscription plans to workspace limits."""

from __future__ import annotations

from app.workspace.types import WorkspaceLimits

_MB = 1024 * 1024
_GB = 1024 * _MB

PLAN_LIMITS: dict[str, WorkspaceLimits] = {
    "free": WorkspaceLimits(
        shell_enabled=False,
        studio_enabled=True,
        max_disk_bytes=256 * _MB,
    ),
    "free_trial": WorkspaceLimits(
        shell_enabled=False,
        studio_enabled=True,
        max_disk_bytes=512 * _MB,
    ),
    "pro": WorkspaceLimits(
        shell_enabled=True,
        studio_enabled=True,
        max_disk_bytes=5 * _GB,
    ),
    "enterprise": WorkspaceLimits(
        shell_enabled=True,
        studio_enabled=True,
        max_disk_bytes=None,
    ),
}


def limits_for_plan(plan: str | None) -> WorkspaceLimits:
    key = (plan or "free").strip().lower()
    return PLAN_LIMITS.get(key, PLAN_LIMITS["free"])
