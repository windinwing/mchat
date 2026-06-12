"""Admin operations on portal channel subscriptions."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from loguru import logger
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.channel_template import ChannelTemplate
from app.models.customer import CustomerConfig
from app.models.user import User
from app.services.subscription_gate import is_subscription_active
from cloud.schemas.admin_subscription import (
    AdminChannelSubscriptionRow,
    AdminChannelSubscriptionUpdate,
    AdminPortalUserSubscription,
)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def extend_end_by_days(
    current_end: datetime | None,
    days: int,
    *,
    now: datetime | None = None,
) -> datetime:
    """Stack extension from active end, else from now."""
    now = now or datetime.now(timezone.utc)
    current_end = _aware(current_end)
    base = current_end if current_end and current_end > now else now
    return base + timedelta(days=days)


def _row_from_parts(
    config: CustomerConfig,
    user: User,
    template: ChannelTemplate | None,
) -> AdminChannelSubscriptionRow:
    return AdminChannelSubscriptionRow(
        channel_id=config.id,
        channel_name=config.name,
        user_id=user.id,
        user_username=user.username,
        user_phone=getattr(user, "phone", None),
        user_display_name=getattr(user, "display_name", None),
        template_id=config.template_id,
        template_name=template.name if template else None,
        plan=config.plan or "free",
        trial_ends_at=config.trial_ends_at,
        subscription_ends_at=config.subscription_ends_at,
        subscription_active=is_subscription_active(
            plan=config.plan or "free",
            trial_ends_at=config.trial_ends_at,
            subscription_ends_at=config.subscription_ends_at,
        )
        and bool(config.enabled),
        enabled=bool(config.enabled),
        created_at=config.created_at,
        updated_at=config.updated_at,
    )


async def list_channel_subscriptions(
    db: AsyncSession,
    *,
    user_id: str | None = None,
    plan: str | None = None,
    q: str | None = None,
    active_only: bool | None = None,
    limit: int = 200,
) -> list[AdminChannelSubscriptionRow]:
    stmt = (
        select(CustomerConfig, User, ChannelTemplate)
        .join(User, CustomerConfig.user_id == User.id)
        .outerjoin(ChannelTemplate, CustomerConfig.template_id == ChannelTemplate.id)
        .order_by(CustomerConfig.updated_at.desc())
        .limit(min(limit, 500))
    )
    if user_id:
        stmt = stmt.where(CustomerConfig.user_id == user_id)
    if plan:
        stmt = stmt.where(CustomerConfig.plan == plan)
    if q:
        term = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                CustomerConfig.name.ilike(term),
                User.username.ilike(term),
                User.phone.ilike(term),
            )
        )
    result = await db.execute(stmt)
    rows: list[AdminChannelSubscriptionRow] = []
    for config, user, template in result.all():
        row = _row_from_parts(config, user, template)
        if active_only is True and not row.subscription_active:
            continue
        if active_only is False and row.subscription_active:
            continue
        rows.append(row)
    return rows


async def get_channel_subscription(
    db: AsyncSession,
    channel_id: str,
) -> AdminChannelSubscriptionRow:
    stmt = (
        select(CustomerConfig, User, ChannelTemplate)
        .join(User, CustomerConfig.user_id == User.id)
        .outerjoin(ChannelTemplate, CustomerConfig.template_id == ChannelTemplate.id)
        .where(CustomerConfig.id == channel_id)
    )
    row = (await db.execute(stmt)).first()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Channel not found")
    config, user, template = row
    return _row_from_parts(config, user, template)


async def apply_channel_subscription_update(
    db: AsyncSession,
    channel_id: str,
    body: AdminChannelSubscriptionUpdate,
    *,
    admin: User,
) -> tuple[AdminChannelSubscriptionRow, str]:
    result = await db.execute(
        select(CustomerConfig).where(CustomerConfig.id == channel_id)
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Channel not found")

    now = datetime.now(timezone.utc)
    changes: list[str] = []

    if body.clear_trial:
        config.trial_ends_at = None
        changes.append("cleared trial")

    if body.clear_subscription:
        config.subscription_ends_at = None
        changes.append("cleared subscription end")

    if body.grant_trial_days is not None:
        config.plan = "free_trial"
        config.trial_ends_at = now + timedelta(days=body.grant_trial_days)
        changes.append(f"granted {body.grant_trial_days}d trial")

    pro_days = body.grant_pro_days if body.grant_pro_days is not None else body.extend_pro_days
    if pro_days is not None:
        config.plan = "pro"
        config.trial_ends_at = None
        config.subscription_ends_at = extend_end_by_days(
            config.subscription_ends_at,
            pro_days,
            now=now,
        )
        if body.grant_pro_days is not None:
            changes.append(f"granted pro by {pro_days}d")
        else:
            changes.append(f"extended pro by {pro_days}d")

    if body.extend_pro_months is not None:
        days = body.extend_pro_months * 30
        config.plan = "pro"
        config.trial_ends_at = None
        config.subscription_ends_at = extend_end_by_days(
            config.subscription_ends_at,
            days,
            now=now,
        )
        changes.append(f"extended pro by {body.extend_pro_months}mo")

    if body.trial_ends_at is not None:
        config.trial_ends_at = _aware(body.trial_ends_at)
        if config.plan in ("free", "free_trial"):
            config.plan = "free_trial"
        changes.append("set trial_ends_at")

    if body.subscription_ends_at is not None:
        config.subscription_ends_at = _aware(body.subscription_ends_at)
        if config.plan in ("free", "free_trial"):
            config.plan = "pro"
        changes.append("set subscription_ends_at")

    if body.plan is not None:
        config.plan = body.plan
        changes.append(f"plan={body.plan}")
        if body.plan == "free":
            if not body.grant_trial_days and body.trial_ends_at is None:
                if body.clear_trial or body.clear_subscription:
                    pass
                elif not any(
                    [
                        body.grant_pro_days,
                        body.extend_pro_days,
                        body.extend_pro_months,
                        body.subscription_ends_at,
                    ]
                ):
                    config.trial_ends_at = None
                    config.subscription_ends_at = None

    if not changes:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="No subscription changes requested",
        )

    config.updated_at = now
    await db.flush()

    logger.info(
        "admin subscription update channel={} admin={} changes={} note={}",
        channel_id,
        admin.username,
        ",".join(changes),
        body.note or "",
    )

    row = await get_channel_subscription(db, channel_id)
    message = "；".join(changes)
    return row, message


async def list_portal_users_with_subscriptions(
    db: AsyncSession,
    *,
    q: str | None = None,
    limit: int = 100,
) -> list[AdminPortalUserSubscription]:
    """Portal users and their workspace channels (including users with no channel)."""
    stmt = (
        select(User)
        .where(User.role == "user")
        .order_by(User.created_at.desc())
        .limit(min(limit, 200))
    )
    if q:
        term = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                User.username.ilike(term),
                User.phone.ilike(term),
                User.display_name.ilike(term),
            )
        )
    users = list((await db.execute(stmt)).scalars().all())
    if not users:
        return []

    user_ids = [u.id for u in users]
    channel_stmt = (
        select(CustomerConfig, User, ChannelTemplate)
        .join(User, CustomerConfig.user_id == User.id)
        .outerjoin(ChannelTemplate, CustomerConfig.template_id == ChannelTemplate.id)
        .where(CustomerConfig.user_id.in_(user_ids))
        .order_by(CustomerConfig.updated_at.desc())
    )
    channel_rows = (await db.execute(channel_stmt)).all()
    by_user: dict[str, list[AdminChannelSubscriptionRow]] = {uid: [] for uid in user_ids}
    for config, user, template in channel_rows:
        by_user.setdefault(user.id, []).append(_row_from_parts(config, user, template))

    return [
        AdminPortalUserSubscription(
            user_id=u.id,
            user_username=u.username,
            user_phone=getattr(u, "phone", None),
            user_display_name=getattr(u, "display_name", None),
            channels=by_user.get(u.id, []),
        )
        for u in users
    ]
