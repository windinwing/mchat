"""Sync platform skills into tenant workspace before execution."""

from __future__ import annotations

import shutil
from pathlib import Path

from loguru import logger

from app.core.skills_paths import resolve_skill_directory
from app.models.skill import Skill
from app.skill.ops_policy import is_server_ops_skill
from app.workspace.paths import ensure_execution_layout
from app.workspace.types import WorkspaceContext


def _skill_source_dir(skill: Skill) -> Path | None:
    if skill.path:
        skill_md = Path(skill.path).resolve()
        if skill_md.is_file() and skill_md.name.lower() == "skill.md":
            return skill_md.parent
        if skill_md.is_dir():
            return skill_md
    resolved = resolve_skill_directory(skill.name)
    return resolved


def sync_skill_directory_to_tenant(source_dir: Path, tenant_skills: Path) -> Path:
    """Copy a platform skill tree into tenant skills/ (overwrite)."""
    source_dir = source_dir.resolve()
    dest = (tenant_skills / source_dir.name).resolve()
    tenant_skills.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(source_dir, dest)
    return dest


def ensure_skill_in_tenant(
    skill: Skill,
    ctx: WorkspaceContext,
    *,
    force: bool = False,
) -> Path:
    """Return tenant-local skill directory, syncing from platform when needed."""
    if is_server_ops_skill(skill):
        source = _skill_source_dir(skill)
        if source is None:
            raise FileNotFoundError(f"server_ops skill not found on disk: {skill.name}")
        return source

    ensure_execution_layout(ctx.tenant_root)
    tenant_skills = ctx.skills_dir()
    tenant_skills.mkdir(parents=True, exist_ok=True)

    folder_name = Path(skill.path).parent.name if skill.path else skill.name
    tenant_dir = (tenant_skills / folder_name).resolve()

    if skill.path:
        host_dir = Path(skill.path).resolve()
        if host_dir.is_file():
            host_dir = host_dir.parent
        try:
            host_dir.relative_to(tenant_skills.resolve())
            if (tenant_dir / "SKILL.md").is_file() and not force:
                return tenant_dir
        except ValueError:
            pass

    if (tenant_dir / "SKILL.md").is_file() and not force:
        return tenant_dir

    source = _skill_source_dir(skill)
    if source is None:
        raise FileNotFoundError(f"Skill directory not found: {skill.name}")

    try:
        source.resolve().relative_to(tenant_skills.resolve())
        return source
    except ValueError:
        pass

    synced = sync_skill_directory_to_tenant(source, tenant_skills)
    logger.debug("Synced skill {} to tenant workspace {}", skill.name, synced)
    return synced
