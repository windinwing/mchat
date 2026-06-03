"""Tests for local vs container tenant skill policy."""

from __future__ import annotations

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
