"""Cloud Portal studio chat — resume conversation + channel binding."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

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
        return await self.chat.get_or_resume_channel_conversation(
            user_id=user_id,
            customer_id=channel_id,
            title=title,
            force_new=force_new,
        )
