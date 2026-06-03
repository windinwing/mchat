"""Tests for usage_storage_bytes sync."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.customer import CustomerConfig
from app.workspace.usage_service import compute_user_storage_bytes, refresh_customer_storage_usage


@pytest.fixture
def tenant_env(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "workspace_root_dir", str(tmp_path / "tenants"))
    return tmp_path


@pytest.mark.asyncio
async def test_refresh_customer_storage_usage(db_session: AsyncSession, tenant_env):
    user_id = "owner-1"
    cc = CustomerConfig(
        id="ch-1",
        name="Test Channel",
        user_id=user_id,
        plan="free",
        enabled=True,
    )
    db_session.add(cc)
    await db_session.flush()

    skills = tenant_env / "tenants" / user_id / "skills"
    skills.mkdir(parents=True)
    (skills / "demo.txt").write_text("hello", encoding="utf-8")

    total = await refresh_customer_storage_usage(db_session, user_id)
    assert total == compute_user_storage_bytes(user_id)
    await db_session.refresh(cc)
    assert cc.usage_storage_bytes == 5
