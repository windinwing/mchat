"""Send-message lifecycle: blocking bot pipeline + 502 on hard failure."""

import asyncio

import pytest
from httpx import AsyncClient

from app.core.event_bus import event_bus
from app.core.database import async_session_factory
from app.models.message import Message


@pytest.fixture
def isolated_bot():
    """Unsubscribe the real bot handler (subscribed by create_app via
    init_bot_engine) so test fakes control the pipeline deterministically."""
    from app.bot.handler import on_message_created

    event_bus.unsubscribe("message_created", on_message_created)
    yield
    event_bus.subscribe("message_created", on_message_created)


def _subscribe(handler):
    event_bus.subscribe("message_created", handler)
    return lambda: event_bus.unsubscribe("message_created", handler)


@pytest.mark.asyncio
async def test_send_502_when_bot_never_replies(
    client: AsyncClient, auth_headers: dict, isolated_bot
):
    """Pipeline ran but no assistant reply was persisted -> 502 Bad Gateway."""

    async def silent_handler(message, conversation, user=None):
        return

    restore = _subscribe(silent_handler)
    try:
        conv_id = (
            await client.post(
                "/api/chat/conversations",
                json={"title": "Lifecycle"},
                headers=auth_headers,
            )
        ).json()["id"]
        resp = await client.post(
            "/api/chat/send",
            json={"conversation_id": conv_id, "content": "hi", "role": "user"},
            headers=auth_headers,
        )
        assert resp.status_code == 502
        assert "AI 服务未返回有效响应" in resp.json()["detail"]
    finally:
        restore()


@pytest.mark.asyncio
async def test_send_200_when_bot_replies(
    client: AsyncClient, auth_headers: dict, isolated_bot
):
    """Pipeline persisted an assistant reply -> 200 with the user message."""

    async def replying_handler(message, conversation, user=None):
        async with async_session_factory() as db:
            db.add(
                Message(
                    conversation_id=conversation.id,
                    role="assistant",
                    content="hello from bot",
                )
            )
            await db.commit()

    restore = _subscribe(replying_handler)
    try:
        conv_id = (
            await client.post(
                "/api/chat/conversations",
                json={"title": "Lifecycle2"},
                headers=auth_headers,
            )
        ).json()["id"]
        resp = await client.post(
            "/api/chat/send",
            json={"conversation_id": conv_id, "content": "hi", "role": "user"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["role"] == "user"
    finally:
        restore()


@pytest.mark.asyncio
async def test_send_502_on_bot_timeout(
    client: AsyncClient, auth_headers: dict, isolated_bot, monkeypatch
):
    """Handler exceeds the configured timeout -> 502 with timeout detail."""
    monkeypatch.setattr(
        "app.core.config.settings.chat_process_timeout_seconds", 0.5
    )

    async def slow_handler(message, conversation, user=None):
        await asyncio.sleep(5)

    restore = _subscribe(slow_handler)
    try:
        conv_id = (
            await client.post(
                "/api/chat/conversations",
                json={"title": "Lifecycle3"},
                headers=auth_headers,
            )
        ).json()["id"]
        resp = await client.post(
            "/api/chat/send",
            json={"conversation_id": conv_id, "content": "hi", "role": "user"},
            headers=auth_headers,
        )
        assert resp.status_code == 502
        assert "超时" in resp.json()["detail"]
    finally:
        restore()


@pytest.mark.asyncio
async def test_real_handler_error_reply_returns_200(
    client: AsyncClient, auth_headers: dict
):
    """With the real bot handler (no AI config in tests) the persisted
    assistant error reply satisfies the 502 check -> 200."""
    conv_id = (
        await client.post(
            "/api/chat/conversations",
            json={"title": "RealHandler"},
            headers=auth_headers,
        )
    ).json()["id"]
    resp = await client.post(
        "/api/chat/send",
        json={"conversation_id": conv_id, "content": "hi", "role": "user"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
