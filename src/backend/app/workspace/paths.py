"""Tenant workspace path helpers (shared by Core and Cloud)."""

from __future__ import annotations

from pathlib import Path

from app.core.config import settings


def resolve_workspace_root(raw: str | None = None) -> Path:
    """Return absolute tenant workspace root."""
    value = (raw if raw is not None else settings.workspace_root_dir or "").strip()
    if not value:
        value = "../../data/tenants"
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    else:
        path = path.resolve()
    return path


def safe_workspace_segment(value: str) -> str | None:
    """Return segment if safe for path components; else None."""
    segment = (value or "").strip()
    if not segment or segment in {".", ".."}:
        return None
    if "/" in segment or "\\" in segment or ".." in segment:
        return None
    return segment


def tenant_root(user_id: str, *, workspace_root: Path | None = None) -> Path:
    uid = safe_workspace_segment(user_id)
    if not uid:
        raise ValueError("Invalid workspace user id")
    root = workspace_root or resolve_workspace_root()
    return root / uid


def tenant_skills_dir(user_id: str, *, workspace_root: Path | None = None) -> Path:
    return tenant_root(user_id, workspace_root=workspace_root) / "skills"


def tenant_uploads_dir(user_id: str, *, workspace_root: Path | None = None) -> Path:
    return tenant_root(user_id, workspace_root=workspace_root) / "uploads"


def tenant_studio_dir(
    user_id: str,
    channel_id: str,
    *,
    workspace_root: Path | None = None,
) -> Path:
    uid = safe_workspace_segment(user_id)
    cid = safe_workspace_segment(channel_id)
    if not uid or not cid:
        raise ValueError("Invalid studio workspace identifiers")
    return tenant_root(uid, workspace_root=workspace_root) / "studio" / cid


def resolve_legacy_studio_root(raw: str | None = None) -> Path:
    """Legacy Cloud layout: {studio_root}/{user_id}/{channel_id}."""
    value = (raw or settings.workspace_legacy_studio_dir or "").strip()
    if not value:
        return resolve_workspace_root()
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    else:
        path = path.resolve()
    return path


def resolve_studio_path(user_id: str, channel_id: str) -> Path:
    """Studio memory path with optional legacy root override."""
    legacy = (settings.workspace_legacy_studio_dir or "").strip()
    if legacy:
        uid = safe_workspace_segment(user_id)
        cid = safe_workspace_segment(channel_id)
        if not uid or not cid:
            raise ValueError("Invalid studio workspace identifiers")
        return resolve_legacy_studio_root(legacy) / uid / cid
    return tenant_studio_dir(user_id, channel_id)


def ensure_execution_layout(tenant_root_path: Path) -> None:
    """Create Phase-1 execution dirs (sidecar-visible: skills, uploads, data)."""
    tenant_root_path.mkdir(parents=True, exist_ok=True)
    (tenant_root_path / "uploads").mkdir(parents=True, exist_ok=True)
    (tenant_root_path / "skills").mkdir(parents=True, exist_ok=True)
    (tenant_root_path / "data").mkdir(parents=True, exist_ok=True)


def ensure_studio_layout(tenant_root_path: Path, channel_id: str) -> None:
    """Studio memory lives on control plane; not mounted into execution sidecars."""
    cid = safe_workspace_segment(channel_id)
    if not cid:
        return
    (tenant_root_path / "studio" / cid).mkdir(parents=True, exist_ok=True)


def ensure_tenant_layout(
    tenant_root_path: Path,
    *,
    include_studio: bool = True,
    channel_id: str | None = None,
) -> None:
    """Create execution + optional studio dirs."""
    ensure_execution_layout(tenant_root_path)
    if include_studio and channel_id:
        ensure_studio_layout(tenant_root_path, channel_id)
