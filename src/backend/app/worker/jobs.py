"""Background worker jobs."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from loguru import logger
from sqlalchemy import or_, update

from app.core.database import async_session_factory
from app.models.customer import CustomerConfig


async def reset_monthly_usage_quotas() -> int:
    """Reset monthly usage counters for channels once per month."""
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    async with async_session_factory() as db:
        stmt = (
            update(CustomerConfig)
            .where(
                or_(
                    CustomerConfig.last_usage_reset_at.is_(None),
                    CustomerConfig.last_usage_reset_at < month_start,
                )
            )
            .values(
                usage_messages_month=0,
                usage_tokens_month=0,
                last_usage_reset_at=now,
            )
        )
        result = await db.execute(stmt)
        await db.commit()
        count = int(result.rowcount or 0)
        logger.info("Worker job reset_monthly_usage_quotas updated {} rows", count)
        return count


async def cleanup_old_logs(retention_days: int) -> int:
    """Delete old rotated logs under logs/ by mtime."""
    logs_dir = Path("logs")
    if not logs_dir.exists():
        logger.info("Worker job cleanup_old_logs skipped: logs/ does not exist")
        return 0

    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, retention_days))
    removed = 0
    for p in logs_dir.iterdir():
        if not p.is_file():
            continue
        if p.name in {"app.log", "error.log"}:
            continue
        # Keep only rotated-like files (app.log.1, error.log.2026-01-01, *.gz ...)
        if ".log." not in p.name and not p.name.endswith(".gz"):
            continue
        modified_at = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
        if modified_at < cutoff:
            try:
                p.unlink()
                removed += 1
            except Exception as e:  # pragma: no cover - filesystem edge case
                logger.warning("Worker cleanup_old_logs failed for {}: {}", p, e)

    logger.info(
        "Worker job cleanup_old_logs removed {} files (retention_days={})",
        removed,
        retention_days,
    )
    return removed


async def recycle_idle_sidecars() -> int:
    """Worker job: remove execution sidecars idle longer than configured threshold."""
    from app.core.config import settings

    if not settings.workspace_sidecar_recycle_enabled:
        logger.info("Worker job recycle_idle_sidecars skipped: disabled")
        return 0
    from app.workspace.sidecar_lifecycle import recycle_idle_sidecars as _recycle

    removed = _recycle()
    logger.info("Worker job recycle_idle_sidecars removed {}", removed)
    return removed

