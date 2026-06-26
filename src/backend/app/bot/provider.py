"""LLM Provider factory and provider implementations."""

import json
from collections.abc import AsyncGenerator
from typing import Any

from loguru import logger

from app.bot.dsml_parser import contains_dsml, parse_dsml_tool_calls, strip_dsml_blocks
from app.models.ai_config import AIConfig
from app.services.llm_credentials import resolve_api_key


def _delta_reasoning_content(delta: Any) -> str | None:
    """DeepSeek thinking mode returns chain-of-thought on the delta."""
    if delta is None:
        return None
    rc = getattr(delta, "reasoning_content", None)
    if rc:
        return str(rc)
    model_extra = getattr(delta, "model_extra", None)
    if isinstance(model_extra, dict) and model_extra.get("reasoning_content"):
        return str(model_extra["reasoning_content"])
    if hasattr(delta, "model_dump"):
        try:
            dumped = delta.model_dump()
            if dumped.get("reasoning_content"):
                return str(dumped["reasoning_content"])
        except Exception:
            pass
    return None


def _chunk_reasoning_content(chunk: Any) -> str | None:
    """Fallback: read reasoning_content from raw chunk JSON."""
    if not hasattr(chunk, "model_dump"):
        return None
    try:
        data = chunk.model_dump()
        choices = data.get("choices") or []
        if not choices:
            return None
        delta = choices[0].get("delta") or {}
        rc = delta.get("reasoning_content")
        return str(rc) if rc else None
    except Exception:
        return None


class LLMProvider:
    """Base class for LLM providers."""

    async def stream_chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Stream chat completion. Yields dicts with 'type' key.

        Types:
        - content: {"type": "content", "content": "..."}
        - tool_call: {"type": "tool_call", "tool_call": {...}}
        - done: {"type": "done"}
        """
        if False:  # pragma: no cover
            yield  # Make this an async generator

    async def _parse_stream_chunks(
        self, stream: Any
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Parse streaming chunks from an OpenAI-compatible API."""
        tool_acc: dict[int, dict[str, Any]] = {}
        content_buffer = ""
        dsml_mode = False

        usage_info = None
        async for chunk in stream:
            if hasattr(chunk, 'usage') and chunk.usage:
                usage_info = {
                    "prompt_tokens": getattr(chunk.usage, 'prompt_tokens', 0) or 0,
                    "completion_tokens": getattr(chunk.usage, 'completion_tokens', 0) or 0,
                    "total_tokens": getattr(chunk.usage, 'total_tokens', 0) or 0,
                }
                continue
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta is None:
                continue

            reasoning = _delta_reasoning_content(delta) or _chunk_reasoning_content(
                chunk
            )
            if reasoning:
                yield {"type": "reasoning", "content": reasoning}

            if delta.content:
                content_buffer += delta.content
                if contains_dsml(content_buffer):
                    dsml_mode = True
                if not dsml_mode:
                    yield {"type": "content", "content": delta.content}

            if delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index if tc.index is not None else 0
                    if idx not in tool_acc:
                        tool_acc[idx] = {
                            "id": "",
                            "name": "",
                            "arguments": "",
                        }
                    if tc.id:
                        tool_acc[idx]["id"] = tc.id
                    if tc.function:
                        if tc.function.name:
                            tool_acc[idx]["name"] = tc.function.name
                        if tc.function.arguments:
                            tool_acc[idx]["arguments"] += tc.function.arguments

        if usage_info:
            yield {"type": "usage", **usage_info}

        for idx in sorted(tool_acc.keys()):
            entry = tool_acc[idx]
            args_raw = entry.get("arguments") or ""
            if args_raw:
                try:
                    arguments = json.loads(args_raw)
                except json.JSONDecodeError:
                    arguments = {"raw": args_raw}
            else:
                arguments = {}
            call_id = entry.get("id") or f"call_{idx}"
            yield {
                "type": "tool_call",
                "tool_call": {
                    "id": call_id,
                    "name": entry.get("name") or "",
                    "arguments": arguments,
                },
            }

        if not tool_acc and content_buffer:
            for call in parse_dsml_tool_calls(content_buffer):
                yield {"type": "tool_call", "tool_call": call}

        yield {"type": "done"}


