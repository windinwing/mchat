"""Tenant and connection-target boundaries for LLM credential fallback."""

import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.models.ai_config import AIConfig
from app.models.channel_template import ChannelTemplate
from app.models.customer import CustomerConfig
from app.models.user import User
from app.services.llm_credentials import (
    clear_legacy_rental_copied_api_keys,
    ensure_ai_config_endpoint_allowed,
    ensure_ai_config_api_key,
    get_platform_default_ai_config,
)
from app.services.model_catalog import ConnectionParams, test_connection as probe_connection


@pytest.mark.asyncio
async def test_platform_default_must_be_owned_by_admin(db_session):
    admin = User(id="admin", username="admin", password_hash="x", role="admin")
    agent = User(id="agent", username="agent", password_hash="x", role="agent")
    db_session.add_all([admin, agent])
    db_session.add_all(
        [
            AIConfig(
                id="agent-default",
                user_id=agent.id,
                name="Personal",
                provider="openai",
                model="gpt-4o-mini",
                api_key="sk-personal-secret",
                is_default=True,
            ),
            AIConfig(
                id="admin-default",
                user_id=admin.id,
                name="Platform",
                provider="openai",
                model="gpt-4o",
                api_key="sk-platform-secret",
                is_default=True,
            ),
        ]
    )
    await db_session.commit()

    resolved = await get_platform_default_ai_config(db_session)

    assert resolved is not None
    assert resolved.id == "admin-default"


@pytest.mark.asyncio
async def test_fallback_ignores_other_tenant_and_copies_trusted_base(db_session):
    admin = User(id="admin", username="admin", password_hash="x", role="admin")
    attacker = User(
        id="attacker", username="attacker", password_hash="x", role="agent"
    )
    victim = User(id="victim", username="victim", password_hash="x", role="agent")
    db_session.add_all([admin, attacker, victim])
    platform = AIConfig(
        id="platform",
        user_id=admin.id,
        name="Platform",
        provider="openai",
        model="gpt-4o-mini",
        api_key="sk-platform-secret",
        api_base="https://api.openai.com/v1",
        is_default=True,
    )
    other_tenant = AIConfig(
        id="victim-config",
        user_id=victim.id,
        name="Victim",
        provider="openai",
        model="gpt-4o-mini",
        api_key="sk-victim-secret",
        api_base="https://victim-provider.invalid/v1",
        is_default=False,
    )
    target = AIConfig(
        id="attacker-config",
        user_id=attacker.id,
        name="Attacker",
        provider="openai",
        model="gpt-4o-mini",
        api_key="",
        api_base="https://attacker.invalid/v1",
        is_default=False,
    )
    db_session.add_all([platform, other_tenant, target])
    await db_session.commit()

    resolved = await ensure_ai_config_api_key(db_session, target)

    assert resolved.api_key == "sk-platform-secret"
    assert resolved.api_base == "https://api.openai.com/v1"
    await db_session.commit()
    await db_session.refresh(target)
    assert target.api_key == ""
    assert target.api_base == "https://attacker.invalid/v1"


@pytest.mark.asyncio
async def test_environment_fallback_cannot_use_tenant_api_base(
    db_session, monkeypatch
):
    user = User(id="agent", username="agent", password_hash="x", role="agent")
    target = AIConfig(
        id="agent-config",
        user_id=user.id,
        name="Agent",
        provider="openai",
        model="gpt-4o-mini",
        api_key="",
        api_base="https://attacker.invalid/v1",
    )
    db_session.add_all([user, target])
    await db_session.commit()
    monkeypatch.setattr(settings, "openai_api_key", "sk-environment-secret")

    resolved = await ensure_ai_config_api_key(db_session, target)

    assert resolved.api_key == "sk-environment-secret"
    assert resolved.api_base == "https://api.openai.com/v1"
    await db_session.commit()
    await db_session.refresh(target)
    assert target.api_key == ""
    assert target.api_base == "https://attacker.invalid/v1"


@pytest.mark.asyncio
async def test_connection_probe_does_not_implicitly_read_environment_key(
    monkeypatch,
):
    captured = {}
    monkeypatch.setattr(settings, "openai_api_key", "sk-environment-secret")

    class FakeProvider:
        async def stream_chat(self, _messages, **_kwargs):
            yield {"type": "done"}

    def fake_create_provider(config):
        captured["api_key"] = config.api_key
        captured["api_base"] = config.api_base
        return FakeProvider()

    monkeypatch.setattr("app.bot.provider.create_provider", fake_create_provider)

    ok, _ = await probe_connection(
        ConnectionParams(
            provider="openai",
            api_key="",
            api_base="https://attacker.invalid/v1",
        ),
        model="gpt-4o-mini",
    )

    assert ok is True
    assert captured == {
        "api_key": "",
        "api_base": "https://attacker.invalid/v1",
    }


