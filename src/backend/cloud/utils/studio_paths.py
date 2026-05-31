"""Resolve Cloud Portal studio workspace paths."""

from __future__ import annotations

from pathlib import Path

from cloud.config import cloud_settings


def resolve_studio_workspace_root(raw: str | None = None) -> Path:
    """Return absolute studio workspace root."""
    value = (raw if raw is not None else cloud_settings.studio_workspace_dir or "").strip()
    if not value:
        value = "../../data/studio"
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
