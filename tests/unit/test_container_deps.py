"""Tests for container-side skill dependency installation."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.workspace.container_deps import ensure_skill_requirements_in_container


def test_ensure_skill_requirements_skips_without_file(tmp_path):
    calls: list[list[str]] = []

    def _run(cmd, **kwargs):
        calls.append(cmd)
        return MagicMock(returncode=0, stdout="", stderr="")

    import subprocess

    tenant = tmp_path / "tenant"
    skill = tenant / "skills" / "demo"
    skill.mkdir(parents=True)

    ensure_skill_requirements_in_container(
        container_name="mchat-ws-u1",
        tenant_root=tenant,
        skill_dir=skill,
        docker_cmd=["docker"],
        container_path_for=lambda p: f"/workspace/{p.relative_to(tenant)}",
    )
    assert calls == []


def test_ensure_skill_requirements_installs_once(tmp_path, monkeypatch):
    import subprocess

    tenant = tmp_path / "tenant"
    skill = tenant / "skills" / "demo"
    skill.mkdir(parents=True)
    (skill / "requirements.txt").write_text("httpx\n", encoding="utf-8")

    calls: list[list[str]] = []

    def _run(cmd, **kwargs):
        calls.append(cmd)
        return MagicMock(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", _run)

    kwargs = dict(
        container_name="mchat-ws-u1",
        tenant_root=tenant,
        skill_dir=skill,
        docker_cmd=["docker"],
        container_path_for=lambda p: f"/workspace/{p.relative_to(tenant).as_posix()}",
    )
    ensure_skill_requirements_in_container(**kwargs)
    ensure_skill_requirements_in_container(**kwargs)

    assert len(calls) == 1
    assert "pip" in calls[0]
    assert "/workspace/skills/demo/requirements.txt" in calls[0]

    marker = tenant / "data" / ".mchat" / "pip-installed"
    assert any(marker.glob("*.done"))


def test_ensure_skill_requirements_raises_on_pip_failure(tmp_path, monkeypatch):
    import subprocess

    tenant = tmp_path / "tenant"
    skill = tenant / "skills" / "demo"
    skill.mkdir(parents=True)
    (skill / "requirements.txt").write_text("badpkg\n", encoding="utf-8")

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: MagicMock(returncode=1, stdout="", stderr="pip failed"),
    )

    with pytest.raises(RuntimeError, match="pip failed"):
        ensure_skill_requirements_in_container(
            container_name="mchat-ws-u1",
            tenant_root=tenant,
            skill_dir=skill,
            docker_cmd=["docker"],
            container_path_for=lambda p: f"/workspace/{p.relative_to(tenant).as_posix()}",
        )
