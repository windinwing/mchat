"""Admin portal channel subscription management."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.models.channel_template import ChannelTemplate
from app.models.customer import CustomerConfig
from app.models.user import User
from cloud.schemas.admin_subscription import AdminChannelSubscriptionUpdate
from cloud.services.admin_subscription_service import (
    apply_channel_subscription_update,
    extend_end_by_days,
    list_channel_subscriptions,
)


@pytest.mark.asyncio
async def test_extend_end_by_days_stacks_from_active_end():
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    current = datetime(2026, 7, 1, tzinfo=timezone.utc)
    end = extend_end_by_days(current, 30, now=now)
    assert end == datetime(2026, 7, 31, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_grant_trial_and_extend_pro(db_session):
    admin = User(id="adm-1", username="admin", password_hash="x", role="admin")
    user = User(id="u-1", username="portal1", password_hash="x", role="user")
    tpl = ChannelTemplate(
        id="tpl-1",
        name="Patent RAG",
        category="patent_rag",
        trial_days=7,
        price_monthly_cents=9900,
        price_yearly_cents=99900,
    )
    ch = CustomerConfig(
        id="ch-1",
        name="My patent bot",
        user_id=user.id,
        template_id=tpl.id,
        plan="free",
        enabled=True,
    )
    db_session.add_all([admin, user, tpl, ch])
    await db_session.flush()

    row, msg = await apply_channel_subscription_update(
        db_session,
        ch.id,
        AdminChannelSubscriptionUpdate(grant_trial_days=14, note="promo"),
        admin=admin,
    )
    assert row.plan == "free_trial"
    assert row.trial_ends_at is not None
    assert "14" in msg

    row2, msg2 = await apply_channel_subscription_update(
        db_session,
        ch.id,
        AdminChannelSubscriptionUpdate(extend_pro_days=30),
        admin=admin,
    )
    assert row2.plan == "pro"
    assert row2.subscription_ends_at is not None
    assert "30" in msg2


@pytest.mark.asyncio
async def test_list_channel_subscriptions_search(db_session):
    user = User(id="u-2", username="alice", phone="13800001111", password_hash="x", role="user")
    ch = CustomerConfig(
        id="ch-2",
        name="Alice workspace",
        user_id=user.id,
        plan="pro",
        subscription_ends_at=datetime.now(timezone.utc) + timedelta(days=10),
        enabled=True,
    )
    db_session.add_all([user, ch])
    await db_session.flush()

    rows = await list_channel_subscriptions(db_session, q="alice")
    assert len(rows) == 1
    assert rows[0].channel_name == "Alice workspace"
    assert rows[0].subscription_active is True


@pytest.mark.asyncio
async def test_empty_update_rejected(db_session):
    admin = User(id="adm-2", username="admin2", password_hash="x", role="admin")
    user = User(id="u-3", username="bob", password_hash="x", role="user")
    ch = CustomerConfig(id="ch-3", name="Bob", user_id=user.id, plan="free", enabled=True)
    db_session.add_all([admin, user, ch])
    await db_session.flush()

    with pytest.raises(HTTPException) as exc:
        await apply_channel_subscription_update(
            db_session,
            ch.id,
            AdminChannelSubscriptionUpdate(),
            admin=admin,
        )
    assert exc.value.status_code == 400
