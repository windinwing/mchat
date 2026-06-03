"""Tests for tenant disk usage and soft quota."""

import pytest

from app.core.config import settings
from app.workspace.disk_usage import check_soft_quota, tenant_execution_usage_bytes
from app.workspace.resolver import build_workspace_context


@pytest.fixture
def tenant_env(tmp_path, monkeypatch):
    root = tmp_path / "tenants"
    monkeypatch.setattr(settings, "workspace_root_dir", str(root))
    return root


def test_tenant_execution_usage_excludes_studio(tenant_env):
    ctx = build_workspace_context("user-1")
    (ctx.skills_dir() / "a.txt").write_text("abc", encoding="utf-8")
    (ctx.tenant_root / "studio" / "ch1" / "MEMORY.md").parent.mkdir(parents=True)
    (ctx.tenant_root / "studio" / "ch1" / "MEMORY.md").write_text("x" * 100, encoding="utf-8")

    usage = tenant_execution_usage_bytes(ctx.tenant_root)
    assert usage["skills"] == 3
    assert usage["total"] == 3


def test_soft_quota_blocks_when_over(tenant_env, monkeypatch):
    from app.workspace.limits import PLAN_LIMITS
    from app.workspace.types import WorkspaceLimits

    monkeypatch.setitem(
        PLAN_LIMITS,
        "free",
        WorkspaceLimits(shell_enabled=False, studio_enabled=True, max_disk_bytes=10),
    )
    ctx = build_workspace_context("user-1")
    (ctx.uploads_dir() / "big.bin").write_bytes(b"x" * 8)
    assert check_soft_quota(ctx, additional_bytes=1) is None
    assert check_soft_quota(ctx, additional_bytes=3) is not None
