"""Per-user execution sidecar (Phase 1 Plan B)."""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from loguru import logger

from app.core.config import settings
from app.workspace.local import LocalWorkspaceProvider
from app.workspace.paths import ensure_execution_layout
from app.workspace.security import execution_volume_mounts, sidecar_run_args
from app.workspace.skill_runner import container_runner_path, deploy_runner_script
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
        deploy_runner_script(self.ctx.tenant_root)
        if not docker_available():
            self.ctx.effective_mode = WorkspaceMode.LOCAL
            self.ctx.fallback_reason = "docker_unavailable"
            logger.warning(
                "Execution sidecar requested but Docker unavailable; "
                "falling back to local for user {}",
                self.ctx.user_id,
            )
            return await super().ensure_ready()

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
            return await super().ensure_ready()
        return self.ctx

    def _container_script_path(self, script_path: Path) -> str:
        """Map host tenant script path to in-container path."""
        rel = script_path.resolve().relative_to(self.ctx.tenant_root.resolve())
        return f"/workspace/{rel.as_posix()}"

    async def run_python_skill(
        self,
        *,
        script_path: Path,
        args: dict[str, Any],
        extra_env: dict[str, str] | None = None,
    ) -> Any:
        if self.ctx.effective_mode != WorkspaceMode.CONTAINER:
            return await super().run_python_skill(
                script_path=script_path,
                args=args,
                extra_env=extra_env,
            )

        name = self.ctx.container_name
        if not name:
            return await super().run_python_skill(
                script_path=script_path,
                args=args,
                extra_env=extra_env,
            )

        try:
            container_script = self._container_script_path(script_path)
        except ValueError:
            return {
                "error": "Skill script must live under tenant workspace for container execution"
            }

        env = {**self.execution_env(), **(extra_env or {})}
        env["MCHAT_SKILL_ARGS"] = json.dumps(args, ensure_ascii=False)
        env_args: list[str] = []
        for key, value in env.items():
            env_args.extend(["-e", f"{key}={value}"])

        cmd = [
            *self._docker_cmd(),
            "exec",
            *env_args,
            name,
            settings.workspace_container_python,
            container_runner_path(),
            container_script,
        ]
        proc = await asyncio.to_thread(
            subprocess.run,
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )
        stdout = (proc.stdout or "").strip()
        stderr = (proc.stderr or "").strip()
        if proc.returncode != 0:
            detail = stderr or stdout
            return {
                "error": detail or f"container skill failed (exit {proc.returncode})"
            }
        if not stdout:
            return {"ok": True, "message": "技能在容器内执行完成（无返回内容）"}
        try:
            return json.loads(stdout)
        except json.JSONDecodeError:
            return stdout

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