def _format_provider_error(exc: Exception) -> str:
    msg = str(exc)
    lower = msg.lower()
    if "401" in msg or "authentication" in lower or "invalid" in lower and "api key" in lower:
        return (
            "Error: API 密钥无效或未配置。请在管理后台「模型工作台」更新该 AI 配置的 API Key，"
            "或在 .env 中设置对应环境变量（如 DEEPSEEK_API_KEY、MOONSHOT_API_KEY）。"
        )
    return f"Error: {exc}"


def resolve_llm_base_url(provider: str, api_base: str | None) -> str | None:
    """Provider default base URL + ensure /v1 suffix for OpenAI-compatible APIs."""
    from app.services.model_catalog import _resolve_base_url

    base = _resolve_base_url((provider or "").lower(), api_base)
    if not base:
        return None
    base = base.rstrip("/")
    openai_compatible = {
        "openai",
        "deepseek",
        "ollama",
        "groq",
        "moonshot",
        "siliconflow",
        "together",
        "openai-compatible",
    }
    if provider.lower() in openai_compatible and not base.endswith("/v1"):
        return f"{base}/v1"
    return base


class OpenAIProvider(LLMProvider):
    """OpenAI-compatible provider."""

    def __init__(self, ai_config: AIConfig) -> None:
        from openai import AsyncOpenAI

        base = resolve_llm_base_url(ai_config.provider, ai_config.api_base)
        api_key = resolve_api_key(ai_config.provider, ai_config.api_key)
        client_kwargs = {"api_key": api_key or "not-needed"}
        if base:
            client_kwargs["base_url"] = base

        self.client = AsyncOpenAI(**client_kwargs)
        self.model = ai_config.model
        self.api_base = base or ""
        self.provider_name = (ai_config.provider or "").lower()

    async def stream_chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> AsyncGenerator[dict[str, Any], None]:
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        # stream_options (usage in stream) is OpenAI-specific; some providers
        # (zhipu/glm) reject it with "API 调用参数有误" (code 1210). Only send
        # it for providers known to support it.
        _supports_usage = self.api_base and any(
            h in self.api_base for h in ("openai.com", "deepseek.com")
        )
        if self.provider_name in ("openai", "deepseek") or _supports_usage:
            kwargs["stream_options"] = {"include_usage": True}
        if tools:
            # Some providers (zhipu/glm coding endpoint) reject the OpenAI tools
            # schema with "API 调用参数有误" (code 1210). Skip tools for them —
            # the model still works for plain chat, just without function calling.
            _supports_tools = self.provider_name not in ("zhipu", "zhipu-coding")
            if _supports_tools:
                kwargs["tools"] = tools

        try:
            stream = await self.client.chat.completions.create(**kwargs)
            async for chunk in self._parse_stream_chunks(stream):
                yield chunk
        except Exception as e:
            logger.error(f"OpenAI provider error: {e}")
            yield {"type": "content", "content": _format_provider_error(e)}
            yield {"type": "done"}


