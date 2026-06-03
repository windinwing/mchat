"""Resolve Cloud Portal studio workspace paths."""

from __future__ import annotations

from pathlib import Path

from app.core.config import settings
from app.workspace.paths import (
    resolve_legacy_studio_root,
    resolve_workspace_root,
    safe_workspace_segment,
)
from cloud.config import cloud_settings


def resolve_studio_workspace_root(raw: str | None = None) -> Path:
    """Return absolute studio workspace root (legacy or unified tenant layout)."""
    legacy = (settings.workspace_legacy_studio_dir or "").strip()
    if legacy:
        return resolve_legacy_studio_root(legacy)
    if raw is not None and raw.strip():
        value = raw.strip()
    elif (cloud_settings.studio_workspace_dir or "").strip():
        value = cloud_settings.studio_workspace_dir.strip()
    else:
        return resolve_workspace_root()
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    else:
        path = path.resolve()
    return path


__all__ = ["resolve_studio_workspace_root", "safe_workspace_segment"]
