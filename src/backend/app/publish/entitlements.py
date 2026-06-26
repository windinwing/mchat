"""Publishing entitlements — gates publishing-account management by plan.

Mirrors the ``workflow_entitlements`` pattern: a user must hold an active
subscription whose ``max_publishing_accounts > 0`` to add/manage publisher
accounts. The quota (e.g. 5 or 10) is copied from the ChannelTemplate to the
CustomerConfig at provisioning, so we read it from the user's active configs.

This is the ONLY gate between "can this user publish" and the channel CRUD.
Kept in the publish package (leaf module) — it depends on CustomerConfig /
subscription_gate but nothing depends back on it except portal.py.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.channel import Channel
from app.models.customer import CustomerConfig
from app.services.subscription_gate import active_customer_configs_for_user

# Channel types that count as "publisher accounts" (outbound publish channels).
PUBLISHER_CHANNEL_TYPES = frozenset({
    "feishu", "dingtalk", "wecom", "wechat_mp", "slack", "discord",
    "telegram_channel", "twitter_x", "facebook", "linkedin", "playwright_client",
})


@dataclass(frozen=True)
class PublishingEntitlement:
    """Result of checking a user's publishing entitlement."""

    allowed: bool
    max_accounts: int
    current_count: int
    remaining: int
    upgrade_message: str = ""


async def get_publishing_entitlement(
    db: AsyncSession, user_id: str
) -> PublishingEntitlement:
    """Compute the user's publishing-account allowance vs current usage.

    - admin/agent roles get unlimited access (mirrors workflow_entitlements
      where they resolve to ``enterprise`` plan directly).
    - ``max_accounts`` = highest ``max_publishing_accounts`` among the user's
      ACTIVE subscriptions (so a higher tier overrides a lower one).
    - ``current_count`` = how many publisher-type channels the user already has.
    """
    from app.models.user import User

    # Look up the user to check role.
    user = await db.get(User, user_id)
    role = (getattr(user, "role", "") or "").strip().lower() if user else ""

    configs = await active_customer_configs_for_user(db, user_id)
    plan_max = max(
        (getattr(c, "max_publishing_accounts", 0) or 0 for c in configs),
        default=0,
    )

    # admin/agent: unlimited (treat as a very high ceiling, not None, so the
    # frontend quota bar still works).
    if role in ("admin", "agent"):
        max_accounts = max(plan_max, 999)
    else:
        max_accounts = plan_max

    result = await db.execute(
        select(Channel).where(
            Channel.user_id == user_id,
            Channel.channel_type.in_(PUBLISHER_CHANNEL_TYPES),
        )
    )
    current = len(result.scalars().all())

    return PublishingEntitlement(
        allowed=max_accounts > 0,
        max_accounts=max_accounts,
        current_count=current,
        remaining=max(0, max_accounts - current),
    )


async def ensure_can_manage_publishing_accounts(db: AsyncSession, user_id: str) -> PublishingEntitlement:
    """Raise 402 if the user has no active publishing plan.

    Portal users hit this when trying to add a publisher account. The 402
    carries an upgrade hint so the frontend can guide them to the template
    market — same UX as workflow entitlements.
    """
    ent = await get_publishing_entitlement(db, user_id)
    if not ent.allowed:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "code": "publishing_plan_required",
                "message": "管理发布账号需开通推广套餐",
                "upgrade_hint": "请前往模板市场开通推广基础版或标准版",
            },
        )
    return ent


async def ensure_within_publishing_quota(db: AsyncSession, user_id: str) -> PublishingEntitlement:
    """Raise 402 if the user has reached their publishing-account quota.

    Called before creating a NEW publisher account.
    """
    ent = await ensure_can_manage_publishing_accounts(db, user_id)
    if ent.remaining <= 0:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "code": "publishing_quota_exceeded",
                "message": f"发布账号已达上限（{ent.max_accounts} 个），请升级套餐",
                "max": ent.max_accounts,
                "current": ent.current_count,
            },
        )
    return ent
