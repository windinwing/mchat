"""Optional chat extension hooks (Core defaults are no-ops).

Cloud edition registers handlers at startup via ``cloud.bot.register``.
"""

from __future__ import annotations

from typing import Any, Callable

from app.models.conversation import Conversation

PrepareContextFn = Callable[[Conversation], Any | None]
AugmentPromptFn = Callable[[Conversation, Any, str], str]
ExtraToolsFn = Callable[[Conversation, Any], list[dict[str, Any]]]
ExecuteToolFn = Callable[[str, dict[str, Any], Any], Any | None]
AfterTurnFn = Callable[[Conversation, Any, str, str], None]
OnForceNewFn = Callable[[str, str], None]
HistoryLimitFn = Callable[[Conversation], int | None]

_handlers: dict[str, Callable[..., Any]] = {
    "prepare_context": lambda _conversation: None,
    "augment_system_prompt": lambda _conversation, _ctx, prompt: prompt,
    "extra_tools": lambda _conversation, _ctx: [],
    "execute_tool": lambda _name, _args, _ctx: None,
    "after_assistant_turn": lambda _conversation, _ctx, _user, _assistant: None,
    "on_force_new_conversation": lambda _user_id, _channel_id: None,
    "history_message_limit": lambda _conversation: None,
}


def register_chat_extensions(**handlers: Callable[..., Any]) -> None:
    """Replace one or more extension handlers (Cloud registers on boot)."""
    _handlers.update(handlers)


def prepare_studio_context(conversation: Conversation) -> Any | None:
    return _handlers["prepare_context"](conversation)


def augment_system_prompt(conversation: Conversation, ctx: Any, prompt: str) -> str:
    fn = _handlers["augment_system_prompt"]
    return fn(conversation, ctx, prompt)


def extra_tools(conversation: Conversation, ctx: Any) -> list[dict[str, Any]]:
    fn = _handlers["extra_tools"]
    return fn(conversation, ctx)


def execute_extension_tool(name: str, args: dict[str, Any], ctx: Any) -> Any | None:
    fn = _handlers["execute_tool"]
    return fn(name, args, ctx)


def after_assistant_turn(
    conversation: Conversation,
    ctx: Any,
    user_text: str,
    assistant_text: str,
) -> None:
    fn = _handlers["after_assistant_turn"]
    fn(conversation, ctx, user_text, assistant_text)


def on_force_new_conversation(user_id: str, channel_id: str) -> None:
    fn = _handlers["on_force_new_conversation"]
    fn(user_id, channel_id)


def history_message_limit(conversation: Conversation) -> int | None:
    fn = _handlers["history_message_limit"]
    return fn(conversation)
