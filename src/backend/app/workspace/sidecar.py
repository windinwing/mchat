"""Inspect Docker sidecar state from control plane."""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any


def sidecar_inspect(container_name: str | None) -> dict[str, Any]:
    if not container_name:
        return {"exists": False, "running": False}
    docker = shutil.which("docker") or "docker"
    proc = subprocess.run(
        [docker, "inspect", container_name, "--format", "{{json .}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return {
            "exists": False,
            "running": False,
            "error": (proc.stderr or proc.stdout or "").strip() or "inspect failed",
        }
    try:
        data = json.loads(proc.stdout)
        state = data.get("State") or {}
        return {
            "exists": True,
            "running": bool(state.get("Running")),
            "status": state.get("Status"),
            "started_at": state.get("StartedAt"),
            "image": (data.get("Config") or {}).get("Image"),
        }
    except json.JSONDecodeError:
        return {"exists": True, "running": False, "error": "invalid inspect json"}
