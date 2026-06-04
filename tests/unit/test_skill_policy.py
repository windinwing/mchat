"""Tests for local vs container tenant skill policy."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.core.config import settings
from app.models.customer import CustomerConfig
from app.models.skill import Skill
from app.models.user import User
from app.workspace.skill_policy import (
    SKILL_ORIGIN_TENANT,
    is_tenant_authored_skill,
    skill_origin_for_disk_path,
    tenant_skill_execution_blocked,
)


@pytest.fixture
def workspace_root(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "workspace_root_dir", str(tmp_path / "tenants"))
    monkeypatch.setattr(settings, "workspace_container_enabled", True)
    return tmp_path


def test_skill_origin_platform_vs_tenant(workspace_root, tmp_path, monkeypatch):
    user_id = "user-a"
    tenant_skills = workspace_root / "tenants" / user_id / "skills"
    tenant_skills.mkdir(parents=True)
    platform_root = tmp_path / "global"
    platform_root.mkdir()
    monkeypatch.setattr(
        "app.workspace.skill_policy.resolve_skill_directory",
        lambda name: platform_root / name if name == "patent-search" else None,
    )

    platform_dir = platform_root / "patent-search"
    platform_dir.mkdir()
    (platform_dir / "SKILL.md").write_text("x", encoding="utf-8")
    tenant_copy = tenant_skills / "patent-search"
    tenant_copy.mkdir()
    (tenant_copy / "SKILL.md").write_text("x", encoding="utf-8")

    assert (
        skill_origin_for_disk_path(
            str(tenant_copy / "SKILL.md"),
            user_id=user_id,
            skill_name="patent-search",
        )
        != SKILL_ORIGIN_TENANT
    )

    custom = tenant_skills / "my-tool"
    custom.mkdir()
    (custom / "SKILL.md").write_text("x", encoding="utf-8")
    assert (
        skill_origin_for_disk_path(
            str(custom / "SKILL.md"),
            user_id=user_id,
            skill_name="my-tool",
        )
        == SKILL_ORIGIN_TENANT
    )


def test_tenant_skill_execution_blocked_on_local():
    skill = Skill(
        id="s1",
        user_id="u1",
        name="my-tool",
        skill_type="tool",
        path="/data/tenants/u1/skills/my-tool/SKILL.md",
        config={"origin": "tenant"},
        enabled=True,
    )
    assert tenant_skill_execution_blocked(skill, "u1", "local") is not None
    assert tenant_skill_execution_blocked(skill, "u1", "container") is None


def test_platform_skill_runs_on_local():
    skill = Skill(
        id="s2",
        user_id="u1",
        name="patent-search",
        skill_type="tool",
        path="/skills/patent-search/SKILL.md",
        config={"origin": "platform"},
        enabled=True,
    )
    assert tenant_skill_execution_blocked(skill, "u1", "local") is None


@pytest.mark.asyncio
async def test_user_container_entitled_pro_plan(db_session, monkeypatch):
    from app.workspace.skill_policy import user_container_entitled

    monkeypatch.setattr(settings, "workspace_container_enabled", True)
    user = User(
        id="u-pro",
        username="prouser",
        password_hash="x",
        role="agent",
    )
    db_session.add(user)
    await db_session.flush()
    db_session.add(
        CustomerConfig(
            id="ch-1",
            name="Pro",
            user_id=user.id,
            plan="pro",
            enabled=True,
        )
    )
    await db_session.flush()
    assert await user_container_entitled(db_session, user.id) is True


@pytest.mark.asyncio
async def test_user_container_entitled_denied(db_session, monkeypatch):
    from app.workspace.skill_policy import user_container_entitled

    monkeypatch.setattr(settings, "workspace_container_enabled", True)
    user = User(
        id="u-deny",
        username="denyuser",
        password_hash="x",
        role="agent",
        workspace_container_allowed=False,
    )
    db_session.add(user)
    await db_session.flush()
    assert await user_container_entitled(db_session, user.id) is False


@pytest.mark.asyncio
async def test_user_may_author_tenant_skills_admin_bypass(db_session, monkeypatch):
    from app.workspace.skill_policy import user_may_author_tenant_skills

    monkeypatch.setattr(settings, "workspace_container_enabled", False)
    admin = User(
        id="u-admin",
        username="admin",
        password_hash="x",
        role="admin",
    )
    db_session.add(admin)
    await db_session.flush()
    assert await user_may_author_tenant_skills(db_session, admin.id) is True


@pytest.mark.asyncio
async def test_user_container_entitled_ignores_expired_container_channel(db_session, monkeypatch):
    from app.workspace.skill_policy import user_container_entitled

    monkeypatch.setattr(settings, "workspace_container_enabled", True)
    user = User(id="u-ch-exp", username="chexp", password_hash="x", role="agent")
    db_session.add(user)
    await db_session.flush()
    db_session.add(
        CustomerConfig(
            id="ch-cont-exp",
            name="Expired Container",
            user_id=user.id,
            plan="pro",
            enabled=True,
            workspace_mode="container",
            subscription_ends_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
    )
    await db_session.flush()
    assert await user_container_entitled(db_session, user.id) is False


@pytest.mark.asyncio
async def test_user_may_author_tenant_skills_tenant_requires_container(db_session, monkeypatch):
    from app.workspace.skill_policy import user_may_author_tenant_skills

    monkeypatch.setattr(settings, "workspace_container_enabled", False)
    user = User(
        id="u-free",
        username="freeuser",
        password_hash="x",
        role="agent",
    )
    db_session.add(user)
    await db_session.flush()
    assert await user_may_author_tenant_skills(db_session, user.id) is False


@pytest.mark.asyncio
async def test_user_may_edit_skill_files_admin_platform_skill(db_session, monkeypatch):
    from app.workspace.skill_policy import user_may_edit_skill_files

    monkeypatch.setattr(settings, "workspace_container_enabled", False)
    admin = User(id="u-admin2", username="admin2", password_hash="x", role="admin")
    db_session.add(admin)
    await db_session.flush()
    platform_skill = Skill(
        id="s-platform",
        user_id=admin.id,
        name="wheelchair-advisor",
        skill_type="tool",
        path="/skills/wheelchair-advisor/SKILL.md",
        config={"origin": "platform"},
        enabled=True,
    )
    assert await user_may_edit_skill_files(db_session, admin.id, platform_skill) is True


@pytest.mark.asyncio
async def test_user_may_edit_skill_files_tenant_denied_platform(db_session, monkeypatch):
    from app.workspace.skill_policy import user_may_edit_skill_files

    monkeypatch.setattr(settings, "workspace_container_enabled", True)
    user = User(id="u-tenant", username="tenant1", password_hash="x", role="agent")
    db_session.add(user)
    await db_session.flush()
    db_session.add(
        CustomerConfig(
            id="ch-tenant",
            name="Pro",
            user_id=user.id,
            plan="pro",
            enabled=True,
        )
    )
    await db_session.flush()
    platform_skill = Skill(
        id="s-p2",
        user_id=user.id,
        name="wheelchair-advisor",
        skill_type="tool",
        path="/skills/wheelchair-advisor/SKILL.md",
        config={"origin": "platform"},
        enabled=True,
    )
    assert await user_may_edit_skill_files(db_session, user.id, platform_skill) is False

    tenant_skill = Skill(
        id="s-t1",
        user_id=user.id,
        name="my-custom",
        skill_type="tool",
        path="/data/tenants/u-tenant/skills/my-custom/SKILL.md",
        config={"origin": "tenant"},
        enabled=True,
    )
    assert await user_may_edit_skill_files(db_session, user.id, tenant_skill) is True
