"""Channel service - business logic for communication channel management."""

import uuid
import re
import json
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, func, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_config import AIConfig
from app.models.channel import Channel
from app.models.conversation import Conversation
from app.models.customer import CustomerConfig
from app.models.workflow import ChannelWorkflowBinding, SkillWorkflow
from app.models.workflow import SkillWorkflowRun
from app.models.setting import Setting
from app.services.workflow_service import WorkflowService
from app.schemas.channel import (
    ChannelCreate,
    ChannelResponse,
    ChannelUpdate,
    ChannelWorkflowBindingItem,
    ChannelWorkflowPreviewItem,
    ChannelWorkflowPreviewResponse,
    ChannelWorkflowBindingResponse,
    ChannelWorkflowBindingBundle,
    ChannelWorkflowTemplateCreate,
    ChannelWorkflowTemplateResponse,
    ChannelWorkflowStatsItem,
    ChannelWorkflowStatsResponse,
)


def _matches_rule(match_type: str, expr: str | None, content: str) -> bool:
    matched, _, _, _, _, _ = _evaluate_rule(match_type, expr, content)
    return matched


def _evaluate_rule(
    match_type: str,
    expr: str | None,
    content: str,
) -> tuple[bool, str, str | None, str | None, str | None, tuple[int, int] | None]:
    """Evaluate one rule and return rich debug tuple."""
    mode = (match_type or "all").strip().lower()
    pattern = (expr or "").strip()
    if mode == "all":
        return True, "all", None, None, None, None
    if mode == "contains":
        if not pattern:
            return False, "contains_empty", None, None, None, None
        idx = content.lower().find(pattern.lower())
        if idx >= 0:
            end = idx + len(pattern)
            return True, "contains_hit", pattern, None, content[idx:end], (idx, end)
        return False, "contains_miss", pattern, None, None, None
    if mode == "regex":
        if not pattern:
            return False, "regex_empty", None, None, None, None
        try:
            m = re.search(pattern, content, flags=re.IGNORECASE)
            is_match = m is not None
            return (
                is_match,
                "regex_hit" if is_match else "regex_miss",
                pattern,
                None,
                (m.group(0) if m else None),
                (m.span() if m else None),
            )
        except re.error as e:
            return False, "regex_error", pattern, str(e), None, None
    return False, "unknown_match_type", mode, None, None, None


def _binding_matches_content(binding: ChannelWorkflowBinding, content: str) -> bool:
    """Return whether an event content matches binding rule."""
    match_type = (binding.match_type or "all").strip().lower()
    expr = (binding.match_expr or "").strip()
    return _matches_rule(match_type, expr, content)


async def channel_get_or_create_conversation(
    db: AsyncSession,
    sender_id: str,
    customer: CustomerConfig,
    *,
    contact_info: str,
    title: str,
    client_ip: str | None = None,
) -> Conversation:
    """Find or create an active conversation for a channel message."""
    result = await db.execute(
        select(Conversation)
        .where(
            Conversation.visitor_id == sender_id,
            Conversation.contact_info == contact_info,
            Conversation.status == "active",
        )
        .order_by(Conversation.updated_at.desc())
        .limit(1)
    )
    conversation = result.scalar_one_or_none()
    if conversation is not None:
        if not conversation.customer_id:
            conversation.customer_id = customer.id
        return conversation

    conversation = Conversation(
        id=str(uuid.uuid4()),
        visitor_id=sender_id,
        customer_id=customer.id,
        client_ip=client_ip,
        ai_config_id=customer.ai_config_id,
        title=title,
        contact_info=contact_info,
        status="active",
    )
    db.add(conversation)
    await db.flush()
    return conversation


async def channel_resolve_ai_config(
    db: AsyncSession, customer: CustomerConfig
) -> AIConfig | None:
    """Resolve AI config from customer or fall back to default."""
    if customer.ai_config_id:
        result = await db.execute(
            select(AIConfig).where(AIConfig.id == customer.ai_config_id)
        )
        cfg = result.scalar_one_or_none()
        if cfg is not None:
            return cfg
    result = await db.execute(
        select(AIConfig).where(AIConfig.is_default == True)
    )
    return result.scalar_one_or_none()