class AnthropicProvider(LLMProvider):
    """Anthropic Claude provider."""

    def __init__(self, ai_config: AIConfig) -> None:
        from anthropic import AsyncAnthropic

        client_kwargs = {"api_key": ai_config.api_key}
        self.client = AsyncAnthropic(**client_kwargs)
        self.model = ai_config.model

    async def stream_chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> AsyncGenerator[dict[str, Any], None]:
        system_prompt = None
        api_messages = []
        for m in messages:
            if m["role"] == "system":
                system_prompt = m["content"]
            else:
                api_messages.append({"role": m["role"], "content": m["content"]})

        anthropic_tools = None
        if tools:
            anthropic_tools = []
            for t in tools:
                func = t.get("function") or t
                anthropic_tools.append({
                    "name": func.get("name", ""),
                    "description": func.get("description", ""),
                    "input_schema": func.get("parameters") or {"type": "object", "properties": {}, "required": []},
                })

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": api_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system_prompt:
            kwargs["system"] = system_prompt
        if anthropic_tools:
            kwargs["tools"] = anthropic_tools

        try:
            tool_use_acc: dict[int, dict[str, Any]] = {}
            content_idx = 0

            async with self.client.messages.stream(**kwargs) as stream:
                async for event in stream:
                    if event.type == "content_block_start":
                        block = event.content_block
                        if block.type == "tool_use":
                            tool_use_acc[event.index] = {
                                "id": block.id,
                                "name": block.name,
                                "arguments": "",
                            }
                            content_idx = event.index
                    elif event.type == "content_block_delta":
                        delta = event.delta
                        if delta.type == "text_delta":
                            yield {"type": "content", "content": delta.text}
                        elif delta.type == "input_json_delta":
                            if event.index in tool_use_acc:
                                tool_use_acc[event.index]["arguments"] += delta.partial_json
                    elif event.type == "content_block_stop":
                        if event.index in tool_use_acc:
                            entry = tool_use_acc[event.index]
                            args_raw = entry["arguments"]
                            try:
                                arguments = json.loads(args_raw) if args_raw else {}
                            except json.JSONDecodeError:
                                arguments = {"raw": args_raw}
                            yield {
                                "type": "tool_call",
                                "tool_call": {
                                    "id": entry["id"],
                                    "name": entry["name"],
                                    "arguments": arguments,
                                },
                            }
                            del tool_use_acc[event.index]

            yield {"type": "done"}
        except Exception as e:
            logger.error(f"Anthropic provider error: {e}")
            yield {"type": "content", "content": f"Error: {e}"}
            yield {"type": "done"}


class GoogleProvider(LLMProvider):
    """Google Generative AI (Gemini) provider."""

    def __init__(self, ai_config: AIConfig) -> None:
        from google import genai

        self.client = genai.Client(api_key=ai_config.api_key)
        self.model = ai_config.model

    async def stream_chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> AsyncGenerator[dict[str, Any], None]:
        from google.genai import types

        system_instruction = None
        google_contents: list[Any] = []
        for m in messages:
            if m["role"] == "system":
                system_instruction = m["content"]
            else:
                role = "model" if m["role"] == "assistant" else m["role"]
                google_contents.append(
                    types.Content(
                        role=role,
                        parts=[types.Part.from_text(text=m["content"])],
                    )
                )

        google_tools = None
        if tools:
            func_declarations = []
            for t in tools:
                func = t.get("function") or t
                params = func.get("parameters") or {"type": "object", "properties": {}}
                func_declarations.append(
                    types.FunctionDeclaration(
                        name=func.get("name", ""),
                        description=func.get("description", ""),
                        parameters=params,
                    )
                )
            google_tools = [types.Tool(function_declarations=func_declarations)]

        gen_config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
            system_instruction=system_instruction,
            tools=google_tools,
        )

        try:
            accumulated_text = ""
            async for response in self.client.aio.models.generate_content_stream(
                model=self.model,
                contents=google_contents,
                config=gen_config,
            ):
                if response.candidates is None:
                    # Handle safety block or empty response
                    continue
                for candidate in response.candidates:
                    if candidate.content is None:
                        continue
                    for part in candidate.content.parts:
                        if part.text:
                            accumulated_text += part.text
                            yield {"type": "content", "content": part.text}
                        elif hasattr(part, "function_call") and part.function_call:
                            fc = part.function_call
                            args = {}
                            if fc.args:
                                args = dict(fc.args) if isinstance(fc.args, dict) else fc.args
                            yield {
                                "type": "tool_call",
                                "tool_call": {
                                    "id": fc.id or f"call_{fc.name}",
                                    "name": fc.name,
                                    "arguments": args,
                                },
                            }

            yield {"type": "done"}
        except Exception as e:
            logger.error(f"Google provider error: {e}")
            yield {"type": "content", "content": f"Error: {e}"}
            yield {"type": "done"}


class OllamaProvider(OpenAIProvider):
    """Ollama local model provider (OpenAI-compatible API)."""

    def __init__(self, ai_config: AIConfig) -> None:
        from openai import AsyncOpenAI

        base_url = ai_config.api_base or "http://localhost:11434/v1"
        self.client = AsyncOpenAI(
            api_key=ai_config.api_key or "ollama",
            base_url=base_url,
        )
        self.model = ai_config.model


