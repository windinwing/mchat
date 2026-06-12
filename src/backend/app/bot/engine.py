"""Bot engine - core message processing pipeline with streaming."""

from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from typing import Any
import uuid

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.messages import (
    build_assistant_tool_call_message,
    build_tool_result_message,
    sanitize_history_messages,
)
from app.utils.chat_upload import attachment_prompt_text
from app.bot.provider import create_provider
from app.bot.patent_links import linkify_patent_ids, patent_link_settings_from_skills
from app.bot.patent_search_followup import (
    _DEFAULT_EXPORT_NUDGE,
    find_patent_search_skill,
    is_patent_search_success,
    patent_search_enable_presentation,
    patent_search_enable_summary,
    patent_search_observation_nudge,
    patent_search_presentation_nudge,
)
from app.bot.skill_context import (
    append_patent_tool_hints,
    build_executable_skill_prompt_section,
    build_openai_tools,
    build_prompt_skill_section,
    knowledge_base_ids_for_chat,
    load_skills_for_chat,
)
from app.knowledge.rag import RagService
from app.models.ai_config import AIConfig
from app.models.conversation import Conversation
from app.models.customer import CustomerConfig
from app.models.group import GroupMemoryEntry
from app.models.knowledge import KnowledgeBase
from app.models.message import Message
from app.models.skill import Skill
from app.utils.outbound_assets import enrich_message_extra_data
from app.bot.auto_reply_rules import (
    build_auto_reply_note,
    detect_message_channel,
    match_auto_reply_rules,
)
from app.bot import chat_extensions

_HISTORY_MESSAGE_LIMIT = 30


def _history_message_limit(conversation: Conversation) -> int:
    """Edition extensions may raise the limit for studio chats."""
    custom = chat_extensions.history_message_limit(conversation)
    if custom is not None:
        return custom
    return _HISTORY_MESSAGE_LIMIT


def _format_structured_tool_dict(result: dict[str, Any]) -> str:
    """Render ops/health-style dicts when message/content/text are absent."""
    import json

    lines: list[str] = []
    if result.get("ok") is False and result.get("error"):
        return ""
    if "status" in result:
        icon = "✅" if result.get("ok") else "⚠️"
        lines.append(f"{icon} **status**: `{result.get('status')}`")
    for key in (
        "database",
        "milvus",
        "redis",
        "maintenance_mode",
        "server_ops_skills_enabled",
    ):
        if key in result:
            lines.append(f"- **{key}**: `{result[key]}`")
    if lines:
        return "\n".join(lines)

    try:
        body = json.dumps(result, ensure_ascii=False, indent=2)
    except (TypeError, ValueError):
        body = str(result)
    if len(body) > 3500:
        body = body[:3500] + "\n…"
    return f"```json\n{body}\n```"


def _tool_result_display_text(result: Any) -> str:
    """Text to stream to the user from a tool result (preserves markdown links)."""
    if isinstance(result, str) and result.strip():
        return result.strip() + "\n\n"
    if isinstance(result, dict):
        err = result.get("error")
        if err:
            hint = result.get("hint")
            block = f"❌ {err}"
            if hint:
                block += f"\n{hint}"
            return block + "\n\n"
        parts: list[str] = []
        for key in ("message", "content", "text"):
            val = result.get(key)
            if isinstance(val, str) and val.strip():
                parts.append(val.strip())
        for asset in result.get("outbound_assets") or []:
            if not isinstance(asset, dict):
                continue
            url = str(asset.get("url") or "").strip()
            if not url:
                continue
            name = str(asset.get("name") or "下载文件").strip()
            parts.append(f"📥 **下载**：[{name}]({url})")
        if parts:
            return "\n\n".join(parts) + "\n\n"
        if isinstance(result.get("lines"), list) and result["lines"]:
            text = "\n".join(str(x) for x in result["lines"])
            header = f"**日志** `{result.get('path', '')}`"
            return f"{header}\n\n```text\n{text.rstrip()}\n```\n\n"
        stdout = result.get("stdout")
        stderr = result.get("stderr")
        if stdout is not None or stderr is not None:
            from app.skill.shell_allowlist import format_command_output_message

            cmd = str(result.get("command") or result.get("shell_id") or "command")
            code = int(result.get("exit_code", 0 if result.get("ok") else 1))
            return (
                format_command_output_message(
                    cmd,
                    str(stdout or ""),
                    str(stderr or ""),
                    code,
                )
                + "\n\n"
            )
        if result.get("ok") and any(
            key in result for key in ("project", "listing", "file", "changes", "builds", "releases")
        ):
            return ""
        structured = _format_structured_tool_dict(result)
        if structured.strip():
            return structured.strip() + "\n\n"
    return ""


