"""Core chat extensions: propose_skill tool for multi-turn skill drafting."""

from __future__ import annotations

from typing import Any

from loguru import logger

from app.bot import chat_extensions
from app.bot.tool_runtime import get_bot_conversation, get_bot_db, get_bot_user_id
from app.models.conversation import Conversation
from app.services.skill_draft_service import SkillDraftService

PROPOSE_SKILL_TOOL = {
    "type": "function",
    "function": {
        "name": "propose_skill",
        "description": (
            "Propose or revise a tenant skill draft from the current conversation. "
            "Use when the user wants to turn this chat into a reusable skill."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "hint": {
                    "type": "string",
                    "description": "Optional focus for the skill (name, purpose, behavior).",
                },
                "draft_id": {
                    "type": "string",
                    "description": "Existing draft id to revise; omit to create new.",
                },
            },
            "required": [],
        },
    },
}

_SKILL_DRAFT_TOOL_HINT = (
    "\n\nWhen the user wants to turn this chat into a reusable skill, call propose_skill "
    "with a short hint. Users may also type /skill, /做技能, or /保存技能 in chat."
)


def _draft_extra_tools(conversation: Conversation, _ctx: Any) -> list[dict[str, Any]]:
    if not conversation.user_id:
        return []
    return [PROPOSE_SKILL_TOOL]


def _draft_augment(conversation: Conversation, _ctx: Any, prompt: str) -> str:
    if not conversation.user_id:
        return prompt
    return prompt + _SKILL_DRAFT_TOOL_HINT


async def _draft_execute(name: str, args: dict[str, Any], _ctx: Any) -> Any | None:
    if name != "propose_skill":
        return None

    db = get_bot_db()
    conversation = get_bot_conversation()
    user_id = get_bot_user_id()
    if db is None or conversation is None or not user_id:
        return {"error": "Bot runtime not ready"}

    service = SkillDraftService(db)
    try:
        draft = await service.create_from_chat(
            user_id=user_id,
            conversation_id=conversation.id,
            hint=str(args.get("hint") or "").strip() or None,
            existing_draft_id=str(args.get("draft_id") or "").strip() or None,
        )
        extra = service.draft_extra_data(draft)
        return {
            "ok": True,
            "message": (
                f"Skill draft **{draft.name}** ready for review "
                f"({extra['file_count']} files). Ask the user to confirm in the chat UI."
            ),
            "draft": extra,
        }
    except Exception as e:
        logger.error(f"propose_skill failed: {e}")
        return {"error": str(e)}


def register_skill_draft_extensions() -> None:
    """Chain skill-draft hooks onto any existing chat extensions (e.g. Cloud studio)."""
    prev_extra = chat_extensions._handlers["extra_tools"]
    prev_augment = chat_extensions._handlers["augment_system_prompt"]
    prev_execute = chat_extensions._handlers["execute_tool"]

    def merged_extra(conversation: Conversation, ctx: Any) -> list[dict[str, Any]]:
        tools = _draft_extra_tools(conversation, ctx)
        tools.extend(prev_extra(conversation, ctx))
        return tools

    def merged_augment(conversation: Conversation, ctx: Any, prompt: str) -> str:
        text = _draft_augment(conversation, ctx, prompt)
        return prev_augment(conversation, ctx, text)

    async def merged_execute(name: str, args: dict[str, Any], ctx: Any) -> Any | None:
        result = await _draft_execute(name, args, ctx)
        if result is not None:
            return result
        prev_result = prev_execute(name, args, ctx)
        if prev_result is not None and hasattr(prev_result, "__await__"):
            return await prev_result
        return prev_result

    chat_extensions.register_chat_extensions(
        extra_tools=merged_extra,
        augment_system_prompt=merged_augment,
        execute_tool=merged_execute,
    )
