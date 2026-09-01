"""Resolve LLM API keys from config, environment, or fallbacks."""

from __future__ import annotations

from sqlalchemy import and_, case, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from loguru import logger

from app.core.config import settings
from app.models.ai_config import AIConfig
from app.models.channel_template import ChannelTemplate
from app.models.customer import CustomerConfig
from app.models.user import User

#: Providers that run locally and never require an API key.
#: Validation/skip-points treat an empty key as valid for these.
LOCAL_PROVIDERS: frozenset[str] = frozenset({"ollama", "lmstudio"})
_TRUSTED_ENDPOINT_MARKER = "_mchat_trusted_api_endpoint"


def platform_default_ai_config_predicate():
    """SQL predicate for an explicit platform-wide default configuration.

    ``is_default`` is user-scoped. Only a default owned by an administrator is
    a platform default that may be shared with other accounts.
    """
    admin_user_ids = select(User.id).where(User.role == "admin")
    return and_(
        AIConfig.is_default.is_(True),
        AIConfig.user_id.in_(admin_user_ids),
    )


async def is_platform_default_ai_config(
    db: AsyncSession, config: AIConfig
) -> bool:
    """Return whether ``config`` is an administrator-owned default."""
    if not config.is_default:
        return False
    result = await db.execute(
        select(AIConfig.id).where(
            AIConfig.id == config.id,
            platform_default_ai_config_predicate(),
        )
    )
    return result.scalar_one_or_none() is not None


async def get_accessible_ai_config(
    db: AsyncSession,
    config_id: str,
    user_id: str,
) -> AIConfig | None:
    """Resolve a config the user may consume: own or platform default."""
    result = await db.execute(
        select(AIConfig).where(
            AIConfig.id == config_id,
            or_(
                AIConfig.user_id == user_id,
                platform_default_ai_config_predicate(),
            ),
        )
    )
    return result.scalar_one_or_none()


async def get_platform_default_ai_config(
    db: AsyncSession,
    *,
    require_ready: bool = False,
) -> AIConfig | None:
    """Resolve the newest administrator-owned platform default.

    When ``require_ready`` is true, invalid remote-provider credentials are
    skipped while local providers remain eligible.
    """
    result = await db.execute(
        select(AIConfig)
        .where(platform_default_ai_config_predicate())
        .order_by(AIConfig.updated_at.desc())
    )
    for config in result.scalars():
        if not require_ready or is_ai_config_ready(config.provider, config.api_key):
            return config
    return None


def is_local_provider(provider: str | None) -> bool:
    return (provider or "").strip().lower() in LOCAL_PROVIDERS


def is_usable_api_key(key: str | None) -> bool:
    k = (key or "").strip()
    if len(k) < 8:
        return False
    if "*" in k:
        return False
    if k.lower() in ("not-needed", "your-api-key", "sk-xxx", "changeme"):
        return False
    return True


def is_ai_config_ready(provider: str | None, key: str | None) -> bool:
    """Whether a (provider, key) pair is ready for actual chat/business use.

    Local providers (Ollama, LM Studio) never require a key, so they're
    considered ready regardless of the key value. Other providers must pass
    the usual key-usable check after env/DB resolution.
    """
    if is_local_provider(provider):
        return True
    if is_usable_api_key(resolve_api_key(provider, key)):
        return True
    return is_usable_api_key(provider_env_api_key(provider or ""))


def provider_env_api_key(provider: str) -> str:
    p = (provider or "").lower()
    env_map = {
        "openai": settings.openai_api_key,
        "deepseek": settings.deepseek_api_key,
        "moonshot": settings.moonshot_api_key,
        "openai-compatible": settings.openai_api_key,
        "zhipu": settings.zhipu_api_key,
        "zhipu-coding": settings.zhipu_coding_api_key,
        "groq": settings.groq_api_key,
        "siliconflow": settings.siliconflow_api_key,
        "together": settings.together_api_key,
    }
    return (env_map.get(p) or "").strip()


def resolve_api_key(provider: str, configured: str | None) -> str:
    """Return only the explicitly configured key.

    Environment credentials are resolved exclusively by
    :func:`ensure_ai_config_api_key`, which also binds them to a trusted
    provider endpoint. Keeping this helper explicit-only prevents a missed
    ensure call from pairing a platform secret with a tenant-controlled base.
    """
    return (configured or "").strip()


