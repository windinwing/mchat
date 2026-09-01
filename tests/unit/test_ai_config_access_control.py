"""AI configuration bindings must respect tenant and platform boundaries."""

import pytest
from fastapi import HTTPException

from app.models.ai_config import AIConfig
from app.models.conversation import Conversation
from app.models.user import User
from app.schemas.agent import CustomerConfigCreate
from app.schemas.group import GroupCreateRequest
from app.services.agent_service import AgentService
from app.services.chat_service import ChatService
from app.services.group_service import GroupService


async def _seed_configs(db_session):
    admin = User(id="admin", username="admin", password_hash="x", role="admin")
    owner = User(id="owner", username="owner", password_hash="x", role="agent")
    other = User(id="other", username="other", password_hash="x", role="agent")
    db_session.add_all([admin, owner, other])
    own = AIConfig(
        id="own-config",
        user_id=owner.id,
        name="Own",
        provider="openai",
        model="gpt-4o-mini",
        api_key="sk-owner-secret",
    )
    foreign = AIConfig(
        id="foreign-config",
        user_id=other.id,
        name="Foreign",
        provider="openai",
        model="gpt-4o-mini",
        api_key="sk-foreign-secret",
        is_default=True,
    )
    platform = AIConfig(
        id="platform-config",
        user_id=admin.id,
        name="Platform",
        provider="openai",
        model="gpt-4o-mini",
        api_key="sk-platform-secret",
        is_default=True,
    )
    db_session.add_all([own, foreign, platform])
    await db_session.commit()
    return admin, owner, other, own, foreign, platform


@pytest.mark.asyncio
async def test_conversation_bindings_allow_own_or_platform_only(db_session):
    _, owner, _, own, foreign, platform = await _seed_configs(db_session)
    service = ChatService(db_session)

    with pytest.raises(HTTPException) as denied:
        await service.create_conversation(
            user_id=owner.id,
            ai_config_id=foreign.id,
        )
    assert denied.value.status_code == 404

    own_conversation = await service.create_conversation(
        user_id=owner.id,
        ai_config_id=own.id,
    )
    stored_own = await db_session.get(Conversation, own_conversation.id)
    assert stored_own is not None
    assert stored_own.ai_config_id == own.id
    platform_conversation = await service.create_conversation(
        user_id=owner.id,
        ai_config_id=platform.id,
    )
    stored_platform = await db_session.get(Conversation, platform_conversation.id)
    assert stored_platform is not None
    assert stored_platform.ai_config_id == platform.id

    with pytest.raises(HTTPException) as anonymous_denied:
        await service.init_visitor_conversation(ai_config_id=foreign.id)
    assert anonymous_denied.value.status_code == 404
    visitor = await service.init_visitor_conversation(ai_config_id=platform.id)
    stored_visitor = await db_session.get(Conversation, visitor.id)
    assert stored_visitor is not None
    assert stored_visitor.ai_config_id == platform.id


@pytest.mark.asyncio
async def test_customer_and_group_bindings_reject_foreign_config(db_session):
    _, owner, _, _, foreign, platform = await _seed_configs(db_session)

    with pytest.raises(HTTPException) as customer_denied:
        await AgentService(db_session).create_customer_config(
            owner.id,
            CustomerConfigCreate(name="Foreign channel", ai_config_id=foreign.id),
        )
    assert customer_denied.value.status_code == 404

    customer = await AgentService(db_session).create_customer_config(
        owner.id,
        CustomerConfigCreate(name="Platform channel", ai_config_id=platform.id),
    )
    assert customer.ai_config_id == platform.id

    with pytest.raises(HTTPException) as group_denied:
        await GroupService(db_session).create_group(
            owner.id,
            GroupCreateRequest(name="Foreign group", ai_config_id=foreign.id),
        )
    assert group_denied.value.status_code == 404

    group = await GroupService(db_session).create_group(
        owner.id,
        GroupCreateRequest(name="Platform group", ai_config_id=platform.id),
    )
    assert group.ai_config_id == platform.id