async def channel_trigger_bound_workflows(
    db: AsyncSession,
    channel: Channel,
    *,
    event_type: str,
    event_payload: dict,
) -> list[str]:
    """Execute enabled workflows bound to the given channel."""
    result = await db.execute(
        select(ChannelWorkflowBinding)
        .where(
            ChannelWorkflowBinding.channel_id == channel.id,
            ChannelWorkflowBinding.user_id == channel.user_id,
            ChannelWorkflowBinding.enabled == True,
        )
        .order_by(ChannelWorkflowBinding.priority.asc(), ChannelWorkflowBinding.created_at.asc())
    )
    bindings = result.scalars().all()
    if not bindings:
        return []

    workflow_ids = [b.workflow_id for b in bindings]
    wf_result = await db.execute(
        select(SkillWorkflow).where(
            SkillWorkflow.id.in_(workflow_ids),  # type: ignore[arg-type]
            SkillWorkflow.user_id == channel.user_id,
            SkillWorkflow.enabled == True,
        )
    )
    workflow_map = {w.id: w for w in wf_result.scalars().all()}
    service = WorkflowService(db)
    run_ids: list[str] = []
    message_text = str(
        event_payload.get("content")
        or event_payload.get("text")
        or event_payload.get("message")
        or ""
    )
    dispatch_mode = str((channel.config or {}).get("workflow_dispatch_mode") or "all")
    dispatch_mode = dispatch_mode.strip().lower()
    selected_ids: list[str] = []
    for binding in bindings:
        if not _binding_matches_content(binding, message_text):
            continue
        selected_ids.append(binding.workflow_id)
        if dispatch_mode == "first_match":
            break
    for workflow_id in selected_ids:
        workflow = workflow_map.get(workflow_id)
        if workflow is None:
            continue
        run = await service.execute_workflow(
            workflow=workflow,
            trigger_type="channel",
            input_payload={
                "event_type": event_type,
                "channel": {
                    "id": channel.id,
                    "name": channel.name,
                    "type": channel.channel_type,
                },
                "event": event_payload,
            },
        )
        run_ids.append(run.id)
    await db.commit()
    return run_ids


def _preview_select_workflow_ids(
    *,
    bindings: list[ChannelWorkflowBinding | ChannelWorkflowBindingItem],
    content: str,
    dispatch_mode: str,
) -> list[str]:
    selected_ids: list[str] = []
    for binding in bindings:
        match_type = (binding.match_type or "all").strip().lower()
        match_expr = getattr(binding, "match_expr", None)
        matched, _, _, _, _, _ = _evaluate_rule(match_type, match_expr, content)
        if not matched:
            continue
        selected_ids.append(binding.workflow_id)
        if dispatch_mode == "first_match":
            break
    return selected_ids


