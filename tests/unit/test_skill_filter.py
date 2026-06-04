"""Tests for tenant/global skill id filtering."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.skill_filter import filter_skill_ids_global, tenant_facing_skill_error
from app.skill.ops_policy import SCOPE_SERVER_OPS


def _skill_row(skill_id: str, scope: str = "tenant") -> SimpleNamespace:
    return SimpleNamespace(
        id=skill_id,
        name="test",
        config={"scope": scope},
    )


@pytest.mark.asyncio
async def test_filter_skill_ids_global_strips_server_ops():
    ops = _skill_row("ops-1", SCOPE_SERVER_OPS)
    tenant = _skill_row("t-1", "tenant")
    db = MagicMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = [ops, tenant]
    db.execute = AsyncMock(return_value=result)

    out = await filter_skill_ids_global(db, ["ops-1", "t-1", "missing"])
    assert out == ["t-1"]


def test_tenant_facing_skill_error_blocks_server_ops():
    ops = _skill_row("ops-1", SCOPE_SERVER_OPS)
    tenant = _skill_row("t-1", "tenant")
    assert tenant_facing_skill_error(ops) is not None
    assert tenant_facing_skill_error(tenant) is None
