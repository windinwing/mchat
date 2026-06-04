"""Channel subscription / trial gate for widget and chat traffic."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import CustomerConfig


def subscription_end_from_period(
    billing_period: str, *, from_time: datetime | None = None
) -> datetime:
    """Compute subscription end from monthly/yearly billing."""
    start = from_time or datetime.now(timezone.utc)
    if billing_period == "yearly":
        return start + timedelta(days=365)
    return start + timedelta(days=30)


def extend_subscription_end(
    current_end: datetime | None,
    billing_period: str,
    *,
    now: datetime | None = None,
) -> datetime:
    """Stack renewal from current end if still active, else from now."""
    now = now or datetime.now(timezone.utc)
    if current_end is not None:
        if current_end.tzinfo is None:
            current_end = current_end.replace(tzinfo=timezone.utc)
        base = current_end if current_end > now else now
    else:
        base = now
    return subscription_end_from_period(billing_period, from_time=base)


def is_subscription_active(
    *,
    plan: str,
    trial_ends_at: datetime | None,
    subscription_ends_at: datetime | None,
    now: datetime | None = None,
) -> bool:
    """Whether channel should accept chat/widget traffic."""
    now = now or datetime.now(timezone.utc)
    if plan in ("free", "free_trial"):
        if trial_ends_at:
            end = trial_ends_at
            if end.tzinfo is None:
                end = end.replace(tzinfo=timezone.utc)
            if end < now:
                return False
        return True
    if plan in ("pro", "enterprise"):
        if subscription_ends_at:
            end = subscription_ends_at
            if end.tzinfo is None:
                end = end.replace(tzinfo=timezone.utc)
            if end < now:
                return False
        return True
    return True


def channel_subscription_active(config: CustomerConfig) -> bool:
    if not config.enabled:
        return False
    return is_subscription_active(
        plan=config.plan or "free",
        trial_ends_at=config.trial_ends_at,
        subscription_ends_at=config.subscription_ends_at,
    )


async def active_customer_configs_for_user(
    db: AsyncSession,
    user_id: str,
) -> list[CustomerConfig]:
    """Enabled channels whose subscription/trial is still active."""
    result = await db.execute(
        select(CustomerConfig).where(
            CustomerConfig.user_id == user_id,
            CustomerConfig.enabled.is_(True),
        )
    )
    return [c for c in result.scalars().all() if channel_subscription_active(c)]


def subscription_inactive_message(config: CustomerConfig) -> str:
    if config.offline_message:
        return config.offline_message
    plan = config.plan or "free"
    if plan in ("pro", "enterprise"):
        return "订阅已到期，请续费后继续使用。"
    return "试用已结束，请升级方案后继续使用。"


def ensure_channel_subscription_active(config: CustomerConfig) -> None:
    """Raise 402 when channel subscription/trial is expired."""
    if channel_subscription_active(config):
        return
    raise HTTPException(
        status_code=status.HTTP_402_PAYMENT_REQUIRED,
        detail={
            "code": "subscription_expired",
            "message": subscription_inactive_message(config),
            "plan": config.plan,
            "subscription_ends_at": (
                config.subscription_ends_at.isoformat()
                if config.subscription_ends_at
                else None
            ),
            "trial_ends_at": (
                config.trial_ends_at.isoformat() if config.trial_ends_at else None
            ),
        },
    )
