"""Tests for portal channel plan ↔ workspace_mode validation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import settings
from app.models.customer import CustomerConfig
from app.workspace.channel_plan import (
    channel_container_entitled,
    channel_workspace_snapshot,
    validate_channel_workspace_mode,
)
from app.workspace.types import WorkspaceMode


@pytest.fixture(autouse=True)
def _container_enabled(monkeypatch):
    monkeypatch.setattr(settings, "workspace_container_enabled", True)
    monkeypatch.setattr(settings, "workspace_root_dir", "/tmp/test-tenants")


def _customer(**kwargs) -> CustomerConfig:
    defaults = dict(
        id="ch-1",
        name="Test",
        user_id="u-1",
        plan="free",
        enabled=True,
    )
    defaults.update(kwargs)
    return CustomerConfig(**defaults)


def test_free_plan_allows_explicit_container_override():
    customer = _customer(plan="free", workspace_mode="container")
    validate_channel_workspace_mode(customer, "container")
    assert channel_container_entitled(customer) is True


def test_pro_active_allows_container():
    customer = _customer(
        plan="pro",
        workspace_mode="container",
        subscription_ends_at=datetime.now(timezone.utc) + timedelta(days=30),
    )
    validate_channel_workspace_mode(customer, "container")
    assert channel_container_entitled(customer) is True


def test_pro_expired_blocks_auto_container():
    customer = _customer(
        plan="pro",
        subscription_ends_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    assert channel_container_entitled(customer) is False


def test_channel_workspace_snapshot_modes():
    customer = _customer(
        plan="pro",
        workspace_mode="container",
        subscription_ends_at=datetime.now(timezone.utc) + timedelta(days=10),
    )
    snap = channel_workspace_snapshot(customer)
    assert snap["workspace_requested_mode"] == WorkspaceMode.CONTAINER.value
    assert snap["container_entitled"] is True
