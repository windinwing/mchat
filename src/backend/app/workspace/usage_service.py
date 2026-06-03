"""Sync tenant disk usage into channel quota fields."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import CustomerConfig
from app.workspace.disk_usage import tenant_execution_usage_bytes
from app.workspace.paths import tenant_root


def compute_user_storage_bytes(user_id: str) -> int:
    """Bytes used under tenant execution dirs (skills/uploads/data)."""
    return tenant_execution_usage_bytes(tenant_root(user_id))["total"]


async def refresh_customer_storage_usage(
    db: AsyncSession,
    user_id: str,
) -> int:
    """Write tenant execution usage to all channels owned by this user."""
    total = compute_user_storage_bytes(user_id)
    result = await db.execute(
        select(CustomerConfig).where(CustomerConfig.user_id == user_id)
    )
    channels = list(result.scalars().all())
    if not channels:
        return total
    for channel in channels:
        channel.usage_storage_bytes = total
    await db.flush()
    return total
