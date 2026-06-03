"""Persist assistant replies (including configuration errors) to the database."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_config import AIConfig
from app.models.conversation import Conversation
from app.models.message import Message


def looks_like_config_error(content: str) -> bool:
    text = (content or "").strip()
    if not text:
        return False
    if text.startswith("Error:"):
        return True
    markers = (
        "未配置",
        "No AI configuration",
        "API 密钥",
        "API Key",
        "configure an AI",
        "模型工作台",
    )
    return any(m in text for m in markers)


async def find_assistant_reply_after(
    db: AsyncSession,
    conversation_id: str,
    user_message: Message,
) -> Message | None:
    result = await db.execute(
        select(Message)
        .where(
            Message.conversation_id == conversation_id,
            Message.role == "assistant",
            Message.created_at >= user_message.created_at,
        )
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def persist_assistant_reply(
    db: AsyncSession,
    conversation: Conversation,
    content: str,
    *,
    is_error: bool | None = None,
    ai_config: AIConfig | None = None,
) -> Message:
    text = (content or "").strip()
    if not text:
        raise ValueError("assistant reply content is empty")

    err = is_error if is_error is not None else looks_like_config_error(text)
    extra_data: dict = {}
    if err:
        extra_data["is_error"] = True
    if ai_config is not None:
        extra_data["model"] = ai_config.model
        extra_data["provider"] = ai_config.provider

    msg = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=text,
        extra_data=extra_data or None,
    )
    db.add(msg)
    now = datetime.now(timezone.utc)
    conversation.updated_at = now
    conversation.last_seen_at = now
    await db.flush()
    return msg


async def ensure_assistant_reply_persisted(
    db: AsyncSession,
    conversation: Conversation,
    user_message: Message,
    full_content: str,
    ai_config: AIConfig | None = None,
) -> Message | None:
    text = (full_content or "").strip()
    if not text:
        return None

    existing = await find_assistant_reply_after(db, conversation.id, user_message)
    if existing is not None and (existing.content or "").strip() == text:
        return existing
    if existing is not None and not looks_like_config_error(text):
        return existing

    return await persist_assistant_reply(
        db,
        conversation,
        text,
        is_error=looks_like_config_error(text),
        ai_config=ai_config,
    )
