"""Register Cloud studio memory hooks into Core chat extensions."""

from __future__ import annotations

from typing import Any

from loguru import logger

from app.bot import chat_extensions
from app.models.conversation import Conversation
from cloud.config import cloud_settings
from cloud.services.studio_memory_service import (
    STUDIO_MEMORY_OPENAI_TOOLS,
    STUDIO_MEMORY_TOOL_HINT,
    StudioMemoryService,
    execute_studio_memory_tool,
    format_studio_memory_section,
    is_studio_chat,
)

_STUDIO_HISTORY_LIMIT = 100


def prepare_context(conversation: Conversation) -> StudioMemoryService | None:
    if not cloud_settings.studio_memory_enabled or not is_studio_chat(conversation):
        return None
    return StudioMemoryService.for_conversation(conversation)


def augment_system_prompt(
    conversation: Conversation,
    ctx: StudioMemoryService | None,
    prompt: str,
) -> str:
    if ctx is None:
        return prompt
    bootstrap = ctx.read_bootstrap()
    return prompt + format_studio_memory_section(bootstrap) + STUDIO_MEMORY_TOOL_HINT


def extra_tools(
    conversation: Conversation,
    ctx: StudioMemoryService | None,
) -> list[dict[str, Any]]:
    if ctx is None:
        return []
    return list(STUDIO_MEMORY_OPENAI_TOOLS)


def execute_tool(
    name: str,
    args: dict[str, Any],
    ctx: StudioMemoryService | None,
) -> Any | None:
    if ctx is None or not name.startswith("studio_memory_"):
        return None
    try:
        return execute_studio_memory_tool(ctx, name, args)
    except Exception as e:
        logger.error(f"Studio memory tool {name} failed: {e}")
        return {"error": str(e)}


def after_assistant_turn(
    conversation: Conversation,
    ctx: StudioMemoryService | None,
    user_text: str,
    assistant_text: str,
) -> None:
    if ctx is None or not user_text.strip():
        return
    try:
        ctx.append_daily_turn(
            user_text,
            assistant_text,
            conversation_id=conversation.id,
        )
    except Exception as e:
        logger.warning(f"Studio daily memory append failed: {e}")


def on_force_new_conversation(user_id: str, channel_id: str) -> None:
    if not cloud_settings.studio_memory_enabled:
        return
    try:
        StudioMemoryService(user_id, channel_id).append_session_reset()
    except Exception as e:
        logger.warning(f"Studio session reset marker failed: {e}")


def history_message_limit(conversation: Conversation) -> int | None:
    if is_studio_chat(conversation):
        return _STUDIO_HISTORY_LIMIT
    return None


def register_cloud_chat_extensions() -> None:
    """Wire Cloud Portal studio memory into Core bot pipeline."""
    chat_extensions.register_chat_extensions(
        prepare_context=prepare_context,
        augment_system_prompt=augment_system_prompt,
        extra_tools=extra_tools,
        execute_tool=execute_tool,
        after_assistant_turn=after_assistant_turn,
        on_force_new_conversation=on_force_new_conversation,
        history_message_limit=history_message_limit,
    )
