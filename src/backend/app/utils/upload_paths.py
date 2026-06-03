"""Resolve upload directory consistently for storage and HTTP serving."""

from __future__ import annotations

import os
from pathlib import Path

from app.core.config import settings


def _backend_root() -> Path:
    """Directory containing the `app` package (src/backend locally, /app in Docker)."""
    return Path(__file__).resolve().parents[2]


def resolve_upload_root(raw: str | None = None) -> Path:
    """Return absolute upload root."""
    if raw is None:
        env_upload = os.environ.get("UPLOAD_DIR", "").strip()
        raw = env_upload or (settings.upload_dir or "").strip()
    if not raw:
        raw = "../../uploads"
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = (_backend_root() / path).resolve()
    else:
        path = path.resolve()
    return path


def safe_upload_file_path(key: str, *, root: Path | None = None) -> Path | None:
    """Map storage key to a path under upload root; None if traversal attempted."""
    root_dir = root or resolve_upload_root()
    key = (key or "").strip().lstrip("/")
    if not key or ".." in key.split("/"):
        return None
    full = (root_dir / key).resolve()
    try:
        full.relative_to(root_dir)
    except ValueError:
        return None
    return full
