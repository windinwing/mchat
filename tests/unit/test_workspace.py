"""Unit tests for tenant workspace (Plan A / Plan B)."""

from __future__ import annotations

import pytest

from app.core.config import settings
from app.models.customer import CustomerConfig
from app.workspace.paths import (
    resolve_studio_path,
    resolve_workspace_root,
    safe_workspace_segment,
    tenant_studio_dir,
)
from app.workspace.resolver import build_workspace_context, resolve_workspace_mode
from app.workspace.types import WorkspaceMode


@pytest.fixture
def workspace_root(tmp_path, monkeypatch):
    root = tmp_path / "tenants"
    monkeypatch.setattr(settings, "workspace_root_dir", str(root))
    monkeypatch.setattr(settings, "workspace_legacy_studio_dir", "")
    monkeypatch.setattr(settings, "workspace_container_enabled", False)
    monkeypatch.setattr(settings, "workspace_default_mode", "local")
    return root


def test_safe_workspace_segment_rejects_traversal():
    assert safe_workspace_segment("user-1") == "user-1"
    assert safe_workspace_segment("../etc") is None
    assert safe_workspace_segment("") is None


def test_tenant_studio_layout(workspace_root):
    path = tenant_studio_dir("user-a", "channel-1")
    assert path == workspace_root / "user-a" / "studio" / "channel-1"
    path.mkdir(parents=True)
    assert path.is_dir()


def test_resolve_workspace_mode_by_plan(monkeypatch):
    monkeypatch.setattr(settings, "workspace_container_enabled", True)
    assert resolve_workspace_mode(plan="free") == WorkspaceMode.LOCAL
    assert resolve_workspace_mode(plan="pro", subscription_active=True) == WorkspaceMode.CONTAINER


def test_build_workspace_context_free(workspace_root):
    customer = CustomerConfig(
        id="ch-1",
        name="Test",
        user_id="owner-1",
        plan="free",
        enabled=True,
    )
    ctx = build_workspace_context("owner-1", customer_config=customer, channel_id="ch-1")
    assert ctx.mode.value == "local"
    assert ctx.tenant_root == workspace_root / "owner-1"
    assert ctx.uploads_dir().is_dir()
    assert ctx.studio_dir("ch-1").is_dir()


def test_build_workspace_context_pro_container(workspace_root, monkeypatch):
    monkeypatch.setattr(settings, "workspace_container_enabled", True)
    customer = CustomerConfig(
        id="ch-pro",
        name="Pro",
        user_id="owner-2",
        plan="pro",
        enabled=True,
    )
    ctx = build_workspace_context("owner-2", customer_config=customer)
    assert ctx.mode.value == "container"
    assert ctx.container_name is not None


def test_legacy_studio_path(monkeypatch, tmp_path):
    legacy = tmp_path / "legacy-studio"
    monkeypatch.setattr(settings, "workspace_legacy_studio_dir", str(legacy))
    path = resolve_studio_path("user-x", "ch-y")
    assert path == legacy / "user-x" / "ch-y"
