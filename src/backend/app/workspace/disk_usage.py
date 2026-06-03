"""Tenant workspace disk usage and soft quota checks."""

from __future__ import annotations

from pathlib import Path

from app.workspace.types import WorkspaceContext

_EXECUTION_SUBDIRS = ("skills", "uploads", "data")


def dir_size_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    total = 0
    for child in path.rglob("*"):
        if child.is_file():
            try:
                total += child.stat().st_size
            except OSError:
                continue
    return total


def tenant_execution_usage_bytes(tenant_root: Path) -> dict[str, int]:
    """Byte usage for sidecar-visible dirs only (excludes studio)."""
    breakdown: dict[str, int] = {}
    for name in _EXECUTION_SUBDIRS:
        breakdown[name] = dir_size_bytes(tenant_root / name)
    breakdown["total"] = sum(breakdown.values())
    return breakdown


def check_soft_quota(
    ctx: WorkspaceContext,
    *,
    additional_bytes: int = 0,
) -> str | None:
    limit = ctx.limits.max_disk_bytes
    if limit is None:
        return None
    used = tenant_execution_usage_bytes(ctx.tenant_root)["total"]
    if used + additional_bytes > limit:
        return (
            f"租户工作区配额不足：已用 {used} 字节，"
            f"本次需 {additional_bytes} 字节，上限 {limit} 字节"
        )
    return None
