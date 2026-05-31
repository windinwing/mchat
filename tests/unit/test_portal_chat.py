"""Cloud Portal chat tests (not loaded in Core-only deployments)."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.conversation import Conversation
from app.models.customer import CustomerConfig
from app.models.message import Message
from app.models.user import User
from cloud.bot.studio_memory import register_cloud_chat_extensions
from cloud.services.portal_chat_service import PortalChatService

register_cloud_chat_extensions()


@pytest.mark.asyncio
async def test_resume_channel_conversation(db_session: AsyncSession):
    user = User(username="portal_user", password_hash="x", role="user")
    db_session.add(user)
    await db_session.flush()

    channel = CustomerConfig(
        id="ch-portal-1",
        name="Patent Assistant",
        user_id=user.id,
        enabled=True,
    )
    db_session.add(channel)
    await db_session.flush()

    service = PortalChatService(db_session)
    first = await service.get_or_resume_channel_conversation(
        user_id=user.id,
        channel_id=channel.id,
        title=channel.name,
    )
    db_session.add(
        Message(
            conversation_id=first.id,
            role="user",
            content="继续昨天的专利检索任务",
        )
    )
    await db_session.commit()

    second = await service.get_or_resume_channel_conversation(
        user_id=user.id,
        channel_id=channel.id,
    )

    assert second.id == first.id
    assert second.messages is not None
    assert len(second.messages) == 1
    assert second.messages[0].content == "继续昨天的专利检索任务"


@pytest.mark.asyncio
async def test_resume_channel_conversation_force_new(db_session: AsyncSession):
    user = User(username="portal_user2", password_hash="x", role="user")
    db_session.add(user)
    await db_session.flush()

    channel = CustomerConfig(
        id="ch-portal-2",
        name="Project Bot",
        user_id=user.id,
        enabled=True,
    )
    db_session.add(channel)
    await db_session.flush()

    service = PortalChatService(db_session)
    first = await service.get_or_resume_channel_conversation(
        user_id=user.id,
        channel_id=channel.id,
    )
    second = await service.get_or_resume_channel_conversation(
        user_id=user.id,
        channel_id=channel.id,
        force_new=True,
    )

    assert second.id != first.id

    first_row = await db_session.get(Conversation, first.id)
    assert first_row is not None
    assert first_row.status == "closed"


@pytest_asyncio.fixture
async def cloud_client(db_session: AsyncSession):
    from app.core.database import get_db
    from cloud.main import create_app

    app = create_app()

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_resume_channel_chat_api(cloud_client: AsyncClient, db_session: AsyncSession):
    user = User(username="portal_api", password_hash="x", role="user")
    db_session.add(user)
    await db_session.flush()

    channel = CustomerConfig(
        id="ch-portal-api",
        name="Studio Channel",
        user_id=user.id,
        enabled=True,
    )
    db_session.add(channel)
    await db_session.commit()

    token = create_access_token(
        data={"sub": user.id, "username": user.username, "role": user.role}
    )
    headers = {"Authorization": f"Bearer {token}"}

    first = await cloud_client.post(
        f"/api/portal/channels/{channel.id}/chat/resume",
        json={"title": "Studio Channel"},
        headers=headers,
    )
    assert first.status_code == 200
    first_id = first.json()["id"]

    second = await cloud_client.post(
        f"/api/portal/channels/{channel.id}/chat/resume",
        json={},
        headers=headers,
    )
    assert second.status_code == 200
    assert second.json()["id"] == first_id
    assert second.json()["customer_id"] == channel.id
