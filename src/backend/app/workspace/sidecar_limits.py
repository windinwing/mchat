"""Per-user sidecar resource limits (sync read for docker run)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.workspace.sidecar_lifecycle import meta_path_for_user


def sidecar_limits_path(user_id: str) -> Path:
    return meta_path_for_user(user_id).parent / "sidecar.limits.json"


def read_user_sidecar_limits(user_id: str) -> dict[str, str]:
    path = sidecar_limits_path(user_id)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, str] = {}
    for key in ("memory", "cpus"):
        raw = data.get(key)
        if raw is not None and str(raw).strip():
            out[key] = str(raw).strip()
    return out


def write_user_sidecar_limits(
    user_id: str,
    *,
    memory: str | None = None,
    cpus: str | None = None,
    clear: bool = False,
) -> dict[str, str]:
    path = sidecar_limits_path(user_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    if clear or (memory is None and cpus is None):
        if path.is_file():
            path.unlink()
        return {}
    payload: dict[str, Any] = {}
    if memory is not None and str(memory).strip():
        payload["memory"] = str(memory).strip()
    if cpus is not None and str(cpus).strip():
        payload["cpus"] = str(cpus).strip()
    if not payload:
        if path.is_file():
            path.unlink()
        return {}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {k: str(v) for k, v in payload.items()}


def effective_sidecar_limits(user_id: str) -> dict[str, str]:
    from app.core.config import settings

    overrides = read_user_sidecar_limits(user_id)
    memory = overrides.get("memory") or (settings.workspace_container_memory or "").strip()
    cpus = overrides.get("cpus") or (settings.workspace_container_cpus or "").strip()
    out: dict[str, str] = {}
    if memory:
        out["memory"] = memory
    if cpus:
        out["cpus"] = cpus
    return out
