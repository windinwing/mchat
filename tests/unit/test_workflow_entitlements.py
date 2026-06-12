"""Tests for workflow / schedule plan entitlements."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.models.channel_template import ChannelTemplate
from app.models.customer import CustomerConfig
from app.models.user import User
from app.services.workflow_entitlements import (
    _pick_upgrade_target,
    ensure_can_create_workflow,
    get_workflow_entitlements,
    limits_for_plan,
)


def test_limits_for_plan_free_blocks_automation():
    limits = limits_for_plan("free")
    assert limits.max_workflows == 0
    assert limits.max_schedules == 0
    assert limits.dag_enabled is False


def test_limits_for_plan_pro_allows_automation():
    limits = limits_for_plan("pro")
    assert limits.max_workflows == 30
    assert limits.dag_enabled is True


@pytest.mark.asyncio
async def test_pick_upgrade_target_prefers_patent_channel(db_session):
    db_session.add(
        ChannelTemplate(
            id="tpl-cs",
            name="AI 智能客服 (基础版)",
            category="customer_service",
            price_monthly_cents=0,
        )
    )
    db_session.add(
        ChannelTemplate(
            id="tpl-patent",
            name="专利查新助手",
            category="patent_rag",
            price_monthly_cents=2900,
        )
    )
    channels = [
        CustomerConfig(id="ch-1", name="A", user_id="u1", template_id="tpl-cs", plan="free"),
        CustomerConfig(id="ch-2", name="B", user_id="u1", template_id="tpl-patent", plan="free"),
    ]
    ch_id, tpl_id, name, cents = await _pick_upgrade_target(db_session, channels, "free")
    assert ch_id == "ch-2"
    assert tpl_id == "tpl-patent"
    assert name == "专利查新助手"
    assert cents == 2900


@pytest.mark.asyncio
async def test_admin_has_unlimited_entitlements(db_session):
    user = User(id="admin-u", username="staff", password_hash="x", role="admin")
    db_session.add(user)
    await db_session.flush()

    ent = await get_workflow_entitlements(db_session, user)
    assert ent.plan == "enterprise"
    assert ent.can_create_workflow is True
    assert ent.can_create_schedule is True
    assert ent.can_run_workflow is True
    assert ent.upgrade_required is False


@pytest.mark.asyncio
async def test_portal_user_free_cannot_create_workflow(db_session):
    user = User(id="u-free", username="freeuser", password_hash="x", role="user")
    db_session.add(user)
    await db_session.flush()

    db_session.add(
        ChannelTemplate(
            id="tpl-free",
            name="AI 智能客服 (基础版)",
            category="customer_service",
            price_monthly_cents=0,
        )
    )
    db_session.add(
        CustomerConfig(
            id="ch-free",
            name="Free channel",
            user_id=user.id,
            plan="free",
            template_id="tpl-free",
            enabled=True,
        )
    )
    await db_session.flush()

    ent = await get_workflow_entitlements(db_session, user)
    assert ent.plan == "free"
    assert ent.can_create_workflow is False
    assert ent.upgrade_required is True
    assert ent.upgrade_instant is True
    assert ent.upgrade_amount_cents == 0

    with pytest.raises(HTTPException) as exc:
        await ensure_can_create_workflow(db_session, user)
    assert exc.value.status_code == 402
    assert exc.value.detail["code"] == "workflow_plan_required"


@pytest.mark.asyncio
async def test_portal_user_pro_can_create_workflow(db_session):
    user = User(id="u-pro", username="prouser", password_hash="x", role="user")
    db_session.add(user)
    await db_session.flush()
    db_session.add(
        CustomerConfig(
            id="ch-pro",
            name="Pro channel",
            user_id=user.id,
            plan="pro",
            template_id="tpl-pro",
            enabled=True,
            subscription_ends_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
    )
    await db_session.flush()

    ent = await get_workflow_entitlements(db_session, user)
    assert ent.plan == "pro"
    assert ent.can_create_workflow is True
    assert ent.can_create_schedule is True
    assert ent.can_run_workflow is True
    await ensure_can_create_workflow(db_session, user)