def is_official_llm_endpoint(provider: str, api_base: str | None) -> bool:
    """Return whether a tenant endpoint stays on a known public provider.

    Administrators may intentionally connect the self-hosted server to local
    Ollama/LM Studio or another private gateway. Untrusted tenant accounts may
    only use a provider's built-in public endpoint, preventing AI config and
    connection-test APIs from becoming an SSRF proxy.
    """
    normalized_provider = (provider or "").strip().lower()
    if normalized_provider in LOCAL_PROVIDERS:
        return False

    from app.services.model_catalog import DEFAULT_BASE_URLS, _resolve_base_url

    official = DEFAULT_BASE_URLS.get(normalized_provider)
    if not official:
        return False
    if not (api_base or "").strip():
        return True
    requested = _resolve_base_url(normalized_provider, api_base)
    expected = _resolve_base_url(normalized_provider, official)
    return bool(
        requested
        and expected
        and requested.rstrip("/").lower() == expected.rstrip("/").lower()
    )


async def ensure_llm_endpoint_allowed(
    db: AsyncSession,
    *,
    user_id: str,
    provider: str,
    api_base: str | None,
    trusted_endpoint: bool = False,
) -> None:
    """Reject private/custom LLM routing for non-administrator owners."""
    if trusted_endpoint:
        return
    owner = await db.get(User, user_id)
    if owner is not None and owner.role == "admin":
        return
    if is_official_llm_endpoint(provider, api_base):
        return

    from fastapi import HTTPException, status

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Custom or local AI API endpoints are restricted to administrators",
    )


async def ensure_ai_config_endpoint_allowed(
    db: AsyncSession,
    config: AIConfig,
) -> None:
    """Apply endpoint policy to a stored or transient AI configuration."""
    await ensure_llm_endpoint_allowed(
        db,
        user_id=config.user_id,
        provider=config.provider,
        api_base=getattr(config, "api_base", None),
        trusted_endpoint=bool(
            getattr(config, _TRUSTED_ENDPOINT_MARKER, False)
        ),
    )


def _runtime_ai_config_copy(config: AIConfig) -> AIConfig:
    """Create a transient copy for one-request credential resolution.

    Fallback secrets must never be assigned to a tenant-owned ORM instance:
    an unrelated later flush could otherwise persist the platform credential.
    """
    values = {
        column.key: getattr(config, column.key)
        for column in AIConfig.__table__.columns
    }
    return AIConfig(**values)


def _apply_fallback_llm_config(
    target: AIConfig,
    source: AIConfig,
    api_key: str,
    *,
    trusted_endpoint: bool = False,
) -> None:
    """Copy credentials; align provider/model when fallback differs (portal template stubs)."""
    src_provider = (source.provider or "").lower()
    tgt_provider = (target.provider or "").lower()
    if src_provider != tgt_provider:
        logger.warning(
            f"AI config {target.id} ({target.provider}/{target.model}) "
            f"inherits provider+model from {source.id} ({source.provider}/{source.model})"
        )
        target.provider = source.provider
        target.model = source.model
    target.api_key = api_key
    # Credentials and their connection target are one trust unit. Always copy
    # the source base, including None (which selects the provider's official
    # default), so a user-controlled base cannot receive a fallback secret.
    target.api_base = source.api_base
    if trusted_endpoint:
        setattr(target, _TRUSTED_ENDPOINT_MARKER, True)


