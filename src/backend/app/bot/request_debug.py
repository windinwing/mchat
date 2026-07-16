"""Build and record AI request payloads for debugging.

Two outputs, each gated by an admin setting (``chat_debug_log_enabled`` /
``chat_debug_extra_data_enabled``):

- **Full payload** → ``logs/ai_request.log`` (one line per request, daily
  rotation). Contains the complete system prompt, every message, and the tool
  JSON definitions — everything actually sent to the model. Used for offline
  debugging of context-overflow and prompt issues.
- **Summary** → the assistant message's ``extra_data.debug_request``. Compact
  stats only (token estimate, tool count, RAG hits, …) so the DB row stays
  small; the full text lives in the log file.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from loguru import logger

from app.bot.context_compressor import estimate_messages_tokens, get_context_limit

if TYPE_CHECKING:
    from app.models.ai_config import AIConfig


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tool_names(tools: list[dict[str, Any]] | None) -> list[str]:
    if not tools:
        return []
    names: list[str] = []
    for t in tools:
        if isinstance(t, dict):
            func = t.get("function") or t
            name = func.get("name")
            if name:
                names.append(str(name))
    return names


def build_debug_summary(
    ai_config: "AIConfig",
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    knowledge_hits: list[dict[str, Any]] | None,
    rag_top_k: int | None,
    system_prompt: str,
    *,
    estimated_prompt_tokens: int | None = None,
) -> dict[str, Any]:
    """Return a compact ``{"debug_request": {...}}`` dict for extra_data."""
    token_est = estimated_prompt_tokens
    if token_est is None:
        token_est = estimate_messages_tokens(messages)
    context_limit = get_context_limit(ai_config.model or "")
    max_tokens = ai_config.max_tokens or 0
    return {
        "debug_request": {
            "provider": ai_config.provider,
            "model": ai_config.model,
            "max_tokens": max_tokens,
            "temperature": ai_config.temperature,
            "message_count": len(messages),
            "tool_count": len(tools or []),
            "tool_names": _tool_names(tools),
            "knowledge_hit_count": len(knowledge_hits or []),
            "rag_top_k": rag_top_k,
            "estimated_prompt_tokens": token_est,
            "estimated_total_tokens": token_est + max_tokens,
            "context_limit": context_limit,
            "over_context_limit": (token_est + max_tokens) > context_limit,
            "system_prompt_length": len(system_prompt or ""),
            "timestamp": _now_iso(),
        }
    }


def log_full_request(
    *,
    conversation_id: str,
    message_id: str | None,
    ai_config: "AIConfig",
    system_prompt: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    knowledge_hits: list[dict[str, Any]] | None,
    rag_top_k: int | None,
    estimated_prompt_tokens: int,
) -> None:
    """Write the complete request payload to ``logs/ai_request.log``.

    The message body is a single JSON line containing every field the model
    actually received, so it can be replayed/inspected offline.
    """
    payload = {
        "timestamp": _now_iso(),
        "conversation_id": conversation_id,
        "message_id": message_id,
        "provider": ai_config.provider,
        "model": ai_config.model,
        "api_base": ai_config.api_base,
        "temperature": ai_config.temperature,
        "max_tokens": ai_config.max_tokens,
        "rag_top_k": rag_top_k,
        "estimated_prompt_tokens": estimated_prompt_tokens,
        "context_limit": get_context_limit(ai_config.model or ""),
        "knowledge_hits": knowledge_hits or [],
        "system_prompt": system_prompt,
        "tools": tools or [],
        "messages": messages,
    }
    logger.bind(ai_request=True).info(
        json.dumps(payload, ensure_ascii=False, default=str)
    )
