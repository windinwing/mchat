"""Tests for tenant skill sync and runner."""

from pathlib import Path

import pytest

from app.workspace.paths import tenant_skills_dir
from app.workspace.resolver import build_workspace_context
from app.workspace.skill_runner import deploy_runner_script, execute_skill_script
from app.workspace.skill_sync import (
    directory_content_fingerprint,
    ensure_skill_in_tenant,
    sync_skill_directory_to_tenant,
    tenant_missing_platform_files,
    tenant_skill_is_current,
)


@pytest.fixture
def tenant_env(tmp_path, monkeypatch):
    monkeypatch.setattr("app.core.config.settings.workspace_root_dir", str(tmp_path / "tenants"))
    monkeypatch.setattr("app.core.config.settings.workspace_container_enabled", False)
    return tmp_path


def test_sync_platform_skill_to_tenant(tenant_env, tmp_path):
    platform = tmp_path / "platform" / "demo-skill"
    platform.mkdir(parents=True)
    (platform / "SKILL.md").write_text("---\nname: demo-skill\n---\n", encoding="utf-8")
    (platform / "main.py").write_text(
        "def run(**kwargs):\n    return {'ok': True, 'q': kwargs.get('query')}\n",
        encoding="utf-8",
    )

    tenant_skills = tmp_path / "tenants" / "user-1" / "skills"
    dest = sync_skill_directory_to_tenant(platform, tenant_skills)
    assert dest.is_dir()
    assert (dest / "main.py").is_file()


def test_execute_skill_script_run(tmp_path):
    skill_dir = tmp_path / "demo"
    skill_dir.mkdir()
    (skill_dir / "main.py").write_text(
        "def run(query=None, **_):\n    return {'query': query}\n",
        encoding="utf-8",
    )
    out = execute_skill_script(skill_dir / "main.py", {"query": "hello"})
    assert out == {"query": "hello"}


def test_deploy_runner_script(tenant_env):
    ctx = build_workspace_context("user-1")
    path = deploy_runner_script(ctx.tenant_root)
    assert path.is_file()
    assert path.name == "run_skill.py"


def test_ensure_skill_in_tenant_from_platform(tenant_env, tmp_path, monkeypatch):
    platform_root = tmp_path / "global-skills"
    platform_root.mkdir()
    skill_dir = platform_root / "my-tool"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: my-tool\n---\n", encoding="utf-8")

    monkeypatch.setattr(
        "app.workspace.skill_sync.resolve_skill_directory",
        lambda name: skill_dir if name == "my-tool" else None,
    )

    class _Skill:
        name = "my-tool"
        path = str(skill_dir / "SKILL.md")
        config = {}
        skill_type = "tool"

    ctx = build_workspace_context("user-1")
    dest = ensure_skill_in_tenant(_Skill(), ctx)
    assert dest.resolve().is_relative_to(tenant_skills_dir("user-1"))


def test_ensure_skill_resyncs_when_platform_source_changes(tenant_env, tmp_path, monkeypatch):
    platform_root = tmp_path / "global-skills"
    platform_root.mkdir()
    skill_dir = platform_root / "my-tool"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: my-tool\nversion: 1\n---\n", encoding="utf-8")

    monkeypatch.setattr(
        "app.workspace.skill_sync.resolve_skill_directory",
        lambda name: skill_dir if name == "my-tool" else None,
    )

    class _Skill:
        name = "my-tool"
        path = str(skill_dir / "SKILL.md")
        config = {}
        skill_type = "tool"

    ctx = build_workspace_context("user-1")
    first = ensure_skill_in_tenant(_Skill(), ctx)
    assert "version: 1" in (first / "SKILL.md").read_text(encoding="utf-8")

    (skill_dir / "SKILL.md").write_text("---\nname: my-tool\nversion: 2\n---\n", encoding="utf-8")
    assert not tenant_skill_is_current(skill_dir, first)

    second = ensure_skill_in_tenant(_Skill(), ctx)
    assert second == first
    assert "version: 2" in (second / "SKILL.md").read_text(encoding="utf-8")


def test_directory_fingerprint_detects_content_change(tmp_path):
    root = tmp_path / "skill"
    root.mkdir()
    (root / "SKILL.md").write_text("v1", encoding="utf-8")
    fp1 = directory_content_fingerprint(root)
    (root / "SKILL.md").write_text("v2", encoding="utf-8")
    fp2 = directory_content_fingerprint(root)
    assert fp1 != fp2


def test_tenant_missing_platform_files_detects_stale_copy(tmp_path):
    source = tmp_path / "source"
    tenant = tmp_path / "tenant"
    source.mkdir()
    tenant.mkdir()
    (source / "SKILL.md").write_text("skill", encoding="utf-8")
    (source / "charts_fonts.py").write_text("# fonts", encoding="utf-8")
    (tenant / "SKILL.md").write_text("skill", encoding="utf-8")
    assert tenant_missing_platform_files(source, tenant)
    (tenant / "charts_fonts.py").write_text("# fonts", encoding="utf-8")
    assert not tenant_missing_platform_files(source, tenant)
