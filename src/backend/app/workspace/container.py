"""Per-user execution sidecar (Phase 1 Plan B)."""

from __future__ import annotations

import asyncio
import shutil
import subprocess

from loguru import logger

from app.core.config import settings
from app.workspace.local import LocalWorkspaceProvider
from app.workspace.paths import ensure_execution_layout
from app.workspace.security import execution_volume_mounts, sidecar_run_args
from app.workspace.types import WorkspaceContext, WorkspaceMode


def docker_available() -> bool:
    if not settings.workspace_container_enabled:
        return False
    docker_bin = shutil.which("docker")
    if not docker_bin:
        return False
    try:
        proc = subprocess.run(
            [docker_bin, "info"],
            capture_output=True,
            timeout=5,
            check=False,
        )
        return proc.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


class ContainerWorkspaceProvider(LocalWorkspaceProvider):
    """One sidecar per platform user; only tenant skills/uploads/data are mounted."""

    async def ensure_ready(self) -> WorkspaceContext:
        ensure_execution_layout(self.ctx.tenant_root)
        if not docker_available():
            self.ctx.effective_mode = WorkspaceMode.LOCAL
            self.ctx.fallback_reason = "docker_unavailable"
            logger.warning(
                "Execution sidecar requested but Docker unavailable; "
                "falling back to local for user {}",
                self.ctx.user_id,
            )
            return self.ctx

        try:
            await asyncio.to_thread(self._ensure_container_sync)
            self.ctx.effective_mode = WorkspaceMode.CONTAINER
            self.ctx.fallback_reason = None
        except Exception as exc:
            self.ctx.effective_mode = WorkspaceMode.LOCAL
            self.ctx.fallback_reason = f"container_start_failed:{exc}"
            logger.warning(
                "Failed to start execution sidecar for user {}: {}",
                self.ctx.user_id,
                exc,
            )
        return self.ctx

    def execution_env(self) -> dict[str, str]:
        """Container paths when running inside sidecar; host paths when local fallback."""
        if self.ctx.effective_mode == WorkspaceMode.CONTAINER:
            root = "/workspace"
            uploads = f"{root}/uploads"
        else:
            uploads_path = self.ctx.uploads_dir()
            uploads_path.mkdir(parents=True, exist_ok=True)
            root = str(self.ctx.tenant_root)
            uploads = str(uploads_path)

        env = {
            "MCHAT_WORKSPACE_ROOT": root,
            "MCHAT_UPLOAD_DIR": uploads,
            "MCHAT_WORKSPACE_SKILLS_DIR": f"{root}/skills",
            "MCHAT_WORKSPACE_DATA_DIR": f"{root}/data",
            "MCHAT_WORKSPACE_MODE": self.ctx.effective_mode.value,
            "MCHAT_WORKSPACE_USER_ID": self.ctx.user_id,
        }
        if self.ctx.customer_id:
            env["MCHAT_WORKSPACE_CUSTOMER_ID"] = self.ctx.customer_id
        if self.ctx.channel_id:
            env["MCHAT_WORKSPACE_CHANNEL_ID"] = self.ctx.channel_id
        return env

    def _docker_cmd(self) -> list[str]:
        return [shutil.which("docker") or "docker"]

    def _ensure_container_sync(self) -> None:
        name = self.ctx.container_name
        if not name:
            raise RuntimeError("missing container name")

        inspect = subprocess.run(
            [*self._docker_cmd(), "inspect", "-f", "{{.State.Running}}", name],
            capture_output=True,
            text=True,
            check=False,
        )
        if inspect.returncode == 0 and inspect.stdout.strip() == "true":
            return

        if inspect.returncode == 0:
            subprocess.run(
                [*self._docker_cmd(), "rm", "-f", name],
                capture_output=True,
                check=False,
            )

        tenant = str(self.ctx.tenant_root)
        cmd = [
            *self._docker_cmd(),
            "run",
            "-d",
            "--name",
            name,
            *sidecar_run_args(user_id=self.ctx.user_id, container_name=name),
            *execution_volume_mounts(tenant),
            "-w",
            "/workspace",
            settings.workspace_container_image,
            "sleep",
            "infinity",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise RuntimeError(
                proc.stderr.strip() or proc.stdout.strip() or "docker run failed"
            )