async def ensure_ai_config_api_key(
    db: AsyncSession, ai_config: AIConfig
) -> AIConfig:
    """Fill missing/invalid api_key from env or another config for the same provider."""
    explicit_key = resolve_api_key(ai_config.provider, ai_config.api_key)
    if is_usable_api_key(explicit_key):
        return ai_config

    env_key = provider_env_api_key(ai_config.provider)
    if is_usable_api_key(env_key):
        runtime_config = _runtime_ai_config_copy(ai_config)
        runtime_config.api_key = env_key
        # Environment credentials are platform secrets. Bind them to the
        # provider's official endpoint instead of a tenant-controlled URL.
        from app.services.model_catalog import DEFAULT_BASE_URLS

        runtime_config.api_base = DEFAULT_BASE_URLS.get(
            (ai_config.provider or "").strip().lower()
        )
        return runtime_config

    result = await db.execute(
        select(AIConfig)
        .where(
            AIConfig.provider == ai_config.provider,
            AIConfig.api_key != "",
            AIConfig.id != ai_config.id,
            or_(
                AIConfig.user_id == ai_config.user_id,
                platform_default_ai_config_predicate(),
            ),
        )
        .order_by(
            case((AIConfig.user_id == ai_config.user_id, 0), else_=1),
            AIConfig.is_default.desc(),
            AIConfig.updated_at.desc(),
        )
    )
    for fallback in result.scalars():
        fb_key = resolve_api_key(fallback.provider, fallback.api_key)
        if is_usable_api_key(fb_key):
            logger.warning(
                f"AI config {ai_config.id} has no valid API key; "
                f"using key from config {fallback.id} ({fallback.provider})"
            )
            runtime_config = _runtime_ai_config_copy(ai_config)
            _apply_fallback_llm_config(
                runtime_config,
                fallback,
                fb_key,
                trusted_endpoint=fallback.user_id != ai_config.user_id,
            )
            return runtime_config

    default_result = await db.execute(
        select(AIConfig)
        .where(
            platform_default_ai_config_predicate(),
            AIConfig.api_key != "",
            AIConfig.id != ai_config.id,
        )
        .order_by(AIConfig.updated_at.desc())
    )
    for default_cfg in default_result.scalars():
        fb_key = resolve_api_key(default_cfg.provider, default_cfg.api_key)
        if is_usable_api_key(fb_key):
            logger.warning(
                f"AI config {ai_config.id} has no valid API key; "
                f"using default config {default_cfg.id} ({default_cfg.provider})"
            )
            runtime_config = _runtime_ai_config_copy(ai_config)
            _apply_fallback_llm_config(
                runtime_config,
                default_cfg,
                fb_key,
                trusted_endpoint=True,
            )
            return runtime_config

    return ai_config


async def clear_legacy_rental_copied_api_keys(
    db: AsyncSession,
) -> list[str]:
    """Clear platform/template secrets copied into old tenant rental configs.

    Older channel provisioning duplicated the active platform key (or a key
    embedded in a template spec) into a tenant-owned ``AIConfig``. New rentals
    reference an administrator-owned config instead. To avoid deleting a
    tenant's independently supplied credential, only exact copies of a current
    administrator, environment, or template-spec key are removed.

    The provider credential still needs rotation after upgrading because an
    older API response may already have disclosed the copied plaintext value.
    """
    admin_result = await db.execute(
        select(AIConfig.provider, AIConfig.api_key)
        .join(User, User.id == AIConfig.user_id)
        .where(User.role == "admin", AIConfig.api_key != "")
    )
    platform_keys: dict[str, set[str]] = {}
    for provider, api_key in admin_result:
        key = (api_key or "").strip()
        if key:
            platform_keys.setdefault((provider or "").strip().lower(), set()).add(
                key
            )

    candidate_result = await db.execute(
        select(
            AIConfig,
            ChannelTemplate.default_ai_config_spec,
        )
        .join(CustomerConfig, CustomerConfig.ai_config_id == AIConfig.id)
        .join(ChannelTemplate, ChannelTemplate.id == CustomerConfig.template_id)
        .where(
            CustomerConfig.ai_override.is_(False),
            CustomerConfig.user_id == AIConfig.user_id,
            AIConfig.api_key != "",
        )
    )

    cleared_ids: list[str] = []
    seen: set[str] = set()
    for config, template_spec in candidate_result:
        if config.id in seen:
            continue
        seen.add(config.id)
        provider = (config.provider or "").strip().lower()
        trusted_keys = set(platform_keys.get(provider, set()))
        env_key = provider_env_api_key(provider)
        if env_key:
            trusted_keys.add(env_key)
        if isinstance(template_spec, dict):
            spec_key = str(template_spec.get("api_key") or "").strip()
            if spec_key:
                trusted_keys.add(spec_key)
        if (config.api_key or "").strip() not in trusted_keys:
            continue
        config.api_key = ""
        cleared_ids.append(config.id)

    if cleared_ids:
        await db.flush()
    return cleared_ids