class GroqProvider(OpenAIProvider):
    """Groq cloud provider (OpenAI-compatible API, ultra-fast inference)."""

    def __init__(self, ai_config: AIConfig) -> None:
        from openai import AsyncOpenAI

        base_url = ai_config.api_base or "https://api.groq.com/openai/v1"
        self.client = AsyncOpenAI(
            api_key=ai_config.api_key,
            base_url=base_url,
        )
        self.model = ai_config.model


class OpenAICompatibleProvider(OpenAIProvider):
    """Generic OpenAI-compatible provider for custom endpoints."""

    def __init__(self, ai_config: AIConfig) -> None:
        from openai import AsyncOpenAI

        base = resolve_llm_base_url(ai_config.provider, ai_config.api_base)
        if not base:
            raise ValueError(
                f"api_base is required for provider {ai_config.provider!r} "
                "(or use a known provider id like moonshot/deepseek)"
            )

        self.client = AsyncOpenAI(
            api_key=resolve_api_key(ai_config.provider, ai_config.api_key) or "not-needed",
            base_url=base,
        )
        self.model = ai_config.model
        self.api_base = base or ""
        self.provider_name = (ai_config.provider or "").lower()


def _effective_api_base(ai_config: AIConfig) -> str:
    base = resolve_llm_base_url(ai_config.provider, ai_config.api_base) or ""
    return base.lower()


def _resolve_model_id(ai_config: AIConfig) -> str:
    """Map deprecated provider model ids to current ones."""
    model = ai_config.model or ""
    provider = (ai_config.provider or "").lower()
    base = _effective_api_base(ai_config)

    if provider == "deepseek" or "deepseek.com" in base:
        aliases = {
            "deepseek-chat": "deepseek-v4-flash",
            "deepseek-reasoner": "deepseek-v4-pro",
        }
        if model in aliases:
            return aliases[model]
        if model.startswith("gpt-"):
            logger.warning(
                f"Model {model!r} incompatible with DeepSeek API; using deepseek-v4-flash"
            )
            return "deepseek-v4-flash"
        return model

    return model


def create_provider(ai_config: AIConfig) -> LLMProvider:
    """Factory: create the appropriate LLM provider based on config."""
    provider_map: dict[str, type[LLMProvider]] = {
        "openai": OpenAIProvider,
        "deepseek": OpenAIProvider,  # DeepSeek uses OpenAI-compatible API
        "ollama": OllamaProvider,
        "groq": GroqProvider,
        "anthropic": AnthropicProvider,
        "google": GoogleProvider,
        # Generic / compatible providers
        "openai-compatible": OpenAICompatibleProvider,
        "zhipu": OpenAICompatibleProvider,  # Zhipu GLM uses OpenAI-compatible API
        "zhipu-coding": OpenAICompatibleProvider,  # Zhipu GLM Coding Plan (coding endpoint)
        "moonshot": OpenAICompatibleProvider,  # Moonshot/Kimi uses OpenAI-compatible API
        "siliconflow": OpenAICompatibleProvider,  # SiliconFlow uses OpenAI-compatible API
        "together": OpenAICompatibleProvider,  # Together AI uses OpenAI-compatible API
    }

    provider_class = provider_map.get(ai_config.provider)
    if provider_class is None:
        raise ValueError(
            f"Unsupported provider: {ai_config.provider}. "
            f"Supported: {list(provider_map.keys())}"
        )

    resolved_model = _resolve_model_id(ai_config)
    if resolved_model != ai_config.model:
        logger.info(
            f"Model alias: {ai_config.model} -> {resolved_model} "
            f"({ai_config.provider})"
        )
        ai_config.model = resolved_model

    base = resolve_llm_base_url(ai_config.provider, ai_config.api_base)
    logger.info(
        f"Creating provider: {ai_config.provider} with model {ai_config.model}"
        + (f" base={base}" if base else "")
    )
    return provider_class(ai_config)
