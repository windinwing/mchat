"""Admin schemas for portal channel subscription management."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class AdminChannelSubscriptionRow(BaseModel):
    """Portal workspace channel with buyer and subscription status."""

    channel_id: str
    channel_name: str
    user_id: str
    user_username: str | None = None
    user_phone: str | None = None
    user_display_name: str | None = None
    template_id: str | None = None
    template_name: str | None = None
    plan: str
    trial_ends_at: datetime | None = None
    subscription_ends_at: datetime | None = None
    subscription_active: bool = True
    enabled: bool = True
    created_at: datetime
    updated_at: datetime


class AdminChannelSubscriptionUpdate(BaseModel):
    """Manual subscription adjustment by admin."""

    plan: Literal["free", "free_trial", "pro", "enterprise"] | None = None
    trial_ends_at: datetime | None = None
    subscription_ends_at: datetime | None = None
    grant_trial_days: int | None = Field(
        None, ge=1, le=730, description="Set free_trial and trial end from now"
    )
    grant_pro_days: int | None = Field(
        None, ge=1, le=3650, description="Grant or extend Pro by N days from now or active end"
    )
    extend_pro_days: int | None = Field(
        None, ge=1, le=3650, description="Extend Pro subscription by N days"
    )
    extend_pro_months: int | None = Field(
        None, ge=1, le=120, description="Extend Pro subscription by N months (30d each)"
    )
    clear_trial: bool = False
    clear_subscription: bool = False
    note: str | None = Field(None, max_length=500, description="Optional audit note")


class AdminProvisionChannelRequest(BaseModel):
    """Admin creates a workspace for a user and grants subscription in one step."""

    template_id: str = Field(..., min_length=1)
    channel_name: str | None = Field(None, max_length=200)
    grant_trial_days: int | None = Field(None, ge=1, le=730)
    grant_pro_days: int | None = Field(None, ge=1, le=3650)
    extend_pro_months: int | None = Field(None, ge=1, le=120)
    note: str | None = Field(None, max_length=500)


class AdminPortalUserSubscription(BaseModel):
    """Portal user with zero or more workspace channels."""

    user_id: str
    user_username: str | None = None
    user_phone: str | None = None
    user_display_name: str | None = None
    channels: list[AdminChannelSubscriptionRow] = Field(default_factory=list)


class AdminChannelSubscriptionUpdateResult(BaseModel):
    """Channel row after admin update."""

    channel: AdminChannelSubscriptionRow
    message: str
