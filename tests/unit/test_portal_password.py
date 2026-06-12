"""Portal password set / change behavior."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.models.user import User
from app.services.auth_service import AuthService


@pytest.mark.asyncio
async def test_first_password_set_without_current(db_session):
    user = User(
        id="u-phone",
        username="u13800138000",
        password_hash=AuthService._random_password_hash(),
        role="user",
        phone="13800138000",
    )
    db_session.add(user)
    await db_session.flush()

    auth = AuthService(db_session)
    await auth.change_password(user, None, "newpass123")
    await db_session.refresh(user)

    assert user.password_set_at is not None
    token = await auth.login("13800138000", "newpass123")
    assert token.user.has_password is True


@pytest.mark.asyncio
async def test_change_password_requires_current_when_set(db_session):
    auth = AuthService(db_session)
    user = User(
        id="u-agent",
        username="agent1",
        password_hash=AuthService._random_password_hash(),
        role="agent",
        password_set_at=None,
    )
    db_session.add(user)
    await db_session.flush()
    await auth.change_password(user, None, "firstpass1")
    await db_session.refresh(user)

    with pytest.raises(HTTPException) as exc:
        await auth.change_password(user, "wrong", "secondpass2")
    assert exc.value.status_code == 400

    await auth.change_password(user, "firstpass1", "secondpass2")
    token = await auth.login("agent1", "secondpass2")
    assert token.access_token


@pytest.mark.asyncio
async def test_external_user_cannot_set_password(db_session):
    user = User(
        id="u-9235",
        username="e9235",
        password_hash=AuthService._random_password_hash(),
        role="user",
        external_provider="patent9235",
        external_id="13900000000",
    )
    db_session.add(user)
    await db_session.flush()

    auth = AuthService(db_session)
    with pytest.raises(HTTPException) as exc:
        await auth.change_password(user, None, "newpass123")
    assert exc.value.status_code == 403
