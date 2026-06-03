"""Agent service - business logic for AI config and customer config management."""

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_config import AIConfig
from app.models.customer import CustomerConfig
from app.schemas.agent import (
    AIConfigCreate,
    AIConfigUpdate,
    CustomerConfigCreate,
    CustomerConfigResponse,
    AIConfigResponse,
)


class AgentService:
    """Handles agent configuration business logic."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_ai_config(
        self, user_id: str, data: AIConfigCreate
    ) -> AIConfigResponse:
        """Create a new AI configuration."""
        # If setting as default, unset other defaults
        if data.is_default:
            await self._unset_default_ai_configs(user_id)

        config = AIConfig(
            user_id=user_id,
            name=data.name,
            provider=data.provider,
            model=data.model,
            api_key=data.api_key,
            api_base=data.api_base,
            system_prompt=data.system_prompt,
            temperature=data.temperature,
            max_tokens=data.max_tokens,
            is_default=data.is_default,
        )
        self.db.add(config)
        await self.db.flush()
        await self.db.refresh(config)
        return AIConfigResponse.model_validate(config)

    async def list_ai_configs(
        self, user_id: str
    ) -> list[AIConfigResponse]:
        """List all AI configs for a user."""
        result = await self.db.execute(
            select(AIConfig)
            .where(AIConfig.user_id == user_id)
            .order_by(AIConfig.created_at.desc())
        )
        configs = result.scalars().all()
        return [AIConfigResponse.model_validate(c) for c in configs]

    async def get_ai_config(
        self, config_id: str, user_id: str
    ) -> AIConfigResponse | None:
        """Get a specific AI config."""
        result = await self.db.execute(
            select(AIConfig).where(
                AIConfig.id == config_id, AIConfig.user_id == user_id
            )
        )
        config = result.scalar_one_or_none()
        if config is None:
            return None
        return AIConfigResponse.model_validate(config)

    async def update_ai_config(
        self, config_id: str, user_id: str, data: AIConfigUpdate
    ) -> AIConfigResponse | None:
        """Update an AI config."""
        result = await self.db.execute(
            select(AIConfig).where(
                AIConfig.id == config_id, AIConfig.user_id == user_id
            )
        )
        config = result.scalar_one_or_none()
        if config is None:
            return None

        update_data = data.model_dump(exclude_unset=True)

        # Keep existing key when the client omits or sends an empty api_key
        if "api_key" in update_data and not (update_data.get("api_key") or "").strip():
            update_data.pop("api_key")

        # If setting as default, unset other defaults
        if update_data.get("is_default"):
            await self._unset_default_ai_configs(user_id, exclude_id=config_id)

        for key, value in update_data.items():
            setattr(config, key, value)

        await self.db.flush()
        await self.db.refresh(config)
        return AIConfigResponse.model_validate(config)

    async def delete_ai_config(
        self, config_id: str, user_id: str
    ) -> bool:
        """Delete an AI config."""
        result = await self.db.execute(
            select(AIConfig).where(
                AIConfig.id == config_id, AIConfig.user_id == user_id
            )
        )
        config = result.scalar_one_or_none()
        if config is None:
            return False
        await self.db.delete(config)
        await self.db.flush()
        return True

    async def create_customer_config(
        self, user_id: str, data: CustomerConfigCreate
    ) -> CustomerConfigResponse:
        """Create a new customer config."""
        from app.services.skill_filter import filter_tenant_skill_ids

        skill_ids = await filter_tenant_skill_ids(
            self.db, user_id, data.skill_ids
        )
        config = CustomerConfig(
            name=data.name,
            short_code=(data.short_code.strip() if data.short_code else None),
            user_id=user_id,
            ai_config_id=data.ai_config_id,
            skill_ids=skill_ids,
            knowledge_base_ids=data.knowledge_base_ids,
            auto_reply_rules=[rule.model_dump() for rule in data.auto_reply_rules],
            channel_prompt=data.channel_prompt,
            welcome_message=data.welcome_message,
            offline_message=data.offline_message,
            theme=data.theme,
            domains=data.domains,
            position=data.position,
            enabled=data.enabled,
            widget_session_ttl_hours=data.widget_session_ttl_hours,
            workspace_mode=data.workspace_mode,
        )
        self.db.add(config)
        await self.db.flush()
        await self.db.refresh(config)
        return CustomerConfigResponse.model_validate(config)

    async def list_customer_configs(
        self, user_id: str
    ) -> list[CustomerConfigResponse]:
        """List all customer configs for a user."""
        result = await self.db.execute(
            select(CustomerConfig)
            .where(CustomerConfig.user_id == user_id)
            .order_by(CustomerConfig.created_at.desc())
        )
        configs = result.scalars().all()
        return [CustomerConfigResponse.model_validate(c) for c in configs]

    async def get_customer_config(
        self, config_id: str, user_id: str
    ) -> CustomerConfigResponse | None:
        """Get a specific customer config."""
        result = await self.db.execute(
            select(CustomerConfig).where(
                CustomerConfig.id == config_id,
                CustomerConfig.user_id == user_id,
            )
        )
        config = result.scalar_one_or_none()
        if config is None:
            return None
        return CustomerConfigResponse.model_validate(config)

    async def update_customer_config(
        self, config_id: str, user_id: str, data: CustomerConfigCreate
    ) -> CustomerConfigResponse | None:
        """Update a customer config."""
        result = await self.db.execute(
            select(CustomerConfig).where(
                CustomerConfig.id == config_id,
                CustomerConfig.user_id == user_id,
            )
        )
        config = result.scalar_one_or_none()
        if config is None:
            return None

        from app.services.skill_filter import filter_tenant_skill_ids

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            if key == "auto_reply_rules":
                value = [rule.model_dump() for rule in data.auto_reply_rules]
            if key == "skill_ids" and value is not None:
                value = await filter_tenant_skill_ids(self.db, user_id, value)
            setattr(config, key, value)

        await self.db.flush()
        await self.db.refresh(config)
        return CustomerConfigResponse.model_validate(config)

    async def _unset_default_ai_configs(
        self, user_id: str, exclude_id: str | None = None
    ) -> None:
        """Unset all default AI configs for a user, optionally excluding one."""
        query = select(AIConfig).where(
            AIConfig.user_id == user_id,
            AIConfig.is_default == True,
        )
        if exclude_id:
            query = query.where(AIConfig.id != exclude_id)

        result = await self.db.execute(query)
        configs = result.scalars().all()
        for config in configs:
            config.is_default = False
