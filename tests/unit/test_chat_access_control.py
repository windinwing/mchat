"""Conversation ownership checks shared by HTTP and WebSocket chat."""

import pytest
from app.core.security import create_access_token
from app.models.conversation import Conversation
from app.models.customer import CustomerConfig
from app.models.group import Group, GroupMember
from app.models.message import Message
from app.models.user import User
from app.services.chat_service import ChatService
from app.websocket.route import _check_subscribe_permission
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy import func, select


def _user(username: str, *, role: str = "agent") -> User:
    return User(username=username, password_hash="test", role=role)


def _headers(user: User) -> dict[str, str]:
    token = create_access_token(
        data={"sub": user.id, "username": user.username, "role": user.role}
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_send_message_allows_owner_and_admin_but_denies_cross_user(db_session):
    owner = _user("conversation-owner")
    stranger = _user("conversation-stranger")
    admin = _user("conversation-admin", role="admin")
    db_session.add_all([owner, stranger, admin])
    await db_session.flush()
    conversation = Conversation(user_id=owner.id, title="Private")
    db_session.add(conversation)
    await db_session.flush()

    service = ChatService(db_session)
    owner_message = await service.send_message(
        conversation.id,
        "owner reply",
        role="assistant",
        user=owner,
    )
    assert owner_message.content == "owner reply"

    with pytest.raises(HTTPException) as exc:
        await service.send_message(
            conversation.id,
            "cross-user reply",
            role="assistant",
            user=stranger,
        )
    assert exc.value.status_code == 403

    admin_message = await service.send_message(
        conversation.id,
        "admin reply",
        role="assistant",
        user=admin,
    )
    assert admin_message.content == "admin reply"


@pytest.mark.asyncio
async def test_send_message_requires_matching_visitor_token_and_denies_ownerless(
    db_session,
):
    visitor_conversation = Conversation(
        visitor_id="visitor-secret",
        title="Widget visitor",
    )
    ownerless_conversation = Conversation(title="No owner")
    db_session.add_all([visitor_conversation, ownerless_conversation])
    await db_session.flush()

    service = ChatService(db_session)
    visitor_message = await service.send_message(
        visitor_conversation.id,
        "visitor reply",
        role="assistant",
        visitor_token="visitor-secret",
    )
    assert visitor_message.content == "visitor reply"

    for token in (None, "wrong-secret"):
        with pytest.raises(HTTPException) as exc:
            await service.send_message(
                visitor_conversation.id,
                "not allowed",
                role="assistant",
                visitor_token=token,
            )
        assert exc.value.status_code == 403

    with pytest.raises(HTTPException) as exc:
        await service.send_message(
            ownerless_conversation.id,
            "anonymous ownerless reply",
            role="assistant",
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_send_message_allows_group_member_and_channel_tenant(db_session):
    tenant = _user("channel-tenant")
    member = _user("group-member")
    outsider = _user("access-outsider")
    db_session.add_all([tenant, member, outsider])
    await db_session.flush()

    channel = CustomerConfig(name="Tenant widget", user_id=tenant.id)
    group = Group(name="Authorized group", owner_user_id=tenant.id)
    db_session.add_all([channel, group])
    await db_session.flush()
    db_session.add(GroupMember(group_id=group.id, user_id=member.id))

    channel_conversation = Conversation(
        customer_id=channel.id,
        visitor_id="channel-visitor",
        title="Channel visitor",
    )
    group_conversation = Conversation(
        user_id=tenant.id,
        scope_type="group",
        scope_id=group.id,
        title="Group chat",
    )
    db_session.add_all([channel_conversation, group_conversation])
    await db_session.flush()

    service = ChatService(db_session)
    assert (
        await service.send_message(
            channel_conversation.id,
            "tenant reply",
            role="assistant",
            user=tenant,
        )
    ).content == "tenant reply"
    assert (
        await service.send_message(
            group_conversation.id,
            "member reply",
            role="assistant",
            user=member,
        )
    ).content == "member reply"

    for conversation in (channel_conversation, group_conversation):
        with pytest.raises(HTTPException) as exc:
            await service.send_message(
                conversation.id,
                "outsider reply",
                role="assistant",
                user=outsider,
            )
        assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_http_send_enforces_conversation_owner(
    client: AsyncClient,
    auth_headers: dict,
    db_session,
):
    owner = _user("http-owner")
    stranger = _user("http-stranger")
    db_session.add_all([owner, stranger])
    await db_session.flush()
    conversation = Conversation(user_id=owner.id, title="HTTP private")
    db_session.add(conversation)
    await db_session.commit()

    denied = await client.post(
        "/api/chat/send",
        json={
            "conversation_id": conversation.id,
            "content": "cross-user reply",
            "role": "assistant",
        },
        headers=_headers(stranger),
    )
    assert denied.status_code == 403

    owner_response = await client.post(
        "/api/chat/send",
        json={
            "conversation_id": conversation.id,
            "content": "owner reply",
            "role": "assistant",
        },
        headers=_headers(owner),
    )
    assert owner_response.status_code == 200

    admin_response = await client.post(
        "/api/chat/send",
        json={
            "conversation_id": conversation.id,
            "content": "admin reply",
            "role": "assistant",
        },
        headers=auth_headers,
    )
    assert admin_response.status_code == 200

    message_count = await db_session.scalar(
        select(func.count(Message.id)).where(Message.conversation_id == conversation.id)
    )
    assert message_count == 2


@pytest.mark.asyncio
async def test_websocket_subscription_uses_same_owner_and_visitor_rules(db_session):
    owner = _user("ws-owner")
    stranger = _user("ws-stranger")
    admin = _user("ws-admin", role="admin")
    db_session.add_all([owner, stranger, admin])
    await db_session.flush()
    personal = Conversation(user_id=owner.id, title="WS private")
    visitor = Conversation(visitor_id="ws-visitor-secret", title="WS visitor")
    ownerless = Conversation(title="WS ownerless")
    db_session.add_all([personal, visitor, ownerless])
    await db_session.commit()

    assert await _check_subscribe_permission(personal.id, owner, None) == (True, "")
    assert await _check_subscribe_permission(personal.id, stranger, None) == (
        False,
        "ACCESS_DENIED",
    )
    assert await _check_subscribe_permission(personal.id, admin, None) == (True, "")
    assert await _check_subscribe_permission(visitor.id, None, "ws-visitor-secret") == (
        True,
        "",
    )
    assert await _check_subscribe_permission(visitor.id, None, None) == (
        False,
        "MISSING_VISITOR_TOKEN",
    )
    assert await _check_subscribe_permission(visitor.id, None, "wrong") == (
        False,
        "ACCESS_DENIED",
    )
    assert await _check_subscribe_permission(ownerless.id, None, None) == (
        False,
        "ACCESS_DENIED",
    )
