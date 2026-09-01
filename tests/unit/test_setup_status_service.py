"""Tests for first-run setup status."""

import pytest

from app.models.ai_config import AIConfig
from app.models.customer import CustomerConfig
from app.models.user import User
from app.services.setup_status_service import get_setup_status


@pytest.mark.asyncio
async def test_setup_status_empty(db_session):
    user = User(
        id="u1",
        username="admin",
        password_hash="x",
        role="admin",
    )
    db_session.add(user)
    await db_session.commit()

    status = await get_setup_status(db_session, user)
    assert status.ai_ready is False
    assert status.has_assistant is False
    assert status.ai_config_count == 0


@pytest.mark.asyncio
async def test_setup_status_ai_without_key(db_session):
    user = User(
        id="u1",
        username="agent1",
        password_hash="x",
        role="agent",
    )
    db_session.add(user)
    db_session.add(
        AIConfig(
            id="ai1",
            user_id="u1",
            name="DeepSeek",
            provider="deepseek",
            model="deepseek-chat",
            api_key="",
        )
    )
    await db_session.commit()

    status = await get_setup_status(db_session, user)
    assert status.ai_config_count == 1
    assert status.ai_ready is False


@pytest.mark.asyncio
async def test_setup_status_ready(db_session):
    user = User(
        id="u1",
        username="agent1",
        password_hash="x",
        role="agent",
    )
    db_session.add(user)
    db_session.add(
        AIConfig(
            id="ai1",
            user_id="u1",
            name="DeepSeek",
            provider="deepseek",
            model="deepseek-chat",
            api_key="sk-test-key-12345678",
        )
    )
    db_session.add(
        CustomerConfig(
            id="ch1",
            user_id="u1",
            name="Demo",
            enabled=True,
        )
    )
    await db_session.commit()

    status = await get_setup_status(db_session, user)
    assert status.ai_ready is True
    assert status.has_assistant is True


@pytest.mark.asyncio
async def test_setup_status_admin_assistant_is_user_scoped(db_session):
    admin = User(
        id="u-admin",
        username="admin1",
        password_hash="x",
        role="admin",
    )
    owner = User(
        id="u-owner",
        username="owner1",
        password_hash="x",
        role="agent",
    )
    db_session.add_all([admin, owner])
    db_session.add(
        AIConfig(
            id="ai-owner",
            user_id="u-owner",
            name="DeepSeek",
            provider="deepseek",
            model="deepseek-chat",
            api_key="sk-test-key-12345678",
            is_default=True,
        )
    )
    db_session.add(
        CustomerConfig(
            id="ch-owner",
            user_id="u-owner",
            name="Tenant Assistant",
            enabled=True,
        )
    )
    await db_session.commit()

    status = await get_setup_status(db_session, admin)
    assert status.ai_ready is False
    assert status.ai_config_count == 0
    assert status.has_assistant is False
