"""Knowledge read/write permission boundary tests."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, get_password_hash
from app.models.user import User


@pytest.mark.asyncio
async def test_agent_can_list_but_not_create_knowledge_bases(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    agent = User(
        username="knowledge_reader",
        password_hash=get_password_hash("testpass123"),
        role="agent",
    )
    db_session.add(agent)
    await db_session.flush()
    token = create_access_token(
        data={"sub": agent.id, "username": agent.username, "role": agent.role}
    )
    headers = {"Authorization": f"Bearer {token}"}

    list_response = await client.get("/api/knowledge/bases", headers=headers)
    create_response = await client.post(
        "/api/knowledge/bases",
        headers=headers,
        json={"name": "not-allowed"},
    )

    assert list_response.status_code == 200
    assert list_response.json() == []
    assert create_response.status_code == 403
