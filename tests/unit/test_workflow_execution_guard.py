"""Regression tests for workflow/schedule execution guards and workspace context."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.core.config import settings
from app.models.customer import CustomerConfig
from app.models.skill import Skill
from app.models.user import User
from app.services.skill_filter import tenant_facing_skill_error
from app.services.workflow_service import (
    _execute_skill_for_user,
    _tenant_facing_from_trigger,
)
from app.skill.ops_policy import SCOPE_SERVER_OPS
from app.workspace.automation_context import build_automation_workspace_context
from app.workspace.types import WorkspaceMode


def test_tenant_facing_from_trigger():
    assert _tenant_facing_from_trigger("channel") is True
    assert _tenant_facing_from_trigger("manual") is False
    assert _tenant_facing_from_trigger("cron") is False


@pytest.mark.asyncio
async def test_execute_skill_blocks_server_ops_on_channel(db_session, monkeypatch):
    skill = Skill(
        id="ops-1",
        user_id="u1",
        name="mchat-ops",
        skill_type="tool",
        path="/skills/mchat-ops/SKILL.md",
        config={"scope": SCOPE_SERVER_OPS},
        enabled=True,
    )
    execute_called = False

    async def _fake_execute(*_args, **_kwargs):
        nonlocal execute_called
        execute_called = True
        return {"ok": True}

    monkeypatch.setattr("app.services.workflow_service.execute_skill", _fake_execute)

    class _NullScope:
        async def __aenter__(self):
            return None

        async def __aexit__(self, *_args):
            return None

    monkeypatch.setattr(
        "app.services.workflow_service.workspace_execution_scope",
        lambda _ctx: _NullScope(),
    )

    result = await _execute_skill_for_user(
        db_session, "u1", skill, {}, tenant_facing=True
    )
    assert isinstance(result, dict)
    assert result.get("error")
    assert "server_ops" in str(result["error"])
    assert execute_called is False


@pytest.mark.asyncio
async def test_automation_workspace_uses_best_plan(db_session, monkeypatch):
    monkeypatch.setattr(settings, "workspace_container_enabled", True)
    monkeypatch.setattr(settings, "workspace_root_dir", "/tmp/test-tenants")
    user = User(id="u-plan", username="planuser", password_hash="x", role="agent")
    db_session.add(user)
    await db_session.flush()
    db_session.add_all(
        [
            CustomerConfig(
                id="ch-free",
                name="Free",
                user_id=user.id,
                plan="free",
                enabled=True,
            ),
            CustomerConfig(
                id="ch-pro",
                name="Pro",
                user_id=user.id,
                plan="pro",
                enabled=True,
                subscription_ends_at=datetime.now(timezone.utc) + timedelta(days=30),
            ),
        ]
    )
    await db_session.flush()

    ctx = await build_automation_workspace_context(db_session, user.id)
    assert ctx.mode == WorkspaceMode.CONTAINER


@pytest.mark.asyncio
async def test_best_plan_ignores_expired_pro_channel(db_session, monkeypatch):
    from app.workspace.skill_policy import best_plan_for_user, user_container_entitled

    monkeypatch.setattr(settings, "workspace_container_enabled", True)
    user = User(id="u-exp", username="expuser", password_hash="x", role="agent")
    db_session.add(user)
    await db_session.flush()
    db_session.add(
        CustomerConfig(
            id="ch-expired",
            name="Expired Pro",
            user_id=user.id,
            plan="pro",
            enabled=True,
            subscription_ends_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
    )
    await db_session.flush()

    assert await best_plan_for_user(db_session, user.id) == "free"
    assert await user_container_entitled(db_session, user.id) is False


@pytest.mark.asyncio
async def test_automation_workspace_channel_container_override(db_session, monkeypatch):
    monkeypatch.setattr(settings, "workspace_container_enabled", True)
    monkeypatch.setattr(settings, "workspace_root_dir", "/tmp/test-tenants")
    user = User(
        id="u-allow",
        username="allowuser",
        password_hash="x",
        role="agent",
    )
    db_session.add(user)
    await db_session.flush()
    db_session.add(
        CustomerConfig(
            id="ch-cont",
            name="Container",
            user_id=user.id,
            plan="pro",
            workspace_mode="container",
            enabled=True,
            subscription_ends_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
    )
    await db_session.flush()

    ctx = await build_automation_workspace_context(db_session, user.id)
    assert ctx.mode == WorkspaceMode.CONTAINER


@pytest.mark.asyncio
async def test_best_plan_ignores_disabled_channel(db_session):
    from app.workspace.skill_policy import best_plan_for_user

    user = User(id="u-dis", username="disuser", password_hash="x", role="agent")
    db_session.add(user)
    await db_session.flush()
    db_session.add(
        CustomerConfig(
            id="ch-disabled",
            name="Disabled Pro",
            user_id=user.id,
            plan="pro",
            enabled=False,
            subscription_ends_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
    )
    await db_session.flush()
    assert await best_plan_for_user(db_session, user.id) == "free"


@pytest.mark.asyncio
async def test_workflow_get_skill_rejects_disabled(db_session):
    from app.services.workflow_service import WorkflowService

    user = User(id="u-wf", username="wfuser", password_hash="x", role="agent")
    db_session.add(user)
    await db_session.flush()
    skill = Skill(
        id="sk-off",
        user_id=user.id,
        name="off-skill",
        skill_type="tool",
        path="/tmp/off/SKILL.md",
        enabled=False,
    )
    db_session.add(skill)
    await db_session.flush()

    svc = WorkflowService(db_session)
    with pytest.raises(RuntimeError, match="disabled"):
        await svc._get_skill(skill_id=skill.id, user_id=user.id, require_enabled=True)


def test_tenant_facing_skill_error_blocks_notification_scope():
    notify = SimpleNamespace(
        id="n-1",
        name="mchat-notify",
        config={"scope": "notification"},
    )
    assert tenant_facing_skill_error(notify) is not None
