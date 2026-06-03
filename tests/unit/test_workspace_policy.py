"""Tests for workspace container eligibility policy."""

from __future__ import annotations

import pytest

from app.core.config import settings
from app.workspace.policy import container_block_reason, plan_allows_container_auto
from app.workspace.resolver import resolve_workspace_mode
from app.workspace.types import WorkspaceMode


@pytest.fixture(autouse=True)
def _container_enabled(monkeypatch):
    monkeypatch.setattr(settings, "workspace_container_enabled", True)
    monkeypatch.setattr(settings, "workspace_default_mode", "local")


def test_plan_allows_container_auto():
    assert plan_allows_container_auto("free", subscription_active=True) is False
    assert plan_allows_container_auto("pro", subscription_active=True) is True
    assert plan_allows_container_auto("pro", subscription_active=False) is False


def test_user_denied_blocks_container():
    reason = container_block_reason(
        plan="pro",
        subscription_active=True,
        workspace_mode_override="container",
        user_container_allowed=False,
        requested_mode=WorkspaceMode.CONTAINER,
    )
    assert reason == "user_container_denied"
    assert (
        resolve_workspace_mode(
            plan="pro",
            workspace_mode_override="container",
            user_container_allowed=False,
        )
        == WorkspaceMode.LOCAL
    )


def test_user_allowed_enables_container_on_free_override():
    assert (
        resolve_workspace_mode(
            plan="free",
            workspace_mode_override="container",
            user_container_allowed=True,
        )
        == WorkspaceMode.CONTAINER
    )


def test_free_override_blocked_without_user_allow():
    reason = container_block_reason(
        plan="free",
        subscription_active=True,
        workspace_mode_override="container",
        user_container_allowed=None,
        requested_mode=WorkspaceMode.CONTAINER,
    )
    assert reason == "container_not_allowed_for_plan"
    assert (
        resolve_workspace_mode(
            plan="free",
            workspace_mode_override="container",
            user_container_allowed=None,
        )
        == WorkspaceMode.LOCAL
    )


def test_global_disabled_blocks_container(monkeypatch):
    monkeypatch.setattr(settings, "workspace_container_enabled", False)
    reason = container_block_reason(
        plan="pro",
        subscription_active=True,
        workspace_mode_override="container",
        user_container_allowed=True,
        requested_mode=WorkspaceMode.CONTAINER,
    )
    assert reason == "container_disabled_globally"
