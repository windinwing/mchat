"""Portal service — user-facing channel rental business logic."""

from datetime import datetime, timezone, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_config import AIConfig
from app.schemas.agent import AIConfigCreate, AIConfigUpdate
from app.services.agent_service import AgentService
from app.services.maintenance_gate import ensure_public_api_available
from app.services.skill_filter import filter_skill_ids_global
from app.services.llm_credentials import is_usable_api_key, resolve_api_key
from app.models.channel_template import ChannelTemplate
from app.models.skill import Skill
from app.models.conversation import Conversation
from app.models.customer import CustomerConfig
from app.models.message import Message
from app.models.user import User
from cloud.schemas.portal import (
    ChannelIntegrationsResponse,
    ChannelTemplateResponse,
    EmbedCodeResponse,
    MyChannelResponse,
    MyChannelUpdate,
    PortalAiConfigCreate,
    PortalAiConfigOption,
    PortalAiConfigUpdate,
    PortalDashboardStats,
    RentChannelRequest,
    SkillIntegrationBlockSchema,
    SkillIntegrationFieldSchema,
)
from app.skill.integration import (
    integration_spec_from_config,
    merge_integration_schemas,
)
from app.services.field_encryption import (
    decrypt_skill_bindings,
    encrypt_skill_bindings,
)
from app.services.subscription_gate import (
    channel_subscription_active,
    subscription_end_from_period,
)


