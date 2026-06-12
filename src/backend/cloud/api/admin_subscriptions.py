"""Admin: portal channel subscription management (Cloud)."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.middleware.auth import Permission, require_permission
from app.models.user import User
from cloud.schemas.admin_subscription import (
    AdminChannelSubscriptionRow,
    AdminChannelSubscriptionUpdate,
    AdminChannelSubscriptionUpdateResult,
    AdminPortalUserSubscription,
    AdminProvisionChannelRequest,
)
from cloud.services.admin_subscription_service import (
    apply_channel_subscription_update,
    get_channel_subscription,
    list_channel_subscriptions,
    list_portal_users_with_subscriptions,
    provision_user_channel,
)

router = APIRouter()


@router.get(
    "/admin/subscriptions/channels",
    response_model=list[AdminChannelSubscriptionRow],
)
async def admin_list_channel_subscriptions(
    user_id: str | None = None,
    plan: str | None = None,
    q: str | None = None,
    active_only: bool | None = None,
    limit: int = 200,
    _admin: User = Depends(require_permission(Permission.USERS_WRITE)),
    db: AsyncSession = Depends(get_db),
) -> list[AdminChannelSubscriptionRow]:
    """List portal workspaces with plan / trial / subscription status."""
    return await list_channel_subscriptions(
        db,
        user_id=user_id,
        plan=plan,
        q=q,
        active_only=active_only,
        limit=limit,
    )


@router.get(
    "/admin/subscriptions/users",
    response_model=list[AdminPortalUserSubscription],
)
async def admin_list_portal_user_subscriptions(
    q: str | None = None,
    limit: int = 100,
    _admin: User = Depends(require_permission(Permission.USERS_WRITE)),
    db: AsyncSession = Depends(get_db),
) -> list[AdminPortalUserSubscription]:
    """Portal users with their channels; includes users who have not rented a workspace."""
    return await list_portal_users_with_subscriptions(db, q=q, limit=limit)


@router.post(
    "/admin/subscriptions/users/{user_id}/provision",
    response_model=AdminChannelSubscriptionUpdateResult,
)
async def admin_provision_user_channel(
    user_id: str,
    body: AdminProvisionChannelRequest,
    admin: User = Depends(require_permission(Permission.USERS_WRITE)),
    db: AsyncSession = Depends(get_db),
) -> AdminChannelSubscriptionUpdateResult:
    """Create a workspace from a template and grant trial/Pro without user checkout."""
    row, message = await provision_user_channel(db, user_id, body, admin=admin)
    return AdminChannelSubscriptionUpdateResult(channel=row, message=message)


@router.get(
    "/admin/subscriptions/channels/{channel_id}",
    response_model=AdminChannelSubscriptionRow,
)
async def admin_get_channel_subscription(
    channel_id: str,
    _admin: User = Depends(require_permission(Permission.USERS_WRITE)),
    db: AsyncSession = Depends(get_db),
) -> AdminChannelSubscriptionRow:
    return await get_channel_subscription(db, channel_id)


@router.patch(
    "/admin/subscriptions/channels/{channel_id}",
    response_model=AdminChannelSubscriptionUpdateResult,
)
async def admin_update_channel_subscription(
    channel_id: str,
    body: AdminChannelSubscriptionUpdate,
    admin: User = Depends(require_permission(Permission.USERS_WRITE)),
    db: AsyncSession = Depends(get_db),
) -> AdminChannelSubscriptionUpdateResult:
    """Grant trial, extend Pro, or set plan / end dates manually."""
    row, message = await apply_channel_subscription_update(
        db, channel_id, body, admin=admin
    )
    return AdminChannelSubscriptionUpdateResult(channel=row, message=message)
