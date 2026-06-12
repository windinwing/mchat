"""Context window compression via summarization of old messages."""

from __future__ import annotations

from typing import Any

from app.core.logging import logger

_MODEL_CONTEXT_LIMITS: dict[str, int] = {
    "deepseek-v4-flash": 131072,
    "deepseek-v4-pro": 131072,
    "deepseek-chat": 65536,
    "deepseek-reasoner": 65536,
    "gpt-4o": 131072,
    "gpt-4o-mini": 131072,
    "gpt-4-turbo": 131072,
    "gpt-4": 8192,
    "gpt-3.5-turbo": 16384,
    "claude-3.5-sonnet": 200000,
    "claude-3-opus": 200000,
    "claude-3-haiku": 200000,
    "claude-3-sonnet": 200000,
    "gemini-1.5-pro": 1048576,
    "gemini-1.5-flash": 1048576,
    "gemini-2.0-flash": 1048576,
}


def get_context_limit(model: str) -> int:
    """Return approximate context window size for known models."""
    model_lower = (model or "").lower()
    for key, limit in _MODEL_CONTEXT_LIMITS.items():
        if key in model_lower or model_lower in key:
            return limit
    return 65536  # safe default


def estimate_tokens(text: str) -> int:
    """Rough token count: ~3 chars per token for mixed Chinese/English."""
    if not text:
        return 0
    chars = len(text)
    # Heuristic: Chinese chars ~1 token each, ASCII words ~0.75 tokens each
    cjk = sum(1 for c in text if '\u4e00' <= c <= '\u9fff' or '\u3000' <= c <= '\u303f')
    ascii_chars = chars - cjk
    return int(cjk + ascii_chars * 0.3)


def estimate_messages_tokens(messages: list[dict[str, Any]]) -> int:
    total = 0
    for m in messages:
        content = str(m.get("content") or "")
        total += estimate_tokens(content)
        total += 4  # per-message overhead (role separator)
    return total


async def compress_history(
    messages: list[dict[str, Any]],
    *,
    max_percent: float = 0.80,
    context_limit: int | None = None,
    provider_factory=None,
    model: str = "",
    api_key: str = "",
    api_base: str | None = None,
) -> list[dict[str, Any]]:
    """Compress oldest messages when total exceeds limit. Returns (possibly shortened) list."""
    if not messages or context_limit is None or context_limit <= 0:
        return messages

    total = estimate_messages_tokens(messages)
    limit = int(context_limit * max_percent)
    if total <= limit:
        return messages

    # Find cutoff: keep as many recent messages as fit within limit
    kept: list[dict[str, Any]] = []
    kept_tokens = 0
    summarizable: list[dict[str, Any]] = []
    summarizable_tokens = 0

    for m in reversed(messages):
        content = str(m.get("content") or "")
        m_tokens = estimate_tokens(content) + 4
        if kept_tokens + m_tokens <= limit:
            kept.insert(0, m)
            kept_tokens += m_tokens
        else:
            summarizable.insert(0, m)
            summarizable_tokens += m_tokens

    if not summarizable:
        return kept

    # Try LLM summarization
    summary = await _try_summarize(
        summarizable,
        provider_factory=provider_factory,
        model=model,
        api_key=api_key,
        api_base=api_base,
    )

    if summary:
        result = [{"role": "system", "content": summary}]
        result.extend(kept)
        logger.info(
            f"Context compressed: {len(summarizable)} messages ({summarizable_tokens} tokens) → summary (~{estimate_tokens(summary)} tokens)"
        )
        return result
    else:
        logger.warning("Context summarization failed, keeping recent messages only")
        return kept


async def _try_summarize(
    old_messages: list[dict[str, Any]],
    *,
    provider_factory=None,
    model: str = "",
    api_key: str = "",
    api_base: str | None = None,
) -> str | None:
    """Summarize old messages using LLM. Returns summary text or None."""
    if not provider_factory or not model or not api_key:
        return _simple_truncation_summary(old_messages)

    transcript_parts: list[str] = []
    for m in old_messages:
        role = str(m.get("role") or "unknown")
        content = str(m.get("content") or "")
        if len(content) > 2000:
            content = content[:2000] + "…"
        transcript_parts.append(f"[{role}]: {content}")

    transcript = "\n\n".join(transcript_parts)
    if estimate_tokens(transcript) > 12000:
        transcript = transcript[:48000] + "\n\n…[truncated]"

    summary_prompt = (
        "你是一个对话压缩助手。请用 200-500 字的中文总结以下对话历史，"
        "保留以下关键信息：\n"
        "- 用户的核心请求和意图\n"
        "- 做出的重要决策和结论\n"
        "- 修改的代码文件和关键变更\n"
        "- 遗留的待办事项或后续步骤\n"
        "- 项目上下文（项目名、技术栈等）\n\n"
        "只输出摘要本身，不要加任何前缀或说明。\n\n"
        f"{transcript}"
    )

    try:
        from dataclasses import dataclass

        @dataclass
        class TempAIConfig:
            provider: str = "openai"
            model: str = model
            api_key: str = api_key
            api_base: str | None = api_base
            temperature: float = 0.3
            max_tokens: int = 1024
            system_prompt: str | None = None

        temp_config = TempAIConfig()
        provider = provider_factory(temp_config)

        summary = ""
        async for chunk in provider.stream_chat(
            messages=[{"role": "user", "content": summary_prompt}],
            temperature=0.3,
            max_tokens=1024,
        ):
            if chunk.get("type") == "content":
                summary += chunk.get("content", "")
            elif chunk.get("type") == "tool_call":
                pass  # ignore tools during summarization

        summary = summary.strip()
        if summary:
            return f"## 对话历史摘要\n\n{summary}\n\n---\n\n以下是最近的对话："
    except Exception as e:
        logger.warning(f"LLM summarization failed: {e}")

    return _simple_truncation_summary(old_messages)


def _simple_truncation_summary(old_messages: list[dict[str, Any]]) -> str | None:
    """Fallback: return a brief note about dropped messages."""
    if not old_messages:
        return None
    user_msgs = [m for m in old_messages if m.get("role") == "user"]
    if not user_msgs:
        return None
    first = user_msgs[0].get("content", "")[:100]
    last = user_msgs[-1].get("content", "")[:100]
    count = len(old_messages)
    parts = [f"## 对话历史（已压缩 {count} 条消息）\n\n"]
    if first:
        parts.append(f"最早的用户问题: {first}…\n")
    if last:
        parts.append(f"最后一个被压缩的用户问题: {last}…\n")
    parts.append("\n---\n\n以下是最近的对话：")
    return "".join(parts)
