"""Small helper for one-shot JSON LLM completions."""

from __future__ import annotations

import json
from typing import Any

from loguru import logger

from app.bot.provider import create_provider
from app.models.ai_config import AIConfig


async def llm_complete_json(
    ai_config: AIConfig,
    *,
    system: str,
    user: str,
    temperature: float = 0.3,
    max_tokens: int = 4096,
) -> dict[str, Any]:
    """Return parsed JSON object from a chat completion."""
    provider = create_provider(ai_config)
    client = getattr(provider, "client", None)
    if client is None:
        raise RuntimeError(f"Provider {ai_config.provider} has no chat client")

    response = await client.chat.completions.create(
        model=provider.model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
    )
    raw = (response.choices[0].message.content or "").strip()
    if not raw:
        raise ValueError("Empty LLM response")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.warning(f"LLM returned invalid JSON: {raw[:500]}")
        raise ValueError(f"Invalid JSON from LLM: {e}") from e
    if not isinstance(payload, dict):
        raise ValueError("LLM JSON must be an object")
    return payload