def _collect_tool_outbound_assets(result: Any) -> list[dict[str, Any]]:
    if not isinstance(result, dict):
        return []
    raw = result.get("outbound_assets")
    if not isinstance(raw, list):
        return []
    return [a for a in raw if isinstance(a, dict)]


def _merge_tool_call(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing)
    if incoming.get("id"):
        merged["id"] = incoming["id"]
    if incoming.get("name"):
        merged["name"] = incoming["name"]
    if incoming.get("arguments"):
        prev = merged.get("arguments") or {}
        if isinstance(prev, dict) and isinstance(incoming["arguments"], dict):
            merged["arguments"] = {**prev, **incoming["arguments"]}
        else:
            merged["arguments"] = incoming["arguments"]
    return merged


async def _append_rag_context(
    system_prompt: str,
    query: str,
    user_id: str,
    customer_config: CustomerConfig | None,
    db_session: AsyncSession,
    conversation: Conversation,
    chat_fn=None,
    *,
    conversation_id: str | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    kb_ids = list(knowledge_base_ids_for_chat(customer_config) or [])
    if conversation.scope_type == "group" and conversation.scope_id:
        group_kb_result = await db_session.execute(
            select(KnowledgeBase.id).where(
                KnowledgeBase.group_id == conversation.scope_id,
                KnowledgeBase.enabled == True,
            )
        )
        kb_ids.extend(str(row[0]) for row in group_kb_result.all())
    kb_ids = list(dict.fromkeys(kb_ids))
    if not kb_ids:
        return await _append_group_memory_context(
            system_prompt,
            query,
            db_session,
            conversation,
        )

    rag = RagService()
    all_results = []

    try:
        import asyncio

        async def _search_kb(kb_id: str):
            return await rag.search(
                query=query,
                user_id=user_id,
                knowledge_base_id=kb_id,
                top_k=3,
                chat_fn=chat_fn,
                conversation_id=conversation_id,
                log_source="chat",
            )

        batches = await asyncio.gather(
            *[_search_kb(kb_id) for kb_id in kb_ids],
            return_exceptions=True,
        )
        for batch in batches:
            if isinstance(batch, Exception):
                logger.warning(f"RAG search failed for a knowledge base: {batch}")
                continue
            all_results.extend(batch.results)
    except Exception as e:
        logger.warning(f"RAG search failed: {e}")
        return system_prompt, []

    if not all_results:
        return system_prompt, []

    seen: set[str] = set()
    context_parts: list[str] = []
    hit_items: list[dict[str, Any]] = []
    for r in all_results:
        key = f"{r.document_id}:{r.content[:80]}"
        if key in seen:
            continue
        seen.add(key)
        context_parts.append(f"[Source: {r.title}]\n{r.content}")
        hit_items.append(
            {
                "document_id": r.document_id,
                "title": r.title,
                "knowledge_base_id": r.knowledge_base_id,
                "score": round(float(r.score), 4),
            }
        )

    if not context_parts:
        return await _append_group_memory_context(
            system_prompt,
            query,
            db_session,
            conversation,
        )

    rag_prompt = (
        system_prompt
        + "\n\n## Knowledge Base Context\n"
        "Use the following information to help answer the user's question:\n\n"
        + "\n\n".join(context_parts)
    )
    return await _append_group_memory_context(
        rag_prompt,
        query,
        db_session,
        conversation,
        knowledge_hits=hit_items,
    )


async def _append_group_memory_context(
    system_prompt: str,
    query: str,
    db_session: AsyncSession,
    conversation: Conversation,
    *,
    knowledge_hits: list[dict[str, Any]] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    if conversation.scope_type != "group" or not conversation.scope_id:
        return system_prompt, knowledge_hits or []

    result = await db_session.execute(
        select(GroupMemoryEntry)
        .where(
            GroupMemoryEntry.group_id == conversation.scope_id,
            GroupMemoryEntry.status.in_(["verified", "draft"]),
        )
        .order_by(GroupMemoryEntry.updated_at.desc())
        .limit(30)
    )
    entries = list(result.scalars().all())
    if not entries:
        return system_prompt, knowledge_hits or []

    terms = [part.strip().lower() for part in query.split() if part.strip()][:8]

    def _score(entry: GroupMemoryEntry) -> int:
        haystacks = [
            (entry.title or "").lower(),
            (entry.topic or "").lower(),
            " ".join(str(tag).lower() for tag in (entry.tags or [])),
            (entry.content or "").lower()[:2000],
        ]
        score = 0
        for term in terms:
            for hay in haystacks:
                if term and term in hay:
                    score += 1
        return score

    ranked = sorted(entries, key=_score, reverse=True)
    selected = [entry for entry in ranked if _score(entry) > 0][:3] or ranked[:2]
    parts: list[str] = []
    for entry in selected:
        header = f"[{entry.memory_type}] {entry.title}"
        parts.append(f"{header}\n{entry.content}")
    if not parts:
        return system_prompt, knowledge_hits or []

    return (
        system_prompt
        + "\n\n## Group Memory Context\n"
        "Use the following team memory and shared prompts when they are relevant:\n\n"
        + "\n\n".join(parts),
        knowledge_hits or [],
    )


async def process_message(
    conversation: Conversation,
    message: Message,
    ai_config: AIConfig | None,
    db_session: AsyncSession,
    customer_config: CustomerConfig | None = None,
    skill_ids_override: list[str] | None = None,
    end_user = None,
) -> AsyncGenerator[str, None]:
    """Process a user message through the bot pipeline."""
    try:
        if ai_config is None:
            result = await db_session.execute(
                select(AIConfig).where(AIConfig.is_default == True)
            )
            ai_config = result.scalar_one_or_none()

        if ai_config is None:
            yield "Error: No AI configuration available. Please configure an AI provider first."
            return

        if not (ai_config.api_key or "").strip():
            from app.services.llm_credentials import ensure_ai_config_api_key, is_usable_api_key

            ai_config = await ensure_ai_config_api_key(db_session, ai_config)
            if not is_usable_api_key(ai_config.api_key):
                yield (
                    "Error: 未配置有效的 AI API 密钥。请在管理后台「模型工作台」填写 API Key，"
                    "或在 .env 设置 DEEPSEEK_API_KEY / MOONSHOT_API_KEY。"
                )
                return

        system_prompt = ai_config.system_prompt or "You are a helpful AI assistant."
        channel_extra = (
            (getattr(customer_config, "channel_prompt", None) or "").strip()
            if customer_config
            else ""
        )
        if channel_extra:
            system_prompt = system_prompt.rstrip() + "\n\n" + channel_extra

        prompt_skills, tool_skills = await load_skills_for_chat(
            db_session,
            user_id=ai_config.user_id,
            customer_config=customer_config,
            skill_ids_override=skill_ids_override,
            end_user=end_user,
            group_id=conversation.scope_id if conversation.scope_type == "group" else None,
        )
        skill_section = build_prompt_skill_section(prompt_skills)
        if skill_section:
            system_prompt += skill_section

        tool_guidance = build_executable_skill_prompt_section(tool_skills)
        if tool_guidance:
            system_prompt += tool_guidance

        studio_ctx = chat_extensions.prepare_studio_context(conversation)

        from app.bot.tool_runtime import clear_bot_tool_context, set_bot_tool_context
        from app.workspace.resolver import workspace_user_id_for_execution

        ws_user_id = workspace_user_id_for_execution(
            customer_config=customer_config,
            fallback_user_id=ai_config.user_id,
        )
        group_devbridge_allowlists: dict[str, set[str]] | None = None
        group_member_role: str | None = None
        if conversation.scope_type == "group" and conversation.scope_id:
            from app.models.group import Group
            from app.services.group_service import GroupService, resolve_devbridge_project_allowlists

            group_row = await db_session.get(Group, conversation.scope_id)
            if group_row:
                raw = resolve_devbridge_project_allowlists(group_row)
                if raw is not None:
                    group_devbridge_allowlists = {
                        provider: {slug for slug in slugs if slug}
                        for provider, slugs in raw.items()
                    }
            membership = await GroupService(db_session).get_membership(
                conversation.scope_id,
                ws_user_id,
            )
            if membership is not None:
                group_member_role = membership.role
        set_bot_tool_context(
            db=db_session,
            conversation=conversation,
            user_id=ws_user_id,
            group_devbridge_allowlists=group_devbridge_allowlists,
            platform_user_role=getattr(end_user, "role", None) if end_user is not None else None,
            group_member_role=group_member_role,
        )

        tools = list(build_openai_tools(tool_skills))
        tools.extend(chat_extensions.extra_tools(conversation, studio_ctx))
        seen_tool_names: set[str] = set()
        deduped_tools: list[dict] = []
        for tool in tools:
            name = (tool.get("function") or {}).get("name") if isinstance(tool, dict) else None
            if name and name in seen_tool_names:
                continue
            if name:
                seen_tool_names.add(name)
            deduped_tools.append(tool)
        tools = deduped_tools
        system_prompt = append_patent_tool_hints(system_prompt, tool_skills)
        from app.bot.gamecenter_bridge_extensions import conversation_allows_bridge
        from app.bot.skill_context import append_gamecenter_dev_hints

        system_prompt = append_gamecenter_dev_hints(
            system_prompt,
            prompt_skills=prompt_skills,
            bridge_allowed=conversation_allows_bridge(conversation),
        )
        patent_links = patent_link_settings_from_skills(tool_skills)
        logger.info("patent_links enabled={} template={}", patent_links["enabled"], patent_links["template"])

        def _with_patent_links(text: str) -> str:
            return linkify_patent_ids(
                text,
                enabled=patent_links["enabled"],
                template=str(patent_links["template"]),
            )

        system_prompt, knowledge_hits = await _append_rag_context(
            system_prompt,
            message.content,
            ai_config.user_id,
            customer_config,
            db_session,
            conversation,
            chat_fn=None,
            conversation_id=conversation.id,
        )

        system_prompt = chat_extensions.augment_system_prompt(
            conversation, studio_ctx, system_prompt
        )

        auto_reply_matches = await match_auto_reply_rules(
            message.content,
            getattr(customer_config, "auto_reply_rules", None),
            channel=detect_message_channel(getattr(conversation, "contact_info", None)),
        )

        messages_list: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt}
        ]

        history_result = await db_session.execute(
            select(Message)
            .where(Message.conversation_id == conversation.id)
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(_history_message_limit(conversation))
        )
        history = list(reversed(history_result.scalars().all()))

        history_payload = []
        for hist_msg in history:
            if hist_msg.id == message.id:
                continue
            history_payload.append(
                {
                    "role": hist_msg.role,
                    "content": hist_msg.content,
                    "extra_data": hist_msg.extra_data,
                }
            )
        messages_list.extend(sanitize_history_messages(history_payload))

        # Compress context if approaching model limit
        from app.bot.context_compressor import compress_history, get_context_limit

        context_limit = get_context_limit(ai_config.model or "")
        from app.bot.provider import create_provider as _provider_factory

        messages_list = await compress_history(
            messages_list,
            context_limit=context_limit,
            provider_factory=_provider_factory,
            model=ai_config.model or "",
            api_key=ai_config.api_key or "",
            api_base=ai_config.api_base,
        )

        messages_list.append(
            {
                "role": "user",
                "content": attachment_prompt_text(
                    message.content, message.extra_data
                ),
            }
        )

        provider = create_provider(ai_config)
        full_response = ""
        usage_info: dict[str, int] = {}
        tool_turn_assets: list[dict[str, Any]] = []
        devbridge_modified_files: list[str] = []
        patent_skill = find_patent_search_skill(tool_skills)
        max_tool_rounds = 12
        tools_executed_this_turn = False
        synthesis_done = False

        def _merge_usage(chunk: dict[str, Any]) -> None:
            pt = int(chunk.get("prompt_tokens") or 0)
            ct = int(chunk.get("completion_tokens") or 0)
            tt = int(chunk.get("total_tokens") or 0) or (pt + ct)
            usage_info["prompt_tokens"] = usage_info.get("prompt_tokens", 0) + pt
            usage_info["completion_tokens"] = (
                usage_info.get("completion_tokens", 0) + ct
            )
            usage_info["total_tokens"] = usage_info.get("total_tokens", 0) + tt

        async def _stream_followup(
            *,
            with_tools: bool,
            parts_out: list[str] | None = None,
        ) -> None:
            nonlocal full_response
            async for chunk in provider.stream_chat(
                messages=messages_list,
                tools=tools if with_tools and tools else None,
                temperature=ai_config.temperature,
                max_tokens=ai_config.max_tokens,
            ):
                if chunk.get("type") == "usage":
                    _merge_usage(chunk)
                elif chunk.get("type") == "reasoning":
                    pass
                elif chunk.get("type") == "content":
                    token = chunk.get("content", "")
                    if not token:
                        continue
                    if token.startswith("Error:"):
                        full_response += token
                        yield token
                        if parts_out is not None:
                            parts_out.append(token)
                    else:
                        full_response += token
                        yield token
                        if parts_out is not None:
                            parts_out.append(token)

        for _tool_round in range(max_tool_rounds):
            tool_calls_map: dict[str, dict[str, Any]] = {}
            first_pass_content = ""
            round_reasoning = ""

            async for chunk in provider.stream_chat(
                messages=messages_list,
                tools=tools if tools else None,
                temperature=ai_config.temperature,
                max_tokens=ai_config.max_tokens,
            ):
                if chunk.get("type") == "usage":
                    _merge_usage(chunk)
                elif chunk.get("type") == "reasoning":
                    token = chunk.get("content", "") or ""
                    if token:
                        round_reasoning += token
                elif chunk.get("type") == "content":
                    token = chunk.get("content", "")
                    if not token:
                        continue
                    if token.startswith("Error:"):
                        full_response += token
                        yield token
                    else:
                        first_pass_content += token
                        full_response += token
                        yield token
                elif chunk.get("type") == "tool_call":
                    tc = chunk.get("tool_call", {})
                    tid = tc.get("id") or f"call_{uuid.uuid4().hex[:8]}"
                    if tid in tool_calls_map:
                        tool_calls_map[tid] = _merge_tool_call(tool_calls_map[tid], tc)
                    else:
                        tool_calls_map[tid] = {
                            "id": tid,
                            "name": tc.get("name", ""),
                            "arguments": tc.get("arguments") or {},
                        }

            tool_calls_list = list(tool_calls_map.values())
            if not tool_calls_list:
                break

            messages_list.append(
                build_assistant_tool_call_message(
                    first_pass_content,
                    tool_calls_list,
                    reasoning_content=round_reasoning or None,
                )
            )

            patent_search_for_summary = False
            patent_search_for_presentation = False
            patent_search_for_export = False
            tools_executed_this_turn = True
            for tc in tool_calls_list:
                tool_name = tc.get("name", "")
                tool_args = dict(tc.get("arguments") or {})
                if tool_name == "patent-search":
                    cmd = str(tool_args.get("command") or "search").lower()
                    if cmd == "search" and tool_args.get("details") is None:
                        tool_args["details"] = True

                step_header = f"\n\n**🔧 `{tool_name}`**\n"
                full_response += step_header
                yield step_header

                try:
                    from app.workspace.resolver import workspace_user_id_for_execution

                    ws_user_id = workspace_user_id_for_execution(
                        customer_config=customer_config,
                        fallback_user_id=ai_config.user_id,
                    )
                    tool_result = await _execute_tool(
                        tool_name,
                        tool_args,
                        tool_skills,
                        db_session,
                        studio_ctx=studio_ctx,
                        user_id=ws_user_id,
                        customer_config=customer_config,
                    )
                except BaseException as e:
                    logger.error(f"Tool execution crashed: {e}", exc_info=True)
                    tool_result = {
                        "error": f"技能执行失败: {e}。请检查 API Key 与参数。"
                    }
                messages_list.append(
                    build_tool_result_message(tc["id"], tool_result)
                )
                tool_turn_assets.extend(_collect_tool_outbound_assets(tool_result))
                if isinstance(tool_result, dict):
                    modified = str(tool_result.get("modified_path") or tool_result.get("path") or "").strip()
                    if modified and tool_name == "patch_gamecenter_project_file" and not tool_result.get("unchanged"):
                        if modified not in devbridge_modified_files:
                            devbridge_modified_files.append(modified)

                tool_display = _tool_result_display_text(tool_result)
                if tool_display:
                    tool_display = _with_patent_links(tool_display)
                    cmd = str(tool_args.get("command") or "search").lower()
                    patent_search_ok = is_patent_search_success(
                        tool_name, cmd, tool_display
                    )
                    is_export = cmd == "export"
                    if patent_search_enable_presentation(patent_skill) and patent_search_ok and not is_export:
                        patent_search_for_presentation = True
                    elif is_export:
                        # Export: show tool display (correct download URL), use short nudge
                        full_response += tool_display
                        yield tool_display
                        patent_search_for_export = True
                    else:
                        full_response += tool_display
                        yield tool_display
                    if patent_search_enable_summary(patent_skill) and patent_search_ok:
                        patent_search_for_summary = True

            if patent_search_for_presentation:
                messages_list.append(
                    {
                        "role": "user",
                        "content": patent_search_presentation_nudge(patent_skill),
                    }
                )
                presentation_parts: list[str] = []
                async for token in _stream_followup(with_tools=False, parts_out=presentation_parts):
                    yield token
                if presentation_parts:
                    presentation_text = _with_patent_links("".join(presentation_parts))
                    if not presentation_text.endswith("\n\n"):
                        presentation_text = presentation_text.rstrip() + "\n\n"
                    full_response += presentation_text
                synthesis_done = True
                break

            if patent_search_for_summary:
                messages_list.append(
                    {
                        "role": "user",
                        "content": patent_search_observation_nudge(patent_skill),
                    }
                )
                summary_parts: list[str] = []
                async for token in _stream_followup(with_tools=False, parts_out=summary_parts):
                    yield token
                if summary_parts:
                    summary_text = _with_patent_links("".join(summary_parts))
                    if not summary_text.startswith("\n"):
                        summary_text = "\n\n" + summary_text.lstrip()
                    if not summary_text.endswith("\n\n"):
                        summary_text = summary_text.rstrip() + "\n\n"
                    full_response += summary_text
                synthesis_done = True
                break

            if patent_search_for_export:
                messages_list.append(
                    {
                        "role": "user",
                        "content": _DEFAULT_EXPORT_NUDGE,
                    }
                )
                export_parts: list[str] = []
                async for token in _stream_followup(with_tools=False, parts_out=export_parts):
                    yield token
                if export_parts:
                    export_text = "".join(export_parts)
                    full_response += export_text
                synthesis_done = True
                break

        if tools_executed_this_turn and not synthesis_done:
            messages_list.append(
                {
                    "role": "user",
                    "content": (
                        "请根据以上工具调用结果，用中文向用户说明：已查看或修改了什么、"
                        "关键结论与建议的下一步。若任务尚未完成，请明确还差什么。"
                        "不要再次调用工具。"
                    ),
                }
            )
            synthesis_parts: list[str] = []
            async for token in _stream_followup(
                with_tools=False, parts_out=synthesis_parts
            ):
                yield token
            if synthesis_parts:
                synthesis_text = _with_patent_links("".join(synthesis_parts))
                if not synthesis_text.startswith("\n"):
                    synthesis_text = "\n\n" + synthesis_text.lstrip()
                if not synthesis_text.endswith("\n\n"):
                    synthesis_text = synthesis_text.rstrip() + "\n\n"
                full_response += synthesis_text

        auto_reply_note = build_auto_reply_note(auto_reply_matches)
        if auto_reply_note:
            note_chunk = f"\n\n{auto_reply_note}" if full_response.strip() else auto_reply_note
            full_response += note_chunk
            yield note_chunk

        if full_response:
            full_response = _with_patent_links(full_response)
            # Fix AI-generated download URLs that use wrong domain
            full_response = full_response.replace(
                "https://www.9235.net/uploads/", "/uploads/"
            )
            auto_reply_assets = [match["asset"] for match in auto_reply_matches]
            merged_assets = auto_reply_assets + tool_turn_assets
            assistant_extra_data = enrich_message_extra_data(
                full_response,
                {
                    "model": ai_config.model,
                    "provider": ai_config.provider,
                    "devbridge_modified_files": devbridge_modified_files or None,
                    "knowledge_hits": knowledge_hits,
                    "auto_reply_rule_hits": [
                        {
                            "rule_id": match["rule_id"],
                            "rule_name": match["rule_name"],
                            "score": round(float(match["score"]), 4),
                            "asset_name": match["asset"].get("title")
                            or match["asset"].get("name")
                            or match["asset"].get("url"),
                            "matched_keywords": match.get("matched_keywords") or [],
                        }
                        for match in auto_reply_matches
                    ],
                    "outbound_assets": merged_assets,
                },
            )
            assistant_msg = Message(
                conversation_id=conversation.id,
                role="assistant",
                content=full_response,
                extra_data=assistant_extra_data,
                prompt_tokens=usage_info.get("prompt_tokens"),
                completion_tokens=usage_info.get("completion_tokens"),
            )
            db_session.add(assistant_msg)

            if message.content:
                chat_extensions.after_assistant_turn(
                    conversation,
                    studio_ctx,
                    message.content,
                    full_response,
                )

            # Increment token usage on the associated channel
            customer_id = getattr(conversation, "customer_id", None)
            if customer_id:
                tokens_used = int(usage_info.get("total_tokens") or 0)
                if not tokens_used:
                    tokens_used = int(usage_info.get("prompt_tokens") or 0) + int(
                        usage_info.get("completion_tokens") or 0
                    )
                if not tokens_used and (
                    assistant_msg.prompt_tokens or assistant_msg.completion_tokens
                ):
                    tokens_used = int(assistant_msg.prompt_tokens or 0) + int(
                        assistant_msg.completion_tokens or 0
                    )
                if tokens_used > 0:
                    result = await db_session.execute(
                        select(CustomerConfig).where(CustomerConfig.id == customer_id)
                    )
                    config = result.scalar_one_or_none()
                    if config is not None:
                        config.usage_tokens_month = (
                            config.usage_tokens_month or 0
                        ) + tokens_used
                        await db_session.flush()

            conversation.updated_at = datetime.now(timezone.utc)
            conversation.last_seen_at = datetime.now(timezone.utc)

    except BaseException as e:
        logger.error(f"Bot engine error: {e}", exc_info=True)
        yield f"\n\n抱歉，处理消息时出错：{e}"
    finally:
        from app.bot.tool_runtime import clear_bot_tool_context

        clear_bot_tool_context()


