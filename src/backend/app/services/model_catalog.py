"""Fetch model lists and test LLM connections (AstrBot-style catalog API)."""

from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

# Fallback when remote list API is unavailable
STATIC_MODELS: dict[str, list[str]] = {
    "openai": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
    "anthropic": [
        "claude-3-5-sonnet-20241022",
        "claude-3-haiku-20240307",
        "claude-3-opus-20240229",
    ],
    "google": ["gemini-2.0-flash", "gemini-2.0-pro"],
    "deepseek": [
        "deepseek-v4-flash",
        "deepseek-v4-pro",
        "deepseek-chat",
        "deepseek-reasoner",
    ],
    "ollama": ["llama3.2", "qwen2.5", "deepseek-r1", "mistral"],
    "lmstudio": ["local-model"],
    "groq": [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "mixtral-8x7b-32768",
    ],
    "zhipu": ["glm-4-plus", "glm-4-flash", "glm-4.5-air", "glm-4.6", "glm-4.7", "glm-5", "glm-5.1", "glm-5.2", "glm-5-turbo"],
    "zhipu-coding": ["glm-5.2", "glm-5-turbo", "glm-5.1", "glm-4.7", "glm-4.5-air"],
    "moonshot": ["moonshot-v1-8k", "moonshot-v1-32k"],
    "siliconflow": ["Qwen/Qwen2.5-7B-Instruct", "deepseek-ai/DeepSeek-V3"],
    "together": [
        "meta-llama/Llama-3.3-70B-Instruct-Turbo",
        "mistralai/Mixtral-8x7B-Instruct-v0.1",
    ],
}

# Legacy DeepSeek model ids (deprecated 2026-07-24)
DEEPSEEK_MODEL_ALIASES: dict[str, str] = {
    "deepseek-chat": "deepseek-v4-flash",
    "deepseek-reasoner": "deepseek-v4-pro",
}

DEFAULT_BASE_URLS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com",
    "google": "https://generativelanguage.googleapis.com",
    "deepseek": "https://api.deepseek.com/v1",
    "ollama": "http://localhost:11434/v1",
    "lmstudio": "http://localhost:1234/v1",
    "groq": "https://api.groq.com/openai/v1",
    "zhipu": "https://open.bigmodel.cn/api/paas/v4",
    "zhipu-coding": "https://open.bigmodel.cn/api/coding/paas/v4",
    "moonshot": "https://api.moonshot.cn/v1",
    "siliconflow": "https://api.siliconflow.cn/v1",
    "together": "https://api.together.xyz/v1",
}


@dataclass
class ConnectionParams:
    provider: str
    api_key: str
    api_base: str | None = None


#: Providers whose base URL needs a /v1 suffix when one isn't present.
#: NOTE: this is NOT the same as "OpenAI-compatible". Zhipu GLM is OpenAI-
#: compatible but its URL already includes its own version path (/paas/v4),
#: so adding /v1 would corrupt it. Listed here are providers whose default
#: base ends in a bare host (e.g. http://localhost:11434) needing /v1 appended.
_NEEDS_V1_SUFFIX_PROVIDERS = frozenset({
    "openai",
    "deepseek",
    "ollama",
    "lmstudio",
    "groq",
    "moonshot",
    "siliconflow",
    "together",
    "openai-compatible",
})


def _resolve_base_url(provider: str, api_base: str | None) -> str | None:
    base = (api_base or "").strip().rstrip("/") or DEFAULT_BASE_URLS.get(provider)
    if not base:
        return None
    # Ensure /v1 suffix for OpenAI-compatible endpoints (Ollama, LM Studio, …).
    # Omitting it silently breaks /v1/models and /v1/chat/completions.
    if (provider or "").lower() in _NEEDS_V1_SUFFIX_PROVIDERS and not base.endswith("/v1"):
        base = f"{base}/v1"
    return base


async def list_models(params: ConnectionParams) -> list[str]:
    """Return model ids from the provider API, with static fallback."""
    provider = params.provider.lower()
    try:
        if provider in (
            "openai",
            "deepseek",
            "ollama",
            "lmstudio",
            "groq",
            "zhipu",
            "zhipu-coding",
            "moonshot",
            "siliconflow",
            "together",
            "openai-compatible",
        ):
            return await _list_openai_compatible(params)
        if provider == "anthropic":
            return await _list_anthropic(params)
        if provider == "google":
            return await _list_google(params)
    except Exception as e:
        logger.warning(f"list_models failed for {provider}: {e}")

    return list(STATIC_MODELS.get(provider, []))


async def _list_openai_compatible(params: ConnectionParams) -> list[str]:
    from openai import AsyncOpenAI

    from app.services.llm_credentials import is_local_provider

    base = _resolve_base_url(params.provider, params.api_base)
    key = params.api_key or (
        params.provider if is_local_provider(params.provider) else "not-needed"
    )
    client_kwargs: dict = {"api_key": key}
    if base:
        client_kwargs["base_url"] = base
    client = AsyncOpenAI(**client_kwargs)
    page = await client.models.list()
    ids = sorted({m.id for m in page.data if getattr(m, "id", None)})
    return ids


async def _list_anthropic(params: ConnectionParams) -> list[str]:
    from anthropic import AsyncAnthropic

    client = AsyncAnthropic(api_key=params.api_key)
    page = await client.models.list()
    ids = sorted({m.id for m in page.data if getattr(m, "id", None)})
    return ids or list(STATIC_MODELS["anthropic"])


async def _list_google(params: ConnectionParams) -> list[str]:
    from google import genai

    client = genai.Client(api_key=params.api_key)
    names: list[str] = []
    for m in client.models.list():
        name = getattr(m, "name", None) or ""
        if name.startswith("models/"):
            name = name[7:]
        if name:
            names.append(name)
    return sorted(set(names)) or list(STATIC_MODELS["google"])


def normalize_model_id(provider: str, model: str) -> str:
    if provider == "deepseek":
        return DEEPSEEK_MODEL_ALIASES.get(model, model)
    return model


async def test_connection(
    params: ConnectionParams,
    model: str | None = None,
) -> tuple[bool, str]:
    """Send a minimal request to verify credentials."""
    from app.models.ai_config import AIConfig
    from app.bot.provider import create_provider

    raw_model = model or STATIC_MODELS.get(params.provider, ["test"])[0]
    probe_model = normalize_model_id(params.provider, raw_model)
    from app.services.llm_credentials import resolve_api_key

    cfg = AIConfig(
        id="probe",
        user_id="probe",
        name="probe",
        provider=params.provider,
        model=probe_model,
        api_key=resolve_api_key(params.provider, params.api_key),
        api_base=params.api_base or _resolve_base_url(params.provider, None),
        system_prompt=None,
        temperature=0,
        max_tokens=16,
        is_default=False,
    )
    try:
        llm = create_provider(cfg)
        messages = [{"role": "user", "content": "hi"}]
        error_text = ""
        got_content = False
        async for chunk in llm.stream_chat(messages, max_tokens=8):
            if chunk.get("type") == "content":
                text = chunk.get("content") or ""
                # stream_chat wraps request failures as {"content": "Error: ..."}
                # rather than raising. Treat those as a failed connection so the
                # user sees the real cause (connection refused, model not found, …).
                if text.startswith("Error:"):
                    error_text = text
                elif text:
                    got_content = True
            elif chunk.get("type") == "done":
                break
        if got_content:
            return True, "连接成功"
        if error_text:
            return False, error_text
        return True, "连接成功（无返回内容）"
    except Exception as e:
        return False, str(e)
