"""Tests for execution sidecar security flags."""

from app.workspace.security import execution_volume_mounts, sidecar_run_args


def test_sidecar_run_args_drop_caps_and_labels():
    args = sidecar_run_args(user_id="user-1", container_name="mchat-ws-abc")
    assert "--cap-drop=ALL" in args
    assert "--security-opt=no-new-privileges" in args
    assert any("mchat.workspace.user_id=user-1" in a for a in args)
    assert any("execution-sidecar" in a for a in args)


def test_execution_volume_mounts_only_tenant_subdirs():
    mounts = execution_volume_mounts("/data/tenants/u1")
    assert mounts.count("-v") == 3
    joined = " ".join(mounts)
    assert "/data/tenants/u1/skills:/workspace/skills" in joined
    assert "/data/tenants/u1/uploads:/workspace/uploads" in joined
    assert "/data/tenants/u1/data:/workspace/data" in joined
    assert "studio" not in joined
