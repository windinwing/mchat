"""Detect first-run setup: AI provider and assistant readiness."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_config import AIConfig
from app.models.customer import CustomerConfig
from app.models.group import GroupMember
from app.models.user import User
from app.schemas.setup import SetupStatusResponse
from app.services.llm_credentials import (
    is_ai_config_ready,
    is_usable_api_key,
    platform_default_ai_config_predicate,
    provider_env_api_key,
)

_ENV_PROVIDERS = (
    "openai",
    "deepseek",
    "moonshot",
    "zhipu",
    "zhipu-coding",
    "groq",
    "siliconflow",
    "together",
)


def _env_configured_providers() -> list[str]:
    out: list[str] = []
    for provider in _ENV_PROVIDERS:
        if is_usable_api_key(provider_env_api_key(provider)):
            out.append(provider)
    return out


def _ai_configs_ready(configs: list[AIConfig]) -> bool:
    for cfg in configs:
        if is_ai_config_ready(cfg.provider, cfg.api_key):
            return True
    return False


async def get_setup_status(db: AsyncSession, user: User) -> SetupStatusResponse:
    """Return setup flags for the current user.

    Admins may use platform-wide AI configs, but chat-home assistant readiness
    should still reflect whether the current account has its own enabled channel.

    Portal ``user`` role accounts never self-configure platform AI; readiness is
    based on rented/subscribed channels only.
    """
    env_key_providers = _env_configured_providers()
    assistant_query = select(CustomerConfig).where(
        CustomerConfig.user_id == user.id,
        CustomerConfig.enabled == True,
    )
    asst_result = await db.execute(assistant_query.limit(1))
    has_assistant = asst_result.scalar_one_or_none() is not None
    group_result = await db.execute(
        select(GroupMember).where(GroupMember.user_id == user.id).limit(1)
    )
    has_group = group_result.scalar_one_or_none() is not None
    chat_ready = has_assistant or has_group

    if user.role == "user":
        return SetupStatusResponse(
            ai_ready=True,
            has_assistant=chat_ready,
            ai_config_count=0,
            env_key_providers=env_key_providers,
        )

    # Admins and agents may use administrator-owned platform defaults. A
    # regular user's personal default must not become system-wide.
    # A newly created admin/agent account therefore does not need to configure
    # its own provider before chatting.
    ai_query = select(AIConfig).where(
        (AIConfig.user_id == user.id) | platform_default_ai_config_predicate()
    )

    ai_result = await db.execute(ai_query)
    ai_configs = list(ai_result.scalars().all())

    return SetupStatusResponse(
        ai_ready=_ai_configs_ready(ai_configs),
        has_assistant=chat_ready,
        ai_config_count=len(ai_configs),
        env_key_providers=env_key_providers,
    )
