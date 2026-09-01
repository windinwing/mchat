"""Agent service - business logic for AI config and customer config management."""

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_config import AIConfig
from app.models.conversation import Conversation
from app.models.customer import CustomerConfig
from app.models.group import Group
from app.models.user import User
from app.schemas.agent import (
    AIConfigCreate,
    AIConfigUpdate,
    CustomerConfigCreate,
    CustomerConfigResponse,
    AIConfigResponse,
)
from app.services.llm_credentials import (
    ensure_llm_endpoint_allowed,
    get_accessible_ai_config,
    is_platform_default_ai_config,
    platform_default_ai_config_predicate,
)


class AgentService:
    """Handles agent configuration business logic."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    @staticmethod
    def _ai_config_response(
        config: AIConfig, *, shared: bool = False
    ) -> AIConfigResponse:
        """Build a public response without copying the write-only API key."""
        response = AIConfigResponse.model_validate(config)
        return response.model_copy(
            update={
                "api_key": "",
                "has_api_key": bool((config.api_key or "").strip()),
                "shared": shared,
            }
        )

    async def get_ai_config_record(
        self, config_id: str, user_id: str
    ) -> AIConfig | None:
        """Get an owned or platform-default config for internal credential use."""
        return await get_accessible_ai_config(self.db, config_id, user_id)

    async def _owner_container_policy(self, user_id: str) -> bool | None:
        user = await self.db.get(User, user_id)
        return user.workspace_container_allowed if user else None

    async def _assert_workspace_mode_allowed(
        self,
        user_id: str,
        workspace_mode: str | None,
        *,
        plan: str = "free",
    ) -> None:
        if (workspace_mode or "").strip().lower() != "container":
            return
        from fastapi import HTTPException, status

        from app.workspace.policy import container_block_reason
        from app.workspace.types import WorkspaceMode

        block = container_block_reason(
            plan=plan,
            subscription_active=True,
            workspace_mode_override="container",
            user_container_allowed=await self._owner_container_policy(user_id),
            requested_mode=WorkspaceMode.CONTAINER,
        )
        if block:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=block,
            )

    def _customer_response(
        self,
        config: CustomerConfig,
        *,
        workspace_container_allowed: bool | None,
    ) -> CustomerConfigResponse:
        return CustomerConfigResponse.model_validate(config).model_copy(
            update={"workspace_container_allowed": workspace_container_allowed}
        )

    async def create_ai_config(
        self, user_id: str, data: AIConfigCreate
    ) -> AIConfigResponse:
        """Create a new AI configuration."""
        await ensure_llm_endpoint_allowed(
            self.db,
            user_id=user_id,
            provider=data.provider,
            api_base=data.api_base,
        )
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
        return self._ai_config_response(config)

    async def list_ai_configs(
        self, user_id: str
    ) -> list[AIConfigResponse]:
        """List a user's own AI configs plus shared system defaults.

        A default owned by an administrator is treated as a system-wide
        default and surfaced to every admin/agent as a shared, read-only entry.
        Other users' defaults remain private to their owners.
        """
        result = await self.db.execute(
            select(AIConfig)
            .where(AIConfig.user_id == user_id)
            .order_by(AIConfig.created_at.desc())
        )
        own_configs = result.scalars().all()
        own_ids = {c.id for c in own_configs}

        # Surface global system defaults not already owned by this user.
        shared_result = await self.db.execute(
            select(AIConfig)
            .where(
                platform_default_ai_config_predicate(),
                AIConfig.user_id != user_id,
            )
            .order_by(AIConfig.updated_at.desc())
        )
        shared_configs = [
            c for c in shared_result.scalars().all() if c.id not in own_ids
        ]

        responses: list[AIConfigResponse] = [
            self._ai_config_response(c) for c in own_configs
        ]
        for c in shared_configs:
            responses.append(self._ai_config_response(c, shared=True))
        return responses

    async def get_ai_config(
        self, config_id: str, user_id: str
    ) -> AIConfigResponse | None:
        """Get a specific AI config.

        Reads are allowed for the owner, or for an administrator-owned shared
        system default. The latter is returned with ``shared=True`` so the
        workbench can render it read-only.
        """
        config = await self.get_ai_config_record(config_id, user_id)
        if config is None:
            return None
        return self._ai_config_response(
            config,
            shared=config.user_id != user_id,
        )

    async def update_ai_config(
        self, config_id: str, user_id: str, data: AIConfigUpdate, is_admin: bool = False
    ) -> AIConfigResponse | None:
        """Update an AI config.

        Owners always update their own configs. Admins (``is_admin``) may
        additionally update a *shared system default* — an ``is_default``
        config owned by another account — so platform-wide defaults can be
        maintained without reassigning ownership.
        """
        result = await self.db.execute(
            select(AIConfig).where(AIConfig.id == config_id)
        )
        config = result.scalar_one_or_none()
        if config is None:
            return None
        is_shared_default = config.user_id != user_id and (
            await is_platform_default_ai_config(self.db, config)
        )
        if config.user_id != user_id and not (is_admin and is_shared_default):
            return None

        update_data = data.model_dump(exclude_unset=True)

        submitted_key = (update_data.get("api_key") or "").strip()
        has_fresh_key = bool(
            submitted_key and not set(submitted_key) <= {"*", "•"}
        )
        next_provider = update_data.get("provider", config.provider)
        next_api_base = update_data.get("api_base", config.api_base)
        routing_changed = (
            (next_provider or "").strip().lower()
            != (config.provider or "").strip().lower()
            or (next_api_base or "").strip().rstrip("/").lower()
            != (config.api_base or "").strip().rstrip("/").lower()
        )
        if routing_changed and not has_fresh_key:
            from fastapi import HTTPException, status

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "A new API key is required when changing the AI provider "
                    "or API base"
                ),
            )

        await ensure_llm_endpoint_allowed(
            self.db,
            user_id=config.user_id,
            provider=next_provider,
            api_base=next_api_base,
        )

        # Keep the existing key when a client omits it, leaves it blank, or
        # echoes a legacy masked placeholder.
        if "api_key" in update_data:
            if not submitted_key or set(submitted_key) <= {"*", "•"}:
                update_data.pop("api_key")

        # If setting as default, unset other defaults for this config's owner.
        # For a shared default edited by an admin, that owner is the config's
        # original ``user_id`` (not the acting admin) — keeps one default per
        # account intact.
        if update_data.get("is_default"):
            await self._unset_default_ai_configs(
                config.user_id, exclude_id=config_id
            )

        for key, value in update_data.items():
            setattr(config, key, value)

        await self.db.flush()
        await self.db.refresh(config)
        return self._ai_config_response(
            config,
            shared=config.user_id != user_id,
        )

    async def delete_ai_config(
        self, config_id: str, user_id: str, is_admin: bool = False
    ) -> bool:
        """Delete an AI config.

        As with updates, admins may delete a shared system default owned by
        another account; everyone else is scoped to their own configs.
        """
        result = await self.db.execute(
            select(AIConfig).where(AIConfig.id == config_id)
        )
        config = result.scalar_one_or_none()
        if config is None:
            return False
        is_shared_default = config.user_id != user_id and (
            await is_platform_default_ai_config(self.db, config)
        )
        if config.user_id != user_id and not (is_admin and is_shared_default):
            return False
        # Null out dangling foreign-key references so conversations, groups,
        # customer configs and channel templates don't point at a deleted row.
        await self.db.execute(
            update(Conversation).where(Conversation.ai_config_id == config_id)
            .values(ai_config_id=None)
        )
        await self.db.execute(
            update(CustomerConfig).where(CustomerConfig.ai_config_id == config_id)
            .values(ai_config_id=None)
        )
        await self.db.execute(
            update(Group).where(Group.ai_config_id == config_id)
            .values(ai_config_id=None)
        )
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
        if data.ai_config_id and await get_accessible_ai_config(
            self.db, data.ai_config_id, user_id
        ) is None:
            from fastapi import HTTPException, status

            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="AI config not found",
            )
        await self._assert_workspace_mode_allowed(user_id, data.workspace_mode)
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
        return self._customer_response(
            config,
            workspace_container_allowed=await self._owner_container_policy(user_id),
        )

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
        policy = await self._owner_container_policy(user_id)
        return [
            self._customer_response(c, workspace_container_allowed=policy)
            for c in configs
        ]

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
        return self._customer_response(
            config,
            workspace_container_allowed=await self._owner_container_policy(user_id),
        )

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
        if update_data.get("ai_config_id") and await get_accessible_ai_config(
            self.db, update_data["ai_config_id"], user_id
        ) is None:
            from fastapi import HTTPException, status

            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="AI config not found",
            )
        next_mode = update_data.get("workspace_mode", config.workspace_mode)
        await self._assert_workspace_mode_allowed(
            user_id,
            next_mode,
            plan=config.plan or "free",
        )
        for key, value in update_data.items():
            if key == "auto_reply_rules":
                value = [rule.model_dump() for rule in data.auto_reply_rules]
            if key == "skill_ids" and value is not None:
                value = await filter_tenant_skill_ids(self.db, user_id, value)
            setattr(config, key, value)

        await self.db.flush()
        await self.db.refresh(config)
        return self._customer_response(
            config,
            workspace_container_allowed=await self._owner_container_policy(user_id),
        )

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
