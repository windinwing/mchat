"""WebSocket route for real-time chat."""

import json
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.middleware.auth import has_global_scope
from app.models.conversation import Conversation
from app.models.user import User
from app.websocket import ws_manager

router = APIRouter()


async def _authenticate_ws(token: str | None) -> User | None:
    """Validate token and return user, or None."""
    if not token:
        return None
    try:
        from app.core.security import verify_access_token
        payload = verify_access_token(token)
        user_id = payload.get("sub")
        if not user_id:
            return None
        async with async_session_factory() as db:
            result = await db.execute(select(User).where(User.id == user_id))
            return result.scalar_one_or_none()
    except Exception:
        return None


async def _check_subscribe_permission(
    conversation_id: str,
    user: User | None,
    visitor_token: str | None,
) -> tuple[bool, str]:
    """Check if this client is allowed to subscribe to the given conversation.

    Returns (allowed, error_code). Error codes:
    - NOT_FOUND: conversation does not exist
    - ACCESS_DENIED: user/visitor lacks permission
    - MISSING_VISITOR_TOKEN: conversation requires visitor token but none provided
    """
    async with async_session_factory() as db:
        result = await db.execute(
            select(Conversation).where(Conversation.id == conversation_id)
        )
        conv = result.scalar_one_or_none()
        if conv is None:
            return False, "NOT_FOUND"

        if user is not None:
            if await has_global_scope(user, db):
                return True, ""
            if conv.user_id == user.id:
                return True, ""
            if conv.scope_type == "group" and conv.scope_id:
                from app.models.group import GroupMember

                member_result = await db.execute(
                    select(GroupMember).where(
                        GroupMember.group_id == conv.scope_id,
                        GroupMember.user_id == user.id,
                    )
                )
                if member_result.scalar_one_or_none() is not None:
                    return True, ""
            return False, "ACCESS_DENIED"

        if conv.visitor_id and visitor_token and conv.visitor_id == visitor_token:
            return True, ""
        if conv.visitor_id and not visitor_token:
            return False, "MISSING_VISITOR_TOKEN"
        if conv.visitor_id and visitor_token and conv.visitor_id != visitor_token:
            return False, "ACCESS_DENIED"

        return True, ""


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str | None = Query(None),
):
    """WebSocket endpoint for real-time chat streaming.

    Client messages:
    - { "type": "subscribe", "conversation_id": "..." }
    - { "type": "unsubscribe", "conversation_id": "..." }
    - { "type": "chat:message", "conversationId": "...", "content": "..." }  (HTTP is preferred)

    Server messages:
    - { "type": "chat:stream", "conversation_id": "...", "content": "..." }
    - { "type": "chat:stream:end", "conversation_id": "..." }
    - { "type": "chat:message", "message": {...} }
    """
    user = await _authenticate_ws(token)
    if user:
        logger.info(f"WebSocket authenticated as {user.username}")
    else:
        logger.info("WebSocket connected (anonymous)")

    await websocket.accept()
    current_conversation: str | None = None

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg_type = data.get("type", "")

            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})

            elif msg_type == "subscribe":
                conv_id = data.get("conversation_id") or data.get("conversationId")
                if conv_id:
                    visitor_token = data.get("visitor_token")
                    allowed, error_code = await _check_subscribe_permission(
                        conv_id, user, visitor_token
                    )
                    if not allowed:
                        logger.warning(
                            f"WebSocket subscribe denied for conversation {conv_id}: {error_code}"
                        )
                        await websocket.send_json({
                            "type": "error",
                            "code": error_code,
                            "message": error_code.replace("_", " ").title(),
                        })
                        continue

                    if current_conversation:
                        ws_manager.disconnect(websocket)
                    ws_manager._conversation_connections[conv_id].append(websocket)
                    ws_manager._ws_conversation[websocket] = conv_id
                    current_conversation = conv_id
                    logger.debug(f"WebSocket subscribed to conversation {conv_id}")
                    await websocket.send_json({"type": "subscribed", "conversation_id": conv_id})

            elif msg_type == "unsubscribe":
                ws_manager.disconnect(websocket)
                current_conversation = None

            elif msg_type == "chat:message":
                conv_id = data.get("conversationId") or data.get("conversation_id")
                content = data.get("content", "")
                if conv_id and content:
                    try:
                        from app.services.chat_service import ChatService
                        async with async_session_factory() as db:
                            chat_service = ChatService(db)
                            await chat_service.send_message(
                                conversation_id=conv_id,
                                content=content,
                                role="user",
                                user=user,
                            )
                    except Exception as e:
                        logger.error(f"WebSocket chat:message error: {e}")
                        await websocket.send_json({
                            "type": "error",
                            "code": "SEND_FAILED",
                            "message": "Failed to send message",
                        })

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WebSocket error: {e}")

    finally:
        ws_manager.disconnect(websocket)
