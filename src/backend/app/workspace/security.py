"""Docker sidecar security defaults (Phase 1 execution plane)."""

from __future__ import annotations

from app.core.config import settings

# Phase 1: control plane manages containers via host Docker CLI; sidecars must not
# receive docker.sock, privileged mode, or arbitrary host bind mounts.


def sidecar_run_args(*, user_id: str, container_name: str) -> list[str]:
    """Extra ``docker run`` flags for tenant execution sidecars."""
    args = [
        "--init",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--label",
        f"{settings.workspace_container_label}=true",
        "--label",
        f"{settings.workspace_container_label}.user_id={user_id}",
        "--label",
        f"{settings.workspace_container_label}.role=execution-sidecar",
    ]
    network = (settings.workspace_container_network or "").strip()
    if network:
        args.extend(["--network", network])
    pids_limit = settings.workspace_container_pids_limit
    if pids_limit and pids_limit > 0:
        args.extend(["--pids-limit", str(pids_limit)])
    memory = (settings.workspace_container_memory or "").strip()
    if memory:
        args.extend(["--memory", memory])
    cpus = (settings.workspace_container_cpus or "").strip()
    if cpus:
        args.extend(["--cpus", cpus])
    return args


def execution_volume_mounts(tenant_root: str) -> list[str]:
    """Mount only tenant execution dirs — never studio or host paths."""
    root = tenant_root.rstrip("/")
    mounts: list[str] = []
    for sub in ("skills", "uploads", "data"):
        mounts.extend(["-v", f"{root}/{sub}:/workspace/{sub}"])
    return mounts
