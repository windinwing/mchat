"""Sidecar idle tracking, image upgrade, and recycle."""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger

from app.core.config import settings
from app.workspace.paths import resolve_workspace_root, safe_workspace_segment, tenant_root


META_REL = Path("data") / ".mchat" / "sidecar.meta.json"


def _docker() -> list[str]:
    return [shutil.which("docker") or "docker"]


def meta_path_for_user(user_id: str) -> Path:
    return tenant_root(user_id) / META_REL


def read_sidecar_meta(user_id: str) -> dict[str, Any]:
    path = meta_path_for_user(user_id)
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def touch_sidecar_activity(user_id: str, *, image: str | None = None) -> None:
    """Record last execution / ensure_ready time for idle recycle."""
    path = meta_path_for_user(user_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "last_active_at": datetime.now(timezone.utc).isoformat(),
        "image": (image or settings.workspace_container_image or "").strip(),
        "user_id": user_id,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def idle_minutes_since(user_id: str, *, started_at: str | None = None) -> int | None:
    meta = read_sidecar_meta(user_id)
    last = _parse_iso(meta.get("last_active_at")) or _parse_iso(started_at)
    if last is None:
        return None
    delta = datetime.now(timezone.utc) - last
    return max(0, int(delta.total_seconds() // 60))


def normalize_image_ref(image: str | None) -> str:
    return (image or "").strip().split("@")[0].split(":")[0]


def image_matches_running(configured: str, running: str | None) -> bool:
    if not running:
        return False
    cfg = normalize_image_ref(configured)
    run = normalize_image_ref(running)
    return cfg == run or configured.strip() in running or running in configured


def inspect_container(container_name: str) -> dict[str, Any]:
    proc = subprocess.run(
        [*_docker(), "inspect", container_name, "--format", "{{json .}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return {}
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {}


def sidecar_needs_recreate(container_name: str) -> tuple[bool, str | None]:
    """True when configured image differs from running container."""
    data = inspect_container(container_name)
    if not data:
        return False, None
    running_image = (data.get("Config") or {}).get("Image") or ""
    configured = settings.workspace_container_image
    if image_matches_running(configured, running_image):
        return False, running_image
    return True, running_image


def remove_sidecar(container_name: str) -> bool:
    proc = subprocess.run(
        [*_docker(), "rm", "-f", container_name],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode == 0


def list_sidecars() -> list[dict[str, Any]]:
    """List MChat execution sidecars via Docker labels."""
    proc = subprocess.run(
        [
            *_docker(),
            "ps",
            "-a",
            "--filter",
            f"label={settings.workspace_container_label}=true",
            "--format",
            "{{json .}}",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return []

    items: list[dict[str, Any]] = []
    configured = settings.workspace_container_image
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        name = row.get("Names") or row.get("Name") or ""
        container_id = row.get("ID") or ""
        state = (row.get("State") or "").lower()
        image = row.get("Image") or ""
        user_id = ""
        inspect = inspect_container(name) if name else {}
        labels = (inspect.get("Config") or {}).get("Labels") or {}
        label_key = f"{settings.workspace_container_label}.user_id"
        user_id = labels.get(label_key, "")
        started_at = ((inspect.get("State") or {}).get("StartedAt")) if inspect else None
        idle = idle_minutes_since(user_id, started_at=started_at) if user_id else None
        items.append(
            {
                "container_name": name,
                "container_id": container_id,
                "user_id": user_id,
                "running": state == "running",
                "status": row.get("Status") or state,
                "image": image,
                "configured_image": configured,
                "image_matches": image_matches_running(configured, image),
                "started_at": started_at,
                "last_active_at": read_sidecar_meta(user_id).get("last_active_at")
                if user_id
                else None,
                "idle_minutes": idle,
            }
        )
    return items


def recycle_idle_sidecars(*, idle_minutes: int | None = None) -> int:
    """Stop and remove sidecars idle longer than threshold. Returns count removed."""
    threshold = idle_minutes
    if threshold is None:
        threshold = settings.workspace_sidecar_idle_minutes
    if threshold <= 0:
        return 0

    removed = 0
    for item in list_sidecars():
        if not item.get("running"):
            continue
        idle = item.get("idle_minutes")
        if idle is None or idle < threshold:
            continue
        name = item.get("container_name")
        if not name:
            continue
        if remove_sidecar(str(name)):
            removed += 1
            logger.info(
                "Recycled idle sidecar {} (user={}, idle_min={})",
                name,
                item.get("user_id"),
                idle,
            )
    return removed


def tenant_root_for_container(container_name: str) -> Path | None:
    data = inspect_container(container_name)
    if not data:
        return None
    labels = (data.get("Config") or {}).get("Labels") or {}
    user_id = labels.get(f"{settings.workspace_container_label}.user_id")
    if not user_id or not safe_workspace_segment(str(user_id)):
        return None
    return tenant_root(str(user_id), workspace_root=resolve_workspace_root())
