"""Tests for skill quota using best customer plan."""

from __future__ import annotations

import pytest

from app.core.config import settings
from app.models.customer import CustomerConfig
from app.workspace.disk_usage import check_soft_quota
from app.workspace.resolver import build_workspace_context


@pytest.fixture
def workspace_root(tmp_path, monkeypatch):
    root = tmp_path / "tenants"
    monkeypatch.setattr(settings, "workspace_root_dir", str(root))
    monkeypatch.setattr(settings, "workspace_container_enabled", False)
    return root


def test_build_workspace_context_uses_plan_override(workspace_root):
    ctx_free = build_workspace_context("owner-1")
    assert ctx_free.limits.max_disk_bytes == 256 * 1024 * 1024

    ctx_pro = build_workspace_context("owner-1", plan_override="pro")
    assert ctx_pro.limits.max_disk_bytes == 5 * 1024 * 1024 * 1024


def test_check_soft_quota_respects_plan_override(workspace_root, monkeypatch):
    user_dir = workspace_root / "owner-1" / "data"
    user_dir.mkdir(parents=True)
    # Above free (256MB) but below pro (5GB)
    big = 300 * 1024 * 1024
    (user_dir / "blob.bin").write_bytes(b"x" * big)

    ctx_free = build_workspace_context("owner-1")
    assert check_soft_quota(ctx_free, additional_bytes=0) is not None

    ctx_pro = build_workspace_context("owner-1", plan_override="pro")
    assert check_soft_quota(ctx_pro, additional_bytes=0) is None


def test_customer_config_plan_used_when_provided(workspace_root):
    customer = CustomerConfig(
        id="ch-1",
        name="Paid",
        user_id="owner-2",
        plan="enterprise",
        enabled=True,
    )
    ctx = build_workspace_context("owner-2", customer_config=customer)
    assert ctx.limits.max_disk_bytes is None
