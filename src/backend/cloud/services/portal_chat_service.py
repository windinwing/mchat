"""Cloud Portal studio chat — resume conversation + channel binding."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import chat_extensions
from app.models.conversation import Conversation
from app.models.customer import CustomerConfig
from app.schemas.chat import ConversationResponse
from app.services.chat_service import ChatService


class PortalChatService:
    """Portal-only chat helpers (not used by Core / dev edition)."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.chat = ChatService(db)

    async def get_or_resume_channel_conversation(
        self,
        user_id: str,
        channel_id: str,
        title: str | None = None,
        force_new: bool = False,
    ) -> ConversationResponse:
        """Latest active conversation for this user's channel, or create a new one."""
        channel_result = await self.db.execute(
            select(CustomerConfig).where(
                CustomerConfig.id == channel_id,
                CustomerConfig.user_id == user_id,
                CustomerConfig.enabled == True,
            )
        )
        channel = channel_result.scalar_one_or_none()
        if channel is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Channel not found",
            )

        resolved_title = title or channel.name or "New Chat"

        if force_new:
            active_result = await self.db.execute(
                select(Conversation).where(
                    Conversation.user_id == user_id,
                    Conversation.customer_id == channel_id,
                    Conversation.status == "active",
                )
            )
            for conv in active_result.scalars().all():
                conv.status = "closed"
                conv.updated_at = datetime.now(timezone.utc)
            await self.db.flush()
            chat_extensions.on_force_new_conversation(user_id, channel_id)
        else:
            result = await self.db.execute(
                select(Conversation)
                .where(
                    Conversation.user_id == user_id,
                    Conversation.customer_id == channel_id,
                    Conversation.status == "active",
                )
                .order_by(Conversation.updated_at.desc(), Conversation.created_at.desc())
                .limit(1)
            )
            existing = result.scalar_one_or_none()
            if existing is not None:
                loaded = await self.chat.get_conversation(existing.id, user_id=user_id)
                if loaded is not None:
                    return loaded

        return await self.chat.create_conversation(
            user_id=user_id,
            title=resolved_title,
            customer_id=channel_id,
        )