async def _execute_tool(
    tool_name: str,
    tool_args: dict[str, Any],
    skills: list[Skill],
    db_session: AsyncSession,
    *,
    studio_ctx: Any | None = None,
    user_id: str | None = None,
    customer_config: CustomerConfig | None = None,
) -> Any:
    """Execute a skill tool function."""
    extension_result = await chat_extensions.execute_extension_tool_async(
        tool_name, tool_args, studio_ctx
    )
    if extension_result is not None:
        return extension_result

    from app.workspace.context import workspace_execution_scope
    from app.workspace.resolver import build_workspace_context

    channel_id = getattr(studio_ctx, "channel_id", None) if studio_ctx else None
    if channel_id is None and customer_config is not None:
        channel_id = customer_config.id

    ws_ctx = None
    if user_id:
        user_container_allowed = None
        from sqlalchemy import select

        from app.models.user import User

        user_row = await db_session.execute(select(User).where(User.id == user_id))
        owner = user_row.scalar_one_or_none()
        if owner is not None:
            user_container_allowed = owner.workspace_container_allowed
        ws_ctx = build_workspace_context(
            user_id,
            customer_config=customer_config,
            channel_id=channel_id,
            user_container_allowed=user_container_allowed,
        )

    for skill in skills:
        if skill.name == tool_name and skill.enabled:
            try:
                from app.skill.executor import execute_skill

                async with workspace_execution_scope(ws_ctx):
                    return await execute_skill(skill, tool_args)
            except BaseException as e:
                logger.error(f"Tool {tool_name} execution failed: {e}")
                return {"error": str(e)}

    return {"error": f"Tool '{tool_name}' not found or not enabled"}
