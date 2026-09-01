"""Test agent/AI config API."""

import pytest
from httpx import AsyncClient

from app.models.ai_config import AIConfig


@pytest.mark.asyncio
async def test_create_ai_config(client: AsyncClient, auth_headers: dict):
    """Create AI config should succeed."""
    response = await client.post(
        "/api/agents/ai-configs",
        json={
            "name": "Test Config",
            "provider": "openai",
            "model": "gpt-4o",
            "api_key": "sk-test-key",
        },
        headers=auth_headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test Config"
    assert data["provider"] == "openai"
    assert data["api_key"] == ""
    assert data["has_api_key"] is True
    assert "sk-test-key" not in response.text


@pytest.mark.asyncio
async def test_create_ai_config_empty_key(client: AsyncClient, auth_headers: dict):
    """Create AI config with empty API key should work."""
    response = await client.post(
        "/api/agents/ai-configs",
        json={
            "name": "No Key Config",
            "provider": "openai",
            "model": "gpt-4o",
        },
        headers=auth_headers,
    )
    assert response.status_code == 201
    assert response.json()["api_key"] == ""
    assert response.json()["has_api_key"] is False


@pytest.mark.asyncio
async def test_list_ai_configs(client: AsyncClient, auth_headers: dict):
    """List AI configs should return all."""
    # Create one
    await client.post(
        "/api/agents/ai-configs",
        json={
            "name": "List Test",
            "provider": "openai",
            "model": "gpt-4o",
            "api_key": "sk-test",
        },
        headers=auth_headers,
    )
    response = await client.get(
        "/api/agents/ai-configs",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_update_ai_config(client: AsyncClient, auth_headers: dict, db_session):
    """Update AI config should preserve or update API key."""
    # Create
    create_resp = await client.post(
        "/api/agents/ai-configs",
        json={
            "name": "Update Test",
            "provider": "openai",
            "model": "gpt-4o",
            "api_key": "sk-original",
        },
        headers=auth_headers,
    )
    config_id = create_resp.json()["id"]

    # Update (without changing key)
    response = await client.put(
        f"/api/agents/ai-configs/{config_id}",
        json={
            "name": "Updated Name",
            "provider": "openai",
            "model": "gpt-4o",
            "api_key": "sk-original",
        },
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Name"
    assert data["api_key"] == ""
    assert data["has_api_key"] is True
    assert "sk-original" not in response.text

    masked_update = await client.put(
        f"/api/agents/ai-configs/{config_id}",
        json={"api_key": "********", "name": "Still Updated"},
        headers=auth_headers,
    )
    assert masked_update.status_code == 200
    stored = await db_session.get(AIConfig, config_id)
    assert stored is not None
    assert stored.api_key == "sk-original"

    reroute_without_key = await client.put(
        f"/api/agents/ai-configs/{config_id}",
        json={"api_base": "https://gateway.example/v1"},
        headers=auth_headers,
    )
    assert reroute_without_key.status_code == 400
    assert "new API key" in reroute_without_key.json()["detail"]
    await db_session.refresh(stored)
    assert stored.api_base is None

    reroute_with_key = await client.put(
        f"/api/agents/ai-configs/{config_id}",
        json={
            "api_base": "https://gateway.example/v1",
            "api_key": "sk-new-routing-secret",
        },
        headers=auth_headers,
    )
    assert reroute_with_key.status_code == 200
    await db_session.refresh(stored)
    assert stored.api_base == "https://gateway.example/v1"
    assert stored.api_key == "sk-new-routing-secret"


@pytest.mark.asyncio
async def test_shared_platform_default_is_redacted_and_user_default_is_private(
    client: AsyncClient, auth_headers: dict
):
    """Only admin defaults are shared, and their key is never serialized."""
    platform = await client.post(
        "/api/agents/ai-configs",
        json={
            "name": "Platform Default",
            "provider": "openai",
            "model": "gpt-4o",
            "api_key": "sk-platform-secret",
            "is_default": True,
        },
        headers=auth_headers,
    )
    assert platform.status_code == 201

    first_registration = await client.post(
        "/api/auth/register",
        json={"username": "trial_agent_1", "password": "secret1"},
    )
    first_headers = {
        "Authorization": f"Bearer {first_registration.json()['access_token']}"
    }
    shared = await client.get("/api/agents/ai-configs", headers=first_headers)
    assert shared.status_code == 200
    platform_item = next(
        item for item in shared.json() if item["name"] == "Platform Default"
    )
    assert platform_item["shared"] is True
    assert platform_item["api_key"] == ""
    assert platform_item["has_api_key"] is True
    assert "sk-platform-secret" not in shared.text

    personal = await client.post(
        "/api/agents/ai-configs",
        json={
            "name": "Personal Default",
            "provider": "openai",
            "model": "gpt-4o-mini",
            "api_key": "sk-personal-secret",
            "is_default": True,
        },
        headers=first_headers,
    )
    assert personal.status_code == 201

    second_registration = await client.post(
        "/api/auth/register",
        json={"username": "trial_agent_2", "password": "secret2"},
    )
    second_headers = {
        "Authorization": f"Bearer {second_registration.json()['access_token']}"
    }
    second_list = await client.get(
        "/api/agents/ai-configs", headers=second_headers
    )
    names = {item["name"] for item in second_list.json()}
    assert "Platform Default" in names
    assert "Personal Default" not in names


@pytest.mark.asyncio
async def test_stored_shared_key_uses_server_side_connection_target(
    client: AsyncClient, auth_headers: dict, monkeypatch
):
    """A caller cannot route a stored platform key to an attacker URL."""
    platform = await client.post(
        "/api/agents/ai-configs",
        json={
            "name": "Trusted Provider",
            "provider": "openai",
            "model": "gpt-4o-mini",
            "api_key": "sk-platform-secret",
            "api_base": "https://api.openai.com/v1",
            "is_default": True,
        },
        headers=auth_headers,
    )
    config_id = platform.json()["id"]
    registration = await client.post(
        "/api/auth/register",
        json={"username": "routing_agent", "password": "secret3"},
    )
    agent_headers = {
        "Authorization": f"Bearer {registration.json()['access_token']}"
    }

    captured = {}

    async def fake_list_models(params):
        captured["provider"] = params.provider
        captured["api_key"] = params.api_key
        captured["api_base"] = params.api_base
        return ["gpt-4o-mini"]

    monkeypatch.setattr("app.api.agent.list_models", fake_list_models)
    response = await client.post(
        "/api/agents/ai-configs/models",
        json={
            "provider": "openai-compatible",
            "api_key": "",
            "api_base": "https://attacker.invalid/v1",
            "config_id": config_id,
        },
        headers=agent_headers,
    )
    assert response.status_code == 200
    assert captured == {
        "provider": "openai",
        "api_key": "sk-platform-secret",
        "api_base": "https://api.openai.com/v1",
    }

    async def fake_test_connection(params, *, model=None):
        captured["provider"] = params.provider
        captured["api_key"] = params.api_key
        captured["api_base"] = params.api_base
        captured["model"] = model
        return True, "ok"

    monkeypatch.setattr("app.api.agent.test_connection", fake_test_connection)
    test_response = await client.post(
        "/api/agents/ai-configs/test",
        json={
            "provider": "openai-compatible",
            "model": "attacker-model",
            "api_key": "",
            "api_base": "https://attacker.invalid/v1",
            "config_id": config_id,
        },
        headers=agent_headers,
    )
    assert test_response.status_code == 200
    assert captured == {
        "provider": "openai",
        "api_key": "sk-platform-secret",
        "api_base": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
    }


@pytest.mark.asyncio
async def test_delete_ai_config(client: AsyncClient, auth_headers: dict):
    """Delete AI config should succeed."""
    create_resp = await client.post(
        "/api/agents/ai-configs",
        json={
            "name": "Delete Test",
            "provider": "openai",
            "model": "gpt-4o",
            "api_key": "sk-test",
        },
        headers=auth_headers,
    )
    config_id = create_resp.json()["id"]

    response = await client.delete(
        f"/api/agents/ai-configs/{config_id}",
        headers=auth_headers,
    )
    assert response.status_code == 204
