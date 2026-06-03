"""Install skill Python deps inside execution sidecar."""

from __future__ import annotations

import hashlib
import subprocess
from collections.abc import Callable
from pathlib import Path

from loguru import logger

from app.core.config import settings


def _requirements_path(skill_dir: Path) -> Path | None:
    for name in ("requirements.txt", "requirements-dev.txt"):
        candidate = skill_dir / name
        if candidate.is_file():
            return candidate
    return None


def _marker_path(tenant_root: Path, fingerprint: str) -> Path:
    return tenant_root / "data" / ".mchat" / "pip-installed" / f"{fingerprint}.done"


def ensure_skill_requirements_in_container(
    *,
    container_name: str,
    tenant_root: Path,
    skill_dir: Path,
    docker_cmd: list[str],
    container_path_for: Callable[[Path], str],
) -> None:
    """pip install -r requirements.txt inside sidecar (once per requirements hash)."""
    req = _requirements_path(skill_dir)
    if req is None:
        return
    fingerprint = hashlib.sha256(req.read_bytes()).hexdigest()[:24]
    marker = _marker_path(tenant_root, fingerprint)
    if marker.is_file():
        return

    container_req = container_path_for(req)
    proc = subprocess.run(
        [
            *docker_cmd,
            "exec",
            container_name,
            settings.workspace_container_python,
            "-m",
            "pip",
            "install",
            "-q",
            "--disable-pip-version-check",
            "-r",
            container_req,
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(
            detail or f"pip install failed in container (exit {proc.returncode})"
        )
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(container_req, encoding="utf-8")
    logger.info(
        "Installed skill requirements in sidecar {} from {}",
        container_name,
        req.name,
    )