@pytest.mark.asyncio
async def test_non_admin_ai_config_cannot_target_private_or_custom_endpoint(
    db_session,
):
    user = User(id="tenant", username="tenant", password_hash="x", role="agent")
    private = AIConfig(
        id="tenant-private",
        user_id=user.id,
        name="Private target",
        provider="openai-compatible",
        model="test",
        api_key="tenant-explicit-key",
        api_base="http://127.0.0.1:8080/v1",
    )
    db_session.add_all([user, private])
    await db_session.flush()

    with pytest.raises(HTTPException) as denied:
        await ensure_ai_config_endpoint_allowed(db_session, private)
    assert denied.value.status_code == 400


@pytest.mark.asyncio
async def test_admin_ai_config_may_target_self_hosted_endpoint(db_session):
    admin = User(id="admin-local", username="admin-local", password_hash="x", role="admin")
    local = AIConfig(
        id="admin-local-config",
        user_id=admin.id,
        name="Local Ollama",
        provider="ollama",
        model="qwen",
        api_key="",
        api_base="http://127.0.0.1:11434/v1",
    )
    db_session.add_all([admin, local])
    await db_session.flush()

    await ensure_ai_config_endpoint_allowed(db_session, local)


@pytest.mark.asyncio
async def test_non_admin_generic_provider_requires_trusted_endpoint(db_session):
    user = User(id="generic-user", username="generic", password_hash="x", role="agent")
    generic = AIConfig(
        id="generic-config",
        user_id=user.id,
        name="Generic",
        provider="openai-compatible",
        model="test",
        api_key="tenant-explicit-key",
        api_base=None,
    )
    db_session.add_all([user, generic])
    await db_session.flush()

    with pytest.raises(HTTPException) as denied:
        await ensure_ai_config_endpoint_allowed(db_session, generic)
    assert denied.value.status_code == 400


@pytest.mark.asyncio
async def test_legacy_rental_cleanup_only_removes_exact_copied_keys(db_session):
    admin = User(id="cleanup-admin", username="cleanup-admin", password_hash="x", role="admin")
    tenant = User(id="cleanup-tenant", username="cleanup-tenant", password_hash="x", role="agent")
    platform = AIConfig(
        id="cleanup-platform",
        user_id=admin.id,
        name="Platform",
        provider="openai",
        model="gpt-4o-mini",
        api_key="sk-platform-copied-secret",
        is_default=True,
    )
    copied = AIConfig(
        id="cleanup-copied",
        user_id=tenant.id,
        name="Copied",
        provider="openai",
        model="gpt-4o-mini",
        api_key="sk-platform-copied-secret",
    )
    template_copied = AIConfig(
        id="cleanup-template-copied",
        user_id=tenant.id,
        name="Template copied",
        provider="deepseek",
        model="deepseek-chat",
        api_key="sk-template-copied-secret",
    )
    independent = AIConfig(
        id="cleanup-independent",
        user_id=tenant.id,
        name="Independent",
        provider="openai",
        model="gpt-4o-mini",
        api_key="sk-tenant-independent-secret",
    )
    explicit_override = AIConfig(
        id="cleanup-override",
        user_id=tenant.id,
        name="Override",
        provider="openai",
        model="gpt-4o-mini",
        api_key="sk-platform-copied-secret",
    )
    template = ChannelTemplate(
        id="cleanup-template",
        name="Legacy",
        default_ai_config_spec={
            "provider": "deepseek",
            "api_key": "sk-template-copied-secret",
        },
    )
    db_session.add_all(
        [
            admin,
            tenant,
            platform,
            copied,
            template_copied,
            independent,
            explicit_override,
            template,
        ]
    )
    await db_session.flush()
    db_session.add_all(
        [
            CustomerConfig(
                id="cleanup-channel-copied",
                name="Copied channel",
                user_id=tenant.id,
                template_id=template.id,
                ai_config_id=copied.id,
                ai_override=False,
            ),
            CustomerConfig(
                id="cleanup-channel-template",
                name="Template channel",
                user_id=tenant.id,
                template_id=template.id,
                ai_config_id=template_copied.id,
                ai_override=False,
            ),
            CustomerConfig(
                id="cleanup-channel-independent",
                name="Independent channel",
                user_id=tenant.id,
                template_id=template.id,
                ai_config_id=independent.id,
                ai_override=False,
            ),
            CustomerConfig(
                id="cleanup-channel-override",
                name="Override channel",
                user_id=tenant.id,
                template_id=template.id,
                ai_config_id=explicit_override.id,
                ai_override=True,
            ),
        ]
    )
    await db_session.flush()

    cleared = await clear_legacy_rental_copied_api_keys(db_session)

    assert set(cleared) == {copied.id, template_copied.id}
    assert copied.api_key == ""
    assert template_copied.api_key == ""
    assert independent.api_key == "sk-tenant-independent-secret"
    assert explicit_override.api_key == "sk-platform-copied-secret"


def test_anthropic_provider_pins_default_base_url(monkeypatch):
    from app.bot.provider import AnthropicProvider

    captured = {}

    class FakeAnthropic:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("anthropic.AsyncAnthropic", FakeAnthropic)
    config = AIConfig(
        user_id="admin",
        name="Anthropic",
        provider="anthropic",
        model="claude-test",
        api_key="anthropic-explicit-key",
        api_base=None,
    )

    AnthropicProvider(config)

    assert captured["base_url"] == "https://api.anthropic.com"
