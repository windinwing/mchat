"""Sync platform skills into tenant workspace before execution."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from loguru import logger

from app.core.skills_paths import resolve_skill_directory
from app.models.skill import Skill
from app.skill.ops_policy import is_server_ops_skill
from app.workspace.paths import ensure_execution_layout
from app.workspace.types import WorkspaceContext

_SKIP_FINGERPRINT_DIRS = frozenset({".git", "__pycache__", ".mchat"})


def _skill_source_dir(skill: Skill) -> Path | None:
    if skill.path:
        skill_md = Path(skill.path).resolve()
        if skill_md.is_file() and skill_md.name.lower() == "skill.md":
            return skill_md.parent
        if skill_md.is_dir():
            return skill_md
    resolved = resolve_skill_directory(skill.name)
    return resolved


def directory_content_fingerprint(root: Path) -> str:
    """Stable hash of skill tree contents for stale sync detection."""
    root = root.resolve()
    if not root.is_dir():
        return ""
    digest = hashlib.sha256()
    for path in sorted(
        p
        for p in root.rglob("*")
        if p.is_file() and not any(part in _SKIP_FINGERPRINT_DIRS for part in p.parts)
    ):
        rel = path.relative_to(root).as_posix()
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def tenant_skill_is_current(source: Path, tenant_dir: Path) -> bool:
    """True when tenant copy matches platform source."""
    if not (tenant_dir / "SKILL.md").is_file() or not source.is_dir():
        return False
    if tenant_missing_platform_files(source, tenant_dir):
        return False
    try:
        return directory_content_fingerprint(source) == directory_content_fingerprint(
            tenant_dir
        )
    except OSError:
        return False


def tenant_missing_platform_files(source: Path, tenant_dir: Path) -> bool:
    """True when tenant copy is missing files present on platform (stale partial sync)."""
    if not tenant_dir.is_dir():
        return True
    source = source.resolve()
    for path in source.rglob("*"):
        if not path.is_file():
            continue
        if any(part in _SKIP_FINGERPRINT_DIRS for part in path.parts):
            continue
        rel = path.relative_to(source)
        if not (tenant_dir / rel).is_file():
            return True
    return False


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

    source = _skill_source_dir(skill)
    if source is None:
        if (tenant_dir / "SKILL.md").is_file() and not force:
            return tenant_dir
        raise FileNotFoundError(f"Skill directory not found: {skill.name}")

    if (tenant_dir / "SKILL.md").is_file() and not force:
        if tenant_skill_is_current(source, tenant_dir):
            return tenant_dir

    try:
        source.resolve().relative_to(tenant_skills.resolve())
        return source
    except ValueError:
        pass

    synced = sync_skill_directory_to_tenant(source, tenant_skills)
    logger.debug("Synced skill {} to tenant workspace {}", skill.name, synced)
    return synced
