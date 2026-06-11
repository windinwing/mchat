"""Runtime context for bot tool extensions (skill drafts, etc.)."""

from __future__ import annotations

from contextvars import ContextVar
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.conversation import Conversation

_bot_db: ContextVar[AsyncSession | None] = ContextVar("bot_db", default=None)
_bot_conversation: ContextVar[Conversation | None] = ContextVar("bot_conversation", default=None)
_bot_user_id: ContextVar[str | None] = ContextVar("bot_user_id", default=None)
_bot_group_devbridge_allowlists: ContextVar[dict[str, set[str]] | None] = ContextVar(
    "bot_group_devbridge_allowlists",
    default=None,
)


def set_bot_tool_context(
    *,
    db: AsyncSession,
    conversation: Conversation,
    user_id: str,
    group_devbridge_allowlists: dict[str, set[str]] | None = None,
) -> None:
    _bot_db.set(db)
    _bot_conversation.set(conversation)
    _bot_user_id.set(user_id)
    _bot_group_devbridge_allowlists.set(group_devbridge_allowlists)


def clear_bot_tool_context() -> None:
    _bot_db.set(None)
    _bot_conversation.set(None)
    _bot_user_id.set(None)
    _bot_group_devbridge_allowlists.set(None)


def get_bot_db() -> AsyncSession | None:
    return _bot_db.get()


def get_bot_conversation() -> Conversation | None:
    return _bot_conversation.get()


def get_bot_user_id() -> str | None:
    return _bot_user_id.get()


def get_bot_group_devbridge_allowlists() -> dict[str, set[str]] | None:
    return _bot_group_devbridge_allowlists.get()
