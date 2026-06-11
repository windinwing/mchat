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
    """Wire Cloud Portal studio memory into Core bot pipeline (chain, do not replace)."""
    prev_prepare = chat_extensions._handlers["prepare_context"]
    prev_augment = chat_extensions._handlers["augment_system_prompt"]
    prev_extra = chat_extensions._handlers["extra_tools"]
    prev_execute = chat_extensions._handlers["execute_tool"]
    prev_after = chat_extensions._handlers["after_assistant_turn"]
    prev_force_new = chat_extensions._handlers["on_force_new_conversation"]
    prev_history = chat_extensions._handlers["history_message_limit"]

    def merged_prepare(conversation: Conversation) -> StudioMemoryService | None:
        ctx = prepare_context(conversation)
        if ctx is not None:
            return ctx
        return prev_prepare(conversation)

    def merged_augment(
        conversation: Conversation,
        ctx: StudioMemoryService | None,
        prompt: str,
    ) -> str:
        text = augment_system_prompt(conversation, ctx, prompt)
        return prev_augment(conversation, ctx, text)

    def merged_extra(
        conversation: Conversation,
        ctx: StudioMemoryService | None,
    ) -> list[dict[str, Any]]:
        tools = list(extra_tools(conversation, ctx))
        tools.extend(prev_extra(conversation, ctx))
        return tools

    async def merged_execute(name: str, args: dict[str, Any], ctx: StudioMemoryService | None) -> Any | None:
        result = execute_tool(name, args, ctx)
        if result is not None:
            return result
        prev_result = prev_execute(name, args, ctx)
        if prev_result is not None and hasattr(prev_result, "__await__"):
            return await prev_result
        return prev_result

    def merged_after(
        conversation: Conversation,
        ctx: StudioMemoryService | None,
        user_text: str,
        assistant_text: str,
    ) -> None:
        after_assistant_turn(conversation, ctx, user_text, assistant_text)
        prev_after(conversation, ctx, user_text, assistant_text)

    def merged_force_new(user_id: str, channel_id: str) -> None:
        on_force_new_conversation(user_id, channel_id)
        prev_force_new(user_id, channel_id)

    def merged_history(conversation: Conversation) -> int | None:
        limit = history_message_limit(conversation)
        if limit is not None:
            return limit
        return prev_history(conversation)

    chat_extensions.register_chat_extensions(
        prepare_context=merged_prepare,
        augment_system_prompt=merged_augment,
        extra_tools=merged_extra,
        execute_tool=merged_execute,
        after_assistant_turn=merged_after,
        on_force_new_conversation=merged_force_new,
        history_message_limit=merged_history,
    )