class ChannelService:
    """Handles channel management business logic."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_channels(self, user_id: str) -> list[ChannelResponse]:
        """List all channels for a user."""
        result = await self.db.execute(
            select(Channel)
            .where(Channel.user_id == user_id)
            .order_by(Channel.created_at.desc())
        )
        channels = result.scalars().all()
        return [ChannelResponse.model_validate(c) for c in channels]

    async def get_channel(
        self, channel_id: str, user_id: str
    ) -> ChannelResponse | None:
        """Get a specific channel."""
        result = await self.db.execute(
            select(Channel).where(
                Channel.id == channel_id, Channel.user_id == user_id
            )
        )
        channel = result.scalar_one_or_none()
        if channel is None:
            return None
        return ChannelResponse.model_validate(channel)

    async def create_channel(
        self, user_id: str, data: ChannelCreate
    ) -> ChannelResponse:
        """Create a new channel."""
        channel = Channel(
            user_id=user_id,
            name=data.name,
            channel_type=data.channel_type,
            config=data.config or {},
            enabled=data.enabled,
        )
        self.db.add(channel)
        await self.db.flush()
        await self.db.refresh(channel)
        return ChannelResponse.model_validate(channel)

    async def update_channel(
        self, channel_id: str, user_id: str, data: ChannelUpdate
    ) -> ChannelResponse | None:
        """Update a channel."""
        result = await self.db.execute(
            select(Channel).where(
                Channel.id == channel_id, Channel.user_id == user_id
            )
        )
        channel = result.scalar_one_or_none()
        if channel is None:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(channel, key, value)

        await self.db.flush()
        await self.db.refresh(channel)
        return ChannelResponse.model_validate(channel)

    async def delete_channel(
        self, channel_id: str, user_id: str
    ) -> bool:
        """Delete a channel."""
        result = await self.db.execute(
            select(Channel).where(
                Channel.id == channel_id, Channel.user_id == user_id
            )
        )
        channel = result.scalar_one_or_none()
        if channel is None:
            return False
        await self.db.delete(channel)
        await self.db.flush()
        return True

    async def test_channel(
        self, user_id: str, channel_type: str, config: dict | None
    ) -> dict:
        """Test a channel connection."""
        config = config or {}

        if channel_type == "web_widget":
            widget_id = (config.get("widget_id") or "").strip()
            if not widget_id:
                return {
                    "ok": False,
                    "message": "请填写 Widget ID（在「AI 与客服配置 → 客服配置」中复制 Agent ID）",
                }

            result = await self.db.execute(
                select(CustomerConfig).where(
                    CustomerConfig.id == widget_id,
                    CustomerConfig.user_id == user_id,
                )
            )
            customer = result.scalar_one_or_none()
            if customer is None:
                return {
                    "ok": False,
                    "message": f"未找到 Widget 配置 ID: {widget_id}",
                }
            if not customer.enabled:
                return {
                    "ok": False,
                    "message": f"客服配置「{customer.name}」已禁用，请先在管理后台启用",
                }

            preview_path = f"/widget.html?agentId={widget_id}"
            return {
                "ok": True,
                "message": f"Widget「{customer.name}」配置有效，可打开预览页测试",
                "widget_id": widget_id,
                "preview_url": preview_path,
                "config_api": f"/api/widget/config/{widget_id}/full",
            }

        if channel_type == "wechat":
            missing = []
            for key, label in (
                ("app_id", "App ID"),
                ("app_secret", "App Secret"),
                ("token", "Token"),
                ("customer_id", "客服配置（Agent）"),
            ):
                if not str(config.get(key) or "").strip():
                    missing.append(label)
            if missing:
                return {
                    "ok": False,
                    "message": f"请填写：{', '.join(missing)}",
                }
            try:
                import wechatpy  # noqa: F401
            except ImportError:
                aes = str(config.get("encoding_aes_key") or "").strip()
                if aes:
                    return {
                        "ok": False,
                        "message": "安全模式需安装 wechatpy：pip install wechatpy",
                    }
            try:
                from app.services.wechat_channel_service import _fetch_wechat_access_token

                await _fetch_wechat_access_token(
                    str(config.get("app_id") or "").strip(),
                    str(config.get("app_secret") or "").strip(),
                    force_refresh=True,
                )
            except Exception as e:
                return {
                    "ok": False,
                    "message": f"微信公众号配置未通过 access_token 校验：{e}",
                }
            return {
                "ok": True,
                "message": (
                    "微信公众号配置完整。当前默认使用客服消息主动下发模式"
                    "（App ID + App Secret 获取 access_token）。"
                    "请在公众平台配置服务器 URL，并确保已绑定客服 Agent。"
                ),
            }

        if channel_type == "telegram":
            return await self._test_telegram(config, user_id)

        if channel_type == "dingtalk":
            return await self._test_dingtalk(config, user_id)

        return {
            "ok": True,
            "message": (
                f"频道类型「{channel_type}」配置格式有效；"
                "第三方平台连通性测试尚未实现"
            ),
        }

    async def _validate_customer_binding(
        self, user_id: str, config: dict
    ) -> CustomerConfig | None:
        customer_id = str(config.get("customer_id") or "").strip()
        if not customer_id:
            return None
        result = await self.db.execute(
            select(CustomerConfig).where(
                CustomerConfig.id == customer_id,
                CustomerConfig.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def _test_telegram(self, config: dict, user_id: str) -> dict:
        token = str(config.get("bot_token") or "").strip()
        if not token:
            return {"ok": False, "message": "请填写 Bot Token"}
        customer = await self._validate_customer_binding(user_id, config)
        if customer is None:
            return {"ok": False, "message": "请填写有效的客服配置（customer_id / Agent ID）"}
        try:
            import httpx

            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"https://api.telegram.org/bot{token}/getMe"
                )
                resp.raise_for_status()
                data = resp.json()
            if not data.get("ok"):
                return {"ok": False, "message": f"Telegram getMe 失败: {data}"}
            username = (data.get("result") or {}).get("username") or "bot"
            return {
                "ok": True,
                "message": f"Telegram Bot @{username} 连接成功，已绑定「{customer.name}」",
            }
        except Exception as e:
            return {"ok": False, "message": f"Telegram 连接失败: {e}"}

    async def _test_dingtalk(self, config: dict, user_id: str) -> dict:
        customer = await self._validate_customer_binding(user_id, config)
        if customer is None:
            return {"ok": False, "message": "请填写有效的客服配置（customer_id / Agent ID）"}
        app_secret = str(config.get("app_secret") or "").strip()
        webhook_url = str(config.get("webhook_url") or "").strip()
        if not app_secret and not webhook_url:
            return {
                "ok": False,
                "message": "请填写 App Secret（入站签名校验）或 Webhook URL（出站兜底）",
            }
        parts = [f"已绑定「{customer.name}」"]
        if app_secret:
            parts.append("App Secret 已配置")
        if webhook_url:
            parts.append("Webhook URL 已配置")
        return {"ok": True, "message": "；".join(parts) + "。请在钉钉开放平台配置出站消息 URL。"}

    async def list_channel_workflow_bindings(
        self, *, channel_id: str, user_id: str
    ) -> list[ChannelWorkflowBindingResponse]:
        channel = await self.db.execute(
            select(Channel).where(Channel.id == channel_id, Channel.user_id == user_id)
        )
        if channel.scalar_one_or_none() is None:
            return []

        result = await self.db.execute(
            select(ChannelWorkflowBinding)
            .where(
                ChannelWorkflowBinding.channel_id == channel_id,
                ChannelWorkflowBinding.user_id == user_id,
            )
            .order_by(
                ChannelWorkflowBinding.priority.asc(),
                ChannelWorkflowBinding.created_at.asc(),
            )
        )
        rows = result.scalars().all()
        wf_ids = [r.workflow_id for r in rows]
        wf_map: dict[str, SkillWorkflow] = {}
        if wf_ids:
            wf_result = await self.db.execute(
                select(SkillWorkflow).where(SkillWorkflow.id.in_(wf_ids))  # type: ignore[arg-type]
            )
            wf_map = {w.id: w for w in wf_result.scalars().all()}
        return [
            ChannelWorkflowBindingResponse(
                id=row.id,
                channel_id=row.channel_id,
                workflow_id=row.workflow_id,
                workflow_name=(wf_map.get(row.workflow_id).name if wf_map.get(row.workflow_id) else ""),
                enabled=row.enabled,
                priority=row.priority,
                match_type=row.match_type,
                match_expr=row.match_expr,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in rows
        ]

    async def replace_channel_workflow_bindings(
        self,
        *,
        channel_id: str,
        user_id: str,
        bindings: list[ChannelWorkflowBindingItem],
    ) -> list[ChannelWorkflowBindingResponse]:
        channel_result = await self.db.execute(
            select(Channel).where(Channel.id == channel_id, Channel.user_id == user_id)
        )
        channel = channel_result.scalar_one_or_none()
        if channel is None:
            return []

        wf_ids = [b.workflow_id for b in bindings]
        if wf_ids:
            wf_result = await self.db.execute(
                select(SkillWorkflow).where(
                    SkillWorkflow.id.in_(wf_ids),  # type: ignore[arg-type]
                    SkillWorkflow.user_id == user_id,
                )
            )
            valid_ids = {w.id for w in wf_result.scalars().all()}
            missing = [wid for wid in wf_ids if wid not in valid_ids]
            if missing:
                raise ValueError(f"workflow not found: {missing[0]}")

        existing = await self.db.execute(
            select(ChannelWorkflowBinding).where(
                ChannelWorkflowBinding.channel_id == channel_id,
                ChannelWorkflowBinding.user_id == user_id,
            )
        )
        for row in existing.scalars().all():
            await self.db.delete(row)
        await self.db.flush()

        for item in bindings:
            row = ChannelWorkflowBinding(
                user_id=user_id,
                channel_id=channel_id,
                workflow_id=item.workflow_id,
                enabled=item.enabled,
                priority=item.priority,
                match_type=item.match_type,
                match_expr=(item.match_expr.strip() if item.match_expr else None),
            )
            self.db.add(row)
        await self.db.flush()

        return await self.list_channel_workflow_bindings(
            channel_id=channel_id, user_id=user_id
        )

    async def preview_channel_workflow_bindings(
        self,
        *,
        channel_id: str,
        user_id: str,
        content: str,
        event_type: str = "message",
        dispatch_mode: str | None = None,
        bindings_override: list[ChannelWorkflowBindingItem] | None = None,
    ) -> ChannelWorkflowPreviewResponse:
        channel_result = await self.db.execute(
            select(Channel).where(Channel.id == channel_id, Channel.user_id == user_id)
        )
        channel = channel_result.scalar_one_or_none()
        if channel is None:
            raise ValueError("channel not found")

        if bindings_override is not None:
            bindings: list[ChannelWorkflowBinding | ChannelWorkflowBindingItem] = sorted(
                bindings_override, key=lambda x: x.priority
            )
        else:
            result = await self.db.execute(
                select(ChannelWorkflowBinding)
                .where(
                    ChannelWorkflowBinding.channel_id == channel_id,
                    ChannelWorkflowBinding.user_id == user_id,
                    ChannelWorkflowBinding.enabled == True,
                )
                .order_by(ChannelWorkflowBinding.priority.asc(), ChannelWorkflowBinding.created_at.asc())
            )
            bindings = result.scalars().all()

        workflow_ids = [b.workflow_id for b in bindings]
        wf_map: dict[str, SkillWorkflow] = {}
        if workflow_ids:
            wf_result = await self.db.execute(
                select(SkillWorkflow).where(
                    SkillWorkflow.id.in_(workflow_ids),  # type: ignore[arg-type]
                    SkillWorkflow.user_id == user_id,
                )
            )
            wf_map = {w.id: w for w in wf_result.scalars().all()}

        mode = (dispatch_mode or str((channel.config or {}).get("workflow_dispatch_mode") or "all")).strip().lower()
        if mode not in {"all", "first_match"}:
            mode = "all"
        selected_ids = _preview_select_workflow_ids(
            bindings=bindings,
            content=content,
            dispatch_mode=mode,
        )

        items: list[ChannelWorkflowPreviewItem] = []
        for binding in bindings:
            workflow = wf_map.get(binding.workflow_id)
            workflow_name = workflow.name if workflow else ""
            matched, reason_code, reason_detail, reason_error, matched_text, matched_span = _evaluate_rule(
                (binding.match_type or "all"),
                getattr(binding, "match_expr", None),
                content,
            )
            selected = binding.workflow_id in selected_ids
            if matched and not selected and mode == "first_match":
                reason_code = "matched_but_skipped"
                first_selected_id = selected_ids[0] if selected_ids else None
                if first_selected_id and wf_map.get(first_selected_id):
                    reason_detail = wf_map[first_selected_id].name
                else:
                    reason_detail = first_selected_id
            item = ChannelWorkflowPreviewItem(
                workflow_id=binding.workflow_id,
                workflow_name=workflow_name,
                priority=getattr(binding, "priority", 100),
                match_type=(binding.match_type or "all"),
                match_expr=getattr(binding, "match_expr", None),
                matched=matched,
                selected=selected,
                reason_code=reason_code,
                reason_detail=reason_detail,
                error=reason_error,
                matched_text=matched_text,
                match_start=(matched_span[0] if matched_span else None),
                match_end=(matched_span[1] if matched_span else None),
            )
            items.append(item)

        return ChannelWorkflowPreviewResponse(
            event_type=event_type,
            dispatch_mode=mode,
            matched_workflow_ids=selected_ids,
            evaluations=items,
        )

    async def export_channel_workflow_bundle(
        self, *, channel_id: str, user_id: str
    ) -> ChannelWorkflowBindingBundle:
        channel_result = await self.db.execute(
            select(Channel).where(Channel.id == channel_id, Channel.user_id == user_id)
        )
        channel = channel_result.scalar_one_or_none()
        if channel is None:
            raise ValueError("channel not found")
        bindings = await self.list_channel_workflow_bindings(
            channel_id=channel_id,
            user_id=user_id,
        )
        items = [
            ChannelWorkflowBindingItem(
                workflow_id=b.workflow_id,
                enabled=b.enabled,
                priority=b.priority,
                match_type=b.match_type,
                match_expr=b.match_expr,
            )
            for b in bindings
        ]
        dispatch_mode = str((channel.config or {}).get("workflow_dispatch_mode") or "all")
        return ChannelWorkflowBindingBundle(
            dispatch_mode=dispatch_mode,
            bindings=items,
        )

    async def import_channel_workflow_bundle(
        self,
        *,
        channel_id: str,
        user_id: str,
        bundle: ChannelWorkflowBindingBundle,
    ) -> list[ChannelWorkflowBindingResponse]:
        channel_result = await self.db.execute(
            select(Channel).where(Channel.id == channel_id, Channel.user_id == user_id)
        )
        channel = channel_result.scalar_one_or_none()
        if channel is None:
            raise ValueError("channel not found")
        config = dict(channel.config or {})
        config["workflow_dispatch_mode"] = bundle.dispatch_mode
        channel.config = config
        rows = await self.replace_channel_workflow_bindings(
            channel_id=channel_id,
            user_id=user_id,
            bindings=bundle.bindings,
        )
        await self.db.flush()
        return rows

    async def channel_workflow_stats(
        self, *, channel_id: str, user_id: str, days: int = 7
    ) -> ChannelWorkflowStatsResponse:
        safe_days = max(1, min(days, 90))
        bindings = await self.list_channel_workflow_bindings(
            channel_id=channel_id, user_id=user_id
        )
        wf_ids = [b.workflow_id for b in bindings]
        if not wf_ids:
            return ChannelWorkflowStatsResponse(channel_id=channel_id, days=safe_days, items=[])

        cutoff = datetime.now(timezone.utc) - timedelta(days=safe_days)
        stmt = (
            select(
                SkillWorkflowRun.workflow_id,
                func.count(SkillWorkflowRun.id).label("total_runs"),
                func.sum(case((SkillWorkflowRun.status == "success", 1), else_=0)).label("success_runs"),
                func.sum(case((SkillWorkflowRun.status == "failed", 1), else_=0)).label("failed_runs"),
                func.max(SkillWorkflowRun.started_at).label("last_run_at"),
            )
            .where(
                SkillWorkflowRun.user_id == user_id,
                SkillWorkflowRun.trigger_type == "channel",
                SkillWorkflowRun.started_at >= cutoff,
                SkillWorkflowRun.workflow_id.in_(wf_ids),  # type: ignore[arg-type]
            )
            .group_by(SkillWorkflowRun.workflow_id)
        )
        result = await self.db.execute(stmt)
        stats_rows = result.all()
        wf_map = {b.workflow_id: b.workflow_name for b in bindings}
        items = [
            ChannelWorkflowStatsItem(
                workflow_id=row.workflow_id,
                workflow_name=wf_map.get(row.workflow_id, ""),
                total_runs=int(row.total_runs or 0),
                success_runs=int(row.success_runs or 0),
                failed_runs=int(row.failed_runs or 0),
                last_run_at=row.last_run_at,
            )
            for row in stats_rows
        ]
        items.sort(key=lambda x: x.total_runs, reverse=True)
        return ChannelWorkflowStatsResponse(channel_id=channel_id, days=safe_days, items=items)

    async def list_workflow_templates(self, *, user_id: str) -> list[ChannelWorkflowTemplateResponse]:
        key = f"channel_workflow_templates:{user_id}"
        row = (await self.db.execute(select(Setting).where(Setting.key == key))).scalar_one_or_none()
        data = []
        if row and row.value:
            try:
                data = json.loads(row.value)
            except Exception:
                data = []
        templates: list[ChannelWorkflowTemplateResponse] = []
        for item in data if isinstance(data, list) else []:
            try:
                templates.append(ChannelWorkflowTemplateResponse.model_validate(item))
            except Exception:
                continue
        return templates

    async def save_workflow_template(
        self, *, user_id: str, data: ChannelWorkflowTemplateCreate
    ) -> ChannelWorkflowTemplateResponse:
        templates = await self.list_workflow_templates(user_id=user_id)
        now = datetime.now(timezone.utc)
        item = ChannelWorkflowTemplateResponse(
            id=str(uuid.uuid4()),
            name=data.name.strip(),
            description=(data.description or "").strip() or None,
            dispatch_mode=data.dispatch_mode,
            bindings=data.bindings,
            usage_count=0,
            created_at=now,
            updated_at=now,
        )
        templates.append(item)
        key = f"channel_workflow_templates:{user_id}"
        row = (await self.db.execute(select(Setting).where(Setting.key == key))).scalar_one_or_none()
        serialized = json.dumps([t.model_dump(mode="json") for t in templates], ensure_ascii=False)
        if row is None:
            row = Setting(key=key, value=serialized, category="workflow_templates")
            self.db.add(row)
        else:
            row.value = serialized
            row.category = "workflow_templates"
        await self.db.flush()
        return item

    async def delete_workflow_template(self, *, user_id: str, template_id: str) -> bool:
        templates = await self.list_workflow_templates(user_id=user_id)
        next_templates = [t for t in templates if t.id != template_id]
        if len(next_templates) == len(templates):
            return False
        key = f"channel_workflow_templates:{user_id}"
        row = (await self.db.execute(select(Setting).where(Setting.key == key))).scalar_one_or_none()
        serialized = json.dumps([t.model_dump(mode="json") for t in next_templates], ensure_ascii=False)
        if row is None:
            row = Setting(key=key, value=serialized, category="workflow_templates")
            self.db.add(row)
        else:
            row.value = serialized
            row.category = "workflow_templates"
        await self.db.flush()
        return True

    async def apply_workflow_template_to_channel(
        self,
        *,
        channel_id: str,
        user_id: str,
        template_id: str,
    ) -> list[ChannelWorkflowBindingResponse]:
        templates = await self.list_workflow_templates(user_id=user_id)
        template = next((t for t in templates if t.id == template_id), None)
        if template is None:
            raise ValueError("template not found")
        rows = await self.import_channel_workflow_bundle(
            channel_id=channel_id,
            user_id=user_id,
            bundle=ChannelWorkflowBindingBundle(
                dispatch_mode=template.dispatch_mode,
                bindings=template.bindings,
            ),
        )
        # update usage counter in settings payload
        for t in templates:
            if t.id == template_id:
                t.usage_count += 1
                t.updated_at = datetime.now(timezone.utc)
        key = f"channel_workflow_templates:{user_id}"
        row = (await self.db.execute(select(Setting).where(Setting.key == key))).scalar_one_or_none()
        serialized = json.dumps([t.model_dump(mode="json") for t in templates], ensure_ascii=False)
        if row is None:
            row = Setting(key=key, value=serialized, category="workflow_templates")
            self.db.add(row)
        else:
            row.value = serialized
            row.category = "workflow_templates"
        await self.db.flush()
        return rows