class PortalService:
    """Handles user-facing channel rental and management."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _to_channel_response(self, config: CustomerConfig) -> MyChannelResponse:
        data = MyChannelResponse.model_validate(config)
        data.subscription_active = channel_subscription_active(config)
        if config.skill_bindings:
            data.skill_bindings = decrypt_skill_bindings(config.skill_bindings)
        template_default_ai: str | None = None
        if config.template_id:
            t_result = await self.db.execute(
                select(ChannelTemplate.default_ai_config_id).where(
                    ChannelTemplate.id == config.template_id
                )
            )
            template_default_ai = t_result.scalar_one_or_none()
        data.template_default_ai_config_id = template_default_ai
        if config.ai_config_id:
            ai_result = await self.db.execute(
                select(AIConfig).where(AIConfig.id == config.ai_config_id)
            )
            ai = ai_result.scalar_one_or_none()
            if ai:
                data.ai_provider = ai.provider
                data.ai_model = ai.model
        return data

    # ── Templates ───────────────────────────────────────────────────

    async def list_published_templates(self) -> list[ChannelTemplateResponse]:
        result = await self.db.execute(
            select(ChannelTemplate)
            .where(ChannelTemplate.is_published == True)
            .order_by(ChannelTemplate.sort_order, ChannelTemplate.created_at.desc())
        )
        return [ChannelTemplateResponse.model_validate(t) for t in result.scalars().all()]

    async def get_template(self, template_id: str) -> ChannelTemplateResponse:
        result = await self.db.execute(
            select(ChannelTemplate).where(
                ChannelTemplate.id == template_id,
                ChannelTemplate.is_published == True,
            )
        )
        template = result.scalar_one_or_none()
        if template is None:
            raise HTTPException(status_code=404, detail="Template not found")
        return ChannelTemplateResponse.model_validate(template)

    # ── Channel rental ──────────────────────────────────────────────

    async def rent_channel(
        self,
        user: User,
        request: RentChannelRequest,
        *,
        paid_order: bool = False,
        billing_period: str = "monthly",
        active_order_id: str | None = None,
        subscription_ends_at: datetime | None = None,
        admin_grant: bool = False,
    ) -> MyChannelResponse:
        if not admin_grant:
            ensure_public_api_available()
        tpl_q = select(ChannelTemplate).where(ChannelTemplate.id == request.template_id)
        if not admin_grant:
            tpl_q = tpl_q.where(ChannelTemplate.is_published == True)
        result = await self.db.execute(tpl_q)
        template = result.scalar_one_or_none()
        if template is None:
            raise HTTPException(status_code=404, detail="Template not found")

        if not admin_grant:
            price = (
                template.price_yearly_cents
                if billing_period == "yearly" and template.price_yearly_cents > 0
                else template.price_monthly_cents
            )
            if price > 0 and not paid_order:
                raise HTTPException(
                    status_code=status.HTTP_402_PAYMENT_REQUIRED,
                    detail="Payment required for this template",
                )

        # Prevent duplicate channels from the same template
        dup_result = await self.db.execute(
            select(CustomerConfig).where(
                CustomerConfig.user_id == user.id,
                CustomerConfig.template_id == request.template_id,
            )
        )
        if dup_result.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=409,
                detail="You already have a channel from this template",
            )

        if admin_grant:
            trial_end = None
        else:
            trial_end = (
                datetime.now(timezone.utc) + timedelta(days=template.trial_days)
                if template.trial_days > 0
                else None
            )

        # Use template's referenced AI config, or create from spec
        ai_config_id = None
        if template.default_ai_config_id:
            # Verify the referenced config exists
            result = await self.db.execute(
                select(AIConfig).where(AIConfig.id == template.default_ai_config_id)
            )
            if result.scalar_one_or_none() is not None:
                ai_config_id = template.default_ai_config_id
        if ai_config_id is None:
            default_result = await self.db.execute(
                select(AIConfig).where(AIConfig.is_default == True)
            )
            platform_default = default_result.scalar_one_or_none()
            if platform_default is not None:
                key = resolve_api_key(
                    platform_default.provider, platform_default.api_key
                )
                if is_usable_api_key(key):
                    ai_config = AIConfig(
                        name=f"{template.name} AI",
                        user_id=user.id,
                        provider=platform_default.provider,
                        model=platform_default.model,
                        api_key=key,
                        api_base=platform_default.api_base,
                        system_prompt=(
                            platform_default.system_prompt
                            or (template.default_ai_config_spec or {}).get(
                                "system_prompt", ""
                            )
                        ),
                        temperature=platform_default.temperature,
                        max_tokens=platform_default.max_tokens,
                    )
                    self.db.add(ai_config)
                    await self.db.flush()
                    ai_config_id = ai_config.id

        if ai_config_id is None:
            ai_spec = template.default_ai_config_spec or {}
            if ai_spec:
                ai_config = AIConfig(
                    name=f"{template.name} AI",
                    user_id=user.id,
                    provider=ai_spec.get("provider", "openai"),
                    model=ai_spec.get("model", "gpt-4o-mini"),
                    api_key=ai_spec.get("api_key", ""),
                    system_prompt=ai_spec.get("system_prompt", ""),
                    temperature=ai_spec.get("temperature", 0.7),
                    max_tokens=ai_spec.get("max_tokens", 2048),
                )
                self.db.add(ai_config)
                await self.db.flush()
                ai_config_id = ai_config.id

        knowledge_base_ids: list[str] = []
        if template.default_knowledge_base_ids:
            knowledge_base_ids.extend(
                [str(k) for k in template.default_knowledge_base_ids if k]
            )
        if not knowledge_base_ids:
            kb_id = await self._create_kb_from_spec(
                user, template.default_knowledge_base_spec or {}
            )
            if kb_id:
                knowledge_base_ids.append(kb_id)

        if admin_grant:
            plan = "free"
            sub_end = None
        elif paid_order:
            plan = "pro"
            sub_end = subscription_ends_at or subscription_end_from_period(
                billing_period
            )
        else:
            plan = "free_trial" if template.trial_days > 0 else "free"
            sub_end = None

        config = CustomerConfig(
            name=request.name or template.name,
            user_id=user.id,
            template_id=template.id,
            ai_config_id=ai_config_id,
            channel_category=template.category,
            plan=plan,
            trial_ends_at=trial_end if not paid_order else None,
            subscription_ends_at=sub_end,
            active_order_id=active_order_id,
            welcome_message=template.default_welcome_message,
            offline_message=template.default_offline_message,
            theme=template.default_theme or {},
            skill_ids=await filter_skill_ids_global(
                self.db, template.default_skill_ids or []
            ),
            knowledge_base_ids=knowledge_base_ids or None,
            position="right",
            enabled=True,
            widget_session_ttl_hours=24,
        )
        self.db.add(config)
        await self.db.flush()
        await self.db.refresh(config)
        return await self._to_channel_response(config)

    # ── My channels ─────────────────────────────────────────────────

    async def list_my_channels(self, user: User) -> list[MyChannelResponse]:
        result = await self.db.execute(
            select(CustomerConfig)
            .where(CustomerConfig.user_id == user.id)
            .order_by(CustomerConfig.created_at.desc())
        )
        out: list[MyChannelResponse] = []
        for c in result.scalars().all():
            out.append(await self._to_channel_response(c))
        return out

    async def get_my_channel(self, user: User, channel_id: str) -> MyChannelResponse:
        result = await self.db.execute(
            select(CustomerConfig).where(
                CustomerConfig.id == channel_id,
                CustomerConfig.user_id == user.id,
            )
        )
        config = result.scalar_one_or_none()
        if config is None:
            raise HTTPException(status_code=404, detail="Channel not found")
        return await self._to_channel_response(config)

    async def list_user_ai_configs(self, user: User) -> list[PortalAiConfigOption]:
        result = await self.db.execute(
            select(AIConfig)
            .where(AIConfig.user_id == user.id)
            .order_by(AIConfig.is_default.desc(), AIConfig.name)
        )
        return [
            PortalAiConfigOption(
                id=c.id,
                name=c.name,
                provider=c.provider,
                model=c.model,
                is_default=bool(c.is_default),
                has_api_key=bool((c.api_key or "").strip()),
            )
            for c in result.scalars().all()
        ]

    async def create_user_ai_config(
        self, user: User, data: PortalAiConfigCreate
    ) -> PortalAiConfigOption:
        cfg = await AgentService(self.db).create_ai_config(
            user_id=user.id,
            data=AIConfigCreate(**data.model_dump()),
        )
        return PortalAiConfigOption(
            id=cfg.id,
            name=cfg.name,
            provider=cfg.provider,
            model=cfg.model,
            is_default=bool(cfg.is_default),
            has_api_key=bool((cfg.api_key or "").strip()),
        )

    async def update_user_ai_config(
        self, user: User, config_id: str, data: PortalAiConfigUpdate
    ) -> PortalAiConfigOption:
        payload = data.model_dump(exclude_unset=True)
        if "api_key" in payload and not (payload.get("api_key") or "").strip():
            payload.pop("api_key", None)
        cfg = await AgentService(self.db).update_ai_config(
            config_id=config_id,
            user_id=user.id,
            data=AIConfigUpdate(**payload),
        )
        return PortalAiConfigOption(
            id=cfg.id,
            name=cfg.name,
            provider=cfg.provider,
            model=cfg.model,
            is_default=bool(cfg.is_default),
            has_api_key=bool((cfg.api_key or "").strip()),
        )

    async def get_channel_integrations(
        self, user: User, channel_id: str
    ) -> ChannelIntegrationsResponse:
        result = await self.db.execute(
            select(CustomerConfig).where(
                CustomerConfig.id == channel_id,
                CustomerConfig.user_id == user.id,
            )
        )
        config = result.scalar_one_or_none()
        if config is None:
            raise HTTPException(status_code=404, detail="Channel not found")

        template_schema: list | None = None
        if config.template_id:
            t_result = await self.db.execute(
                select(ChannelTemplate).where(ChannelTemplate.id == config.template_id)
            )
            tmpl = t_result.scalar_one_or_none()
            if tmpl and tmpl.integration_schema:
                template_schema = tmpl.integration_schema

        skill_specs: list[dict] = []
        channel_skills: list[Skill] = []
        skill_ids = [str(s) for s in (config.skill_ids or []) if s]
        if skill_ids:
            s_result = await self.db.execute(
                select(Skill).where(Skill.id.in_(skill_ids), Skill.enabled == True)
            )
            channel_skills = list(s_result.scalars().all())
            for skill in channel_skills:
                spec = integration_spec_from_config(skill.name, skill.config)
                if spec:
                    skill_specs.append(spec)

        merged = merge_integration_schemas(template_schema, skill_specs)
        merged_names = {b.get("skill") for b in merged}
        for skill in channel_skills:
            if skill.name in merged_names:
                continue
            merged.append(
                {
                    "skill": skill.name,
                    "fields": [
                        {
                            "key": "api_token",
                            "label": "API Token / Key",
                            "secret": True,
                            "help": "技能所需接口密钥",
                        }
                    ],
                    "allow_channel_override": True,
                    "source": "channel",
                }
            )
            merged_names.add(skill.name)
        blocks = [
            SkillIntegrationBlockSchema(
                skill=b["skill"],
                fields=[SkillIntegrationFieldSchema(**f) for f in b.get("fields", [])],
                allow_channel_override=bool(b.get("allow_channel_override", True)),
                source=b.get("source"),
            )
            for b in merged
        ]
        return ChannelIntegrationsResponse(
            integrations=blocks,
            skill_bindings=decrypt_skill_bindings(config.skill_bindings),
        )

    async def update_my_channel(
        self, user: User, channel_id: str, data: MyChannelUpdate
    ) -> MyChannelResponse:
        result = await self.db.execute(
            select(CustomerConfig).where(
                CustomerConfig.id == channel_id,
                CustomerConfig.user_id == user.id,
            )
        )
        config = result.scalar_one_or_none()
        if config is None:
            raise HTTPException(status_code=404, detail="Channel not found")

        update_data = data.model_dump(exclude_unset=True)
        if "skill_bindings" in update_data and update_data["skill_bindings"] is not None:
            if not isinstance(update_data["skill_bindings"], dict):
                raise HTTPException(
                    status_code=400, detail="skill_bindings must be an object"
                )
            update_data["skill_bindings"] = encrypt_skill_bindings(
                update_data["skill_bindings"]
            )
        if "ai_config_id" in update_data and update_data["ai_config_id"]:
            ai_result = await self.db.execute(
                select(AIConfig).where(
                    AIConfig.id == update_data["ai_config_id"],
                    AIConfig.user_id == user.id,
                )
            )
            if ai_result.scalar_one_or_none() is None:
                raise HTTPException(status_code=400, detail="Invalid AI config")

        for key, value in update_data.items():
            setattr(config, key, value)
        await self.db.flush()
        await self.db.refresh(config)
        return await self._to_channel_response(config)

    async def delete_my_channel(self, user: User, channel_id: str) -> None:
        result = await self.db.execute(
            select(CustomerConfig).where(
                CustomerConfig.id == channel_id,
                CustomerConfig.user_id == user.id,
            )
        )
        config = result.scalar_one_or_none()
        if config is None:
            raise HTTPException(status_code=404, detail="Channel not found")
        await self.db.delete(config)
        await self.db.flush()

    async def get_embed_code(
        self, user: User, channel_id: str
    ) -> EmbedCodeResponse:
        channel = await self.get_my_channel(user, channel_id)
        position = "right"
        if channel.theme:
            position = channel.theme.get("position", "right")
        embed = (
            '<script\n'
            '  src="/widget-loader.js"\n'
            '  data-mchat-url="/api"\n'
            f'  data-agent-id="{channel.id}"\n'
            f'  data-position="{position}"\n'
            '></script>'
        )
        return EmbedCodeResponse(
            agent_id=channel.id,
            embed_script=embed,
            widget_url=f"/widget?agentId={channel.id}",
        )

    # ── Dashboard ───────────────────────────────────────────────────

    async def get_dashboard_stats(self, user: User) -> PortalDashboardStats:
        result = await self.db.execute(
            select(func.count(CustomerConfig.id)).where(CustomerConfig.user_id == user.id)
        )
        total_channels = result.scalar() or 0

        result = await self.db.execute(
            select(func.count(CustomerConfig.id)).where(
                CustomerConfig.user_id == user.id, CustomerConfig.enabled == True
            )
        )
        active_channels = result.scalar() or 0

        result = await self.db.execute(
            select(func.count(Conversation.id)).where(Conversation.user_id == user.id)
        )
        total_conversations = result.scalar() or 0

        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        result = await self.db.execute(
            select(func.count(Message.id)).where(
                Message.user_id == user.id, Message.created_at >= today_start
            )
        )
        messages_today = result.scalar() or 0

        # Aggregated usage across all user's channels
        result = await self.db.execute(
            select(
                func.coalesce(func.sum(CustomerConfig.usage_messages_month), 0),
                func.coalesce(func.sum(CustomerConfig.usage_tokens_month), 0),
            ).where(CustomerConfig.user_id == user.id)
        )
        row = result.one_or_none()
        total_msgs, total_tokens = row if row else (0, 0)

        return PortalDashboardStats(
            total_channels=total_channels,
            active_channels=active_channels,
            total_conversations=total_conversations,
            messages_today=messages_today,
            total_messages_month=int(total_msgs),
            total_tokens_month=int(total_tokens),
        )

    async def _get_owned_channel(
        self, user: User, channel_id: str
    ) -> CustomerConfig:
        result = await self.db.execute(
            select(CustomerConfig).where(
                CustomerConfig.id == channel_id,
                CustomerConfig.user_id == user.id,
            )
        )
        channel = result.scalar_one_or_none()
        if channel is None:
            raise HTTPException(status_code=404, detail="Channel not found")
        return channel

    async def _create_kb_from_spec(
        self, user: User, spec: dict
    ) -> str | None:
        """Create a knowledge base from template spec; returns kb id or None."""
        if not spec or not spec.get("name"):
            return None
        from app.schemas.knowledge import KnowledgeBaseCreate
        from app.services.knowledge_service import KnowledgeService

        field_names = set(KnowledgeBaseCreate.model_fields.keys())
        extra = {
            k: v
            for k, v in spec.items()
            if k in field_names and k not in ("name", "description", "enabled")
        }
        kb = await KnowledgeService(self.db).create_knowledge_base(
            user.id,
            KnowledgeBaseCreate(
                name=str(spec["name"]),
                description=spec.get("description"),
                enabled=bool(spec.get("enabled", True)),
                **extra,
            ),
        )
        return kb.id

    async def list_channel_knowledge_bases(
        self, user: User, channel_id: str
    ) -> list[dict]:
        from app.models.knowledge import Document, KnowledgeBase

        channel = await self._get_owned_channel(user, channel_id)
        kb_ids = list(channel.knowledge_base_ids or [])
        if not kb_ids:
            return []
        result = await self.db.execute(
            select(KnowledgeBase).where(KnowledgeBase.id.in_(kb_ids))
        )
        kb_by_id = {kb.id: kb for kb in result.scalars().all()}
        items = []
        for kb_id in kb_ids:
            kb = kb_by_id.get(kb_id)
            if kb is None:
                continue
            doc_count_result = await self.db.execute(
                select(func.count(Document.id)).where(
                    Document.knowledge_base_id == kb.id
                )
            )
            doc_count = doc_count_result.scalar() or 0
            is_owned = kb.user_id == user.id
            items.append(
                {
                    "id": kb.id,
                    "name": kb.name,
                    "description": kb.description,
                    "enabled": kb.enabled,
                    "document_count": int(doc_count),
                    "source": "owned" if is_owned else "system",
                    "can_upload": is_owned,
                    "can_delete": True,
                }
            )
        return items

    async def create_channel_knowledge_base(
        self, user: User, channel_id: str, data: dict
    ) -> dict:
        from app.schemas.knowledge import KnowledgeBaseCreate
        from app.services.knowledge_service import KnowledgeService

        channel = await self._get_owned_channel(user, channel_id)
        from app.core.config import settings as app_settings

        kb = await KnowledgeService(self.db).create_knowledge_base(
            user.id,
            KnowledgeBaseCreate(
                name=data.get("name") or f"{channel.name} 知识库",
                description=data.get("description"),
                enabled=data.get("enabled", True),
            ),
        )
        ids = list(channel.knowledge_base_ids or [])
        if kb.id not in ids:
            ids.append(kb.id)
        channel.knowledge_base_ids = ids
        await self.db.flush()
        return {"id": kb.id, "name": kb.name}

    async def import_channel_document(
        self,
        user: User,
        channel_id: str,
        kb_id: str,
        file,
    ):
        from app.models.knowledge import KnowledgeBase
        from app.services.knowledge_service import KnowledgeService

        channel = await self._get_owned_channel(user, channel_id)
        kb_ids = list(channel.knowledge_base_ids or [])
        if kb_id not in kb_ids:
            raise HTTPException(
                status_code=403,
                detail="Knowledge base not linked to this channel",
            )
        kb_result = await self.db.execute(
            select(KnowledgeBase).where(KnowledgeBase.id == kb_id)
        )
        kb = kb_result.scalar_one_or_none()
        if kb is None:
            raise HTTPException(status_code=404, detail="Knowledge base not found")
        if kb.user_id != user.id:
            raise HTTPException(
                status_code=403,
                detail="System knowledge bases are read-only",
            )
        return await KnowledgeService(self.db).import_file(
            kb_id=kb_id,
            user_id=user.id,
            file=file,
        )

    async def remove_channel_knowledge_base(
        self, user: User, channel_id: str, kb_id: str
    ) -> dict:
        """Unlink KB from channel; delete the KB only when owned by the user."""
        from app.models.knowledge import KnowledgeBase
        from app.services.knowledge_service import KnowledgeService

        channel = await self._get_owned_channel(user, channel_id)
        kb_ids = list(channel.knowledge_base_ids or [])
        if kb_id not in kb_ids:
            raise HTTPException(status_code=404, detail="Knowledge base not found")

        kb_result = await self.db.execute(
            select(KnowledgeBase).where(KnowledgeBase.id == kb_id)
        )
        kb = kb_result.scalar_one_or_none()
        if kb is None:
            kb_ids = [x for x in kb_ids if x != kb_id]
            channel.knowledge_base_ids = kb_ids or None
            await self.db.flush()
            return {"ok": True, "deleted": False}

        kb_ids = [x for x in kb_ids if x != kb_id]
        channel.knowledge_base_ids = kb_ids or None
        deleted = False
        if kb.user_id == user.id:
            deleted = await KnowledgeService(self.db).delete_knowledge_base(
                kb_id, user.id
            )
        await self.db.flush()
        return {"ok": True, "deleted": deleted, "source": "owned" if deleted else "system"}
